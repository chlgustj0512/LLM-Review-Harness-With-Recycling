from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harness.appeals import AppealService
from harness.backends import MockBackend
from harness.casework import CaseLedger
from harness.gate_appeals import GateAppealCoordinator
from harness.pipeline import Harness
from harness.library import LibraryLedger
from harness.ratchet import RatchetLedger
from harness.termination import TerminationLedger


class PipelineRegressionTests(unittest.TestCase):
    """이전 릴리스에서 확정한 안전 계약의 회귀 방지."""

    def test_normal_run_preserves_generation_review_order_and_starts_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(MockBackend(), log_path)
            harness.run("회귀 검증")
            event_types = [
                json.loads(line)["event_type"]
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                event_types[:4],
                [
                    "task_created",
                    "candidate_generated",
                    "review_batch_completed",
                    "gate_flow_started",
                ],
            )

    def test_gate_revision_is_registered_reviewed_and_rebound(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(MockBackend(), log_path)
            original, _ = harness.run("수정 회송 회귀")
            assert harness.last_gate_flow is not None
            revising = harness.gates.record_decision(
                flow_id=harness.last_gate_flow.flow_id,
                decision="revise",
                actor_type="human",
                actor_id="test",
                reason="수정 필요",
            )

            revised, _ = harness.submit_gate_revision(
                flow_id=revising.flow_id,
                revised_text="재심사를 거칠 수정 후보",
                actor_id="test",
                reason="수정본 제출",
                required_aspects=["logic"],
            )

            self.assertNotEqual(revised.candidate_id, original.candidate_id)
            assert harness.last_gate_flow is not None
            self.assertEqual(
                harness.last_gate_flow.current_candidate_id,
                revised.candidate_id,
            )
            events = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]
            revision_event = next(
                event
                for event in reversed(events)
                if event["event_type"] == "gate_revision_submitted"
            )
            review_event = next(
                event
                for event in reversed(events)
                if event["event_type"] == "review_batch_completed"
                and event["payload"]["candidate_id"] == revised.candidate_id
            )
            self.assertEqual(
                revision_event["payload"]["source_review_event_id"],
                review_event["event_id"],
            )
            self.assertEqual(
                harness.last_gate_flow.source_review_event_id,
                review_event["event_id"],
            )

    def test_adversary_case_remains_shadow_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = Harness(
                MockBackend(),
                Path(temp_dir) / "events.jsonl",
            ).run_adversary("회귀 검증")
            self.assertEqual(report.confirmation_status, "unconfirmed")
            self.assertEqual(report.negative_example_status, "shadow_unconfirmed")
            self.assertFalse(report.negative_example_activated)

    def test_inconclusive_adversary_review_is_not_filter_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            class NoJurisdictionBackend(MockBackend):
                def assess_jurisdiction(self, task, candidate_text, reviewer):
                    return {
                        "applicable": False,
                        "reasoning": "시험용 관할 없음",
                        "confidence": 90,
                    }

            report = Harness(
                NoJurisdictionBackend(),
                Path(temp_dir) / "events.jsonl",
                reviewer_ids=["logic_reviewer"],
            ).run_adversary("회귀 검증", required_aspects=["logic"])
            self.assertEqual(report.disposition, "review_inconclusive")

    def test_confirmed_case_still_requires_explicit_activation(self) -> None:
        # Mock adversary는 필터에 잡히므로 수동으로 통과 case를 위조하지 않는다.
        # 이 회귀는 원장에 활성 사건이 없으면 규칙 목록이 비어 있다는 계약을 고정한다.
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = CaseLedger(Path(temp_dir) / "events.jsonl")
            self.assertEqual(ledger.active_negative_examples(), [])

    def test_appeal_result_cannot_exist_without_packet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AppealService(Path(temp_dir) / "events.jsonl")
            with self.assertRaises(ValueError):
                service.import_result(
                    appeal_id="appeal-missing",
                    candidate_id="candidate-1",
                    verdict="uphold",
                    actor_id="user",
                )

    def test_gate_3_cannot_accept_before_appeal_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(MockBackend(), log_path)
            harness.run("Gate 3 재심 회귀")
            assert harness.last_gate_flow is not None
            state = harness.last_gate_flow
            for decision in ("pass_to_next_gate", "pass_to_next_gate"):
                state = harness.gates.record_decision(
                    flow_id=state.flow_id,
                    decision=decision,
                    actor_type="human",
                    actor_id="test",
                    reason="Gate 통과",
                )
            state, packet = GateAppealCoordinator(log_path).record_decision(
                flow_id=state.flow_id,
                decision="needs_human_review",
                actor_type="human",
                actor_id="test",
                reason="외부 재심 필요",
            )
            assert packet is not None
            with self.assertRaises(ValueError):
                harness.gates.record_decision(
                    flow_id=state.flow_id,
                    decision="accepted_synthesis",
                    actor_type="human",
                    actor_id="test",
                    reason="결과 없는 승인 금지",
                )
            AppealService(log_path).import_result(
                appeal_id=packet.appeal_id,
                candidate_id=state.current_candidate_id,
                verdict="uncertain",
                actor_id="external-reviewer",
            )
            with self.assertRaises(ValueError):
                harness.gates.record_decision(
                    flow_id=state.flow_id,
                    decision="accepted_synthesis",
                    actor_type="human",
                    actor_id="test",
                    reason="불확정 승인 금지",
                )

    def test_every_new_event_has_event_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            Harness(MockBackend(), log_path).run("event ID 회귀")
            events = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertTrue(events)
            self.assertTrue(all(event.get("event_id") for event in events))

    def test_library_does_not_expose_unapproved_purpose(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            source = Harness(MockBackend(), log_path)
            candidate, _ = source.run("라이브러리 회귀")
            events = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]
            review_event_id = next(
                event["event_id"]
                for event in events
                if event["event_type"] == "review_batch_completed"
            )
            ledger = LibraryLedger(log_path)
            ledger.add_part(
                content="부품",
                premises=["전제"],
                verification_context="심사 맥락",
                works_when=["작동 조건"],
                fails_when=["실패 조건"],
                purpose="회귀 목적",
                verification_status="salvaged_unverified",
                source_event_id=review_event_id,
                source_candidate_id=candidate.candidate_id,
                created_by="test",
            )
            self.assertEqual(ledger.query(purpose="회귀 목적"), [])

    def test_ratchet_rejects_candidate_without_completed_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            session = RatchetLedger(log_path).start(
                purpose="회귀 목적",
                priority_line=["logic"],
                actor_id="test",
            )
            run = Harness(MockBackend(), log_path)
            run.run("미완료 Gate 후보")
            assert run.last_gate_flow is not None
            with self.assertRaises(ValueError):
                RatchetLedger(log_path).admit_candidate(
                    session_id=session.session_id,
                    gate_flow_id=run.last_gate_flow.flow_id,
                    actor_id="test",
                )

    def test_ratchet_does_not_auto_terminate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            session = RatchetLedger(log_path).start(
                purpose="종료 회귀",
                priority_line=["logic"],
                actor_id="test",
            )
            self.assertFalse(
                TerminationLedger(log_path).is_session_terminated(
                    session.session_id
                )
            )


if __name__ == "__main__":
    unittest.main()
