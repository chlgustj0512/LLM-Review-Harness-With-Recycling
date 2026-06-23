from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import harness
from harness.appeals import AppealService
from harness.backends import (
    Backend,
    JURISDICTION_JSON_SCHEMA,
    MockBackend,
    REVIEW_JSON_SCHEMA,
    _extract_json_object,
)
from harness.casework import CaseLedger
from harness.logging import EventLog
from harness.models import (
    Candidate,
    NegativeExampleRule,
    Review,
    ReviewerSpec,
    Task,
)
from harness.model_pipeline import RoleModelPipeline
from harness.orchestrator import ReviewerOrchestrator
from harness.pipeline import Harness
from harness.probes import DEFAULT_PROBES
from harness.prompts import jurisdiction_prompt
from harness.reviewers import ReviewerRegistry

LOGIC_REVIEWER = ReviewerSpec(
    reviewer_id="logic_reviewer",
    aspect="logic",
    description="논리 검사",
    instructions="전제와 결론을 검사한다.",
    dependency="dependent_core",
)


class ScriptedBackend(Backend):
    name = "scripted"

    def __init__(
        self,
        jurisdictions: dict[str, bool],
        verdicts: dict[str, str],
        salvageable_parts: dict[str, str] | None = None,
    ) -> None:
        self.jurisdictions = jurisdictions
        self.verdicts = verdicts
        self.salvageable_parts = dict(salvageable_parts or {})
        self.calls: list[str] = []
        self.last_negative_examples: list[NegativeExampleRule] = []

    def generate_candidate(
        self,
        task: Task,
        negative_examples: list[NegativeExampleRule] | None = None,
    ) -> str:
        self.last_negative_examples = list(negative_examples or [])
        return f"후보 / 활성 규칙 {len(self.last_negative_examples)}개"

    def generate_adversarial_candidate(
        self,
        task: Task,
        reviewers: list[ReviewerSpec],
    ) -> str:
        return "겉보기에는 완성됐지만 결함이 숨은 후보"

    def assess_jurisdiction(
        self,
        task: Task,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict[str, Any]:
        self.calls.append(f"jurisdiction:{reviewer.reviewer_id}")
        return {
            "applicable": self.jurisdictions.get(reviewer.reviewer_id, False),
            "reasoning": "테스트 관할 판정",
            "confidence": 100,
        }

    def review_candidate(
        self,
        task: Task,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict[str, Any]:
        self.calls.append(f"review:{reviewer.reviewer_id}")
        verdict = self.verdicts[reviewer.reviewer_id]
        defect = verdict in {"reject", "revise"}
        return {
            "reviewer": reviewer.reviewer_id,
            "verdict": verdict,
            "defect_found": defect,
            "defect_type": "테스트 결함" if defect else "",
            "defect_where": "후보" if defect else "",
            "reasoning": "테스트 심사 근거",
            "required_revision": "수정" if defect else "",
            "confidence": 90,
            "feedback_to_thesis": "피드백" if defect else "",
            "salvageable_part": self.salvageable_parts.get(
                reviewer.reviewer_id,
                "",
            ),
        }


class ReviewValidationTests(unittest.TestCase):
    @staticmethod
    def review_payload(**overrides: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "reviewer": "logic_reviewer",
            "verdict": "reject",
            "defect_found": True,
            "defect_type": "순환논증",
            "defect_where": "첫 문장",
            "reasoning": "결론을 전제로 썼다.",
            "required_revision": "",
            "confidence": 90,
            "feedback_to_thesis": "",
            "salvageable_part": "",
        }
        payload.update(overrides)
        return payload

    def test_package_version_matches_release(self) -> None:
        self.assertEqual(harness.__version__, "0.15.1")

    def test_rejects_invalid_pass_with_defect(self) -> None:
        with self.assertRaises(ValueError):
            Review.from_dict(
                {
                    "reviewer": "logic_reviewer",
                    "verdict": "pass_to_next_gate",
                    "defect_found": True,
                    "defect_type": "순환논증",
                    "defect_where": "첫 문장",
                    "reasoning": "결론을 전제로 썼다.",
                    "required_revision": "",
                    "confidence": 90,
                    "feedback_to_thesis": "",
                    "salvageable_part": "",
                },
                "candidate-1",
                LOGIC_REVIEWER,
            )

    def test_reject_and_revise_require_detected_defect(self) -> None:
        for verdict in ("reject", "revise"):
            with self.subTest(verdict=verdict), self.assertRaises(ValueError):
                Review.from_dict(
                    self.review_payload(
                        verdict=verdict,
                        defect_found=False,
                        defect_type="",
                        defect_where="",
                        required_revision="수정" if verdict == "revise" else "",
                    ),
                    "candidate-1",
                    LOGIC_REVIEWER,
                )

    def test_detected_defect_requires_type_and_location(self) -> None:
        for missing in ("defect_type", "defect_where"):
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                Review.from_dict(
                    self.review_payload(**{missing: ""}),
                    "candidate-1",
                    LOGIC_REVIEWER,
                )

    def test_revise_requires_revision_instruction(self) -> None:
        with self.assertRaises(ValueError):
            Review.from_dict(
                self.review_payload(verdict="revise", required_revision=""),
                "candidate-1",
                LOGIC_REVIEWER,
            )

    def test_no_defect_rejects_defect_details(self) -> None:
        with self.assertRaises(ValueError):
            Review.from_dict(
                self.review_payload(
                    verdict="pass_to_next_gate",
                    defect_found=False,
                    defect_where="",
                ),
                "candidate-1",
                LOGIC_REVIEWER,
            )

    def test_human_review_preserves_uncertainty(self) -> None:
        unresolved = Review.from_dict(
            self.review_payload(
                verdict="needs_human_review",
                defect_found=False,
                defect_type="",
                defect_where="",
            ),
            "candidate-1",
            LOGIC_REVIEWER,
        )
        suspected = Review.from_dict(
            self.review_payload(verdict="needs_human_review"),
            "candidate-1",
            LOGIC_REVIEWER,
        )
        self.assertFalse(unresolved.defect_found)
        self.assertTrue(suspected.defect_found)

    def test_extracts_json_from_code_fence(self) -> None:
        raw = '```json\n{"verdict":"reject","defect_found":true}\n```'
        parsed = _extract_json_object(raw)
        self.assertEqual(parsed["verdict"], "reject")

    def test_structured_output_schemas_require_contract_fields(self) -> None:
        review_required = set(REVIEW_JSON_SCHEMA["required"])
        self.assertEqual(review_required, set(REVIEW_JSON_SCHEMA["properties"]))
        jurisdiction_required = set(JURISDICTION_JSON_SCHEMA["required"])
        self.assertEqual(
            jurisdiction_required,
            set(JURISDICTION_JSON_SCHEMA["properties"]),
        )

    def test_jurisdiction_prompt_separates_scope_from_defect_finding(self) -> None:
        reviewer = ReviewerRegistry().select(["physics_reviewer"])[0]
        prompt = jurisdiction_prompt(
            Task(task_id="task-1", goal="검산", constraints=[]),
            "운동에너지 식과 단위를 검산한다.",
            reviewer,
        )
        self.assertIn("관할은 결함 발견 여부가 아니라 검사 대상의 존재 여부", prompt)
        self.assertIn("결함의 유무와 판정은 다음 Review 단계", prompt)
        self.assertIn(reviewer.instructions, prompt)
        self.assertIn("누락을 이유로 applicable=false라 하지 마라", prompt)

    def test_scope_reviewer_blocks_arbitrary_measurement_demands(self) -> None:
        reviewer = ReviewerRegistry().select(["scope_reviewer"])[0]
        self.assertIn("임의의 수치 기준", reviewer.instructions)
        self.assertIn("사람 처리·되돌림 경로", reviewer.instructions)
        self.assertIn("logic 측면으로 떠넘기지 마라", reviewer.instructions)

    def test_salvage_requires_reject_or_revise_defect(self) -> None:
        with self.assertRaises(ValueError):
            Review.from_dict(
                {
                    "reviewer": "logic_reviewer",
                    "verdict": "pass_to_next_gate",
                    "defect_found": False,
                    "defect_type": "",
                    "defect_where": "",
                    "reasoning": "결함 없음",
                    "required_revision": "",
                    "confidence": 90,
                    "feedback_to_thesis": "",
                    "salvageable_part": "임의 추출 부품",
                },
                "candidate-1",
                LOGIC_REVIEWER,
            )


class OrchestratorTests(unittest.TestCase):
    def test_runs_reviewers_sequentially_in_registry_order(self) -> None:
        reviewers = [
            LOGIC_REVIEWER,
            ReviewerSpec(
                reviewer_id="scope_reviewer",
                aspect="scope",
                description="범위 검사",
                instructions="범위를 검사한다.",
                dependency="independent",
            ),
        ]
        backend = ScriptedBackend(
            jurisdictions={"logic_reviewer": True, "scope_reviewer": True},
            verdicts={
                "logic_reviewer": "pass_to_next_gate",
                "scope_reviewer": "pass_to_next_gate",
            },
        )
        batch = ReviewerOrchestrator(backend, reviewers).review(
            Task("task-1", "목표"),
            Candidate("candidate-1", "task-1", "후보"),
            required_aspects=["logic", "scope"],
        )
        self.assertEqual(
            backend.calls,
            [
                "jurisdiction:logic_reviewer",
                "review:logic_reviewer",
                "jurisdiction:scope_reviewer",
                "review:scope_reviewer",
            ],
        )
        self.assertEqual(batch.status, "clear")

    def test_detects_empty_required_aspect(self) -> None:
        backend = ScriptedBackend(
            jurisdictions={"logic_reviewer": False},
            verdicts={},
        )
        batch = ReviewerOrchestrator(backend, [LOGIC_REVIEWER]).review(
            Task("task-1", "목표"),
            Candidate("candidate-1", "task-1", "후보"),
            required_aspects=["logic"],
        )
        self.assertEqual(batch.empty_aspects, ["logic"])
        self.assertEqual(batch.status, "empty_aspect")
        self.assertEqual(batch.reviews, [])

    def test_detects_same_aspect_conflict(self) -> None:
        reviewers = [
            LOGIC_REVIEWER,
            ReviewerSpec(
                reviewer_id="logic_reviewer_2",
                aspect="logic",
                description="두 번째 논리 검사",
                instructions="논리를 독립 검사한다.",
                dependency="dependent_core",
            ),
        ]
        backend = ScriptedBackend(
            jurisdictions={
                "logic_reviewer": True,
                "logic_reviewer_2": True,
            },
            verdicts={
                "logic_reviewer": "pass_to_next_gate",
                "logic_reviewer_2": "reject",
            },
        )
        batch = ReviewerOrchestrator(backend, reviewers).review(
            Task("task-1", "목표"),
            Candidate("candidate-1", "task-1", "후보"),
            required_aspects=["logic"],
        )
        self.assertEqual(batch.conflicting_aspects, ["logic"])
        self.assertEqual(batch.status, "conflict")

    def test_dependent_core_objection_is_separate_from_gate_decision(self) -> None:
        backend = ScriptedBackend(
            jurisdictions={"logic_reviewer": True},
            verdicts={"logic_reviewer": "reject"},
        )
        batch = ReviewerOrchestrator(backend, [LOGIC_REVIEWER]).review(
            Task("task-1", "목표"),
            Candidate("candidate-1", "task-1", "후보"),
        )
        result = batch.to_dict()
        self.assertEqual(batch.status, "dependent_core_blocked")
        self.assertEqual(batch.dependent_core_blocked, ["logic"])
        self.assertIsNone(result["gate_decision"])


class PipelineTests(unittest.TestCase):
    def test_end_to_end_run_writes_batch_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(MockBackend(), log_path)
            candidate, batch = harness.run("테스트 가능한 개선안을 제안하라")

            self.assertTrue(candidate.text)
            self.assertEqual(batch.status, "clear")
            self.assertEqual(
                [review.reviewer for review in batch.reviews],
                ["logic_reviewer", "scope_reviewer"],
            )
            events = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                [event["event_type"] for event in events],
                [
                    "task_created",
                    "candidate_generated",
                    "review_batch_completed",
                    "gate_flow_started",
                ],
            )

    def test_registry_rejects_duplicate_ids(self) -> None:
        with self.assertRaises(ValueError):
            ReviewerRegistry([LOGIC_REVIEWER, LOGIC_REVIEWER])

    def test_internal_review_salvage_enters_incomplete_intake(self) -> None:
        backend = ScriptedBackend(
            jurisdictions={"logic_reviewer": True},
            verdicts={"logic_reviewer": "reject"},
            salvageable_parts={
                "logic_reviewer": "검증 방법은 독립 부품으로 보존한다."
            },
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness_instance = Harness(
                backend,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            )
            candidate, batch = harness_instance.run("내부 환원 시험")
            self.assertEqual(
                batch.reviews[0].salvageable_part,
                "검증 방법은 독립 부품으로 보존한다.",
            )
            intake = harness_instance.gates.events.path
            entries = [
                json.loads(line)["payload"]
                for line in intake.read_text(encoding="utf-8").splitlines()
                if json.loads(line)["event_type"]
                == "library_intake_candidate_recorded"
            ]
            self.assertEqual(len(entries), 1)
            self.assertEqual(
                entries[0]["source_candidate_id"],
                candidate.candidate_id,
            )
            self.assertEqual(entries[0]["source_kind"], "internal_review")
            self.assertEqual(entries[0]["source_verdict"], "reject")
            self.assertFalse(entries[0]["searchable"])

    def test_internal_review_without_salvage_creates_no_intake(self) -> None:
        backend = ScriptedBackend(
            jurisdictions={"logic_reviewer": True},
            verdicts={"logic_reviewer": "reject"},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            Harness(
                backend,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            ).run("보존 부품 없음")
            event_types = [
                json.loads(line)["event_type"]
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertNotIn("library_intake_candidate_recorded", event_types)

    def test_all_default_probes_match_expected_detection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            harness = Harness(
                MockBackend(),
                Path(temp_dir) / "events.jsonl",
                reviewer_ids=[
                    "logic_reviewer",
                    "code_reviewer",
                    "math_reviewer",
                    "physics_reviewer",
                    "scope_reviewer",
                    "blindspot_reviewer",
                ],
            )
            results = [harness.run_probe(probe) for probe in DEFAULT_PROBES]
            self.assertTrue(all(result.correct for result in results))
            expected_reviewers = {
                "logic": "logic_reviewer",
                "code": "code_reviewer",
                "math": "math_reviewer",
                "physics": "physics_reviewer",
                "scope": "scope_reviewer",
                "blindspot": "blindspot_reviewer",
            }
            for probe, result in zip(DEFAULT_PROBES, results, strict=True):
                with self.subTest(probe_id=probe.probe_id):
                    self.assertEqual(result.expected_detected, probe.expected_detected)
                    if probe.expected_detected:
                        self.assertIn(
                            expected_reviewers[probe.domain],
                            result.detecting_reviewers,
                        )
                    else:
                        self.assertFalse(result.detecting_reviewers)
                        self.assertEqual(result.review_batch.status, "clear")

    def test_adversary_caught_by_filter_stays_shadowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            harness = Harness(MockBackend(), Path(temp_dir) / "events.jsonl")
            report = harness.run_adversary("조직 개선안을 제안하라")

            self.assertEqual(report.disposition, "caught_by_filter")
            self.assertEqual(report.confirmation_status, "unconfirmed")
            self.assertEqual(report.negative_example_status, "shadow_unconfirmed")
            self.assertFalse(report.negative_example_activated)

    def test_clear_adversary_result_is_candidate_not_confirmed_case(self) -> None:
        backend = ScriptedBackend(
            jurisdictions={"logic_reviewer": True},
            verdicts={"logic_reviewer": "pass_to_next_gate"},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            harness = Harness(
                backend,
                Path(temp_dir) / "events.jsonl",
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            )
            report = harness.run_adversary("검토 대상")

            self.assertEqual(report.disposition, "filter_escape_candidate")
            self.assertEqual(report.confirmation_status, "unconfirmed")
            self.assertFalse(report.negative_example_activated)

    def test_empty_aspect_adversary_review_is_inconclusive(self) -> None:
        backend = ScriptedBackend(
            jurisdictions={"logic_reviewer": False},
            verdicts={},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(
                backend,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            )
            report = harness.run_adversary(
                "검토 대상",
                required_aspects=["logic"],
            )
            self.assertEqual(report.review_batch.status, "empty_aspect")
            self.assertEqual(report.disposition, "review_inconclusive")
            self.assertIsNotNone(harness.last_appeal_packet)
            with self.assertRaises(ValueError):
                CaseLedger(log_path).confirm(
                    case_id=report.case_id,
                    new_status="confirmed",
                    actor_type="human",
                    actor_id="user",
                    evidence="미심사 상태",
                    reason="적발 증거가 아님",
                )

    def test_conflicting_adversary_review_is_inconclusive(self) -> None:
        second_logic = ReviewerSpec(
            reviewer_id="logic_reviewer_2",
            aspect="logic",
            description="두 번째 논리 검사",
            instructions="독립적으로 논리를 검사한다.",
            dependency="dependent_core",
        )
        backend = ScriptedBackend(
            jurisdictions={
                "logic_reviewer": True,
                "logic_reviewer_2": True,
            },
            verdicts={
                "logic_reviewer": "pass_to_next_gate",
                "logic_reviewer_2": "reject",
            },
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            report = Harness(
                backend,
                Path(temp_dir) / "events.jsonl",
                registry=ReviewerRegistry([LOGIC_REVIEWER, second_logic]),
                reviewer_ids=["logic_reviewer", "logic_reviewer_2"],
            ).run_adversary("검토 대상")
            self.assertEqual(report.review_batch.status, "conflict")
            self.assertEqual(report.disposition, "review_inconclusive")

    def test_human_review_adversary_result_is_inconclusive(self) -> None:
        backend = ScriptedBackend(
            jurisdictions={"logic_reviewer": True},
            verdicts={"logic_reviewer": "needs_human_review"},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            report = Harness(
                backend,
                Path(temp_dir) / "events.jsonl",
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            ).run_adversary("검토 대상")
            self.assertEqual(report.review_batch.status, "human_review")
            self.assertEqual(report.disposition, "review_inconclusive")

    def test_legacy_inconclusive_case_is_normalized_on_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            EventLog(log_path).append(
                "filter_escape_case_reported",
                {
                    "case_id": "legacy-inconclusive-case",
                    "task_id": "task-1",
                    "candidate": {
                        "candidate_id": "candidate-1",
                        "task_id": "task-1",
                        "text": "후보",
                    },
                    "review_batch": {
                        "status": "empty_aspect",
                        "reviews": [],
                    },
                    "disposition": "caught_by_filter",
                    "confirmation_status": "unconfirmed",
                    "negative_example_status": "shadow_unconfirmed",
                    "negative_example_activated": False,
                },
            )
            state = CaseLedger(log_path).get("legacy-inconclusive-case")
            self.assertEqual(
                state.report["disposition"],
                "review_inconclusive",
            )
            self.assertEqual(
                state.report["reported_disposition"],
                "caught_by_filter",
            )
            self.assertTrue(
                state.report["disposition_normalized_from_legacy"]
            )

    def test_role_model_pipeline_routes_reviewer_backend(self) -> None:
        thesis = ScriptedBackend({}, {})
        default = ScriptedBackend(
            jurisdictions={"logic_reviewer": False},
            verdicts={},
        )
        dedicated = ScriptedBackend(
            jurisdictions={"logic_reviewer": True},
            verdicts={"logic_reviewer": "reject"},
        )
        pipeline = RoleModelPipeline(
            thesis_backend=thesis,
            adversary_backend=thesis,
            default_reviewer_backend=default,
            reviewer_backends={"logic_reviewer": dedicated},
        )
        batch = ReviewerOrchestrator(pipeline, [LOGIC_REVIEWER]).review(
            Task("task-1", "목표"),
            Candidate("candidate-1", "task-1", "후보"),
        )
        self.assertEqual(batch.status, "dependent_core_blocked")
        self.assertEqual(default.calls, [])
        self.assertEqual(
            dedicated.calls,
            ["jurisdiction:logic_reviewer", "review:logic_reviewer"],
        )

    def test_filter_escape_case_can_be_confirmed_without_activation(self) -> None:
        backend = ScriptedBackend(
            jurisdictions={"logic_reviewer": True},
            verdicts={"logic_reviewer": "pass_to_next_gate"},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(
                backend,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            )
            report = harness.run_adversary("검토 대상")
            state = CaseLedger(log_path).confirm(
                case_id=report.case_id,
                new_status="confirmed",
                actor_type="human",
                actor_id="user",
                evidence="후보의 숨은 순환논증을 직접 확인",
                reason="결론을 전제로 재사용함",
            )

            self.assertEqual(state.confirmation_status, "confirmed")
            self.assertEqual(
                state.negative_example_status,
                "eligible_pending_approval",
            )
            self.assertFalse(state.negative_example_activated)
            events = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn(
                "case_confirmation_recorded",
                [event["event_type"] for event in events],
            )
            self.assertTrue(all("event_id" in event for event in events))

    def test_dismissed_case_cannot_transition_again(self) -> None:
        backend = ScriptedBackend(
            jurisdictions={"logic_reviewer": True},
            verdicts={"logic_reviewer": "pass_to_next_gate"},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(
                backend,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            )
            report = harness.run_adversary("검토 대상")
            ledger = CaseLedger(log_path)
            ledger.confirm(
                case_id=report.case_id,
                new_status="dismissed",
                actor_type="tool",
                actor_id="test-verifier",
                evidence="독립 검산 결과 결함 없음",
                reason="반례가 성립하지 않음",
            )
            with self.assertRaises(ValueError):
                ledger.confirm(
                    case_id=report.case_id,
                    new_status="confirmed",
                    actor_type="human",
                    actor_id="user",
                    evidence="재판정",
                    reason="상태 변경 시도",
                )

    def test_caught_case_cannot_be_promoted_to_confirmed_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            report = Harness(MockBackend(), log_path).run_adversary("조직 개선")
            with self.assertRaises(ValueError):
                CaseLedger(log_path).confirm(
                    case_id=report.case_id,
                    new_status="confirmed",
                    actor_type="human",
                    actor_id="user",
                    evidence="이미 필터가 잡음",
                    reason="통과 사건이 아님",
                )

    def test_confirmed_case_is_not_injected_before_explicit_approval(self) -> None:
        backend = ScriptedBackend(
            jurisdictions={"logic_reviewer": True},
            verdicts={"logic_reviewer": "pass_to_next_gate"},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(
                backend,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            )
            report = harness.run_adversary("검토 대상")
            CaseLedger(log_path).confirm(
                case_id=report.case_id,
                new_status="confirmed",
                actor_type="human",
                actor_id="user",
                evidence="숨은 결함 확인",
                reason="독립 근거 부재",
            )

            harness.run("새 과제")
            self.assertEqual(backend.last_negative_examples, [])

    def test_activation_requires_feedback_readiness(self) -> None:
        backend = ScriptedBackend(
            jurisdictions={"logic_reviewer": True},
            verdicts={"logic_reviewer": "pass_to_next_gate"},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(
                backend,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            )
            report = harness.run_adversary("검토 대상")
            ledger = CaseLedger(log_path)
            ledger.confirm(
                case_id=report.case_id,
                new_status="confirmed",
                actor_type="human",
                actor_id="user",
                evidence="숨은 결함 확인",
                reason="독립 근거 부재",
            )
            with self.assertRaises(ValueError):
                ledger.approve_negative_example(
                    case_id=report.case_id,
                    readiness_id="missing-readiness",
                    actor_id="user",
                    reason="활성 승인",
                )

    def test_approved_negative_example_flows_into_thesis_context(self) -> None:
        backend = ScriptedBackend(
            jurisdictions={"logic_reviewer": True},
            verdicts={"logic_reviewer": "pass_to_next_gate"},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(
                backend,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            )
            report = harness.run_adversary("검토 대상")
            ledger = CaseLedger(log_path)
            ledger.confirm(
                case_id=report.case_id,
                new_status="confirmed",
                actor_type="human",
                actor_id="user",
                evidence="숨은 결함 확인",
                reason="독립 근거 부재",
            )
            readiness_event = ledger.record_feedback_readiness(
                actor_type="human",
                actor_id="user",
                scope="logic feedback",
                evidence="확정 케이스를 검토함",
                reason="되먹임 배관 시험 승인",
            )
            readiness_id = readiness_event["payload"]["readiness_id"]
            state = ledger.approve_negative_example(
                case_id=report.case_id,
                readiness_id=readiness_id,
                actor_id="user",
                reason="Block-rule 활성 승인",
            )

            self.assertTrue(state.negative_example_activated)
            self.assertEqual(state.negative_example_status, "active_approved")
            harness.run("새 과제")
            self.assertEqual(len(backend.last_negative_examples), 1)
            self.assertEqual(
                backend.last_negative_examples[0].case_id,
                report.case_id,
            )
            event_types = [
                json.loads(line)["event_type"]
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn("negative_example_context_applied", event_types)

            with self.assertRaises(ValueError):
                ledger.approve_negative_example(
                    case_id=report.case_id,
                    readiness_id=readiness_id,
                    actor_id="user",
                    reason="중복 승인",
                )

    def test_tampered_activation_without_readiness_is_rejected(self) -> None:
        backend = ScriptedBackend(
            jurisdictions={"logic_reviewer": True},
            verdicts={"logic_reviewer": "pass_to_next_gate"},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(
                backend,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER]),
            )
            report = harness.run_adversary("검토 대상")
            ledger = CaseLedger(log_path)
            state = ledger.confirm(
                case_id=report.case_id,
                new_status="confirmed",
                actor_type="human",
                actor_id="user",
                evidence="숨은 결함 확인",
                reason="독립 근거 부재",
            )
            EventLog(log_path).append(
                "negative_example_activation_approved",
                {
                    "case_id": report.case_id,
                    "readiness_id": "missing-readiness",
                    "actor_id": "tampered",
                    "reason": "원장 수동 변조",
                    "source_event_id": state.source_event_id,
                    "block_rule": "변조 규칙",
                    "negative_example_status": "active_approved",
                    "negative_example_activated": True,
                },
            )
            with self.assertRaises(ValueError):
                ledger.active_negative_examples()

    def test_conflict_writes_external_appeal_document(self) -> None:
        second_logic = ReviewerSpec(
            reviewer_id="logic_reviewer_2",
            aspect="logic",
            description="두 번째 논리 검사",
            instructions="독립적으로 논리를 검사한다.",
            dependency="dependent_core",
        )
        backend = ScriptedBackend(
            jurisdictions={
                "logic_reviewer": True,
                "logic_reviewer_2": True,
            },
            verdicts={
                "logic_reviewer": "pass_to_next_gate",
                "logic_reviewer_2": "reject",
            },
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness_instance = Harness(
                backend,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER, second_logic]),
                reviewer_ids=["logic_reviewer", "logic_reviewer_2"],
            )
            candidate, batch = harness_instance.run("재심 대상")

            self.assertEqual(batch.status, "conflict")
            assert harness_instance.last_gate_flow is not None
            self.assertEqual(
                harness_instance.last_gate_flow.status,
                "awaiting_human_review",
            )
            packet = harness_instance.last_appeal_packet
            self.assertIsNotNone(packet)
            assert packet is not None
            self.assertEqual(packet.trigger, "reviewer_conflict")
            self.assertEqual(packet.candidate_id, candidate.candidate_id)
            document = Path(packet.document_path)
            self.assertTrue(document.exists())
            text = document.read_text(encoding="utf-8")
            self.assertIn("외부 재심관", text)
            self.assertIn("requires_human_or_tool_confirmation", text)

    def test_appeal_overturn_is_second_opinion_not_case_confirmation(self) -> None:
        second_logic = ReviewerSpec(
            reviewer_id="logic_reviewer_2",
            aspect="logic",
            description="두 번째 논리 검사",
            instructions="독립적으로 논리를 검사한다.",
            dependency="dependent_core",
        )
        backend = ScriptedBackend(
            jurisdictions={
                "logic_reviewer": True,
                "logic_reviewer_2": True,
            },
            verdicts={
                "logic_reviewer": "pass_to_next_gate",
                "logic_reviewer_2": "reject",
            },
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness_instance = Harness(
                backend,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER, second_logic]),
                reviewer_ids=["logic_reviewer", "logic_reviewer_2"],
            )
            candidate, _ = harness_instance.run("재심 대상")
            packet = harness_instance.last_appeal_packet
            assert packet is not None
            event = AppealService(log_path).import_result(
                appeal_id=packet.appeal_id,
                candidate_id=candidate.candidate_id,
                verdict="overturn",
                actor_id="user",
                defects=[
                    {
                        "type": "순환논증",
                        "where": "핵심 결론",
                        "why": "결론을 전제로 재사용함",
                    }
                ],
                feedback_to_thesis="결론과 독립된 근거를 요구한다.",
            )

            payload = event["payload"]
            self.assertTrue(payload["requires_human_or_tool_confirmation"])
            self.assertTrue(payload["case_id"])
            case_state = CaseLedger(log_path).get(payload["case_id"])
            self.assertEqual(case_state.confirmation_status, "unconfirmed")
            self.assertEqual(
                case_state.report["disposition"],
                "appeal_overturn_candidate",
            )
            confirmed = CaseLedger(log_path).confirm(
                case_id=payload["case_id"],
                new_status="confirmed",
                actor_type="human",
                actor_id="user",
                evidence="재심 결함을 원문과 대조해 독립 확인",
                reason="순환논증이 실제로 존재함",
            )
            self.assertEqual(confirmed.confirmation_status, "confirmed")
            self.assertFalse(confirmed.negative_example_activated)
            readiness = CaseLedger(log_path).record_feedback_readiness(
                actor_type="human",
                actor_id="user",
                scope="external appeal feedback",
                evidence="확정된 외부 재심 사건을 검토함",
                reason="되먹임 가능성 확인",
            )
            activated = CaseLedger(log_path).approve_negative_example(
                case_id=payload["case_id"],
                readiness_id=readiness["payload"]["readiness_id"],
                actor_id="user",
                reason="명시적 Block-rule 활성 승인",
            )
            self.assertTrue(activated.negative_example_activated)
            rules = CaseLedger(log_path).active_negative_examples()
            self.assertEqual(len(rules), 1)
            self.assertEqual(
                rules[0].block_rule,
                "결론과 독립된 근거를 요구한다.",
            )
            event_types = [
                json.loads(line)["event_type"]
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn("appeal_overturn_case_reported", event_types)
            self.assertIn("case_confirmation_recorded", event_types)
            self.assertIn("negative_example_activation_approved", event_types)
            with self.assertRaises(ValueError):
                AppealService(log_path).import_result(
                    appeal_id=packet.appeal_id,
                    candidate_id=candidate.candidate_id,
                    verdict="uphold",
                    actor_id="user",
                )

    def test_non_overturn_appeal_does_not_create_case_candidate(self) -> None:
        second_logic = ReviewerSpec(
            reviewer_id="logic_reviewer_2",
            aspect="logic",
            description="두 번째 논리 검사",
            instructions="독립적으로 논리를 검사한다.",
            dependency="dependent_core",
        )
        backend = ScriptedBackend(
            jurisdictions={
                "logic_reviewer": True,
                "logic_reviewer_2": True,
            },
            verdicts={
                "logic_reviewer": "pass_to_next_gate",
                "logic_reviewer_2": "reject",
            },
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness_instance = Harness(
                backend,
                log_path,
                registry=ReviewerRegistry([LOGIC_REVIEWER, second_logic]),
                reviewer_ids=["logic_reviewer", "logic_reviewer_2"],
            )
            candidate, _ = harness_instance.run("유지 재심")
            packet = harness_instance.last_appeal_packet
            assert packet is not None
            event = AppealService(log_path).import_result(
                appeal_id=packet.appeal_id,
                candidate_id=candidate.candidate_id,
                verdict="uphold",
                actor_id="user",
            )
            self.assertEqual(event["payload"]["case_id"], "")
            event_types = [
                json.loads(line)["event_type"]
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertNotIn("appeal_overturn_case_reported", event_types)

    def test_tampered_appeal_case_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            EventLog(log_path).append(
                "appeal_overturn_case_reported",
                {
                    "case_id": "appeal-overturn-case-tampered",
                    "task_id": "task-1",
                    "candidate": {
                        "candidate_id": "candidate-1",
                        "task_id": "task-1",
                        "text": "후보",
                    },
                    "review_batch": {"reviews": []},
                    "appeal_result": {},
                    "disposition": "appeal_overturn_candidate",
                    "confirmation_status": "unconfirmed",
                    "negative_example_status": "shadow_unconfirmed",
                    "negative_example_activated": False,
                    "source_appeal_id": "appeal-missing",
                    "source_appeal_result_event_id": "event-missing",
                },
            )
            with self.assertRaises(ValueError):
                CaseLedger(log_path).get("appeal-overturn-case-tampered")

    def test_clear_review_does_not_create_appeal_packet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            harness_instance = Harness(
                MockBackend(),
                Path(temp_dir) / "events.jsonl",
            )
            harness_instance.run("정상 후보")
            self.assertIsNone(harness_instance.last_appeal_packet)


if __name__ == "__main__":
    unittest.main()
