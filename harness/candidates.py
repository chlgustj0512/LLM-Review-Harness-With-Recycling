from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.models import validate_review_batch_semantics


class CandidateRegistry:
    """이벤트 로그에서 과제·후보·심사 결과의 결속을 검증한다."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def task(self, task_id: str) -> dict[str, Any]:
        return self._unique_payload("task_created", "task_id", task_id)

    def candidate(self, candidate_id: str) -> dict[str, Any]:
        return self._unique_payload(
            "candidate_generated",
            "candidate_id",
            candidate_id,
        )

    def review_event(self, event_id: str) -> dict[str, Any]:
        matches = [
            event
            for event in self._read_events()
            if event.get("event_id") == event_id
        ]
        if not matches:
            raise ValueError(f"심사 사건을 찾을 수 없습니다: {event_id}")
        if len(matches) > 1:
            raise ValueError(f"중복 event ID입니다: {event_id}")
        event = matches[0]
        if event.get("event_type") != "review_batch_completed":
            raise ValueError(
                f"Gate 출처는 review_batch_completed 사건이어야 합니다: {event_id}"
            )
        self._validate_review_batch(event.get("payload", {}), event_id)
        return event

    def review_status(self, event_id: str) -> str:
        payload = self.review_event(event_id).get("payload", {})
        status = str(payload.get("status", "")).strip()
        allowed = {
            "clear",
            "objections",
            "dependent_core_blocked",
            "conflict",
            "empty_aspect",
            "human_review",
        }
        if status not in allowed:
            raise ValueError(
                f"심사 사건의 status가 없거나 유효하지 않습니다: {event_id}"
            )
        return status

    def validate_review_binding(
        self,
        *,
        task_id: str,
        candidate_id: str,
        review_event_id: str,
    ) -> None:
        events = self._read_events()
        task_index, task_event = self._unique_event(
            events,
            "task_created",
            "task_id",
            task_id,
        )
        candidate_index, candidate_event = self._unique_event(
            events,
            "candidate_generated",
            "candidate_id",
            candidate_id,
        )
        review_matches = [
            (index, event)
            for index, event in enumerate(events)
            if event.get("event_id") == review_event_id
        ]
        if not review_matches:
            raise ValueError(f"심사 사건을 찾을 수 없습니다: {review_event_id}")
        if len(review_matches) > 1:
            raise ValueError(f"중복 event ID입니다: {review_event_id}")
        review_index, review_event = review_matches[0]
        if review_event.get("event_type") != "review_batch_completed":
            raise ValueError(
                "Gate 출처는 review_batch_completed 사건이어야 합니다: "
                f"{review_event_id}"
            )
        self._validate_review_batch(
            review_event.get("payload", {}),
            review_event_id,
        )

        candidate_payload = candidate_event["payload"]
        review_payload = review_event.get("payload", {})
        if candidate_payload.get("task_id") != task_id:
            raise ValueError(
                f"후보가 다른 과제에 속합니다: {candidate_id} -> "
                f"{candidate_payload.get('task_id')}"
            )
        if review_payload.get("candidate_id") != candidate_id:
            raise ValueError(
                f"심사 사건이 다른 후보를 가리킵니다: {review_event_id} -> "
                f"{review_payload.get('candidate_id')}"
            )
        self.review_status(review_event_id)
        if not task_index < candidate_index < review_index:
            raise ValueError(
                "과제 생성 → 후보 생성 → 심사 완료 순서가 보존되지 않았습니다."
            )
        if task_event.get("payload", {}).get("task_id") != task_id:
            raise ValueError(f"과제 결속이 손상되었습니다: {task_id}")

    @staticmethod
    def _validate_review_batch(
        payload: dict[str, Any],
        event_id: str,
    ) -> None:
        try:
            validate_review_batch_semantics(payload)
        except ValueError as exc:
            raise ValueError(
                f"심사 묶음 계약 위반: {event_id}: {exc}"
            ) from exc

    def _unique_payload(
        self,
        event_type: str,
        key: str,
        value: str,
    ) -> dict[str, Any]:
        _, event = self._unique_event(
            self._read_events(),
            event_type,
            key,
            value,
        )
        return event["payload"]

    @staticmethod
    def _unique_event(
        events: list[dict[str, Any]],
        event_type: str,
        key: str,
        value: str,
    ) -> tuple[int, dict[str, Any]]:
        matches = [
            (index, event)
            for index, event in enumerate(events)
            if event.get("event_type") == event_type
            and event.get("payload", {}).get(key) == value
        ]
        if not matches:
            label = "과제" if event_type == "task_created" else "후보"
            raise ValueError(f"{label}를 찾을 수 없습니다: {value}")
        if len(matches) > 1:
            raise ValueError(f"중복 {key}입니다: {value}")
        return matches[0]

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
