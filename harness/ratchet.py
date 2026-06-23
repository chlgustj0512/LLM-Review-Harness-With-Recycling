from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from harness.event_contracts import EventContractValidator
from harness.gates import GateLedger
from harness.logging import EventLog
from harness.models import RatchetComparisonEvent, RatchetSessionState


class RatchetLedger:
    """Gate 통과 후보만 받는 상대 비교·측면별 챔피언 원장."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.events = EventLog(path)
        self.gates = GateLedger(path)
        self.contracts = EventContractValidator(path)

    def start(
        self,
        *,
        purpose: str,
        priority_line: list[str],
        actor_id: str,
    ) -> RatchetSessionState:
        priority = _clean_unique(priority_line)
        if not purpose.strip() or not actor_id.strip():
            raise ValueError("purpose와 actor_id가 필요합니다.")
        if not priority:
            raise ValueError("priority_line이 하나 이상 필요합니다.")
        session_id = f"ratchet-{uuid4().hex[:12]}"
        self.events.append(
            "ratchet_session_started",
            {
                "session_id": session_id,
                "purpose": purpose.strip(),
                "priority_line": priority,
                "actor_id": actor_id.strip(),
            },
        )
        return self.get(session_id)

    def admit_candidate(
        self,
        *,
        session_id: str,
        gate_flow_id: str,
        actor_id: str,
    ) -> RatchetSessionState:
        state = self.get(session_id)
        if self._is_terminated(session_id):
            raise ValueError("종료 승인된 래칫 세션에는 후보를 추가할 수 없습니다.")
        if state.pending_candidate_id:
            raise ValueError("먼저 현재 pending 후보 평가를 완료해야 합니다.")
        gate_state = self.gates.get(gate_flow_id)
        if gate_state.status != "completed_accepted":
            raise ValueError("Gate 3 accepted 후보만 래칫에 진입할 수 있습니다.")
        candidate_id = gate_state.current_candidate_id
        if candidate_id in state.admitted_candidate_ids:
            raise ValueError("이미 래칫에 진입한 candidate입니다.")
        if not actor_id.strip():
            raise ValueError("actor_id가 필요합니다.")
        task_payload = self.gates.candidates.task(gate_state.task_id)
        task_goal = str(task_payload.get("goal", "")).strip()
        task_constraints = [
            str(item).strip()
            for item in task_payload.get("constraints", [])
            if str(item).strip()
        ]
        if state.scope_task_id and not _same_task_scope(
            state.scope_goal,
            state.scope_constraints,
            task_goal,
            task_constraints,
        ):
            raise ValueError(
                "래칫 세션의 과제 범위와 다른 후보입니다: "
                f"기준={state.scope_goal!r}, 입력={task_goal!r}"
            )
        gate_event_id = _last_gate_event_id(gate_state)
        bootstrap = not state.overall_champion_candidate_id
        self.events.append(
            "ratchet_candidate_admitted",
            {
                "session_id": session_id,
                "candidate_id": candidate_id,
                "gate_flow_id": gate_flow_id,
                "source_gate_event_id": gate_event_id,
                "actor_id": actor_id.strip(),
                "bootstrap": bootstrap,
                "task_id": gate_state.task_id,
                "task_goal": task_goal,
                "task_constraints": task_constraints,
            },
        )
        if bootstrap:
            self.events.append(
                "ratchet_candidate_finalized",
                {
                    "session_id": session_id,
                    "candidate_id": candidate_id,
                    "overall_result": "bootstrap_champion",
                    "decisive_aspect": "",
                    "overall_promoted": True,
                },
            )
            for aspect in state.priority_line:
                self._update_champion(
                    session_id=session_id,
                    aspect=aspect,
                    previous_candidate_id="",
                    new_candidate_id=candidate_id,
                    reason="초기 챔피언",
                )
            self._update_champion(
                session_id=session_id,
                aspect="__overall__",
                previous_candidate_id="",
                new_candidate_id=candidate_id,
                reason="초기 전체 챔피언",
            )
        return self.get(session_id)

    def record_comparison(
        self,
        *,
        session_id: str,
        aspect: str,
        result: str,
        actor_type: str,
        actor_id: str,
        reason: str,
    ) -> RatchetSessionState:
        state = self.get(session_id)
        if not state.pending_candidate_id:
            raise ValueError("비교할 pending 후보가 없습니다.")
        if aspect not in state.priority_line:
            raise ValueError(f"priority_line에 없는 aspect입니다: {aspect}")
        if aspect in state.pending_comparisons:
            raise ValueError(f"이미 비교한 aspect입니다: {aspect}")
        if result not in {"improved", "no_meaningful_change", "regressed"}:
            raise ValueError("지원하지 않는 상대 변화 판정입니다.")
        if actor_type not in {"human", "tool"}:
            raise ValueError("actor_type은 human 또는 tool이어야 합니다.")
        if not actor_id.strip() or not reason.strip():
            raise ValueError("actor_id와 reason이 필요합니다.")
        baseline = state.aspect_champions.get(aspect, "")
        if not baseline:
            raise ValueError(f"측면 챔피언이 없습니다: {aspect}")
        event = RatchetComparisonEvent(
            session_id=session_id,
            candidate_id=state.pending_candidate_id,
            aspect=aspect,
            baseline_candidate_id=baseline,
            result=result,  # type: ignore[arg-type]
            actor_type=actor_type,  # type: ignore[arg-type]
            actor_id=actor_id.strip(),
            reason=reason.strip(),
        )
        self.events.append("ratchet_comparison_recorded", event.to_dict())
        return self.get(session_id)

    def finalize_candidate(
        self,
        *,
        session_id: str,
        actor_id: str,
    ) -> RatchetSessionState:
        state = self.get(session_id)
        candidate_id = state.pending_candidate_id
        if not candidate_id:
            raise ValueError("완료할 pending 후보가 없습니다.")
        missing = [
            aspect
            for aspect in state.priority_line
            if aspect not in state.pending_comparisons
        ]
        if missing:
            raise ValueError(f"비교하지 않은 aspect가 있습니다: {', '.join(missing)}")
        if not actor_id.strip():
            raise ValueError("actor_id가 필요합니다.")

        decisive_aspect = ""
        overall_result = "no_meaningful_change"
        overall_promoted = False
        for aspect in state.priority_line:
            result = state.pending_comparisons[aspect]
            if result == "no_meaningful_change":
                continue
            decisive_aspect = aspect
            overall_result = result
            overall_promoted = result == "improved"
            break

        self.events.append(
            "ratchet_candidate_finalized",
            {
                "session_id": session_id,
                "candidate_id": candidate_id,
                "overall_result": overall_result,
                "decisive_aspect": decisive_aspect,
                "overall_promoted": overall_promoted,
                "actor_id": actor_id.strip(),
            },
        )
        for aspect in state.priority_line:
            result = state.pending_comparisons[aspect]
            if result != "improved":
                continue
            self._update_champion(
                session_id=session_id,
                aspect=aspect,
                previous_candidate_id=state.aspect_champions[aspect],
                new_candidate_id=candidate_id,
                reason="측면 상대 개선",
            )
        if overall_promoted:
            self._update_champion(
                session_id=session_id,
                aspect="__overall__",
                previous_candidate_id=state.overall_champion_candidate_id,
                new_candidate_id=candidate_id,
                reason=f"사전식 첫 결정 측면: {decisive_aspect}",
            )
        return self.get(session_id)

    def get(self, session_id: str) -> RatchetSessionState:
        events = [
            event
            for event in self._read_events()
            if event.get("payload", {}).get("session_id") == session_id
            and event.get("event_type")
            in {
                "ratchet_session_started",
                "ratchet_candidate_admitted",
                "ratchet_comparison_recorded",
                "ratchet_candidate_finalized",
                "ratchet_champion_updated",
            }
        ]
        starts = [
            event for event in events
            if event.get("event_type") == "ratchet_session_started"
        ]
        if not starts:
            raise ValueError(f"래칫 세션을 찾을 수 없습니다: {session_id}")
        if len(starts) > 1:
            raise ValueError(f"중복 래칫 세션: {session_id}")
        start = starts[0]["payload"]
        priority_line = list(start["priority_line"])
        admitted: list[str] = []
        pending = ""
        comparisons: dict[str, str] = {}
        champions: dict[str, str] = {}
        overall = ""
        scope_task_id = ""
        scope_goal = ""
        scope_constraints: list[str] = []
        history: list[dict[str, Any]] = []
        expected_champion_updates: list[tuple[str, str, str, str]] = []

        for event in events:
            event_type = event.get("event_type")
            if event_type == "ratchet_session_started":
                continue
            payload = event["payload"]
            history.append(event)
            if event_type == "ratchet_candidate_admitted":
                if expected_champion_updates:
                    raise ValueError("래칫 챔피언 갱신 사건이 누락됐습니다.")
                candidate_id = str(payload["candidate_id"])
                if candidate_id in admitted:
                    raise ValueError(f"중복 래칫 candidate: {candidate_id}")
                gate_state = self.gates.get(str(payload.get("gate_flow_id", "")))
                source_gate_event_id = _last_gate_event_id(gate_state)
                bootstrap = not overall
                self.contracts.validate_ratchet_admission(
                    payload,
                    session_id=session_id,
                    gate_state=gate_state,
                    source_gate_event_id=source_gate_event_id,
                    bootstrap=bootstrap,
                )
                (
                    event_task_id,
                    event_task_goal,
                    event_task_constraints,
                ) = self._admission_task_scope(payload)
                if not scope_task_id:
                    scope_task_id = event_task_id
                    scope_goal = event_task_goal
                    scope_constraints = event_task_constraints
                elif not _same_task_scope(
                    scope_goal,
                    scope_constraints,
                    event_task_goal,
                    event_task_constraints,
                ):
                    raise ValueError(
                        f"래칫 과제 범위 이력 불연속: {candidate_id}"
                    )
                admitted.append(candidate_id)
                pending = candidate_id
                comparisons = {}
            elif event_type == "ratchet_comparison_recorded":
                if expected_champion_updates:
                    raise ValueError("래칫 챔피언 갱신 사건이 누락됐습니다.")
                if payload["candidate_id"] != pending:
                    raise ValueError("래칫 comparison candidate 이력 불연속")
                aspect = str(payload["aspect"])
                if aspect in comparisons:
                    raise ValueError(f"중복 래칫 comparison: {aspect}")
                if aspect not in priority_line:
                    raise ValueError(f"priority_line에 없는 comparison: {aspect}")
                baseline = champions.get(aspect, "")
                self.contracts.validate_ratchet_comparison(
                    payload,
                    session_id=session_id,
                    candidate_id=pending,
                    baseline_candidate_id=baseline,
                    aspect=aspect,
                )
                comparisons[aspect] = str(payload["result"])
            elif event_type == "ratchet_candidate_finalized":
                if payload["candidate_id"] != pending:
                    raise ValueError("래칫 finalize candidate 이력 불연속")
                bootstrap = not overall
                expected, updates = self.contracts.ratchet_finalization(
                    candidate_id=pending,
                    priority_line=priority_line,
                    comparisons=comparisons,
                    bootstrap=bootstrap,
                )
                self.contracts.validate_ratchet_finalize(
                    payload,
                    session_id=session_id,
                    expected=expected,
                    bootstrap=bootstrap,
                )
                expected_champion_updates = [
                    (
                        aspect,
                        (
                            overall
                            if aspect == "__overall__"
                            else champions.get(aspect, "")
                        ),
                        pending,
                        reason,
                    )
                    for aspect, reason in updates
                ]
                pending = ""
                comparisons = {}
            elif event_type == "ratchet_champion_updated":
                if not expected_champion_updates:
                    raise ValueError("근거 없는 래칫 챔피언 갱신 사건입니다.")
                (
                    expected_aspect,
                    expected_previous,
                    expected_new,
                    expected_reason,
                ) = expected_champion_updates.pop(0)
                self.contracts.validate_champion_update(
                    payload,
                    session_id=session_id,
                    aspect=expected_aspect,
                    previous_candidate_id=expected_previous,
                    new_candidate_id=expected_new,
                    reason=expected_reason,
                )
                aspect = str(payload["aspect"])
                previous = str(payload["previous_candidate_id"])
                current = overall if aspect == "__overall__" else champions.get(aspect, "")
                if previous != current:
                    raise ValueError(f"래칫 챔피언 이력 불연속: {aspect}")
                if aspect == "__overall__":
                    overall = str(payload["new_candidate_id"])
                else:
                    champions[aspect] = str(payload["new_candidate_id"])
            else:
                raise ValueError(f"지원하지 않는 래칫 사건입니다: {event_type}")

        if expected_champion_updates:
            raise ValueError("래칫 챔피언 갱신 사건이 완결되지 않았습니다.")

        return RatchetSessionState(
            session_id=session_id,
            purpose=str(start["purpose"]),
            priority_line=priority_line,
            scope_task_id=scope_task_id,
            scope_goal=scope_goal,
            scope_constraints=scope_constraints,
            overall_champion_candidate_id=overall,
            aspect_champions=champions,
            admitted_candidate_ids=admitted,
            pending_candidate_id=pending,
            pending_comparisons=comparisons,
            history=history,
        )

    def _admission_task_scope(
        self,
        payload: dict[str, Any],
    ) -> tuple[str, str, list[str]]:
        gate_flow_id = str(payload.get("gate_flow_id", ""))
        gate_state = self.gates.get(gate_flow_id)
        if gate_state.current_candidate_id != payload.get("candidate_id"):
            raise ValueError("래칫 입장 후보와 Gate 후보가 일치하지 않습니다.")
        task_payload = self.gates.candidates.task(gate_state.task_id)
        task_id = gate_state.task_id
        task_goal = str(task_payload.get("goal", "")).strip()
        task_constraints = [
            str(item).strip()
            for item in task_payload.get("constraints", [])
            if str(item).strip()
        ]
        stored_task_id = str(payload.get("task_id", task_id))
        stored_goal = str(payload.get("task_goal", task_goal)).strip()
        stored_constraints = [
            str(item).strip()
            for item in payload.get("task_constraints", task_constraints)
            if str(item).strip()
        ]
        if (
            stored_task_id != task_id
            or not _same_task_scope(
                stored_goal,
                stored_constraints,
                task_goal,
                task_constraints,
            )
        ):
            raise ValueError("래칫 입장 사건의 과제 출처가 손상되었습니다.")
        return task_id, task_goal, task_constraints

    def _update_champion(
        self,
        *,
        session_id: str,
        aspect: str,
        previous_candidate_id: str,
        new_candidate_id: str,
        reason: str,
    ) -> None:
        self.events.append(
            "ratchet_champion_updated",
            {
                "session_id": session_id,
                "aspect": aspect,
                "previous_candidate_id": previous_candidate_id,
                "new_candidate_id": new_candidate_id,
                "reason": reason,
            },
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

    def _is_terminated(self, session_id: str) -> bool:
        return any(
            event.get("event_type") == "ratchet_termination_approved"
            and event.get("payload", {}).get("session_id") == session_id
            for event in self._read_events()
        )


def _clean_unique(items: list[str]) -> list[str]:
    cleaned = [item.strip() for item in items if item.strip()]
    return list(dict.fromkeys(cleaned))


def _last_gate_event_id(gate_state) -> str:
    if not gate_state.history:
        raise ValueError("Gate 완료 출처 사건이 없습니다.")
    event = gate_state.history[-1]
    if event.get("event_type") != "gate_decision_recorded":
        raise ValueError("Gate 완료 마지막 사건이 decision이 아닙니다.")
    return str(event.get("event_id", ""))


def _same_task_scope(
    left_goal: str,
    left_constraints: list[str],
    right_goal: str,
    right_constraints: list[str],
) -> bool:
    return (
        _normalize_scope_text(left_goal) == _normalize_scope_text(right_goal)
        and sorted(_normalize_scope_text(item) for item in left_constraints)
        == sorted(_normalize_scope_text(item) for item in right_constraints)
    )


def _normalize_scope_text(value: str) -> str:
    return " ".join(value.casefold().split())
