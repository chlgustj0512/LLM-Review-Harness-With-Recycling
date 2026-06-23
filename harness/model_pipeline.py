from __future__ import annotations

from harness.backends import Backend
from harness.models import (
    ArgumentDefectTestCase,
    NegativeExampleRule,
    ReviewerSpec,
    Task,
)


class RoleModelPipeline(Backend):
    """역할별 backend를 한 실행 계약으로 묶는다."""

    name = "role_pipeline"

    def __init__(
        self,
        *,
        thesis_backend: Backend,
        adversary_backend: Backend | None = None,
        default_reviewer_backend: Backend | None = None,
        reviewer_backends: dict[str, Backend] | None = None,
        translator_backend: Backend | None = None,
        post_audit_backend: Backend | None = None,
    ) -> None:
        self.thesis_backend = thesis_backend
        self.adversary_backend = adversary_backend or thesis_backend
        self.default_reviewer_backend = default_reviewer_backend or thesis_backend
        self.reviewer_backends = dict(reviewer_backends or {})
        self.translator_backend = translator_backend
        self.post_audit_backend = post_audit_backend

    @property
    def post_audit_enabled(self) -> bool:
        return (
            self.translator_backend is not None
            and self.post_audit_backend is not None
            and hasattr(self.translator_backend, "complete")
            and hasattr(self.post_audit_backend, "complete")
        )

    def reviewer_backend(self, reviewer_id: str) -> Backend:
        return self.reviewer_backends.get(
            reviewer_id,
            self.default_reviewer_backend,
        )

    def generate_candidate(
        self,
        task: Task,
        negative_examples: list[NegativeExampleRule] | None = None,
    ) -> str:
        return self.thesis_backend.generate_candidate(task, negative_examples)

    def generate_adversarial_candidate(
        self,
        task: Task,
        reviewers: list[ReviewerSpec],
    ) -> str:
        return self.adversary_backend.generate_adversarial_candidate(task, reviewers)

    def generate_argument_defect_test_case(
        self,
        task: Task,
        reviewers: list[ReviewerSpec],
    ) -> ArgumentDefectTestCase:
        return self.adversary_backend.generate_argument_defect_test_case(
            task,
            reviewers,
        )

    def assess_jurisdiction(
        self,
        task: Task,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict:
        return self.reviewer_backend(reviewer.reviewer_id).assess_jurisdiction(
            task,
            candidate_text,
            reviewer,
        )

    def review_candidate(
        self,
        task: Task,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict:
        return self.reviewer_backend(reviewer.reviewer_id).review_candidate(
            task,
            candidate_text,
            reviewer,
        )
