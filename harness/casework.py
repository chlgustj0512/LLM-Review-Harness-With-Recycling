from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from harness.event_contracts import EventContractValidator
from harness.logging import EventLog
from harness.models import (
    CaseConfirmationEvent,
    CaseState,
    FeedbackReadinessEvent,
    NegativeExampleActivationEvent,
    NegativeExampleRule,
)


class CaseLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.events = EventLog(path)
        self.contracts = EventContractValidator(path)

    def get(self, case_id: str) -> CaseState:
        report: dict[str, Any] | None = None
        source_event_id = ""
        confirmations: list[dict[str, Any]] = []
        activations: list[dict[str, Any]] = []

        for index, event in enumerate(self._read_events()):
            payload = event.get("payload", {})
            if event.get("event_type") in {
                "filter_escape_case_reported",
                "appeal_overturn_case_reported",
            }:
                if payload.get("case_id") == case_id:
                    if report is not None:
                        raise ValueError(f"중복 case report: {case_id}")
                    if event.get("event_type") == "appeal_overturn_case_reported":
                        self._validate_appeal_case_source(payload)
                    report = payload
                    source_event_id = str(
                        event.get("event_id") or f"legacy-event-{index}"
                    )
            elif event.get("event_type") == "case_confirmation_recorded":
                if payload.get("case_id") == case_id:
                    confirmations.append(payload)
            elif event.get("event_type") == "negative_example_activation_approved":
                if payload.get("case_id") == case_id:
                    activations.append(payload)

        if report is None:
            raise ValueError(f"case를 찾을 수 없습니다: {case_id}")
        report = self._normalize_legacy_adversary_disposition(report)

        status = str(report.get("confirmation_status", "unconfirmed"))
        negative_status = str(
            report.get("negative_example_status", "shadow_unconfirmed")
        )
        activated = bool(report.get("negative_example_activated", False))
        for event in confirmations:
            self.contracts.validate_case_confirmation(
                event,
                case_id=case_id,
                previous_status=status,
                source_event_id=source_event_id,
            )
            previous = str(event.get("previous_status", ""))
            if previous != status:
                raise ValueError(
                    f"case 상태 이력이 불연속입니다: expected={status}, event={previous}"
                )
            status = str(event["new_status"])
            negative_status = str(event["negative_example_status"])
            activated = bool(event["negative_example_activated"])
        for event in activations:
            if status != "confirmed":
                raise ValueError("확정되지 않은 case에 활성 승인 사건이 있습니다.")
            if activated:
                raise ValueError(f"중복 부정예시 활성 승인: {case_id}")
            expected_block_rule = self._derive_block_rule(
                CaseState(
                    report=report,
                    source_event_id=source_event_id,
                    confirmation_status=status,  # type: ignore[arg-type]
                    negative_example_status=negative_status,
                    negative_example_activated=activated,
                    confirmation_events=confirmations,
                    activation_events=[],
                )
            )
            self.contracts.validate_activation(
                event,
                case_id=case_id,
                source_event_id=source_event_id,
                expected_block_rule=expected_block_rule,
            )
            negative_status = str(event["negative_example_status"])
            activated = bool(event["negative_example_activated"])

        return CaseState(
            report=report,
            source_event_id=source_event_id,
            confirmation_status=status,  # type: ignore[arg-type]
            negative_example_status=negative_status,
            negative_example_activated=activated,
            confirmation_events=confirmations,
            activation_events=activations,
        )

    def confirm(
        self,
        *,
        case_id: str,
        new_status: str,
        actor_type: str,
        actor_id: str,
        evidence: str,
        reason: str,
    ) -> CaseState:
        state = self.get(case_id)
        if state.confirmation_status != "unconfirmed":
            raise ValueError(
                f"종료된 case 상태는 변경할 수 없습니다: {state.confirmation_status}"
            )
        if new_status not in {"confirmed", "dismissed"}:
            raise ValueError("new_status는 confirmed 또는 dismissed여야 합니다.")
        if actor_type not in {"human", "tool"}:
            raise ValueError("actor_type은 human 또는 tool이어야 합니다.")
        if not actor_id.strip():
            raise ValueError("actor_id가 필요합니다.")
        if not evidence.strip():
            raise ValueError("확인 evidence가 필요합니다.")
        if not reason.strip():
            raise ValueError("확인 reason이 필요합니다.")

        disposition = str(state.report.get("disposition", ""))
        if new_status == "confirmed" and disposition not in {
            "filter_escape_candidate",
            "appeal_overturn_candidate",
        }:
            raise ValueError(
                "필터 통과 또는 외부 재심 결함 후보만 confirmed로 승격할 수 있습니다."
            )

        negative_status = (
            "eligible_pending_approval"
            if new_status == "confirmed"
            else "ineligible_dismissed"
        )
        confirmation = CaseConfirmationEvent(
            case_id=case_id,
            previous_status="unconfirmed",
            new_status=new_status,  # type: ignore[arg-type]
            actor_type=actor_type,  # type: ignore[arg-type]
            actor_id=actor_id.strip(),
            evidence=evidence.strip(),
            reason=reason.strip(),
            source_event_id=state.source_event_id,
            negative_example_status=negative_status,
            negative_example_activated=False,
        )
        self.events.append("case_confirmation_recorded", confirmation.to_dict())
        self.events.append(
            "negative_example_activation_candidate_recorded",
            {
                "case_id": case_id,
                "confirmation_status": new_status,
                "status": negative_status,
                "activated": False,
                "source_event_id": state.source_event_id,
            },
        )
        return self.get(case_id)

    def record_feedback_readiness(
        self,
        *,
        actor_type: str,
        actor_id: str,
        scope: str,
        evidence: str,
        reason: str,
    ) -> dict[str, Any]:
        if actor_type not in {"human", "tool"}:
            raise ValueError("actor_type은 human 또는 tool이어야 합니다.")
        for name, value in {
            "actor_id": actor_id,
            "scope": scope,
            "evidence": evidence,
            "reason": reason,
        }.items():
            if not value.strip():
                raise ValueError(f"{name}가 필요합니다.")
        readiness = FeedbackReadinessEvent(
            readiness_id=f"feedback-readiness-{uuid4().hex[:12]}",
            actor_type=actor_type,  # type: ignore[arg-type]
            actor_id=actor_id.strip(),
            scope=scope.strip(),
            evidence=evidence.strip(),
            reason=reason.strip(),
        )
        return self.events.append(
            "feedback_readiness_approved",
            readiness.to_dict(),
        )

    def approve_negative_example(
        self,
        *,
        case_id: str,
        readiness_id: str,
        actor_id: str,
        reason: str,
    ) -> CaseState:
        state = self.get(case_id)
        if state.confirmation_status != "confirmed":
            raise ValueError("confirmed case만 부정예시로 활성 승인할 수 있습니다.")
        if state.negative_example_activated:
            raise ValueError("이미 활성 승인된 case입니다.")
        readiness = self._find_readiness(readiness_id)
        if not actor_id.strip():
            raise ValueError("actor_id가 필요합니다.")
        if not reason.strip():
            raise ValueError("활성 승인 reason이 필요합니다.")

        block_rule = self._derive_block_rule(state)
        activation = NegativeExampleActivationEvent(
            case_id=case_id,
            readiness_id=str(readiness["readiness_id"]),
            actor_id=actor_id.strip(),
            reason=reason.strip(),
            source_event_id=state.source_event_id,
            block_rule=block_rule,
            negative_example_status="active_approved",
            negative_example_activated=True,
        )
        self.events.append(
            "negative_example_activation_approved",
            activation.to_dict(),
        )
        return self.get(case_id)

    def active_negative_examples(self) -> list[NegativeExampleRule]:
        rules: list[NegativeExampleRule] = []
        seen_cases: set[str] = set()
        for event in self._read_events():
            if event.get("event_type") != "negative_example_activation_approved":
                continue
            payload = event.get("payload", {})
            case_id = str(payload.get("case_id", ""))
            if not case_id or case_id in seen_cases:
                raise ValueError(f"중복 또는 빈 활성 case: {case_id!r}")
            seen_cases.add(case_id)
            state = self.get(case_id)
            if state.confirmation_status != "confirmed":
                raise ValueError(f"미확정 case의 활성 규칙: {case_id}")
            if not state.negative_example_activated:
                raise ValueError(f"활성 상태가 아닌 case의 활성 규칙: {case_id}")
            readiness_id = str(payload["readiness_id"])
            self._find_readiness(readiness_id)
            if str(payload["source_event_id"]) != state.source_event_id:
                raise ValueError(f"case 출처 event 불일치: {case_id}")
            rules.append(
                NegativeExampleRule(
                    case_id=case_id,
                    block_rule=str(payload["block_rule"]),
                    source_event_id=str(payload["source_event_id"]),
                    readiness_id=readiness_id,
                )
            )
        return rules

    def _find_readiness(self, readiness_id: str) -> dict[str, Any]:
        matches = [
            event.get("payload", {})
            for event in self._read_events()
            if event.get("event_type") == "feedback_readiness_approved"
            and event.get("payload", {}).get("readiness_id") == readiness_id
        ]
        if not matches:
            raise ValueError(f"되먹임 준비 승인을 찾을 수 없습니다: {readiness_id}")
        if len(matches) > 1:
            raise ValueError(f"중복 되먹임 준비 승인: {readiness_id}")
        return matches[0]

    @staticmethod
    def _derive_block_rule(state: CaseState) -> str:
        appeal_result = state.report.get("appeal_result", {})
        appeal_feedback = str(
            appeal_result.get("feedback_to_thesis", "")
        ).strip()
        if appeal_feedback:
            return appeal_feedback
        appeal_defects = appeal_result.get("defects", [])
        defect_rules = [
            (
                f"{str(item.get('type', '')).strip()}: "
                f"{str(item.get('where', '')).strip()} — "
                f"{str(item.get('why', '')).strip()}"
            ).strip()
            for item in appeal_defects
            if isinstance(item, dict)
            and all(
                str(item.get(key, "")).strip()
                for key in ("type", "where", "why")
            )
        ]
        if defect_rules:
            return " / ".join(defect_rules)
        reviews = state.report.get("review_batch", {}).get("reviews", [])
        rules = [
            str(review.get("feedback_to_thesis", "")).strip()
            for review in reviews
            if str(review.get("feedback_to_thesis", "")).strip()
        ]
        if rules:
            return " / ".join(dict.fromkeys(rules))
        if state.confirmation_events:
            last = state.confirmation_events[-1]
            return f"{last.get('reason', '')}: {last.get('evidence', '')}".strip(": ")
        raise ValueError("Block-rule을 만들 근거가 없습니다.")

    def _validate_appeal_case_source(self, report: dict[str, Any]) -> None:
        self.contracts.validate_appeal_case(report)

    @staticmethod
    def _normalize_legacy_adversary_disposition(
        report: dict[str, Any],
    ) -> dict[str, Any]:
        review_status = str(
            report.get("review_batch", {}).get("status", "")
        )
        disposition = str(report.get("disposition", ""))
        if (
            disposition == "caught_by_filter"
            and review_status in {"conflict", "empty_aspect", "human_review"}
        ):
            normalized = dict(report)
            normalized["reported_disposition"] = disposition
            normalized["disposition"] = "review_inconclusive"
            normalized["disposition_normalized_from_legacy"] = True
            return normalized
        return report

    def _read_events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"이벤트 로그 JSON 오류: line {line_number}: {exc}"
                ) from exc
            if not isinstance(event, dict):
                raise ValueError(f"이벤트 로그 객체 오류: line {line_number}")
            events.append(event)
        return events
