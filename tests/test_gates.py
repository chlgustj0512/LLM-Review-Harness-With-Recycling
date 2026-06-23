from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harness.appeals import AppealService
from harness.casework import CaseLedger
from harness.gate_appeals import GateAppealCoordinator
from harness.gates import GateLedger
from harness.logging import EventLog
from review_fixtures import review_batch_payload


class GateFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.log_path = Path(self.temp_dir.name) / "events.jsonl"
        self.ledger = GateLedger(self.log_path)
        self.events = EventLog(self.log_path)
        self.events.append(
            "task_created",
            {"task_id": "task-1", "goal": "테스트", "constraints": []},
        )

    def start(self):
        review_event_id = self.register_candidate("candidate-1")
        return self.ledger.start(
            task_id="task-1",
            candidate_id="candidate-1",
            source_review_event_id=review_event_id,
        )

    def register_candidate(
        self,
        candidate_id: str,
        task_id: str = "task-1",
        review_status: str = "clear",
    ) -> str:
        self.events.append(
            "candidate_generated",
            {
                "candidate_id": candidate_id,
                "task_id": task_id,
                "text": "후보",
            },
        )
        event = self.events.append(
            "review_batch_completed",
            review_batch_payload(candidate_id, review_status),
        )
        return event["event_id"]

    def decide(self, flow_id: str, decision: str):
        return self.ledger.record_decision(
            flow_id=flow_id,
            decision=decision,
            actor_type="human",
            actor_id="user",
            reason=f"{decision} 통수 시험",
        )

    def test_passes_gate_1_and_2_then_accepts_gate_3(self) -> None:
        state = self.start()
        self.assertEqual((state.stage, state.status), (1, "awaiting_review"))

        state = self.decide(state.flow_id, "pass_to_next_gate")
        self.assertEqual((state.stage, state.status), (2, "awaiting_review"))

        state = self.decide(state.flow_id, "pass_to_next_gate")
        self.assertEqual((state.stage, state.status), (3, "awaiting_review"))

        state = self.decide(state.flow_id, "accepted_synthesis")
        self.assertEqual((state.stage, state.status), (3, "completed_accepted"))

    def test_forged_gate_transition_is_rejected_on_read(self) -> None:
        state = self.start()
        self.events.append(
            "gate_decision_recorded",
            {
                "flow_id": state.flow_id,
                "task_id": state.task_id,
                "candidate_id": state.current_candidate_id,
                "stage": 1,
                "previous_status": "awaiting_review",
                "decision": "pass_to_next_gate",
                "next_stage": 99,
                "next_status": "completed_accepted",
                "actor_type": "human",
                "actor_id": "tampered",
                "reason": "원장 수동 변조",
                "source_review_event_id": state.source_review_event_id,
                "source_review_status": "clear",
            },
        )
        with self.assertRaises(ValueError):
            self.ledger.get(state.flow_id)

    def test_forged_contradictory_review_is_rejected_before_gate(self) -> None:
        self.events.append(
            "candidate_generated",
            {
                "candidate_id": "candidate-contradictory-review",
                "task_id": "task-1",
                "text": "후보",
            },
        )
        payload = review_batch_payload(
            "candidate-contradictory-review",
            "dependent_core_blocked",
        )
        payload["reviews"][0].update(
            {
                "defect_found": False,
                "defect_type": "",
                "defect_where": "",
                "reasoning": "결함은 없지만 거절",
            }
        )
        review_event = self.events.append("review_batch_completed", payload)
        with self.assertRaises(ValueError):
            self.ledger.start(
                task_id="task-1",
                candidate_id="candidate-contradictory-review",
                source_review_event_id=review_event["event_id"],
            )

    def test_forged_clear_batch_status_is_rejected_before_gate(self) -> None:
        self.events.append(
            "candidate_generated",
            {
                "candidate_id": "candidate-forged-clear",
                "task_id": "task-1",
                "text": "후보",
            },
        )
        payload = review_batch_payload(
            "candidate-forged-clear",
            "dependent_core_blocked",
        )
        payload["status"] = "clear"
        review_event = self.events.append("review_batch_completed", payload)
        with self.assertRaises(ValueError):
            self.ledger.start(
                task_id="task-1",
                candidate_id="candidate-forged-clear",
                source_review_event_id=review_event["event_id"],
            )

    def test_applicable_jurisdiction_without_review_is_rejected(self) -> None:
        self.events.append(
            "candidate_generated",
            {
                "candidate_id": "candidate-missing-review",
                "task_id": "task-1",
                "text": "후보",
            },
        )
        payload = review_batch_payload("candidate-missing-review")
        payload["reviews"] = []
        review_event = self.events.append("review_batch_completed", payload)
        with self.assertRaises(ValueError):
            self.ledger.start(
                task_id="task-1",
                candidate_id="candidate-missing-review",
                source_review_event_id=review_event["event_id"],
            )

    def test_review_bound_to_other_candidate_is_rejected(self) -> None:
        self.events.append(
            "candidate_generated",
            {
                "candidate_id": "candidate-review-binding",
                "task_id": "task-1",
                "text": "후보",
            },
        )
        payload = review_batch_payload("candidate-review-binding")
        payload["reviews"][0]["candidate_id"] = "candidate-other"
        review_event = self.events.append("review_batch_completed", payload)
        with self.assertRaises(ValueError):
            self.ledger.start(
                task_id="task-1",
                candidate_id="candidate-review-binding",
                source_review_event_id=review_event["event_id"],
            )

    def test_revision_returns_to_same_gate_with_new_candidate(self) -> None:
        state = self.start()
        state = self.decide(state.flow_id, "revise")
        self.assertEqual((state.stage, state.status), (1, "awaiting_revision"))

        review_event_id = self.register_candidate("candidate-2")
        state = self.ledger.submit_revision(
            flow_id=state.flow_id,
            revised_candidate_id="candidate-2",
            source_review_event_id=review_event_id,
            actor_id="user",
            reason="수정본 제출",
        )
        self.assertEqual((state.stage, state.status), (1, "awaiting_review"))
        self.assertEqual(state.current_candidate_id, "candidate-2")
        self.assertEqual(state.source_review_event_id, review_event_id)

    def test_gate_3_human_review_requires_followup_decision(self) -> None:
        state = self.start()
        state = self.decide(state.flow_id, "pass_to_next_gate")
        state = self.decide(state.flow_id, "pass_to_next_gate")
        state, packet = GateAppealCoordinator(self.log_path).record_decision(
            flow_id=state.flow_id,
            decision="needs_human_review",
            actor_type="human",
            actor_id="user",
            reason="외부 재심 필요",
        )
        self.assertEqual(state.status, "awaiting_human_review")
        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertTrue(Path(packet.document_path).exists())
        events = [
            json.loads(line)
            for line in self.log_path.read_text(encoding="utf-8").splitlines()
        ]
        decision_event = next(
            event
            for event in events
            if event["event_type"] == "gate_decision_recorded"
            and event["payload"]["decision"] == "needs_human_review"
        )
        connection_event = next(
            event
            for event in events
            if event["event_type"] == "gate_appeal_connected"
        )
        self.assertEqual(decision_event["payload"]["appeal_id"], packet.appeal_id)
        self.assertEqual(
            connection_event["payload"]["gate_decision_event_id"],
            decision_event["event_id"],
        )

        AppealService(self.log_path).import_result(
            appeal_id=packet.appeal_id,
            candidate_id=state.current_candidate_id,
            verdict="uphold",
            actor_id="external-reviewer",
        )
        state = self.decide(state.flow_id, "accepted_synthesis")
        self.assertEqual(state.status, "completed_accepted")

    def test_gate_3_human_review_without_appeal_is_rejected(self) -> None:
        state = self.start()
        state = self.decide(state.flow_id, "pass_to_next_gate")
        state = self.decide(state.flow_id, "pass_to_next_gate")
        with self.assertRaises(ValueError):
            self.decide(state.flow_id, "needs_human_review")

    def test_gate_3_cannot_resolve_before_appeal_result(self) -> None:
        state = self.start()
        state = self.decide(state.flow_id, "pass_to_next_gate")
        state = self.decide(state.flow_id, "pass_to_next_gate")
        state, _ = GateAppealCoordinator(self.log_path).record_decision(
            flow_id=state.flow_id,
            decision="needs_human_review",
            actor_type="human",
            actor_id="user",
            reason="외부 재심 필요",
        )
        for decision in ("accepted_synthesis", "revise", "reject"):
            with self.assertRaises(ValueError):
                self.decide(state.flow_id, decision)

    def test_uncertain_appeal_blocks_accept_but_allows_revision(self) -> None:
        state = self.start()
        state = self.decide(state.flow_id, "pass_to_next_gate")
        state = self.decide(state.flow_id, "pass_to_next_gate")
        state, packet = GateAppealCoordinator(self.log_path).record_decision(
            flow_id=state.flow_id,
            decision="needs_human_review",
            actor_type="human",
            actor_id="user",
            reason="외부 재심 필요",
        )
        assert packet is not None
        AppealService(self.log_path).import_result(
            appeal_id=packet.appeal_id,
            candidate_id=state.current_candidate_id,
            verdict="uncertain",
            actor_id="external-reviewer",
        )
        with self.assertRaises(ValueError):
            self.decide(state.flow_id, "accepted_synthesis")
        state = self.decide(state.flow_id, "revise")
        self.assertEqual(state.status, "awaiting_revision")

    def test_overturn_appeal_requires_case_dismissal_before_accept(self) -> None:
        state = self.start()
        state = self.decide(state.flow_id, "pass_to_next_gate")
        state = self.decide(state.flow_id, "pass_to_next_gate")
        state, packet = GateAppealCoordinator(self.log_path).record_decision(
            flow_id=state.flow_id,
            decision="needs_human_review",
            actor_type="human",
            actor_id="user",
            reason="외부 재심 필요",
        )
        assert packet is not None
        result = AppealService(self.log_path).import_result(
            appeal_id=packet.appeal_id,
            candidate_id=state.current_candidate_id,
            verdict="overturn",
            actor_id="external-reviewer",
            defects=[
                {
                    "type": "순환논증",
                    "where": "결론",
                    "why": "결론을 전제로 사용함",
                }
            ],
        )
        case_id = result["payload"]["case_id"]
        with self.assertRaises(ValueError):
            self.decide(state.flow_id, "accepted_synthesis")

        CaseLedger(self.log_path).confirm(
            case_id=case_id,
            new_status="dismissed",
            actor_type="human",
            actor_id="user",
            evidence="독립 검산에서 결함이 재현되지 않음",
            reason="외부 재심 결함 기각",
        )
        state = self.decide(state.flow_id, "accepted_synthesis")
        self.assertEqual(state.status, "completed_accepted")

    def test_confirmed_overturn_case_blocks_accept(self) -> None:
        state = self.start()
        state = self.decide(state.flow_id, "pass_to_next_gate")
        state = self.decide(state.flow_id, "pass_to_next_gate")
        state, packet = GateAppealCoordinator(self.log_path).record_decision(
            flow_id=state.flow_id,
            decision="needs_human_review",
            actor_type="human",
            actor_id="user",
            reason="외부 재심 필요",
        )
        assert packet is not None
        result = AppealService(self.log_path).import_result(
            appeal_id=packet.appeal_id,
            candidate_id=state.current_candidate_id,
            verdict="overturn",
            actor_id="external-reviewer",
            defects=[
                {
                    "type": "순환논증",
                    "where": "결론",
                    "why": "결론을 전제로 사용함",
                }
            ],
        )
        CaseLedger(self.log_path).confirm(
            case_id=result["payload"]["case_id"],
            new_status="confirmed",
            actor_type="human",
            actor_id="user",
            evidence="독립 검산에서 결함 재현",
            reason="외부 재심 결함 확인",
        )
        with self.assertRaises(ValueError):
            self.decide(state.flow_id, "accepted_synthesis")
        state = self.decide(state.flow_id, "reject")
        self.assertEqual(state.status, "terminated_rejected")

    def test_invalid_gate_3_request_does_not_create_orphan_appeal(self) -> None:
        state = self.start()
        state = self.decide(state.flow_id, "pass_to_next_gate")
        state = self.decide(state.flow_id, "pass_to_next_gate")
        with self.assertRaises(ValueError):
            GateAppealCoordinator(self.log_path).record_decision(
                flow_id=state.flow_id,
                decision="needs_human_review",
                actor_type="invalid",
                actor_id="bad",
                reason="잘못된 요청",
            )
        event_types = [
            json.loads(line)["event_type"]
            for line in self.log_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertNotIn("appeal_packet_created", event_types)

    def test_gate_appeal_packet_retry_is_idempotent(self) -> None:
        state = self.start()
        state = self.decide(state.flow_id, "pass_to_next_gate")
        state = self.decide(state.flow_id, "pass_to_next_gate")
        service = AppealService(self.log_path)
        review_event = self.ledger.candidates.review_event(
            state.source_review_event_id
        )
        arguments = {
            "task_payload": self.ledger.candidates.task(state.task_id),
            "candidate_payload": self.ledger.candidates.candidate(
                state.current_candidate_id
            ),
            "review_payload": review_event["payload"],
            "gate_flow_id": state.flow_id,
            "source_review_event_id": state.source_review_event_id,
        }
        first = service.ensure_gate_appeal(**arguments)
        second = service.ensure_gate_appeal(**arguments)
        self.assertEqual(first.appeal_id, second.appeal_id)
        events = [
            json.loads(line)
            for line in self.log_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            sum(
                event["event_type"] == "appeal_packet_created"
                for event in events
            ),
            1,
        )

    def test_invalid_stage_decisions_are_rejected(self) -> None:
        state = self.start()
        with self.assertRaises(ValueError):
            self.decide(state.flow_id, "accepted_synthesis")
        with self.assertRaises(ValueError):
            self.decide(state.flow_id, "needs_human_review")

    def test_terminal_state_cannot_transition(self) -> None:
        state = self.start()
        state = self.decide(state.flow_id, "reject")
        self.assertEqual(state.status, "terminated_rejected")
        with self.assertRaises(ValueError):
            self.decide(state.flow_id, "pass_to_next_gate")

    def test_revision_submission_requires_revision_state(self) -> None:
        state = self.start()
        with self.assertRaises(ValueError):
            self.ledger.submit_revision(
                flow_id=state.flow_id,
                revised_candidate_id="candidate-2",
                source_review_event_id="missing-review",
                actor_id="user",
                reason="잘못된 제출",
            )

    def test_revision_rejects_nonexistent_candidate(self) -> None:
        state = self.decide(self.start().flow_id, "revise")
        with self.assertRaises(ValueError):
            self.ledger.submit_revision(
                flow_id=state.flow_id,
                revised_candidate_id="candidate-missing",
                source_review_event_id="event-missing",
                actor_id="user",
                reason="존재하지 않는 후보",
            )

    def test_revision_rejects_review_for_another_candidate(self) -> None:
        state = self.decide(self.start().flow_id, "revise")
        review_event_id = self.register_candidate("candidate-2")
        self.events.append(
            "candidate_generated",
            {
                "candidate_id": "candidate-3",
                "task_id": "task-1",
                "text": "다른 후보",
            },
        )
        with self.assertRaises(ValueError):
            self.ledger.submit_revision(
                flow_id=state.flow_id,
                revised_candidate_id="candidate-3",
                source_review_event_id=review_event_id,
                actor_id="user",
                reason="심사 결과 바꿔치기",
            )

    def test_gate_start_rejects_candidate_from_another_task(self) -> None:
        self.events.append(
            "task_created",
            {"task_id": "task-2", "goal": "다른 과제", "constraints": []},
        )
        review_event_id = self.register_candidate("candidate-2", "task-2")
        with self.assertRaises(ValueError):
            self.ledger.start(
                task_id="task-1",
                candidate_id="candidate-2",
                source_review_event_id=review_event_id,
            )

    def test_conflict_enters_human_review_and_tool_cannot_resolve(self) -> None:
        review_event_id = self.register_candidate(
            "candidate-conflict",
            review_status="conflict",
        )
        state = self.ledger.start(
            task_id="task-1",
            candidate_id="candidate-conflict",
            source_review_event_id=review_event_id,
        )
        self.assertEqual(state.status, "awaiting_human_review")
        with self.assertRaises(ValueError):
            self.ledger.record_decision(
                flow_id=state.flow_id,
                decision="pass_to_next_gate",
                actor_type="tool",
                actor_id="auto",
                reason="자동 우회",
            )

    def test_empty_aspect_requires_human_but_can_continue_same_stage(self) -> None:
        review_event_id = self.register_candidate(
            "candidate-empty",
            review_status="empty_aspect",
        )
        state = self.ledger.start(
            task_id="task-1",
            candidate_id="candidate-empty",
            source_review_event_id=review_event_id,
        )
        state = self.decide(state.flow_id, "pass_to_next_gate")
        self.assertEqual((state.stage, state.status), (2, "awaiting_review"))

    def test_human_review_status_cannot_skip_from_gate_1_to_completion(self) -> None:
        review_event_id = self.register_candidate(
            "candidate-human",
            review_status="human_review",
        )
        state = self.ledger.start(
            task_id="task-1",
            candidate_id="candidate-human",
            source_review_event_id=review_event_id,
        )
        with self.assertRaises(ValueError):
            self.decide(state.flow_id, "accepted_synthesis")

    def test_dependent_core_blocked_cannot_pass_or_accept(self) -> None:
        review_event_id = self.register_candidate(
            "candidate-core-blocked",
            review_status="dependent_core_blocked",
        )
        state = self.ledger.start(
            task_id="task-1",
            candidate_id="candidate-core-blocked",
            source_review_event_id=review_event_id,
        )
        with self.assertRaises(ValueError):
            self.decide(state.flow_id, "pass_to_next_gate")

    def test_independent_objection_can_be_passed_by_explicit_decision(self) -> None:
        review_event_id = self.register_candidate(
            "candidate-objection",
            review_status="objections",
        )
        state = self.ledger.start(
            task_id="task-1",
            candidate_id="candidate-objection",
            source_review_event_id=review_event_id,
        )
        state = self.decide(state.flow_id, "pass_to_next_gate")
        self.assertEqual((state.stage, state.status), (2, "awaiting_review"))

    def test_revision_uses_new_review_status_for_reentry(self) -> None:
        state = self.decide(self.start().flow_id, "revise")
        review_event_id = self.register_candidate(
            "candidate-revised-conflict",
            review_status="conflict",
        )
        state = self.ledger.submit_revision(
            flow_id=state.flow_id,
            revised_candidate_id="candidate-revised-conflict",
            source_review_event_id=review_event_id,
            actor_id="user",
            reason="충돌이 남은 수정본",
        )
        self.assertEqual(state.status, "awaiting_human_review")

    def test_legacy_unresolved_flow_cannot_bypass_human_review(self) -> None:
        review_event_id = self.register_candidate(
            "candidate-legacy-conflict",
            review_status="conflict",
        )
        self.events.append(
            "gate_flow_started",
            {
                "flow_id": "gate-flow-legacy",
                "task_id": "task-1",
                "candidate_id": "candidate-legacy-conflict",
                "stage": 1,
                "status": "awaiting_review",
                "source_review_event_id": review_event_id,
            },
        )
        with self.assertRaises(ValueError):
            self.decide("gate-flow-legacy", "pass_to_next_gate")
        state = self.decide("gate-flow-legacy", "needs_human_review")
        self.assertEqual(state.status, "awaiting_human_review")
        state = self.decide("gate-flow-legacy", "pass_to_next_gate")
        self.assertEqual((state.stage, state.status), (2, "awaiting_review"))
        state = self.decide(state.flow_id, "pass_to_next_gate")
        self.assertEqual((state.stage, state.status), (3, "awaiting_review"))
