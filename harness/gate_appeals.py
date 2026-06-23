from __future__ import annotations

from pathlib import Path

from harness.appeals import AppealService
from harness.gates import GateLedger
from harness.logging import EventLog
from harness.models import AppealPacket, GateFlowState


class GateAppealCoordinator:
    """Gate 3 사람 검토 결정과 외부 재심 문서를 하나의 흐름으로 묶는다."""

    def __init__(self, log_path: Path) -> None:
        self.events = EventLog(log_path)
        self.gates = GateLedger(log_path)
        self.appeals = AppealService(log_path)

    def record_decision(
        self,
        *,
        flow_id: str,
        decision: str,
        actor_type: str,
        actor_id: str,
        reason: str,
    ) -> tuple[GateFlowState, AppealPacket | None]:
        before, _, _, _ = self.gates.validate_decision_request(
            flow_id=flow_id,
            decision=decision,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            require_appeal=False,
        )
        packet: AppealPacket | None = None
        if (
            before.stage == 3
            and before.status == "awaiting_review"
            and decision == "needs_human_review"
        ):
            review_event = self.gates.candidates.review_event(
                before.source_review_event_id
            )
            packet = self.appeals.ensure_gate_appeal(
                task_payload=self.gates.candidates.task(before.task_id),
                candidate_payload=self.gates.candidates.candidate(
                    before.current_candidate_id
                ),
                review_payload=review_event["payload"],
                gate_flow_id=flow_id,
                source_review_event_id=before.source_review_event_id,
            )

        after = self.gates.record_decision(
            flow_id=flow_id,
            decision=decision,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            appeal_id=packet.appeal_id if packet else "",
        )
        if packet is not None:
            decision_event = after.history[-1]
            self.events.append(
                "gate_appeal_connected",
                {
                    "flow_id": flow_id,
                    "stage": 3,
                    "candidate_id": before.current_candidate_id,
                    "source_review_event_id": before.source_review_event_id,
                    "gate_decision_event_id": decision_event["event_id"],
                    "appeal_id": packet.appeal_id,
                    "document_path": packet.document_path,
                },
            )
        return after, packet
