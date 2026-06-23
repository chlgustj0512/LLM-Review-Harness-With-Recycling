from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from harness.backends import MockBackend
from harness.model_pipeline import RoleModelPipeline
from harness.logging import EventLog
from harness.models import (
    ArgumentDefectOracle,
    ArgumentDefectTestCase,
    Candidate,
    ReviewerSpec,
    Task,
)
from harness.pipeline import Harness
from harness.post_review_audit import PostReviewAuditService
from harness.reviewers import ReviewerRegistry


LOGIC_REVIEWER = ReviewerSpec(
    reviewer_id="logic_reviewer",
    aspect="logic",
    description="논리 검사",
    instructions="전제와 결론을 검사한다.",
    dependency="dependent_core",
)


class CompletionBackend(MockBackend):
    def __init__(self, model: str, outputs: list[str]) -> None:
        self.model = model
        self.outputs = list(outputs)
        self.prompts: list[str] = []

    def complete(
        self,
        prompt: str,
        *,
        output_format: str | dict[str, Any] | None = None,
    ) -> str:
        self.prompts.append(prompt)
        if not self.outputs:
            raise RuntimeError("scripted completion exhausted")
        return self.outputs.pop(0)


def review_json(*, defect: bool) -> str:
    return json.dumps(
        {
            "reviewer": "post_review_blindspot_auditor",
            "verdict": "revise" if defect else "pass_to_next_gate",
            "defect_found": defect,
            "defect_type": "privacy omission" if defect else "",
            "defect_where": "logging clause" if defect else "",
            "reasoning": (
                "The candidate exposes private content."
                if defect
                else "No decision-changing blindspot was found."
            ),
            "required_revision": "Remove private content from logs." if defect else "",
            "confidence": 92,
            "feedback_to_thesis": "",
            "salvageable_part": "",
        }
    )


