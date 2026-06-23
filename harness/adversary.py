from __future__ import annotations

from uuid import uuid4

from harness.backends import Backend
from harness.models import Candidate, FilterEscapeCaseReport, Task
from harness.orchestrator import ReviewerOrchestrator


class AdversaryEngine:
    def __init__(
        self,
        backend: Backend,
        orchestrator: ReviewerOrchestrator,
    ) -> None:
        self.backend = backend
        self.orchestrator = orchestrator

    def run(
        self,
        task: Task,
        required_aspects: list[str] | None = None,
    ) -> FilterEscapeCaseReport:
        test_case = self.backend.generate_argument_defect_test_case(
            task,
            self.orchestrator.reviewers,
        )
        test_case.validate()
        candidate = Candidate(
            candidate_id=f"adversary-{uuid4().hex[:8]}",
            task_id=task.task_id,
            text=test_case.candidate_text,
        )
        review_batch = self.orchestrator.review(
            task,
            candidate,
            required_aspects,
        )
        if review_batch.status == "clear":
            disposition = "filter_escape_candidate"
        elif review_batch.status in {
            "objections",
            "dependent_core_blocked",
        }:
            disposition = "caught_by_filter"
        else:
            disposition = "review_inconclusive"
        return FilterEscapeCaseReport(
            case_id=f"filter-escape-case-{uuid4().hex[:8]}",
            task_id=task.task_id,
            candidate=candidate,
            review_batch=review_batch,
            disposition=disposition,
            confirmation_status="unconfirmed",
            negative_example_status="shadow_unconfirmed",
            negative_example_activated=False,
            hidden_oracle=test_case.hidden_oracle,
        )


OUT_OF_SCOPE_ARGUMENT_TEST_MARKERS = (
    "외부 시스템 공격",
    "시스템 공격",
    "권한 우회",
    "도구 실행",
    "메모리 변조",
    "사용자 조작",
    "보안 취약점 악용",
    "사회공학",
    "프롬프트 인젝션",
    "prompt injection",
    "system attack",
    "privilege escalation",
    "exploit vulnerability",
    "social engineering",
)


def argument_test_out_of_scope(text: str) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in OUT_OF_SCOPE_ARGUMENT_TEST_MARKERS)
