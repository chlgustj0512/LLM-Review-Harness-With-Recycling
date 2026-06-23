from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness.gates import GateLedger
from harness.logging import EventLog
from harness.ratchet import RatchetLedger
from harness.termination import TerminationLedger
from review_fixtures import review_batch_payload


class TerminationLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.log_path = Path(self.temp_dir.name) / "events.jsonl"
        self.gates = GateLedger(self.log_path)
        self.events = EventLog(self.log_path)
        self.ratchet = RatchetLedger(self.log_path)
        self.termination = TerminationLedger(self.log_path)
        self.session = self.ratchet.start(
            purpose="종료 테스트",
            priority_line=["logic", "scope"],
            actor_id="user",
        )

    def accepted_gate(self, candidate_id: str):
        task_id = f"task-{candidate_id}"
        self.events.append(
            "task_created",
            {"task_id": task_id, "goal": "테스트", "constraints": []},
        )
        self.events.append(
            "candidate_generated",
            {
                "candidate_id": candidate_id,
                "task_id": task_id,
                "text": "후보",
            },
        )
        review_event_id = self.events.append(
            "review_batch_completed",
            review_batch_payload(candidate_id),
        )["event_id"]
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
                reason="Gate 통과",
            )
        return state

    def admit(self, candidate_id: str):
        gate = self.accepted_gate(candidate_id)
        return self.ratchet.admit_candidate(
            session_id=self.session.session_id,
            gate_flow_id=gate.flow_id,
            actor_id="user",
        )

    def compare_and_finalize(self, logic: str, scope: str):
        for aspect, result in (("logic", logic), ("scope", scope)):
            self.ratchet.record_comparison(
                session_id=self.session.session_id,
                aspect=aspect,
                result=result,
                actor_type="human",
                actor_id="user",
                reason="종료 비교",
            )
        return self.ratchet.finalize_candidate(
            session_id=self.session.session_id,
            actor_id="user",
        )

    def prepare_no_improvement(self):
        self.admit("candidate-1")
        self.admit("candidate-2")
        self.compare_and_finalize("no_meaningful_change", "regressed")

    def test_no_improved_aspect_is_termination_eligible(self) -> None:
        self.prepare_no_improvement()
        eligibility = self.termination.eligibility(self.session.session_id)
        self.assertTrue(eligibility["eligible"])
        self.assertEqual(eligibility["reason"], "no_aspect_improved")
        self.assertEqual(
            eligibility["comparisons"],
            {"logic": "no_meaningful_change", "scope": "regressed"},
        )

    def test_any_improved_aspect_blocks_termination(self) -> None:
        self.admit("candidate-1")
        self.admit("candidate-2")
        self.compare_and_finalize("regressed", "improved")
        eligibility = self.termination.eligibility(self.session.session_id)
        self.assertFalse(eligibility["eligible"])
        self.assertEqual(eligibility["reason"], "aspect_improved")
        with self.assertRaises(ValueError):
            self.termination.approve(
                session_id=self.session.session_id,
                actor_type="human",
                actor_id="user",
                reason="잘못된 종료",
            )

    def test_approval_creates_immutable_provisional_snapshot(self) -> None:
        self.prepare_no_improvement()
        before = self.ratchet.get(self.session.session_id)
        snapshot = self.termination.approve(
            session_id=self.session.session_id,
            actor_type="human",
            actor_id="user",
            reason="어느 측면도 개선되지 않음",
        )
        self.assertEqual(snapshot.status, "active")
        self.assertEqual(
            snapshot.overall_champion_candidate_id,
            before.overall_champion_candidate_id,
        )
        self.assertEqual(snapshot.aspect_champions, before.aspect_champions)
        self.assertTrue(snapshot.source_finalize_event_id)
        self.assertFalse(
            self.termination.eligibility(self.session.session_id)["eligible"]
        )
        with self.assertRaises(ValueError):
            self.termination.approve(
                session_id=self.session.session_id,
                actor_type="human",
                actor_id="user",
                reason="중복 종료",
            )

    def test_forged_snapshot_is_rejected_on_read(self) -> None:
        self.prepare_no_improvement()
        state = self.ratchet.get(self.session.session_id)
        finalize_event = next(
            event
            for event in reversed(state.history)
            if event["event_type"] == "ratchet_candidate_finalized"
            and event["payload"]["overall_result"] != "bootstrap_champion"
        )
        self.events.append(
            "ratchet_termination_approved",
            {
                "snapshot_id": "champion-snapshot-forged",
                "session_id": state.session_id,
                "purpose": state.purpose,
                "priority_line": state.priority_line,
                "overall_champion_candidate_id": "candidate-forged",
                "aspect_champions": state.aspect_champions,
                "status": "active",
                "source_finalize_event_id": finalize_event["event_id"],
                "termination_reason": "원장 수동 변조",
                "actor_type": "human",
                "actor_id": "tampered",
            },
        )
        with self.assertRaises(ValueError):
            self.termination.get("champion-snapshot-forged")

    def test_terminated_session_rejects_new_candidate(self) -> None:
        self.prepare_no_improvement()
        self.termination.approve(
            session_id=self.session.session_id,
            actor_type="human",
            actor_id="user",
            reason="종료",
        )
        third = self.accepted_gate("candidate-3")
        with self.assertRaises(ValueError):
            self.ratchet.admit_candidate(
                session_id=self.session.session_id,
                gate_flow_id=third.flow_id,
                actor_id="user",
            )

    def test_metagame_deprecate_and_reactivate_preserves_snapshot(self) -> None:
        self.prepare_no_improvement()
        snapshot = self.termination.approve(
            session_id=self.session.session_id,
            actor_type="human",
            actor_id="user",
            reason="종료",
        )
        original_champions = dict(snapshot.aspect_champions)
        snapshot = self.termination.change_status(
            snapshot_id=snapshot.snapshot_id,
            new_status="deprecated",
            actor_type="human",
            actor_id="user",
            reason="환경 변화",
        )
        self.assertEqual(snapshot.status, "deprecated")
        self.assertEqual(snapshot.aspect_champions, original_champions)
        snapshot = self.termination.change_status(
            snapshot_id=snapshot.snapshot_id,
            new_status="active",
            actor_type="human",
            actor_id="user",
            reason="환경 재변화로 재소환",
        )
        self.assertEqual(snapshot.status, "active")
        self.assertEqual(snapshot.aspect_champions, original_champions)

    def test_same_metagame_status_transition_is_rejected(self) -> None:
        self.prepare_no_improvement()
        snapshot = self.termination.approve(
            session_id=self.session.session_id,
            actor_type="human",
            actor_id="user",
            reason="종료",
        )
        with self.assertRaises(ValueError):
            self.termination.change_status(
                snapshot_id=snapshot.snapshot_id,
                new_status="active",
                actor_type="human",
                actor_id="user",
                reason="중복 상태",
            )


if __name__ == "__main__":
    unittest.main()
