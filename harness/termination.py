from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from harness.event_contracts import EventContractValidator
from harness.logging import EventLog
from harness.models import ChampionSnapshot, MetagameTransitionEvent
from harness.ratchet import RatchetLedger


class TerminationLedger:
    """래칫 종료 승인, 잠정 챔피언 Snapshot, 메타게임 상태를 관리한다."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.events = EventLog(path)
        self.ratchet = RatchetLedger(path)
        self.contracts = EventContractValidator(path)

    def eligibility(self, session_id: str) -> dict[str, Any]:
        state = self.ratchet.get(session_id)
        if state.pending_candidate_id:
            return {
                "session_id": session_id,
                "eligible": False,
                "reason": "pending_candidate_exists",
                "source_finalize_event_id": "",
                "comparisons": {},
            }
        if self._snapshot_for_session(session_id):
            return {
                "session_id": session_id,
                "eligible": False,
                "reason": "already_terminated",
                "source_finalize_event_id": "",
                "comparisons": {},
            }
        latest = self._latest_non_bootstrap_finalization(state.history)
        if latest is None:
            return {
                "session_id": session_id,
                "eligible": False,
                "reason": "no_comparison_cycle",
                "source_finalize_event_id": "",
                "comparisons": {},
            }
        comparisons = self._comparisons_for_candidate(
            state.history,
            str(latest["payload"]["candidate_id"]),
            latest,
        )
        missing = [
            aspect
            for aspect in state.priority_line
            if aspect not in comparisons
        ]
        if missing:
            raise ValueError(
                f"종료 판정용 비교 이력이 불완전합니다: {', '.join(missing)}"
            )
        improved = [
            aspect
            for aspect, result in comparisons.items()
            if result == "improved"
        ]
        return {
            "session_id": session_id,
            "eligible": not improved,
            "reason": "no_aspect_improved" if not improved else "aspect_improved",
            "source_finalize_event_id": str(latest.get("event_id", "")),
            "candidate_id": str(latest["payload"]["candidate_id"]),
            "comparisons": comparisons,
            "improved_aspects": improved,
        }

    def approve(
        self,
        *,
        session_id: str,
        actor_type: str,
        actor_id: str,
        reason: str,
    ) -> ChampionSnapshot:
        eligibility = self.eligibility(session_id)
        if not eligibility["eligible"]:
            raise ValueError(
                f"종료 승인 조건을 충족하지 않습니다: {eligibility['reason']}"
            )
        if actor_type not in {"human", "tool"}:
            raise ValueError("actor_type은 human 또는 tool이어야 합니다.")
        if not actor_id.strip() or not reason.strip():
            raise ValueError("actor_id와 reason이 필요합니다.")
        state = self.ratchet.get(session_id)
        snapshot_id = f"champion-snapshot-{uuid4().hex[:12]}"
        self.events.append(
            "ratchet_termination_approved",
            {
                "snapshot_id": snapshot_id,
                "session_id": session_id,
                "purpose": state.purpose,
                "priority_line": state.priority_line,
                "overall_champion_candidate_id": state.overall_champion_candidate_id,
                "aspect_champions": state.aspect_champions,
                "status": "active",
                "source_finalize_event_id": eligibility["source_finalize_event_id"],
                "termination_reason": reason.strip(),
                "actor_type": actor_type,
                "actor_id": actor_id.strip(),
            },
        )
        return self.get(snapshot_id)

    def get(self, snapshot_id: str) -> ChampionSnapshot:
        starts: list[dict[str, Any]] = []
        transitions: list[dict[str, Any]] = []
        for event in self._read_events():
            payload = event.get("payload", {})
            if payload.get("snapshot_id") != snapshot_id:
                continue
            if event.get("event_type") == "ratchet_termination_approved":
                starts.append(event)
            elif event.get("event_type") == "metagame_status_changed":
                transitions.append(event)
        if not starts:
            raise ValueError(f"Snapshot을 찾을 수 없습니다: {snapshot_id}")
        if len(starts) > 1:
            raise ValueError(f"중복 Snapshot: {snapshot_id}")
        start = starts[0]["payload"]
        session_state = self.ratchet.get(str(start["session_id"]))
        self.contracts.validate_snapshot(
            start,
            session_state=session_state,
        )
        status = str(start["status"])
        for event in transitions:
            payload = event["payload"]
            if payload["previous_status"] != status:
                raise ValueError(f"메타게임 상태 이력 불연속: {snapshot_id}")
            if payload.get("new_status") not in {"active", "deprecated"}:
                raise ValueError(f"유효하지 않은 메타게임 상태: {snapshot_id}")
            if payload.get("actor_type") not in {"human", "tool"}:
                raise ValueError(f"메타게임 actor_type 오류: {snapshot_id}")
            if not str(payload.get("actor_id", "")).strip() or not str(
                payload.get("reason", "")
            ).strip():
                raise ValueError(f"메타게임 전이 근거가 비어 있습니다: {snapshot_id}")
            status = str(payload["new_status"])
        return ChampionSnapshot(
            snapshot_id=snapshot_id,
            session_id=str(start["session_id"]),
            purpose=str(start["purpose"]),
            priority_line=list(start["priority_line"]),
            overall_champion_candidate_id=str(
                start["overall_champion_candidate_id"]
            ),
            aspect_champions=dict(start["aspect_champions"]),
            status=status,  # type: ignore[arg-type]
            source_finalize_event_id=str(start["source_finalize_event_id"]),
            termination_reason=str(start["termination_reason"]),
            history=transitions,
        )

    def change_status(
        self,
        *,
        snapshot_id: str,
        new_status: str,
        actor_type: str,
        actor_id: str,
        reason: str,
    ) -> ChampionSnapshot:
        snapshot = self.get(snapshot_id)
        if new_status not in {"active", "deprecated"}:
            raise ValueError("new_status는 active 또는 deprecated여야 합니다.")
        if new_status == snapshot.status:
            raise ValueError("현재 상태와 같은 메타게임 상태로 전이할 수 없습니다.")
        if actor_type not in {"human", "tool"}:
            raise ValueError("actor_type은 human 또는 tool이어야 합니다.")
        if not actor_id.strip() or not reason.strip():
            raise ValueError("actor_id와 reason이 필요합니다.")
        event = MetagameTransitionEvent(
            snapshot_id=snapshot_id,
            previous_status=snapshot.status,
            new_status=new_status,  # type: ignore[arg-type]
            actor_type=actor_type,  # type: ignore[arg-type]
            actor_id=actor_id.strip(),
            reason=reason.strip(),
        )
        self.events.append("metagame_status_changed", event.to_dict())
        return self.get(snapshot_id)

    def is_session_terminated(self, session_id: str) -> bool:
        return bool(self._snapshot_for_session(session_id))

    @staticmethod
    def _latest_non_bootstrap_finalization(
        history: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        matches = [
            event
            for event in history
            if event.get("event_type") == "ratchet_candidate_finalized"
            and event.get("payload", {}).get("overall_result")
            != "bootstrap_champion"
        ]
        return matches[-1] if matches else None

    @staticmethod
    def _comparisons_for_candidate(
        history: list[dict[str, Any]],
        candidate_id: str,
        finalize_event: dict[str, Any],
    ) -> dict[str, str]:
        comparisons: dict[str, str] = {}
        for event in history:
            if event is finalize_event:
                break
            if event.get("event_type") != "ratchet_comparison_recorded":
                continue
            payload = event["payload"]
            if payload.get("candidate_id") == candidate_id:
                comparisons[str(payload["aspect"])] = str(payload["result"])
        return comparisons

    def _snapshot_for_session(self, session_id: str) -> list[dict[str, Any]]:
        return [
            event
            for event in self._read_events()
            if event.get("event_type") == "ratchet_termination_approved"
            and event.get("payload", {}).get("session_id") == session_id
        ]

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
