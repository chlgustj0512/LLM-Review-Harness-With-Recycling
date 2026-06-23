from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from harness.event_contracts import EventContractValidator
from harness.logging import EventLog
from harness.models import LibraryMatch, LibraryPart, PurposeApprovalEvent


class LibraryLedger:
    """지연 재사용 부품과 목적 주석 승인 이력을 append-only로 관리한다."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.events = EventLog(path)
        self.contracts = EventContractValidator(path)

    def add_part(
        self,
        *,
        content: str,
        premises: list[str],
        verification_context: str,
        works_when: list[str],
        fails_when: list[str],
        purpose: str,
        verification_status: str,
        source_event_id: str,
        source_candidate_id: str,
        created_by: str,
    ) -> LibraryPart:
        required = {
            "content": content,
            "verification_context": verification_context,
            "purpose": purpose,
            "source_event_id": source_event_id,
            "source_candidate_id": source_candidate_id,
            "created_by": created_by,
        }
        for name, value in required.items():
            if not value.strip():
                raise ValueError(f"{name}가 필요합니다.")
        if not premises:
            raise ValueError("성립 전제 premises가 하나 이상 필요합니다.")
        if not works_when:
            raise ValueError("works_when이 하나 이상 필요합니다.")
        if not fails_when:
            raise ValueError("fails_when이 하나 이상 필요합니다.")
        if verification_status not in {
            "preserved_verified",
            "salvaged_unverified",
        }:
            raise ValueError("지원하지 않는 verification_status입니다.")
        self._validate_source_binding(
            source_event_id=source_event_id,
            source_candidate_id=source_candidate_id,
        )

        part = LibraryPart(
            part_id=f"library-part-{uuid4().hex[:12]}",
            content=content.strip(),
            premises=_clean_list(premises),
            verification_context=verification_context.strip(),
            works_when=_clean_list(works_when),
            fails_when=_clean_list(fails_when),
            purpose=purpose.strip(),
            purpose_status="proposed_unapproved",
            verification_status=verification_status,  # type: ignore[arg-type]
            source_event_id=source_event_id,
            source_candidate_id=source_candidate_id.strip(),
            created_by=created_by.strip(),
        )
        self.events.append("library_part_proposed", part.to_dict())
        return self.get(part.part_id)

    def approve_purpose(
        self,
        *,
        part_id: str,
        actor_type: str,
        actor_id: str,
        reason: str,
    ) -> LibraryPart:
        part = self.get(part_id)
        if part.purpose_status != "proposed_unapproved":
            raise ValueError("이미 처리된 목적 주석입니다.")
        if actor_type not in {"human", "tool"}:
            raise ValueError("actor_type은 human 또는 tool이어야 합니다.")
        if not actor_id.strip() or not reason.strip():
            raise ValueError("actor_id와 reason이 필요합니다.")
        approval = PurposeApprovalEvent(
            part_id=part_id,
            previous_status="proposed_unapproved",
            new_status="approved",
            actor_type=actor_type,  # type: ignore[arg-type]
            actor_id=actor_id.strip(),
            reason=reason.strip(),
            source_event_id=part.source_event_id,
        )
        self.events.append("library_purpose_approved", approval.to_dict())
        return self.get(part_id)

    def get(self, part_id: str) -> LibraryPart:
        proposed: dict[str, Any] | None = None
        approvals: list[dict[str, Any]] = []
        for event in self._read_events():
            payload = event.get("payload", {})
            if event.get("event_type") == "library_part_proposed":
                if payload.get("part_id") == part_id:
                    if proposed is not None:
                        raise ValueError(f"중복 library part: {part_id}")
                    proposed = payload
            elif event.get("event_type") == "library_purpose_approved":
                if payload.get("part_id") == part_id:
                    approvals.append(payload)
        if proposed is None:
            raise ValueError(f"library part를 찾을 수 없습니다: {part_id}")
        if len(approvals) > 1:
            raise ValueError(f"중복 목적 승인: {part_id}")
        if approvals:
            self.contracts.validate_library_approval(proposed, approvals[0])
        self._validate_source_binding(
            source_event_id=str(proposed["source_event_id"]),
            source_candidate_id=str(proposed["source_candidate_id"]),
        )
        purpose_status = "approved" if approvals else str(proposed["purpose_status"])
        return LibraryPart(
            part_id=str(proposed["part_id"]),
            content=str(proposed["content"]),
            premises=list(proposed["premises"]),
            verification_context=str(proposed["verification_context"]),
            works_when=list(proposed["works_when"]),
            fails_when=list(proposed["fails_when"]),
            purpose=str(proposed["purpose"]),
            purpose_status=purpose_status,
            verification_status=str(proposed["verification_status"]),  # type: ignore[arg-type]
            source_event_id=str(proposed["source_event_id"]),
            source_candidate_id=str(proposed["source_candidate_id"]),
            created_by=str(proposed["created_by"]),
        )

    def query(
        self,
        *,
        purpose: str,
        conditions: list[str] | None = None,
    ) -> list[LibraryMatch]:
        normalized_purpose = _normalize(purpose)
        if not normalized_purpose:
            raise ValueError("purpose가 필요합니다.")
        requested = [_normalize(item) for item in (conditions or []) if item.strip()]
        matches: list[LibraryMatch] = []
        for part_id in self._part_ids():
            part = self.get(part_id)
            if part.purpose_status != "approved":
                continue
            purpose_matched = _normalize(part.purpose) == normalized_purpose
            if not purpose_matched:
                continue
            available = {
                _normalize(item)
                for item in [*part.premises, *part.works_when]
            }
            matched = [item for item in requested if item in available]
            conditions_matched = len(matched) == len(requested)
            if not conditions_matched:
                continue
            matches.append(
                LibraryMatch(
                    part=part,
                    purpose_matched=True,
                    conditions_matched=True,
                    matched_conditions=matched,
                )
            )
        return matches

    def intake_candidates(self) -> list[dict[str, Any]]:
        return [
            event["payload"]
            for event in self._read_events()
            if event.get("event_type") == "library_intake_candidate_recorded"
        ]

    def _part_ids(self) -> list[str]:
        return [
            str(event["payload"]["part_id"])
            for event in self._read_events()
            if event.get("event_type") == "library_part_proposed"
        ]

    def _require_event(self, event_id: str) -> dict[str, Any]:
        matches = [
            event
            for event in self._read_events()
            if event.get("event_id") == event_id
        ]
        if not matches:
            raise ValueError(f"source event를 찾을 수 없습니다: {event_id}")
        if len(matches) > 1:
            raise ValueError(f"중복 source event ID: {event_id}")
        return matches[0]

    def _validate_source_binding(
        self,
        *,
        source_event_id: str,
        source_candidate_id: str,
    ) -> None:
        self.contracts.validate_library_source(
            source_event_id,
            source_candidate_id,
        )

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


def _clean_list(items: list[str]) -> list[str]:
    cleaned = [item.strip() for item in items if item.strip()]
    return list(dict.fromkeys(cleaned))


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())
