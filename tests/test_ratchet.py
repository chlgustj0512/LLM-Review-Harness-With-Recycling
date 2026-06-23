from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness.gates import GateLedger
from harness.logging import EventLog
from harness.ratchet import RatchetLedger
from review_fixtures import review_batch_payload


class RatchetLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.log_path = Path(self.temp_dir.name) / "events.jsonl"
        self.gates = GateLedger(self.log_path)
        self.ratchet = RatchetLedger(self.log_path)
        self.events = EventLog(self.log_path)
        self.tasks: set[str] = set()

    def register_candidate(
        self,
        candidate_id: str,
        task_id: str,
        *,
        goal: str = "테스트",
        constraints: list[str] | None = None,
    ) -> str:
        if task_id not in self.tasks:
            self.events.append(
                "task_created",
                {
                    "task_id": task_id,
                    "goal": goal,
                    "constraints": constraints or [],
                },
            )
            self.tasks.add(task_id)
        self.events.append(
            "candidate_generated",
            {
                "candidate_id": candidate_id,
                "task_id": task_id,
                "text": "후보",
            },
        )
        return self.events.append(
            "review_batch_completed",
            review_batch_payload(candidate_id),
        )["event_id"]

    def accepted_gate(
        self,
        candidate_id: str,
        task_id: str = "task-1",
        *,
        goal: str = "테스트",
        constraints: list[str] | None = None,
    ):
        review_event_id = self.register_candidate(
            candidate_id,
            task_id,
            goal=goal,
            constraints=constraints,
        )
        state = self.gates.start(
            task_id=task_id,
            candidate_id=candidate_id,
            source_review_event_id=review_event_id,
        )
        for decision in (
            "pass_to_next_gate",
            "pass_to_next_gate",
            "accepted_synthesis",
        ):
            state = self.gates.record_decision(
                flow_id=state.flow_id,
                decision=decision,
                actor_type="human",
                actor_id="user",
                reason="래칫 테스트 Gate 통과",
            )
        return state

    def start_session(self):
        return self.ratchet.start(
            purpose="프로토타입 선택",
            priority_line=["logic", "scope", "reuse"],
            actor_id="user",
        )

    def compare(
        self,
        session_id: str,
        aspect: str,
        result: str,
    ):
        return self.ratchet.record_comparison(
            session_id=session_id,
            aspect=aspect,
            result=result,
            actor_type="human",
            actor_id="user",
            reason=f"{aspect} 상대 비교",
        )

    def test_only_completed_gate_candidate_can_enter(self) -> None:
        session = self.start_session()
        review_event_id = self.register_candidate(
            "candidate-incomplete",
            "task-1",
        )
        incomplete = self.gates.start(
            task_id="task-1",
            candidate_id="candidate-incomplete",
            source_review_event_id=review_event_id,
        )
        with self.assertRaises(ValueError):
            self.ratchet.admit_candidate(
                session_id=session.session_id,
                gate_flow_id=incomplete.flow_id,
                actor_id="user",
            )

    def test_first_candidate_bootstraps_all_champions(self) -> None:
        session = self.start_session()
        gate = self.accepted_gate("candidate-1")
        state = self.ratchet.admit_candidate(
            session_id=session.session_id,
            gate_flow_id=gate.flow_id,
            actor_id="user",
        )
        self.assertEqual(state.overall_champion_candidate_id, "candidate-1")
        self.assertEqual(
            state.aspect_champions,
            {
                "logic": "candidate-1",
                "scope": "candidate-1",
                "reuse": "candidate-1",
            },
        )
        self.assertEqual(state.pending_candidate_id, "")

    def test_first_decisive_aspect_controls_overall(self) -> None:
        session = self.start_session()
        first = self.accepted_gate("candidate-1")
        self.ratchet.admit_candidate(
            session_id=session.session_id,
            gate_flow_id=first.flow_id,
            actor_id="user",
        )
        second = self.accepted_gate("candidate-2", "task-2")
        self.ratchet.admit_candidate(
            session_id=session.session_id,
            gate_flow_id=second.flow_id,
            actor_id="user",
        )
        self.compare(session.session_id, "logic", "regressed")
        self.compare(session.session_id, "scope", "improved")
        self.compare(session.session_id, "reuse", "improved")
        state = self.ratchet.finalize_candidate(
            session_id=session.session_id,
            actor_id="user",
        )

        self.assertEqual(state.overall_champion_candidate_id, "candidate-1")
        self.assertEqual(state.aspect_champions["logic"], "candidate-1")
        self.assertEqual(state.aspect_champions["scope"], "candidate-2")
        self.assertEqual(state.aspect_champions["reuse"], "candidate-2")

    def test_neutral_higher_aspect_allows_lower_improvement(self) -> None:
        session = self.start_session()
        first = self.accepted_gate("candidate-1")
        self.ratchet.admit_candidate(
            session_id=session.session_id,
            gate_flow_id=first.flow_id,
            actor_id="user",
        )
        second = self.accepted_gate("candidate-2", "task-2")
        self.ratchet.admit_candidate(
            session_id=session.session_id,
            gate_flow_id=second.flow_id,
            actor_id="user",
        )
        self.compare(session.session_id, "logic", "no_meaningful_change")
        self.compare(session.session_id, "scope", "improved")
        self.compare(session.session_id, "reuse", "regressed")
        state = self.ratchet.finalize_candidate(
            session_id=session.session_id,
            actor_id="user",
        )
        self.assertEqual(state.overall_champion_candidate_id, "candidate-2")
        self.assertEqual(state.aspect_champions["scope"], "candidate-2")
        self.assertEqual(state.aspect_champions["reuse"], "candidate-1")

    def test_all_aspects_must_be_compared_before_finalize(self) -> None:
        session = self.start_session()
        first = self.accepted_gate("candidate-1")
        self.ratchet.admit_candidate(
            session_id=session.session_id,
            gate_flow_id=first.flow_id,
            actor_id="user",
        )
        second = self.accepted_gate("candidate-2", "task-2")
        self.ratchet.admit_candidate(
            session_id=session.session_id,
            gate_flow_id=second.flow_id,
            actor_id="user",
        )
        self.compare(session.session_id, "logic", "improved")
        with self.assertRaises(ValueError):
            self.ratchet.finalize_candidate(
                session_id=session.session_id,
                actor_id="user",
            )

    def test_one_pending_candidate_at_a_time(self) -> None:
        session = self.start_session()
        first = self.accepted_gate("candidate-1")
        self.ratchet.admit_candidate(
            session_id=session.session_id,
            gate_flow_id=first.flow_id,
            actor_id="user",
        )
        second = self.accepted_gate("candidate-2", "task-2")
        self.ratchet.admit_candidate(
            session_id=session.session_id,
            gate_flow_id=second.flow_id,
            actor_id="user",
        )
        third = self.accepted_gate("candidate-3", "task-3")
        with self.assertRaises(ValueError):
            self.ratchet.admit_candidate(
                session_id=session.session_id,
                gate_flow_id=third.flow_id,
                actor_id="user",
            )

    def test_candidate_from_unrelated_task_scope_is_rejected(self) -> None:
        session = self.start_session()
        first = self.accepted_gate(
            "candidate-1",
            "task-1",
            goal="프로토타입을 선택한다",
        )
        state = self.ratchet.admit_candidate(
            session_id=session.session_id,
            gate_flow_id=first.flow_id,
            actor_id="user",
        )
        self.assertEqual(state.scope_goal, "프로토타입을 선택한다")

        unrelated = self.accepted_gate(
            "candidate-unrelated",
            "task-unrelated",
            goal="식당 메뉴를 추천한다",
        )
        with self.assertRaises(ValueError):
            self.ratchet.admit_candidate(
                session_id=session.session_id,
                gate_flow_id=unrelated.flow_id,
                actor_id="user",
            )

    def test_same_scope_with_different_task_id_is_accepted(self) -> None:
        session = self.start_session()
        first = self.accepted_gate(
            "candidate-1",
            "task-1",
            goal="프로토타입을 선택한다",
            constraints=["예산 내"],
        )
        self.ratchet.admit_candidate(
            session_id=session.session_id,
            gate_flow_id=first.flow_id,
            actor_id="user",
        )
        second = self.accepted_gate(
            "candidate-2",
            "task-2",
            goal="  프로토타입을   선택한다 ",
            constraints=["예산 내"],
        )
        state = self.ratchet.admit_candidate(
            session_id=session.session_id,
            gate_flow_id=second.flow_id,
            actor_id="user",
        )
        self.assertEqual(state.pending_candidate_id, "candidate-2")

    def test_constraint_scope_mismatch_is_rejected(self) -> None:
        session = self.start_session()
        first = self.accepted_gate(
            "candidate-1",
            "task-1",
            constraints=["예산 내"],
        )
        self.ratchet.admit_candidate(
            session_id=session.session_id,
            gate_flow_id=first.flow_id,
            actor_id="user",
        )
        second = self.accepted_gate(
            "candidate-2",
            "task-2",
            constraints=["예산 무제한"],
        )
        with self.assertRaises(ValueError):
            self.ratchet.admit_candidate(
                session_id=session.session_id,
                gate_flow_id=second.flow_id,
                actor_id="user",
            )

    def test_tampered_unrelated_admission_is_rejected_on_read(self) -> None:
        session = self.start_session()
        first = self.accepted_gate(
            "candidate-1",
            "task-1",
            goal="프로토타입을 선택한다",
        )
        self.ratchet.admit_candidate(
            session_id=session.session_id,
            gate_flow_id=first.flow_id,
            actor_id="user",
        )
        unrelated = self.accepted_gate(
            "candidate-tampered",
            "task-tampered",
            goal="식당 메뉴를 추천한다",
        )
        self.events.append(
            "ratchet_candidate_admitted",
            {
                "session_id": session.session_id,
                "candidate_id": "candidate-tampered",
                "gate_flow_id": unrelated.flow_id,
                "source_gate_event_id": unrelated.history[-1]["event_id"],
                "actor_id": "tampered",
                "bootstrap": False,
                "task_id": "task-tampered",
                "task_goal": "식당 메뉴를 추천한다",
                "task_constraints": [],
            },
        )
        with self.assertRaises(ValueError):
            self.ratchet.get(session.session_id)

    def test_forged_champion_update_is_rejected_on_read(self) -> None:
        session = self.start_session()
        first = self.accepted_gate("candidate-1")
        self.ratchet.admit_candidate(
            session_id=session.session_id,
            gate_flow_id=first.flow_id,
            actor_id="user",
        )
        self.events.append(
            "ratchet_champion_updated",
            {
                "session_id": session.session_id,
                "aspect": "logic",
                "previous_candidate_id": "candidate-1",
                "new_candidate_id": "candidate-forged",
                "reason": "원장 수동 변조",
            },
        )
        with self.assertRaises(ValueError):
            self.ratchet.get(session.session_id)


if __name__ == "__main__":
    unittest.main()
