from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from harness.candidates import CandidateRegistry
from harness.casework import CaseLedger
from harness.event_contracts import EventContractValidator
from harness.logging import EventLog
from harness.models import GateDecisionEvent, GateFlowState, GateRevisionEvent


class GateLedger:
    """Gate 1→3의 상태와 이동만 담당한다. 판정 기준은 포함하지 않는다."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.events = EventLog(path)
        self.candidates = CandidateRegistry(path)
        self.cases = CaseLedger(path)
        self.contracts = EventContractValidator(path)

    def start(
        self,
        *,
        task_id: str,
        candidate_id: str,
        source_review_event_id: str,
    ) -> GateFlowState:
        if not all(
            item.strip()
            for item in (task_id, candidate_id, source_review_event_id)
        ):
            raise ValueError("Gate 시작에는 task·candidate·review event ID가 필요합니다.")
        self.candidates.validate_review_binding(
            task_id=task_id,
            candidate_id=candidate_id,
            review_event_id=source_review_event_id,
        )
        review_status = self.candidates.review_status(source_review_event_id)
        if self._flow_for_candidate(candidate_id):
            raise ValueError(f"candidate에 이미 Gate flow가 있습니다: {candidate_id}")
        flow_id = f"gate-flow-{uuid4().hex[:12]}"
        self.events.append(
            "gate_flow_started",
            {
                "flow_id": flow_id,
                "task_id": task_id,
                "candidate_id": candidate_id,
                "stage": 1,
                "status": self._entry_status(review_status),
                "source_review_event_id": source_review_event_id,
                "source_review_status": review_status,
            },
        )
        return self.get(flow_id)

    def get(self, flow_id: str) -> GateFlowState:
        start_event: dict[str, Any] | None = None
        history: list[dict[str, Any]] = []
        for event in self._read_events():
            payload = event.get("payload", {})
            if payload.get("flow_id") != flow_id:
                continue
            if event.get("event_type") == "gate_flow_started":
                if start_event is not None:
                    raise ValueError(f"중복 Gate flow 시작: {flow_id}")
                start_event = event
            elif event.get("event_type") in {
                "gate_decision_recorded",
                "gate_revision_submitted",
            }:
                history.append(event)
        if start_event is None:
            raise ValueError(f"Gate flow를 찾을 수 없습니다: {flow_id}")

        payload = start_event["payload"]
        stage = int(payload["stage"])
        status = str(payload["status"])
        candidate_id = str(payload["candidate_id"])
        source_review_event_id = str(payload["source_review_event_id"])
        task_id = str(payload["task_id"])
        self.candidates.validate_review_binding(
            task_id=task_id,
            candidate_id=candidate_id,
            review_event_id=source_review_event_id,
        )
        expected_start_status = self._entry_status(
            self.candidates.review_status(source_review_event_id)
        )
        legacy_conflict_status = (
            expected_start_status == "awaiting_human_review"
            and status == "awaiting_review"
            and "source_review_status" not in payload
        )
        if (
            int(payload["stage"]) != 1
            or (status != expected_start_status and not legacy_conflict_status)
        ):
            raise ValueError(f"Gate 시작 사건 계약 위반: {flow_id}")
        for event in history:
            event_payload = event["payload"]
            if event["event_type"] == "gate_decision_recorded":
                review_status = self.candidates.review_status(
                    source_review_event_id
                )
                stage, status = self.contracts.validate_gate_decision(
                    event_payload,
                    flow_id=flow_id,
                    task_id=task_id,
                    candidate_id=candidate_id,
                    stage=stage,
                    status=status,
                    source_review_event_id=source_review_event_id,
                    source_review_status=review_status,
                )
            else:
                if status != "awaiting_revision":
                    raise ValueError(f"revision이 허용되지 않는 상태입니다: {status}")
                revised_candidate_id = str(event_payload["revised_candidate_id"])
                revised_review_event_id = str(
                    event_payload["source_review_event_id"]
                )
                self.candidates.validate_review_binding(
                    task_id=task_id,
                    candidate_id=revised_candidate_id,
                    review_event_id=revised_review_event_id,
                )
                expected_next_status = self._entry_status(
                    self.candidates.review_status(revised_review_event_id)
                )
                self.contracts.validate_gate_revision(
                    event_payload,
                    flow_id=flow_id,
                    previous_candidate_id=candidate_id,
                    stage=stage,
                    expected_next_status=expected_next_status,
                )
                candidate_id = revised_candidate_id
                source_review_event_id = revised_review_event_id
                status = expected_next_status

        return GateFlowState(
            flow_id=flow_id,
            task_id=str(payload["task_id"]),
            current_candidate_id=candidate_id,
            stage=stage,
            status=status,  # type: ignore[arg-type]
            source_review_event_id=source_review_event_id,
            history=history,
        )

    def record_decision(
        self,
        *,
        flow_id: str,
        decision: str,
        actor_type: str,
        actor_id: str,
        reason: str,
        appeal_id: str = "",
    ) -> GateFlowState:
        state, review_status, next_stage, next_status = (
            self.validate_decision_request(
                flow_id=flow_id,
                decision=decision,
                actor_type=actor_type,
                actor_id=actor_id,
                reason=reason,
                appeal_id=appeal_id,
                require_appeal=True,
            )
        )
        event = GateDecisionEvent(
            flow_id=flow_id,
            task_id=state.task_id,
            candidate_id=state.current_candidate_id,
            stage=state.stage,
            decision=decision,  # type: ignore[arg-type]
            previous_status=state.status,
            next_status=next_status,  # type: ignore[arg-type]
            next_stage=next_stage,
            actor_type=actor_type,  # type: ignore[arg-type]
            actor_id=actor_id.strip(),
            reason=reason.strip(),
            source_review_event_id=state.source_review_event_id,
            source_review_status=review_status,
            appeal_id=appeal_id.strip(),
        )
        self.events.append("gate_decision_recorded", event.to_dict())
        return self.get(flow_id)

    def validate_decision_request(
        self,
        *,
        flow_id: str,
        decision: str,
        actor_type: str,
        actor_id: str,
        reason: str,
        appeal_id: str = "",
        require_appeal: bool = True,
    ) -> tuple[GateFlowState, str, int, str]:
        state = self.get(flow_id)
        if state.status not in {"awaiting_review", "awaiting_human_review"}:
            raise ValueError(f"Gate 결정을 기록할 수 없는 상태입니다: {state.status}")
        if actor_type not in {"human", "tool"}:
            raise ValueError("actor_type은 human 또는 tool이어야 합니다.")
        if not actor_id.strip() or not reason.strip():
            raise ValueError("actor_id와 reason이 필요합니다.")
        review_status = self.candidates.review_status(
            state.source_review_event_id
        )
        self._validate_review_decision(
            stage=state.stage,
            gate_status=state.status,
            review_status=review_status,
            decision=decision,
            actor_type=actor_type,
            human_resolution_exists=self._human_resolution_exists(state),
        )
        self._validate_human_review_resolution(
            state=state,
            decision=decision,
        )
        if require_appeal:
            self._validate_gate_appeal(
                state=state,
                decision=decision,
                appeal_id=appeal_id,
            )
        next_stage, next_status = self._transition(
            stage=state.stage,
            status=state.status,
            decision=decision,
        )
        return state, review_status, next_stage, next_status

    def submit_revision(
        self,
        *,
        flow_id: str,
        revised_candidate_id: str,
        source_review_event_id: str,
        actor_id: str,
        reason: str,
    ) -> GateFlowState:
        state = self.get(flow_id)
        if state.status != "awaiting_revision":
            raise ValueError(f"revision 제출이 허용되지 않는 상태입니다: {state.status}")
        if not all(
            item.strip()
            for item in (
                revised_candidate_id,
                source_review_event_id,
                actor_id,
                reason,
            )
        ):
            raise ValueError(
                "revised_candidate_id, source_review_event_id, actor_id, "
                "reason이 필요합니다."
            )
        if revised_candidate_id == state.current_candidate_id:
            raise ValueError("revised_candidate_id는 이전 candidate와 달라야 합니다.")
        self.candidates.validate_review_binding(
            task_id=state.task_id,
            candidate_id=revised_candidate_id,
            review_event_id=source_review_event_id,
        )
        review_status = self.candidates.review_status(source_review_event_id)
        next_status = self._entry_status(review_status)
        event = GateRevisionEvent(
            flow_id=flow_id,
            previous_candidate_id=state.current_candidate_id,
            revised_candidate_id=revised_candidate_id.strip(),
            source_review_event_id=source_review_event_id.strip(),
            next_status=next_status,  # type: ignore[arg-type]
            stage=state.stage,
            actor_id=actor_id.strip(),
            reason=reason.strip(),
        )
        self.events.append("gate_revision_submitted", event.to_dict())
        return self.get(flow_id)

    @staticmethod
    def _transition(*, stage: int, status: str, decision: str) -> tuple[int, str]:
        return EventContractValidator.gate_transition(stage, status, decision)

    @staticmethod
    def _entry_status(review_status: str) -> str:
        if review_status in {"conflict", "empty_aspect", "human_review"}:
            return "awaiting_human_review"
        return "awaiting_review"

    @staticmethod
    def _validate_review_decision(
        *,
        stage: int,
        gate_status: str,
        review_status: str,
        decision: str,
        actor_type: str,
        human_resolution_exists: bool,
    ) -> None:
        if gate_status == "awaiting_human_review":
            if actor_type != "human":
                raise ValueError("사람 검토 대기 상태는 human만 해소할 수 있습니다.")
            return
        if (
            review_status in {"conflict", "empty_aspect", "human_review"}
            and not human_resolution_exists
            and decision not in {"needs_human_review", "revise", "reject"}
        ):
            raise ValueError(
                "미해결 심사 상태는 사람 검토 전환·수정·거절만 가능합니다."
            )
        if review_status == "dependent_core_blocked" and decision not in {
            "revise",
            "reject",
        }:
            raise ValueError(
                "종속핵심 결함이 해소되지 않아 revise 또는 reject만 가능합니다."
            )
        if (
            review_status == "clear"
            and stage in {1, 2}
            and decision == "needs_human_review"
        ):
            raise ValueError(
                f"Gate {stage}의 clear 심사는 사람 검토 전환 대상이 아닙니다."
            )

    @staticmethod
    def _human_resolution_exists(state: GateFlowState) -> bool:
        return any(
            event.get("event_type") == "gate_decision_recorded"
            and event.get("payload", {}).get("candidate_id")
            == state.current_candidate_id
            and event.get("payload", {}).get("source_review_event_id")
            == state.source_review_event_id
            and event.get("payload", {}).get("previous_status")
            == "awaiting_human_review"
            and event.get("payload", {}).get("actor_type") == "human"
            for event in state.history
        )

    def _validate_gate_appeal(
        self,
        *,
        state: GateFlowState,
        decision: str,
        appeal_id: str,
    ) -> None:
        if not (
            state.stage == 3
            and state.status == "awaiting_review"
            and decision == "needs_human_review"
        ):
            if appeal_id.strip():
                raise ValueError(
                    "appeal_id는 Gate 3 needs_human_review 결정에만 연결할 수 있습니다."
                )
            return
        if not appeal_id.strip():
            raise ValueError(
                "Gate 3 needs_human_review에는 외부 재심 appeal이 필요합니다."
            )
        matches = [
            event
            for event in self._read_events()
            if event.get("event_type") == "appeal_packet_created"
            and event.get("payload", {}).get("appeal_id") == appeal_id
        ]
        if len(matches) != 1:
            raise ValueError(f"유효한 appeal packet이 아닙니다: {appeal_id}")
        payload = matches[0]["payload"]
        if (
            payload.get("trigger") != "gate_3_needs_human_review"
            or
            payload.get("candidate_id") != state.current_candidate_id
            or payload.get("task_id") != state.task_id
            or payload.get("gate_flow_id") != state.flow_id
            or payload.get("source_review_event_id")
            != state.source_review_event_id
        ):
            raise ValueError("appeal packet이 현재 Gate 상태와 결속되지 않습니다.")

    def _validate_human_review_resolution(
        self,
        *,
        state: GateFlowState,
        decision: str,
    ) -> None:
        if not (
            state.stage == 3
            and state.status == "awaiting_human_review"
        ):
            return

        appeal_id = self._active_gate_appeal_id(state)
        result = self._appeal_result(appeal_id)
        verdict = str(result.get("verdict", ""))
        if decision in {"revise", "reject"}:
            return
        if decision != "accepted_synthesis":
            raise ValueError(
                f"Gate 3 사람 검토에서 허용되지 않는 결정입니다: {decision}"
            )
        if verdict == "uphold":
            return
        if verdict == "uncertain":
            raise ValueError(
                "외부 재심이 uncertain이므로 최종 승인할 수 없습니다."
            )
        if verdict != "overturn":
            raise ValueError(f"지원하지 않는 외부 재심 verdict입니다: {verdict}")

        case_id = str(result.get("case_id", "")).strip()
        if not case_id:
            raise ValueError("overturn 결과에 연결된 case ID가 없습니다.")
        case_state = self.cases.get(case_id)
        if case_state.confirmation_status != "dismissed":
            raise ValueError(
                "overturn 결함 사건이 독립 확인에서 dismissed되기 전에는 "
                "최종 승인할 수 없습니다."
            )

    def _active_gate_appeal_id(self, state: GateFlowState) -> str:
        matches = [
            event
            for event in state.history
            if event.get("event_type") == "gate_decision_recorded"
            and event.get("payload", {}).get("candidate_id")
            == state.current_candidate_id
            and event.get("payload", {}).get("source_review_event_id")
            == state.source_review_event_id
            and event.get("payload", {}).get("decision")
            == "needs_human_review"
            and event.get("payload", {}).get("next_status")
            == "awaiting_human_review"
            and str(event.get("payload", {}).get("appeal_id", "")).strip()
        ]
        if not matches:
            raise ValueError(
                "Gate 3 사람 검토 상태에 연결된 appeal이 없습니다."
            )
        appeal_ids = {
            str(event["payload"]["appeal_id"]).strip()
            for event in matches
        }
        if len(appeal_ids) != 1:
            raise ValueError("Gate 3 사람 검토에 여러 appeal이 연결되어 있습니다.")
        return next(iter(appeal_ids))

    def _appeal_result(self, appeal_id: str) -> dict[str, Any]:
        events = self._read_events()
        packets = [
            event
            for event in events
            if event.get("event_type") == "appeal_packet_created"
            and event.get("payload", {}).get("appeal_id") == appeal_id
        ]
        if len(packets) != 1:
            raise ValueError(f"Gate 3 appeal packet이 없거나 중복입니다: {appeal_id}")
        results = [
            event
            for event in events
            if event.get("event_type") == "appeal_result_recorded"
            and event.get("payload", {}).get("appeal_id") == appeal_id
        ]
        if not results:
            raise ValueError("외부 재심 결과가 입력되기 전에는 Gate 3을 해소할 수 없습니다.")
        if len(results) > 1:
            raise ValueError(f"중복 외부 재심 결과입니다: {appeal_id}")

        packet = packets[0]["payload"]
        result = results[0]["payload"]
        if (
            result.get("candidate_id") != packet.get("candidate_id")
            or result.get("source_event_id") != packets[0].get("event_id")
        ):
            raise ValueError("외부 재심 결과와 packet의 결속이 손상되었습니다.")
        return result

    def _flow_for_candidate(self, candidate_id: str) -> list[dict[str, Any]]:
        return [
            event
            for event in self._read_events()
            if event.get("event_type") == "gate_flow_started"
            and event.get("payload", {}).get("candidate_id") == candidate_id
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