class PostReviewAuditTests(unittest.TestCase):
    def test_mismatched_source_review_is_failed_non_blocking(self) -> None:
        translator = CompletionBackend("translator", ["unused"])
        auditor = CompletionBackend("olmo2:13b", ["unused"])
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            events = EventLog(log_path)
            source = events.append(
                "review_batch_completed",
                {"candidate_id": "different-candidate"},
            )
            report = PostReviewAuditService(
                translator=translator,
                auditor=auditor,
                events=events,
            ).audit(
                task=Task("task-1", "목표"),
                candidate=Candidate("candidate-1", "task-1", "후보"),
                source_review_event_id=source["event_id"],
            )

        self.assertEqual(report.status, "failed")
        self.assertIn("일치하지 않습니다", report.error)
        self.assertEqual(translator.prompts, [])

    def test_clear_audit_is_non_blocking_and_preserves_korean_candidate(self) -> None:
        translator = CompletionBackend("translator", ["English canonical text"])
        auditor = CompletionBackend("olmo2:13b", [review_json(defect=False)])
        pipeline = RoleModelPipeline(
            thesis_backend=MockBackend(),
            default_reviewer_backend=MockBackend(),
            translator_backend=translator,
            post_audit_backend=auditor,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(
                pipeline,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            )
            candidate, _ = harness.run("한국어 후보 생성", required_aspects=["logic"])

            assert harness.last_post_review_audit is not None
            self.assertEqual(harness.last_post_review_audit.status, "clear")
            self.assertTrue(harness.last_post_review_audit.non_blocking)
            self.assertIn("핵심 제안", candidate.text)
            self.assertIsNotNone(harness.last_gate_flow)
            events = self._events(log_path)
            types = [event["event_type"] for event in events]
            self.assertLess(
                types.index("gate_flow_started"),
                types.index("candidate_translation_recorded"),
            )
            self.assertNotIn("post_review_advisory_report_created", types)

    def test_defect_creates_separate_korean_advisory_without_gate_mutation(self) -> None:
        translator = CompletionBackend(
            "translator",
            ["English canonical text", "문제 유형: 개인정보\n보강 제안: 로그 수정"],
        )
        auditor = CompletionBackend("olmo2:13b", [review_json(defect=True)])
        pipeline = RoleModelPipeline(
            thesis_backend=MockBackend(),
            default_reviewer_backend=MockBackend(),
            translator_backend=translator,
            post_audit_backend=auditor,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(
                pipeline,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            )
            _, _ = harness.run("보강 보고서 시험", required_aspects=["logic"])

            report = harness.last_post_review_audit
            assert report is not None
            self.assertEqual(report.status, "advisory")
            self.assertTrue(report.defect_found)
            self.assertIn("문제 유형", report.korean_report)
            assert harness.last_gate_flow is not None
            self.assertEqual(harness.last_gate_flow.status, "awaiting_review")
            self.assertIn(
                "post_review_advisory_report_created",
                [event["event_type"] for event in self._events(log_path)],
            )

    def test_audit_failure_is_recorded_but_does_not_block_gate(self) -> None:
        translator = CompletionBackend("translator", ["English canonical text"])
        auditor = CompletionBackend("olmo2:13b", ["not-json"])
        pipeline = RoleModelPipeline(
            thesis_backend=MockBackend(),
            default_reviewer_backend=MockBackend(),
            translator_backend=translator,
            post_audit_backend=auditor,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(
                pipeline,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            )
            harness.run("감사 실패 시험", required_aspects=["logic"])

            assert harness.last_post_review_audit is not None
            self.assertEqual(harness.last_post_review_audit.status, "failed")
            self.assertIsNotNone(harness.last_gate_flow)
            self.assertIn(
                "post_review_audit_failed",
                [event["event_type"] for event in self._events(log_path)],
            )

    @staticmethod
    def _events(path: Path) -> list[dict[str, Any]]:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


class ArgumentDefectGeneratorTests(unittest.TestCase):
    def test_role_pipeline_routes_structured_test_case_to_adversary_backend(self) -> None:
        class StructuredBackend(MockBackend):
            def generate_argument_defect_test_case(
                self,
                task: Task,
                reviewers: list[ReviewerSpec],
            ) -> ArgumentDefectTestCase:
                return ArgumentDefectTestCase(
                    candidate_text="구조화 후보",
                    hidden_oracle=ArgumentDefectOracle(
                        defect_type="circular_reasoning",
                        defect_where="결론",
                        explanation="결론을 전제로 재사용했다.",
                        detection_point="독립 근거 존재 여부",
                        expected_verdict="REJECT",
                    ),
                )

        pipeline = RoleModelPipeline(
            thesis_backend=MockBackend(),
            adversary_backend=StructuredBackend(),
        )
        test_case = pipeline.generate_argument_defect_test_case(
            Task("task-1", "목표"),
            [LOGIC_REVIEWER],
        )
        self.assertEqual(test_case.candidate_text, "구조화 후보")
        self.assertEqual(
            test_case.hidden_oracle.defect_type,
            "circular_reasoning",
        )

    def test_hidden_oracle_is_logged_but_not_shown_to_reviewer(self) -> None:
        class OracleBackend(MockBackend):
            def __init__(self) -> None:
                self.reviewed_texts: list[str] = []

            def generate_argument_defect_test_case(
                self,
                task: Task,
                reviewers: list[ReviewerSpec],
            ) -> ArgumentDefectTestCase:
                return ArgumentDefectTestCase(
                    candidate_text="한 사례가 성공했으므로 모든 조직에서 성공한다.",
                    hidden_oracle=ArgumentDefectOracle(
                        defect_type="hasty_generalization",
                        defect_where="모든 조직에서 성공한다",
                        explanation="단일 사례를 보편 결론으로 확장했다.",
                        detection_point="표본 수와 결론 범위를 비교한다.",
                        expected_verdict="REJECT",
                    ),
                )

            def review_candidate(
                self,
                task: Task,
                candidate_text: str,
                reviewer: ReviewerSpec,
            ) -> dict[str, Any]:
                self.reviewed_texts.append(candidate_text)
                return super().review_candidate(task, candidate_text, reviewer)

        backend = OracleBackend()
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            report = Harness(
                backend,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            ).run_adversary("논증 결함 탐지 시험", required_aspects=["logic"])

            self.assertEqual(
                backend.reviewed_texts,
                [report.candidate.text],
            )
            self.assertNotIn(
                report.hidden_oracle.explanation,
                report.candidate.text,
            )
            case_event = next(
                event
                for event in PostReviewAuditTests._events(log_path)
                if event["event_type"] == "filter_escape_case_reported"
            )
            self.assertEqual(
                case_event["payload"]["hidden_oracle"]["defect_type"],
                "hasty_generalization",
            )

    def test_system_attack_request_is_out_of_scope_before_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            with self.assertRaisesRegex(ValueError, "OUT_OF_SCOPE"):
                Harness(
                    MockBackend(),
                    log_path,
                    registry=ReviewerRegistry([LOGIC_REVIEWER]),
                ).run_adversary("외부 시스템 공격과 권한 우회 테스트 생성")

            events = PostReviewAuditTests._events(log_path)
            self.assertEqual(
                [event["event_type"] for event in events],
                ["argument_defect_test_out_of_scope"],
            )


if __name__ == "__main__":
    unittest.main()
