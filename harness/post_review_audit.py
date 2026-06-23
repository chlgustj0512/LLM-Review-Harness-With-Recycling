from __future__ import annotations

from typing import Any, Protocol
from uuid import uuid4

from harness.backends import REVIEW_JSON_SCHEMA, _extract_json_object
from harness.event_contracts import EventContractValidator
from harness.logging import EventLog
from harness.models import (
    Candidate,
    PostReviewAuditReport,
    Task,
    validate_review_semantics,
)
from harness.prompts import (
    audit_report_translation_prompt,
    boundary_translation_prompt,
    post_review_audit_prompt,
)


class CompletionModel(Protocol):
    model: str

    def complete(
        self,
        prompt: str,
        *,
        output_format: str | dict[str, Any] | None = None,
    ) -> str: ...


class PostReviewAuditService:
    """정상 Gate와 독립된 비차단 영어 사후 감사 배관."""

    def __init__(
        self,
        *,
        translator: CompletionModel,
        auditor: CompletionModel,
        events: EventLog,
    ) -> None:
        self.translator = translator
        self.auditor = auditor
        self.events = events
        self.contracts = EventContractValidator(events.path)

    def audit(
        self,
        *,
        task: Task,
        candidate: Candidate,
        source_review_event_id: str,
    ) -> PostReviewAuditReport:
        audit_id = f"post-audit-{uuid4().hex[:8]}"
        try:
            self._validate_source(
                candidate=candidate,
                source_review_event_id=source_review_event_id,
            )
            english_candidate = self.translator.complete(
                boundary_translation_prompt(candidate.text)
            ).strip()
            if not english_candidate:
                raise ValueError("영어 정규화본이 비어 있습니다.")
            translation_payload = {
                    "audit_id": audit_id,
                    "task_id": task.task_id,
                    "candidate_id": candidate.candidate_id,
                    "source_review_event_id": source_review_event_id,
                    "source_language": "ko",
                    "target_language": "en",
                    "source_text": candidate.text,
                    "translated_text": english_candidate,
                    "translator_model": self.translator.model,
                }
            self.contracts.validate_candidate_translation(translation_payload)
            translation_event = self.events.append(
                "candidate_translation_recorded",
                translation_payload,
            )
            raw_review = _extract_json_object(
                self.auditor.complete(
                    post_review_audit_prompt(english_candidate),
                    output_format=REVIEW_JSON_SCHEMA,
                )
            )
            validate_review_semantics(raw_review)
            defect_found = bool(raw_review["defect_found"])
            korean_report = ""
            if defect_found:
                korean_report = self.translator.complete(
                    audit_report_translation_prompt(
                        korean_source=candidate.text,
                        english_candidate=english_candidate,
                        defect_type=str(raw_review["defect_type"]),
                        defect_where=str(raw_review["defect_where"]),
                        reasoning=str(raw_review["reasoning"]),
                        required_revision=str(raw_review["required_revision"]),
                    )
                ).strip()
                if not korean_report:
                    raise ValueError("한국어 보강 보고서가 비어 있습니다.")

            report = PostReviewAuditReport(
                audit_id=audit_id,
                candidate_id=candidate.candidate_id,
                source_review_event_id=source_review_event_id,
                status="advisory" if defect_found else "clear",
                non_blocking=True,
                english_candidate=english_candidate,
                defect_found=defect_found,
                defect_type=str(raw_review["defect_type"]),
                defect_where=str(raw_review["defect_where"]),
                reasoning=str(raw_review["reasoning"]),
                required_revision=str(raw_review["required_revision"]),
                confidence=int(raw_review["confidence"]),
                korean_report=korean_report,
            )
            report.validate()
            audit_payload = {
                    **report.to_dict(),
                    "translation_event_id": translation_event["event_id"],
                    "auditor_model": self.auditor.model,
                }
            self.contracts.validate_post_review_audit(audit_payload)
            audit_event = self.events.append(
                "post_review_audit_completed",
                audit_payload,
            )
            if defect_found:
                advisory_payload = {
                    "audit_id": audit_id,
                    "candidate_id": candidate.candidate_id,
                    "source_audit_event_id": audit_event["event_id"],
                    "language": "ko",
                    "report": korean_report,
                    "non_blocking": True,
                }
                self.contracts.validate_post_review_advisory(advisory_payload)
                self.events.append(
                    "post_review_advisory_report_created",
                    advisory_payload,
                )
            return report
        except Exception as exc:
            report = PostReviewAuditReport(
                audit_id=audit_id,
                candidate_id=candidate.candidate_id,
                source_review_event_id=source_review_event_id,
                status="failed",
                non_blocking=True,
                english_candidate="",
                defect_found=False,
                defect_type="",
                defect_where="",
                reasoning="사후 감사를 완료하지 못했다.",
                required_revision="",
                confidence=0,
                korean_report="",
                error=str(exc),
            )
            report.validate()
            self.events.append("post_review_audit_failed", report.to_dict())
            return report

    def _validate_source(
        self,
        *,
        candidate: Candidate,
        source_review_event_id: str,
    ) -> None:
        event = self.contracts.event(
            source_review_event_id,
            "review_batch_completed",
        )
        source_candidate_id = str(
            event.get("payload", {}).get("candidate_id", "")
        ).strip()
        if source_candidate_id != candidate.candidate_id:
            raise ValueError(
                "사후 감사 source Review와 candidate가 일치하지 않습니다."
            )
