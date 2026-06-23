from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from harness.appeals import AppealService
from harness.backends import MockBackend
from harness.casework import CaseLedger
from harness.library import LibraryLedger
from harness.models import NegativeExampleRule, ReviewerSpec, Task
from harness.pipeline import Harness
from harness.ratchet import RatchetLedger
from harness.reviewers import ReviewerRegistry
from harness.termination import TerminationLedger


LOGIC_REVIEWER = ReviewerSpec(
    reviewer_id="logic_reviewer",
    aspect="logic",
    description="논리 검사",
    instructions="전제와 결론을 검사한다.",
    dependency="dependent_core",
)


class FlowBackend(MockBackend):
    def __init__(
        self,
        verdicts: dict[str, str],
        *,
        salvageable_part: str = "",
    ) -> None:
        self.verdicts = verdicts
        self.salvageable_part = salvageable_part
        self.last_negative_examples: list[NegativeExampleRule] = []

    def generate_candidate(
        self,
        task: Task,
        negative_examples: list[NegativeExampleRule] | None = None,
    ) -> str:
        self.last_negative_examples = list(negative_examples or [])
        return super().generate_candidate(task, negative_examples)

    def assess_jurisdiction(
        self,
        task: Task,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict[str, Any]:
        return {
            "applicable": True,
            "reasoning": "통합 통수용 관할",
            "confidence": 95,
        }

    def review_candidate(
        self,
        task: Task,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict[str, Any]:
        verdict = self.verdicts[reviewer.reviewer_id]
        defect_found = verdict in {"reject", "revise"}
        return {
            "reviewer": reviewer.reviewer_id,
            "verdict": verdict,
            "defect_found": defect_found,
            "defect_type": "통합 시험 결함" if defect_found else "",
            "defect_where": "후보 본문" if defect_found else "",
            "reasoning": "통합 통수용 심사 근거",
            "required_revision": "결함을 수정한다." if verdict == "revise" else "",
            "confidence": 90,
            "feedback_to_thesis": (
                "결론과 독립된 근거를 제시한다." if defect_found else ""
            ),
            "salvageable_part": (
                self.salvageable_part if defect_found else ""
            ),
        }


class FullPipelineFlowTests(unittest.TestCase):
    def test_normal_flow_reaches_ratchet_termination_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(MockBackend(), log_path)
            ratchet = RatchetLedger(log_path)
            termination = TerminationLedger(log_path)

            first, _ = harness.run(
                "동일 목적의 후보를 비교한다",
                constraints=["되돌릴 수 있어야 한다"],
                required_aspects=["logic", "scope"],
            )
            first_gate = self._accept_current_gate(harness)
            session = ratchet.start(
                purpose="통합 정상 물길",
                priority_line=["logic", "scope"],
                actor_id="user",
            )
            state = ratchet.admit_candidate(
                session_id=session.session_id,
                gate_flow_id=first_gate.flow_id,
                actor_id="user",
            )
            self.assertEqual(state.overall_champion_candidate_id, first.candidate_id)

            second, _ = harness.run(
                "동일 목적의 후보를 비교한다",
                constraints=["되돌릴 수 있어야 한다"],
                required_aspects=["logic", "scope"],
            )
            second_gate = self._accept_current_gate(harness)
            ratchet.admit_candidate(
                session_id=session.session_id,
                gate_flow_id=second_gate.flow_id,
                actor_id="user",
            )
            for aspect, result in (
                ("logic", "no_meaningful_change"),
                ("scope", "regressed"),
            ):
                ratchet.record_comparison(
                    session_id=session.session_id,
                    aspect=aspect,
                    result=result,
                    actor_type="human",
                    actor_id="user",
                    reason="전체 통수 상대 비교",
                )
            final_state = ratchet.finalize_candidate(
                session_id=session.session_id,
                actor_id="user",
            )
            eligibility = termination.eligibility(session.session_id)
            self.assertTrue(eligibility["eligible"])
            snapshot = termination.approve(
                session_id=session.session_id,
                actor_type="human",
                actor_id="user",
                reason="어느 측면도 개선되지 않음",
            )

            self.assertEqual(
                snapshot.overall_champion_candidate_id,
                first.candidate_id,
            )
            self.assertEqual(
                final_state.overall_champion_candidate_id,
                first.candidate_id,
            )
            self.assertNotEqual(second.candidate_id, first.candidate_id)
            self.assertTrue(
                {
                    "task_created",
                    "review_batch_completed",
                    "gate_decision_recorded",
                    "ratchet_candidate_admitted",
                    "ratchet_comparison_recorded",
                    "ratchet_candidate_finalized",
                    "ratchet_termination_approved",
                }.issubset(set(self._event_types(log_path)))
            )

    def test_confirmed_escape_flows_back_into_next_generation(self) -> None:
        backend = FlowBackend({"logic_reviewer": "pass_to_next_gate"})
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(
                backend,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            )
            report = harness.run_adversary(
                "심사관의 사각지대를 찾는다",
                required_aspects=["logic"],
            )
            ledger = CaseLedger(log_path)
            ledger.confirm(
                case_id=report.case_id,
                new_status="confirmed",
                actor_type="human",
                actor_id="user",
                evidence="후보에서 숨은 순환 전제를 독립 확인",
                reason="결론을 전제로 재사용함",
            )
            readiness = ledger.record_feedback_readiness(
                actor_type="human",
                actor_id="user",
                scope="logic",
                evidence="확정 사건의 재현과 범위를 검토함",
                reason="되먹임 통수 승인",
            )
            ledger.approve_negative_example(
                case_id=report.case_id,
                readiness_id=readiness["payload"]["readiness_id"],
                actor_id="user",
                reason="다음 생성에서 동일 패턴 차단",
            )

            harness.run("후속 후보를 생성한다", required_aspects=["logic"])

            self.assertEqual(len(backend.last_negative_examples), 1)
            self.assertEqual(
                backend.last_negative_examples[0].case_id,
                report.case_id,
            )
            self.assertIn(
                "negative_example_context_applied",
                self._event_types(log_path),
            )

    def test_external_appeal_overturn_flows_to_confirmed_block_rule(self) -> None:
        second_logic = ReviewerSpec(
            reviewer_id="logic_reviewer_2",
            aspect="logic",
            description="독립 논리 검사",
            instructions="첫 심사와 독립적으로 논리를 검사한다.",
            dependency="dependent_core",
        )
        backend = FlowBackend(
            {
                "logic_reviewer": "pass_to_next_gate",
                "logic_reviewer_2": "reject",
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(
                backend,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER, second_logic]),
                reviewer_ids=["logic_reviewer", "logic_reviewer_2"],
            )
            candidate, batch = harness.run(
                "외부 재심 통합 시험",
                required_aspects=["logic"],
            )
            self.assertEqual(batch.status, "conflict")
            packet = harness.last_appeal_packet
            assert packet is not None
            result = AppealService(log_path).import_result(
                appeal_id=packet.appeal_id,
                candidate_id=candidate.candidate_id,
                verdict="overturn",
                actor_id="external-claude",
                defects=[
                    {
                        "type": "순환논증",
                        "where": "핵심 결론",
                        "why": "결론을 독립 근거 없이 전제로 재사용함",
                    }
                ],
                feedback_to_thesis="결론과 독립된 근거를 제시한다.",
            )
            case_id = result["payload"]["case_id"]
            ledger = CaseLedger(log_path)
            ledger.confirm(
                case_id=case_id,
                new_status="confirmed",
                actor_type="human",
                actor_id="user",
                evidence="외부 지적을 원문과 대조해 재현함",
                reason="순환논증 확인",
            )
            readiness = ledger.record_feedback_readiness(
                actor_type="human",
                actor_id="user",
                scope="external appeal logic",
                evidence="재심 결함의 재현과 범위를 확인함",
                reason="재심 되먹임 통수 승인",
            )
            ledger.approve_negative_example(
                case_id=case_id,
                readiness_id=readiness["payload"]["readiness_id"],
                actor_id="user",
                reason="외부 재심 Block-rule 활성",
            )
            harness.run("재심 후 후속 생성", required_aspects=["logic"])

            self.assertEqual(
                [rule.block_rule for rule in backend.last_negative_examples],
                ["결론과 독립된 근거를 제시한다."],
            )
            self.assertTrue(Path(packet.document_path).exists())
            self.assertTrue(
                {
                    "appeal_packet_created",
                    "appeal_result_recorded",
                    "appeal_overturn_case_reported",
                    "case_confirmation_recorded",
                    "negative_example_activation_approved",
                    "negative_example_context_applied",
                }.issubset(set(self._event_types(log_path)))
            )

    def test_rejected_review_salvage_flows_into_approved_library_query(self) -> None:
        salvage = "관찰 가능한 입력과 출력을 분리해 기록한다."
        backend = FlowBackend(
            {"logic_reviewer": "reject"},
            salvageable_part=salvage,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(
                backend,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            )
            candidate, _ = harness.run(
                "실패 후보에서 재사용 부품을 회수한다",
                required_aspects=["logic"],
            )
            events = self._events(log_path)
            intake_event = next(
                event
                for event in events
                if event["event_type"] == "library_intake_candidate_recorded"
            )
            library = LibraryLedger(log_path)
            part = library.add_part(
                content=salvage,
                premises=["입력과 출력을 관찰할 수 있다"],
                verification_context="논리 심사에서 독립 부품으로 회수",
                works_when=["변경을 되돌릴 수 있다"],
                fails_when=["외부 변수를 전혀 관찰할 수 없다"],
                purpose="실패 원인 분리",
                verification_status="salvaged_unverified",
                source_event_id=intake_event["event_id"],
                source_candidate_id=candidate.candidate_id,
                created_by="user",
            )
            self.assertEqual(
                library.query(purpose="실패 원인 분리"),
                [],
            )
            library.approve_purpose(
                part_id=part.part_id,
                actor_type="human",
                actor_id="user",
                reason="회수 당시 사용 목적과 일치함",
            )
            matches = library.query(
                purpose="실패 원인 분리",
                conditions=["변경을 되돌릴 수 있다"],
            )

            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].part.content, salvage)
            self.assertEqual(
                matches[0].part.verification_status,
                "salvaged_unverified",
            )

    @staticmethod
    def _accept_current_gate(harness: Harness):
        assert harness.last_gate_flow is not None
        state = harness.last_gate_flow
        for decision in (
            "pass_to_next_gate",
            "pass_to_next_gate",
            "accepted_synthesis",
        ):
            state = harness.gates.record_decision(
                flow_id=state.flow_id,
                decision=decision,
                actor_type="human",
                actor_id="user",
                reason="전체 통수 Gate 승인",
            )
        return state

    @staticmethod
    def _events(path: Path) -> list[dict[str, Any]]:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    @classmethod
    def _event_types(cls, path: Path) -> list[str]:
        return [event["event_type"] for event in cls._events(path)]


if __name__ == "__main__":
    unittest.main()
