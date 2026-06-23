from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from harness.candidates import CandidateRegistry
from harness.event_contracts import EventContractValidator
from harness.gates import GateLedger
from harness.logging import EventLog
from harness.models import Candidate, FinalDeliveryPacket, Task
from harness.post_review_audit import PostReviewAuditService


class DeliveryLedger:
    """Gate 3 승인본과 최종 사후 감사를 사용자 제출 묶음으로 결속한다."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.events = EventLog(path)
        self.contracts = EventContractValidator(path)
        self.gates = GateLedger(path)
        self.candidates = CandidateRegistry(path)

    def create(
        self,
        *,
        flow_id: str,
        auditor: PostReviewAuditService,
        output_dir: Path,
    ) -> FinalDeliveryPacket:
        if self._delivery_events(flow_id=flow_id):
            raise ValueError(f"Gate flow에 이미 최종 제출 묶음이 있습니다: {flow_id}")
        state = self.gates.get(flow_id)
        if state.status != "completed_accepted" or state.stage != 3:
            raise ValueError(
                "최종 제출 묶음은 Gate 3 accepted_synthesis 완료 후에만 만들 수 있습니다."
            )
        gate_event = self._accepted_gate_event(state.history)
        task_payload = self.candidates.task(state.task_id)
        candidate_payload = self.candidates.candidate(state.current_candidate_id)
        review_event = self.candidates.review_event(state.source_review_event_id)
        candidate = Candidate(
            candidate_id=state.current_candidate_id,
            task_id=state.task_id,
            text=str(candidate_payload["text"]),
        )
        task = Task(
            task_id=state.task_id,
            goal=str(task_payload["goal"]),
            constraints=list(task_payload.get("constraints", [])),
        )

        audit = auditor.audit(
            task=task,
            candidate=candidate,
            source_review_event_id=state.source_review_event_id,
        )
        audit_event = self._audit_event(audit.audit_id)
        delivery_id = f"delivery-{uuid4().hex[:12]}"
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = (output_dir / f"{delivery_id}.json").resolve()
        markdown_path = (output_dir / f"{delivery_id}.md").resolve()
        review_payload = review_event["payload"]
        status = {
            "clear": "ready_clear",
            "advisory": "ready_with_advisory",
            "failed": "ready_audit_failed",
        }[audit.status]
        packet = FinalDeliveryPacket(
            delivery_id=delivery_id,
            flow_id=flow_id,
            task_id=state.task_id,
            candidate_id=state.current_candidate_id,
            source_gate_decision_event_id=str(gate_event["event_id"]),
            source_review_event_id=state.source_review_event_id,
            source_final_audit_event_id=str(audit_event["event_id"]),
            status=status,
            korean_final_text=candidate.text,
            review_status=str(review_payload["status"]),
            review_summary=[
                {
                    "reviewer": item["reviewer"],
                    "aspect": item["aspect"],
                    "verdict": item["verdict"],
                    "defect_found": item["defect_found"],
                    "reasoning": item["reasoning"],
                }
                for item in review_payload.get("reviews", [])
            ],
            audit_status=audit.status,
            audit_advisory_korean=audit.korean_report,
            audit_error=audit.error,
            json_path=str(json_path),
            markdown_path=str(markdown_path),
        )
        packet.validate()
        payload = packet.to_dict()
        self.contracts.validate_final_delivery_packet(payload)
        try:
            json_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            markdown_path.write_text(
                self._render_markdown(packet),
                encoding="utf-8",
            )
            self.events.append("final_delivery_packet_created", payload)
        except Exception:
            json_path.unlink(missing_ok=True)
            markdown_path.unlink(missing_ok=True)
            raise
        return self.get(delivery_id=delivery_id)

    def get(
        self,
        *,
        delivery_id: str = "",
        flow_id: str = "",
    ) -> FinalDeliveryPacket:
        if bool(delivery_id.strip()) == bool(flow_id.strip()):
            raise ValueError("delivery_id 또는 flow_id 중 하나만 지정해야 합니다.")
        matches = self._delivery_events(
            delivery_id=delivery_id.strip(),
            flow_id=flow_id.strip(),
        )
        if len(matches) != 1:
            raise ValueError("최종 제출 묶음이 없거나 중복입니다.")
        payload = matches[0]["payload"]
        self.contracts.validate_final_delivery_packet(payload)
        packet = FinalDeliveryPacket(**payload)
        packet.validate()
        return packet

    def _delivery_events(
        self,
        *,
        delivery_id: str = "",
        flow_id: str = "",
    ) -> list[dict[str, Any]]:
        return [
            event
            for event in self.contracts.read_events()
            if event.get("event_type") == "final_delivery_packet_created"
            and (
                not delivery_id
                or event.get("payload", {}).get("delivery_id") == delivery_id
            )
            and (
                not flow_id
                or event.get("payload", {}).get("flow_id") == flow_id
            )
        ]

    @staticmethod
    def _accepted_gate_event(history: list[dict[str, Any]]) -> dict[str, Any]:
        matches = [
            event
            for event in history
            if event.get("event_type") == "gate_decision_recorded"
            and event.get("payload", {}).get("decision") == "accepted_synthesis"
            and event.get("payload", {}).get("next_status") == "completed_accepted"
        ]
        if len(matches) != 1:
            raise ValueError("최종 accepted_synthesis 사건이 없거나 중복입니다.")
        return matches[0]

    def _audit_event(self, audit_id: str) -> dict[str, Any]:
        matches = [
            event
            for event in self.contracts.read_events()
            if event.get("event_type")
            in {"post_review_audit_completed", "post_review_audit_failed"}
            and event.get("payload", {}).get("audit_id") == audit_id
        ]
        if len(matches) != 1:
            raise ValueError("최종 사후 감사 사건이 없거나 중복입니다.")
        return matches[0]

    @staticmethod
    def _render_markdown(packet: FinalDeliveryPacket) -> str:
        review_lines = "\n".join(
            (
                f"- {item['reviewer']} / {item['aspect']}: "
                f"{item['verdict']} — {item['reasoning']}"
            )
            for item in packet.review_summary
        ) or "- 기록된 개별 심사 없음"
        audit_section = (
            packet.audit_advisory_korean
            if packet.audit_status == "advisory"
            else (
                f"감사 실패: {packet.audit_error}"
                if packet.audit_status == "failed"
                else "추가 보강 의견 없음."
            )
        )
        return (
            "# 최종 제출 묶음\n\n"
            f"- Delivery ID: `{packet.delivery_id}`\n"
            f"- Gate flow: `{packet.flow_id}`\n"
            f"- 상태: `{packet.status}`\n\n"
            "## 최종 한국어 산출물\n\n"
            f"{packet.korean_final_text}\n\n"
            "## 기존 심사 요약\n\n"
            f"{review_lines}\n\n"
            "## 비차단 OLMo 최종 감사\n\n"
            f"{audit_section}\n"
        )
