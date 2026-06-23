from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Sequence

Verdict = Literal[
    "reject",
    "revise",
    "pass_to_next_gate",
    "needs_human_review",
]
AspectDependency = Literal["independent", "dependent_core"]
ReviewStatus = Literal[
    "clear",
    "objections",
    "dependent_core_blocked",
    "conflict",
    "empty_aspect",
    "human_review",
]
AdversaryDisposition = Literal[
    "caught_by_filter",
    "filter_escape_candidate",
    "review_inconclusive",
]
ConfirmationStatus = Literal["unconfirmed", "confirmed", "dismissed"]
ConfirmationActorType = Literal["human", "tool"]
AppealVerdict = Literal["uphold", "overturn", "uncertain"]
GateDecision = Literal[
    "reject",
    "revise",
    "pass_to_next_gate",
    "accepted_synthesis",
    "needs_human_review",
]
GateFlowStatus = Literal[
    "awaiting_review",
    "awaiting_revision",
    "awaiting_human_review",
    "terminated_rejected",
    "completed_accepted",
]
LibraryVerificationStatus = Literal[
    "preserved_verified",
    "salvaged_unverified",
]
RelativeChange = Literal[
    "improved",
    "no_meaningful_change",
    "regressed",
]
MetagameStatus = Literal["active", "deprecated"]


def validate_review_semantics(raw: dict[str, Any]) -> None:
    """Review 판정과 결함 필드 사이의 의미 계약을 검증한다."""
    verdict = str(raw.get("verdict", "")).strip()
    allowed = {
        "reject",
        "revise",
        "pass_to_next_gate",
        "needs_human_review",
    }
    if verdict not in allowed:
        raise ValueError(f"지원하지 않는 verdict: {verdict!r}")

    defect_found = raw.get("defect_found")
    if not isinstance(defect_found, bool):
        raise ValueError("defect_found는 boolean이어야 합니다.")
    if verdict in {"reject", "revise"} and not defect_found:
        raise ValueError(f"{verdict} 판정은 defect_found=true여야 합니다.")
    if verdict == "pass_to_next_gate" and defect_found:
        raise ValueError("결함을 발견한 후보를 pass_to_next_gate로 판정할 수 없습니다.")

    defect_type = str(raw.get("defect_type", "")).strip()
    defect_where = str(raw.get("defect_where", "")).strip()
    if defect_found:
        if not defect_type:
            raise ValueError("결함 발견 시 defect_type이 필요합니다.")
        if not defect_where:
            raise ValueError("결함 발견 시 defect_where가 필요합니다.")
    elif defect_type or defect_where:
        raise ValueError(
            "defect_found=false이면 defect_type과 defect_where는 비어 있어야 합니다."
        )

    reasoning = str(raw.get("reasoning", "")).strip()
    if not reasoning:
        raise ValueError("reasoning이 비어 있습니다.")
    if verdict == "revise" and not str(
        raw.get("required_revision", "")
    ).strip():
        raise ValueError("revise 판정에는 required_revision이 필요합니다.")
    if str(raw.get("salvageable_part", "")).strip() and (
        not defect_found or verdict not in {"reject", "revise"}
    ):
        raise ValueError(
            "salvageable_part는 결함을 찾은 reject·revise 심사에서만 허용됩니다."
        )


