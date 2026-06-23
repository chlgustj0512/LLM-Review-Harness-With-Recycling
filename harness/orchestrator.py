from __future__ import annotations

from harness.backends import Backend
from harness.models import (
    Candidate,
    derive_review_batch_state,
    JurisdictionResult,
    Review,
    ReviewBatch,
    ReviewerSpec,
    Task,
)


class ReviewerOrchestrator:
    def __init__(self, backend: Backend, reviewers: list[ReviewerSpec]) -> None:
        if not reviewers:
            raise ValueError("심사관이 한 명 이상 필요합니다.")
        self.backend = backend
        self.reviewers = list(reviewers)

    def review(
        self,
        task: Task,
        candidate: Candidate,
        required_aspects: list[str] | None = None,
    ) -> ReviewBatch:
        required = _unique(required_aspects or ["logic"])
        jurisdictions: list[JurisdictionResult] = []
        reviews: list[Review] = []

        # 설계서의 순차 로드 원칙에 맞춰 등록 순서대로 한 명씩 실행한다.
        for reviewer in self.reviewers:
            raw_jurisdiction = self.backend.assess_jurisdiction(
                task,
                candidate.text,
                reviewer,
            )
            jurisdiction = JurisdictionResult.from_dict(raw_jurisdiction, reviewer)
            jurisdictions.append(jurisdiction)
            if not jurisdiction.applicable:
                continue

            raw_review = self.backend.review_candidate(
                task,
                candidate.text,
                reviewer,
            )
            reviews.append(Review.from_dict(raw_review, candidate.candidate_id, reviewer))

        derived = derive_review_batch_state(
            required_aspects=required,
            jurisdictions=jurisdictions,
            reviews=reviews,
        )
        batch = ReviewBatch(
            candidate_id=candidate.candidate_id,
            required_aspects=derived["required_aspects"],
            jurisdictions=jurisdictions,
            reviews=reviews,
            empty_aspects=derived["empty_aspects"],
            conflicting_aspects=derived["conflicting_aspects"],
            dependent_core_blocked=derived["dependent_core_blocked"],
            status=derived["status"],
        )
        batch.validate()
        return batch


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in items if item.strip()))