def derive_review_batch_state(
    *,
    required_aspects: Sequence[str],
    jurisdictions: Sequence[Any],
    reviews: Sequence[Any],
) -> dict[str, Any]:
    """관할·개별 심사에서 ReviewBatch의 파생 상태를 계산한다."""
    required = list(
        dict.fromkeys(
            str(item).strip() for item in required_aspects if str(item).strip()
        )
    )
    if not required:
        raise ValueError("required_aspects가 하나 이상 필요합니다.")

    applicable_aspects: set[str] = set()
    applicable_reviewers: set[tuple[str, str]] = set()
    seen_jurisdiction_reviewers: set[str] = set()
    for index, jurisdiction in enumerate(jurisdictions):
        reviewer = str(_field(jurisdiction, "reviewer", "")).strip()
        aspect = str(_field(jurisdiction, "aspect", "")).strip()
        applicable = _field(jurisdiction, "applicable")
        if not reviewer or not aspect or not isinstance(applicable, bool):
            raise ValueError(f"jurisdiction 계약 위반: index {index}")
        if reviewer in seen_jurisdiction_reviewers:
            raise ValueError(f"중복 reviewer 관할 판정입니다: {reviewer}")
        seen_jurisdiction_reviewers.add(reviewer)
        if applicable:
            applicable_aspects.add(aspect)
            applicable_reviewers.add((reviewer, aspect))

    verdict_groups: dict[str, set[str]] = {}
    dependent_core_blocked: set[str] = set()
    has_human_review = False
    has_objection = False
    seen_reviewers: set[str] = set()
    reviewed_assignments: set[tuple[str, str]] = set()
    for index, review in enumerate(reviews):
        raw_review = (
            review if isinstance(review, dict) else asdict(review)
        )
        validate_review_semantics(raw_review)
        reviewer = str(_field(review, "reviewer", "")).strip()
        aspect = str(_field(review, "aspect", "")).strip()
        dependency = str(_field(review, "dependency", "")).strip()
        verdict = str(_field(review, "verdict", "")).strip()
        if not reviewer or not aspect:
            raise ValueError(f"review 담당자·측면이 비어 있습니다: index {index}")
        if reviewer in seen_reviewers:
            raise ValueError(f"중복 reviewer 심사입니다: {reviewer}")
        seen_reviewers.add(reviewer)
        if (reviewer, aspect) not in applicable_reviewers:
            raise ValueError(
                f"관할 적용되지 않은 reviewer의 심사입니다: {reviewer}/{aspect}"
            )
        reviewed_assignments.add((reviewer, aspect))
        if dependency not in {"independent", "dependent_core"}:
            raise ValueError(f"유효하지 않은 review dependency: {dependency}")

        group = (
            "pass"
            if verdict == "pass_to_next_gate"
            else "human"
            if verdict == "needs_human_review"
            else "object"
        )
        verdict_groups.setdefault(aspect, set()).add(group)
        has_human_review = has_human_review or group == "human"
        has_objection = has_objection or group == "object"
        if dependency == "dependent_core" and group == "object":
            dependent_core_blocked.add(aspect)

    if reviewed_assignments != applicable_reviewers:
        missing = sorted(applicable_reviewers - reviewed_assignments)
        raise ValueError(f"적용 관할의 Review가 누락됐습니다: {missing}")

    empty_aspects = sorted(set(required) - applicable_aspects)
    conflicting_aspects = sorted(
        aspect
        for aspect, groups in verdict_groups.items()
        if "pass" in groups and ("object" in groups or "human" in groups)
    )
    blocked = sorted(dependent_core_blocked)
    if conflicting_aspects:
        status = "conflict"
    elif empty_aspects:
        status = "empty_aspect"
    elif has_human_review:
        status = "human_review"
    elif blocked:
        status = "dependent_core_blocked"
    elif has_objection:
        status = "objections"
    else:
        status = "clear"
    return {
        "required_aspects": required,
        "empty_aspects": empty_aspects,
        "conflicting_aspects": conflicting_aspects,
        "dependent_core_blocked": blocked,
        "status": status,
    }


def validate_review_batch_semantics(raw: dict[str, Any]) -> None:
    """저장된 ReviewBatch 파생 필드가 원본 관할·심사와 같은지 검증한다."""
    candidate_id = str(raw.get("candidate_id", "")).strip()
    if not candidate_id:
        raise ValueError("ReviewBatch candidate_id가 비어 있습니다.")
    for key in (
        "required_aspects",
        "jurisdictions",
        "reviews",
        "empty_aspects",
        "conflicting_aspects",
        "dependent_core_blocked",
        "status",
    ):
        if key not in raw:
            raise ValueError(f"ReviewBatch 필수 필드가 없습니다: {key}")
    if not isinstance(raw["required_aspects"], list):
        raise ValueError("required_aspects는 배열이어야 합니다.")
    if not isinstance(raw["jurisdictions"], list):
        raise ValueError("jurisdictions는 배열이어야 합니다.")
    if not isinstance(raw["reviews"], list):
        raise ValueError("reviews는 배열이어야 합니다.")
    for index, review in enumerate(raw["reviews"]):
        if not isinstance(review, dict):
            raise ValueError(f"review 객체 오류: index {index}")
        if str(review.get("candidate_id", "")).strip() != candidate_id:
            raise ValueError(
                f"Review candidate_id 불일치: index {index}"
            )
    expected = derive_review_batch_state(
        required_aspects=raw["required_aspects"],
        jurisdictions=raw["jurisdictions"],
        reviews=raw["reviews"],
    )
    for key, value in expected.items():
        if raw.get(key) != value:
            raise ValueError(
                f"ReviewBatch 파생 상태 불일치: {key} "
                f"expected={value!r}, actual={raw.get(key)!r}"
            )


def _field(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


@dataclass(frozen=True)
class Task:
    task_id: str
    goal: str
    constraints: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    task_id: str
    text: str


ALLOWED_ARGUMENT_DEFECT_TYPES = {
    "correlation_causation",
    "circular_reasoning",
    "hidden_premise",
    "hasty_generalization",
    "false_analogy",
    "equivocation",
    "necessary_sufficient_confusion",
    "quantifier_error",
}


@dataclass(frozen=True)
class ArgumentDefectOracle:
    defect_type: str
    defect_where: str
    explanation: str
    detection_point: str
    expected_verdict: str

    def validate(self) -> None:
        if self.defect_type not in ALLOWED_ARGUMENT_DEFECT_TYPES:
            raise ValueError(
                f"허용되지 않은 논증 결함 유형입니다: {self.defect_type}"
            )
        if self.expected_verdict not in {"REJECT", "REVISE"}:
            raise ValueError(
                "논증 결함 테스트의 expected_verdict는 REJECT 또는 REVISE여야 합니다."
            )
        for key, value in asdict(self).items():
            if not str(value).strip():
                raise ValueError(f"hidden_oracle의 {key}가 비어 있습니다.")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class ArgumentDefectTestCase:
    candidate_text: str
    hidden_oracle: ArgumentDefectOracle

    def validate(self) -> None:
        if not self.candidate_text.strip():
            raise ValueError("논증 결함 테스트 candidate_text가 비어 있습니다.")
        self.hidden_oracle.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "candidate_text": self.candidate_text,
            "hidden_oracle": self.hidden_oracle.to_dict(),
        }


@dataclass(frozen=True)
class ReviewerSpec:
    reviewer_id: str
    aspect: str
    description: str
    instructions: str
    dependency: AspectDependency


@dataclass(frozen=True)
class JurisdictionResult:
    reviewer: str
    aspect: str
    applicable: bool
    reasoning: str
    confidence: int

    @classmethod
    def from_dict(
        cls,
        raw: dict[str, Any],
        reviewer: ReviewerSpec,
    ) -> "JurisdictionResult":
        applicable = raw.get("applicable")
        if not isinstance(applicable, bool):
            raise ValueError("applicable은 boolean이어야 합니다.")
        confidence = int(raw.get("confidence", 0))
        if not 0 <= confidence <= 100:
            raise ValueError("관할 confidence는 0~100이어야 합니다.")
        reasoning = str(raw.get("reasoning", "")).strip()
        if not reasoning:
            raise ValueError("관할 reasoning이 비어 있습니다.")
        return cls(
            reviewer=reviewer.reviewer_id,
            aspect=reviewer.aspect,
            applicable=applicable,
            reasoning=reasoning,
            confidence=confidence,
        )


@dataclass(frozen=True)
class Review:
    candidate_id: str
    reviewer: str
    aspect: str
    dependency: AspectDependency
    verdict: Verdict
    defect_found: bool
    defect_type: str
    defect_where: str
    reasoning: str
    required_revision: str
    confidence: int
    feedback_to_thesis: str
    salvageable_part: str

    @classmethod
    def from_dict(
        cls,
        raw: dict[str, Any],
        candidate_id: str,
        reviewer: ReviewerSpec,
    ) -> "Review":
        validate_review_semantics(raw)
        verdict = str(raw.get("verdict", "")).strip()

        confidence = int(raw.get("confidence", 0))
        if not 0 <= confidence <= 100:
            raise ValueError("confidence는 0~100이어야 합니다.")

        defect_found = raw.get("defect_found")
        assert isinstance(defect_found, bool)

        review = cls(
            candidate_id=candidate_id,
            reviewer=reviewer.reviewer_id,
            aspect=reviewer.aspect,
            dependency=reviewer.dependency,
            verdict=verdict,  # type: ignore[arg-type]
            defect_found=defect_found,
            defect_type=str(raw.get("defect_type", "")),
            defect_where=str(raw.get("defect_where", "")),
            reasoning=str(raw.get("reasoning", "")),
            required_revision=str(raw.get("required_revision", "")),
            confidence=confidence,
            feedback_to_thesis=str(raw.get("feedback_to_thesis", "")),
            salvageable_part=str(raw.get("salvageable_part", "")),
        )
        review.validate()
        return review

    def validate(self) -> None:
        validate_review_semantics(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReviewBatch:
    candidate_id: str
    required_aspects: list[str]
    jurisdictions: list[JurisdictionResult]
    reviews: list[Review]
    empty_aspects: list[str]
    conflicting_aspects: list[str]
    dependent_core_blocked: list[str]
    status: ReviewStatus

    def validate(self) -> None:
        validate_review_batch_semantics(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "required_aspects": self.required_aspects,
            "jurisdictions": [asdict(item) for item in self.jurisdictions],
            "reviews": [item.to_dict() for item in self.reviews],
            "empty_aspects": self.empty_aspects,
            "conflicting_aspects": self.conflicting_aspects,
            "dependent_core_blocked": self.dependent_core_blocked,
            "status": self.status,
            "gate_decision": None,
        }


@dataclass(frozen=True)
class FilterEscapeCaseReport:
    case_id: str
    task_id: str
    candidate: Candidate
    review_batch: ReviewBatch
    disposition: AdversaryDisposition
    confirmation_status: ConfirmationStatus
    negative_example_status: str
    negative_example_activated: bool
    hidden_oracle: ArgumentDefectOracle

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "task_id": self.task_id,
            "candidate": asdict(self.candidate),
            "review_batch": self.review_batch.to_dict(),
            "disposition": self.disposition,
            "confirmation_status": self.confirmation_status,
            "negative_example_status": self.negative_example_status,
            "negative_example_activated": self.negative_example_activated,
            "hidden_oracle": self.hidden_oracle.to_dict(),
        }


@dataclass(frozen=True)
class PostReviewAuditReport:
    audit_id: str
    candidate_id: str
    source_review_event_id: str
    status: str
    non_blocking: bool
    english_candidate: str
    defect_found: bool
    defect_type: str
    defect_where: str
    reasoning: str
    required_revision: str
    confidence: int
    korean_report: str
    error: str = ""

    def validate(self) -> None:
        if self.status not in {"clear", "advisory", "failed"}:
            raise ValueError(f"유효하지 않은 사후 감사 상태입니다: {self.status}")
        if not self.non_blocking:
            raise ValueError("사후 감사는 Gate를 차단할 수 없습니다.")
        if self.status == "advisory" and not self.defect_found:
            raise ValueError("advisory 감사는 defect_found=true여야 합니다.")
        if self.status == "clear" and self.defect_found:
            raise ValueError("clear 감사는 defect_found=false여야 합니다.")
        if self.defect_found and (
            not self.defect_type.strip() or not self.defect_where.strip()
        ):
            raise ValueError("감사 결함 발견 시 유형과 위치가 필요합니다.")
        if self.status == "advisory" and not self.korean_report.strip():
            raise ValueError("advisory 감사에는 한국어 보강 보고서가 필요합니다.")
        if self.status == "failed" and not self.error.strip():
            raise ValueError("failed 감사에는 오류 설명이 필요합니다.")
        if not 0 <= self.confidence <= 100:
            raise ValueError("감사 confidence는 0~100이어야 합니다.")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class FinalDeliveryPacket:
    delivery_id: str
    flow_id: str
    task_id: str
    candidate_id: str
    source_gate_decision_event_id: str
    source_review_event_id: str
    source_final_audit_event_id: str
    status: str
    korean_final_text: str
    review_status: str
    review_summary: list[dict[str, Any]]
    audit_status: str
    audit_advisory_korean: str
    audit_error: str
    json_path: str
    markdown_path: str

    def validate(self) -> None:
        if self.status not in {
            "ready_clear",
            "ready_with_advisory",
            "ready_audit_failed",
        }:
            raise ValueError(f"유효하지 않은 최종 제출 상태입니다: {self.status}")
        for key in (
            "delivery_id",
            "flow_id",
            "task_id",
            "candidate_id",
            "source_gate_decision_event_id",
            "source_review_event_id",
            "source_final_audit_event_id",
            "korean_final_text",
            "review_status",
            "json_path",
            "markdown_path",
        ):
            if not str(getattr(self, key)).strip():
                raise ValueError(f"최종 제출 묶음의 {key}가 비어 있습니다.")
        if self.status == "ready_with_advisory" and not (
            self.audit_status == "advisory"
            and self.audit_advisory_korean.strip()
        ):
            raise ValueError("보강 제출 묶음에는 한국어 감사 보고서가 필요합니다.")
        if self.status == "ready_clear" and self.audit_status != "clear":
            raise ValueError("감사 clear가 아닌 묶음을 ready_clear로 만들 수 없습니다.")
        if self.status == "ready_audit_failed" and not (
            self.audit_status == "failed" and self.audit_error.strip()
        ):
            raise ValueError("감사 실패 제출 묶음에는 오류 설명이 필요합니다.")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class CaseConfirmationEvent:
    case_id: str
    previous_status: ConfirmationStatus
    new_status: ConfirmationStatus
    actor_type: ConfirmationActorType
    actor_id: str
    evidence: str
    reason: str
    source_event_id: str
    negative_example_status: str
    negative_example_activated: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FeedbackReadinessEvent:
    readiness_id: str
    actor_type: ConfirmationActorType
    actor_id: str
    scope: str
    evidence: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NegativeExampleActivationEvent:
    case_id: str
    readiness_id: str
    actor_id: str
    reason: str
    source_event_id: str
    block_rule: str
    negative_example_status: str
    negative_example_activated: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NegativeExampleRule:
    case_id: str
    block_rule: str
    source_event_id: str
    readiness_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AppealPacket:
    appeal_id: str
    candidate_id: str
    task_id: str
    trigger: str
    domain: str
    priority_line: str
    task_goal: str
    constraints: list[str]
    candidate_text: str
    first_review: dict[str, Any]
    hard_checks: list[str]
    suspicion: str
    question: str
    document_path: str
    gate_flow_id: str = ""
    source_review_event_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AppealResultEvent:
    appeal_id: str
    candidate_id: str
    reviewer: str
    verdict: AppealVerdict
    defects: list[dict[str, str]]
    salvageable_part: str
    feedback_to_thesis: str
    actor_id: str
    source_event_id: str
    requires_human_or_tool_confirmation: bool
    case_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GateFlowState:
    flow_id: str
    task_id: str
    current_candidate_id: str
    stage: int
    status: GateFlowStatus
    source_review_event_id: str
    history: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GateDecisionEvent:
    flow_id: str
    task_id: str
    candidate_id: str
    stage: int
    decision: GateDecision
    previous_status: GateFlowStatus
    next_status: GateFlowStatus
    next_stage: int
    actor_type: ConfirmationActorType
    actor_id: str
    reason: str
    source_review_event_id: str
    source_review_status: str
    appeal_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GateRevisionEvent:
    flow_id: str
    previous_candidate_id: str
    revised_candidate_id: str
    source_review_event_id: str
    next_status: GateFlowStatus
    stage: int
    actor_id: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LibraryPart:
    part_id: str
    content: str
    premises: list[str]
    verification_context: str
    works_when: list[str]
    fails_when: list[str]
    purpose: str
    purpose_status: str
    verification_status: LibraryVerificationStatus
    source_event_id: str
    source_candidate_id: str
    created_by: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PurposeApprovalEvent:
    part_id: str
    previous_status: str
    new_status: str
    actor_type: ConfirmationActorType
    actor_id: str
    reason: str
    source_event_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LibraryMatch:
    part: LibraryPart
    purpose_matched: bool
    conditions_matched: bool
    matched_conditions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "part": self.part.to_dict(),
            "purpose_matched": self.purpose_matched,
            "conditions_matched": self.conditions_matched,
            "matched_conditions": self.matched_conditions,
        }


@dataclass(frozen=True)
class RatchetSessionState:
    session_id: str
    purpose: str
    priority_line: list[str]
    scope_task_id: str
    scope_goal: str
    scope_constraints: list[str]
    overall_champion_candidate_id: str
    aspect_champions: dict[str, str]
    admitted_candidate_ids: list[str]
    pending_candidate_id: str
    pending_comparisons: dict[str, str]
    history: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RatchetComparisonEvent:
    session_id: str
    candidate_id: str
    aspect: str
    baseline_candidate_id: str
    result: RelativeChange
    actor_type: ConfirmationActorType
    actor_id: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChampionSnapshot:
    snapshot_id: str
    session_id: str
    purpose: str
    priority_line: list[str]
    overall_champion_candidate_id: str
    aspect_champions: dict[str, str]
    status: MetagameStatus
    source_finalize_event_id: str
    termination_reason: str
    history: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MetagameTransitionEvent:
    snapshot_id: str
    previous_status: MetagameStatus
    new_status: MetagameStatus
    actor_type: ConfirmationActorType
    actor_id: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CaseState:
    report: dict[str, Any]
    source_event_id: str
    confirmation_status: ConfirmationStatus
    negative_example_status: str
    negative_example_activated: bool
    confirmation_events: list[dict[str, Any]]
    activation_events: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Probe:
    probe_id: str
    domain: str
    candidate_text: str
    expected_defect: str
    description: str
    expected_detected: bool = True


@dataclass(frozen=True)
class ProbeResult:
    probe_id: str
    detected: bool
    expected_detected: bool
    correct: bool
    expected_defect: str
    detecting_reviewers: list[str]
    review_batch: ReviewBatch

    def to_dict(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "detected": self.detected,
            "expected_detected": self.expected_detected,
            "correct": self.correct,
            "expected_defect": self.expected_defect,
            "detecting_reviewers": self.detecting_reviewers,
            "review_batch": self.review_batch.to_dict(),
        }
