from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from harness.logging import EventLog
from harness.models import AppealPacket, AppealResultEvent, Candidate, ReviewBatch, Task


class AppealService:
    def __init__(self, log_path: Path, output_dir: Path | None = None) -> None:
        self.log_path = log_path
        self.events = EventLog(log_path)
        self.output_dir = output_dir or log_path.parent / "appeals"

    def maybe_create(
        self,
        task: Task,
        candidate: Candidate,
        review_batch: ReviewBatch,
    ) -> AppealPacket | None:
        trigger = self._trigger(review_batch)
        if trigger is None:
            return None
        return self.create(task, candidate, review_batch, trigger)

    def create(
        self,
        task: Task,
        candidate: Candidate,
        review_batch: ReviewBatch,
        trigger: str,
        *,
        gate_flow_id: str = "",
        source_review_event_id: str = "",
    ) -> AppealPacket:
        appeal_id = f"appeal-{uuid4().hex[:12]}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        document_path = self.output_dir / f"{appeal_id}.md"
        suspicion, question = self._suspicion_and_question(review_batch, trigger)
        packet = AppealPacket(
            appeal_id=appeal_id,
            candidate_id=candidate.candidate_id,
            task_id=task.task_id,
            trigger=trigger,
            domain=",".join(review_batch.required_aspects) or "unspecified",
            priority_line="미구현 — Gate/래칫 단계에서 주입 예정",
            task_goal=task.goal,
            constraints=list(task.constraints),
            candidate_text=candidate.text,
            first_review=review_batch.to_dict(),
            hard_checks=[],
            suspicion=suspicion,
            question=question,
            document_path=str(document_path.resolve()),
            gate_flow_id=gate_flow_id,
            source_review_event_id=source_review_event_id,
        )
        document_path.write_text(self.render(packet), encoding="utf-8")
        event = self.events.append("appeal_packet_created", packet.to_dict())
        self.events.append(
            "appeal_document_written",
            {
                "appeal_id": appeal_id,
                "candidate_id": candidate.candidate_id,
                "document_path": packet.document_path,
                "source_event_id": event["event_id"],
            },
        )
        return packet

    def ensure_gate_appeal(
        self,
        *,
        task_payload: dict[str, Any],
        candidate_payload: dict[str, Any],
        review_payload: dict[str, Any],
        gate_flow_id: str,
        source_review_event_id: str,
    ) -> AppealPacket:
        existing = self._gate_packet(
            gate_flow_id=gate_flow_id,
            candidate_id=str(candidate_payload["candidate_id"]),
            source_review_event_id=source_review_event_id,
        )
        if existing is not None:
            return AppealPacket(**existing["payload"])

        task = Task(
            task_id=str(task_payload["task_id"]),
            goal=str(task_payload["goal"]),
            constraints=list(task_payload.get("constraints", [])),
        )
        candidate = Candidate(
            candidate_id=str(candidate_payload["candidate_id"]),
            task_id=str(candidate_payload["task_id"]),
            text=str(candidate_payload["text"]),
        )
        return self._create_from_payload(
            task=task,
            candidate=candidate,
            review_payload=review_payload,
            trigger="gate_3_needs_human_review",
            gate_flow_id=gate_flow_id,
            source_review_event_id=source_review_event_id,
        )

    def _create_from_payload(
        self,
        *,
        task: Task,
        candidate: Candidate,
        review_payload: dict[str, Any],
        trigger: str,
        gate_flow_id: str,
        source_review_event_id: str,
    ) -> AppealPacket:
        appeal_id = f"appeal-{uuid4().hex[:12]}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        document_path = self.output_dir / f"{appeal_id}.md"
        packet = AppealPacket(
            appeal_id=appeal_id,
            candidate_id=candidate.candidate_id,
            task_id=task.task_id,
            trigger=trigger,
            domain=",".join(review_payload.get("required_aspects", []))
            or "unspecified",
            priority_line="Gate 3 최종 종합 판정",
            task_goal=task.goal,
            constraints=list(task.constraints),
            candidate_text=candidate.text,
            first_review=review_payload,
            hard_checks=[],
            suspicion="Gate 3에서 최종 승인 전 외부 독립 검토가 요청됨",
            question=(
                "1차 심사를 단서 없이 재검했을 때 후보를 유지·뒤집기·"
                "불확정 중 무엇으로 판정하는가?"
            ),
            document_path=str(document_path.resolve()),
            gate_flow_id=gate_flow_id,
            source_review_event_id=source_review_event_id,
        )
        document_path.write_text(self.render(packet), encoding="utf-8")
        event = self.events.append("appeal_packet_created", packet.to_dict())
        self.events.append(
            "appeal_document_written",
            {
                "appeal_id": appeal_id,
                "candidate_id": candidate.candidate_id,
                "document_path": packet.document_path,
                "source_event_id": event["event_id"],
                "gate_flow_id": gate_flow_id,
                "source_review_event_id": source_review_event_id,
            },
        )
        return packet

    def import_result(
        self,
        *,
        appeal_id: str,
        candidate_id: str,
        verdict: str,
        actor_id: str,
        defects: list[dict[str, str]] | None = None,
        salvageable_part: str = "",
        feedback_to_thesis: str = "",
    ) -> dict[str, Any]:
        packet_event = self._packet_event(appeal_id)
        packet = packet_event["payload"]
        if packet.get("candidate_id") != candidate_id:
            raise ValueError("appeal packet과 candidate_id가 일치하지 않습니다.")
        if self._result_events(appeal_id):
            raise ValueError("이미 외부 재심 결과가 입력된 appeal입니다.")
        if verdict not in {"uphold", "overturn", "uncertain"}:
            raise ValueError("verdict는 uphold, overturn, uncertain 중 하나여야 합니다.")
        if not actor_id.strip():
            raise ValueError("actor_id가 필요합니다.")
        normalized_defects = self._validate_defects(defects or [])
        if verdict == "overturn" and not normalized_defects:
            raise ValueError("overturn에는 구체적인 defect가 하나 이상 필요합니다.")
        case_id = (
            f"appeal-overturn-case-{uuid4().hex[:8]}"
            if verdict == "overturn"
            else ""
        )

        result = AppealResultEvent(
            appeal_id=appeal_id,
            candidate_id=candidate_id,
            reviewer="external_claude",
            verdict=verdict,  # type: ignore[arg-type]
            defects=normalized_defects,
            salvageable_part=salvageable_part.strip(),
            feedback_to_thesis=feedback_to_thesis.strip(),
            actor_id=actor_id.strip(),
            source_event_id=str(packet_event.get("event_id", "")),
            requires_human_or_tool_confirmation=verdict in {"overturn", "uncertain"},
            case_id=case_id,
        )
        result_event = self.events.append(
            "appeal_result_recorded",
            result.to_dict(),
        )
        if verdict == "overturn":
            self.events.append(
                "appeal_overturn_case_reported",
                {
                    "case_id": case_id,
                    "task_id": str(packet["task_id"]),
                    "candidate": {
                        "candidate_id": candidate_id,
                        "task_id": str(packet["task_id"]),
                        "text": str(packet["candidate_text"]),
                    },
                    "review_batch": dict(packet["first_review"]),
                    "appeal_result": result.to_dict(),
                    "disposition": "appeal_overturn_candidate",
                    "confirmation_status": "unconfirmed",
                    "negative_example_status": "shadow_unconfirmed",
                    "negative_example_activated": False,
                    "source_kind": "external_appeal_overturn",
                    "source_appeal_id": appeal_id,
                    "source_appeal_result_event_id": result_event["event_id"],
                    "gate_flow_id": str(packet.get("gate_flow_id", "")),
                },
            )
        if result.salvageable_part:
            self.events.append(
                "library_intake_candidate_recorded",
                {
                    "content": result.salvageable_part,
                    "source_kind": "external_appeal",
                    "source_event_id": result_event["event_id"],
                    "source_appeal_id": appeal_id,
                    "source_candidate_id": candidate_id,
                    "metadata_status": "incomplete",
                    "purpose_status": "missing",
                    "searchable": False,
                },
            )
        return result_event

    def render(self, packet: AppealPacket) -> str:
        constraints = "\n".join(f"- {item}" for item in packet.constraints) or "- 없음"
        reviews = json.dumps(packet.first_review, ensure_ascii=False, indent=2)
        hard_checks = "\n".join(f"- {item}" for item in packet.hard_checks) or "- 없음"
        return f"""# 재심 요청 — 다측면 심사 하네스

너는 이 후보의 외부 재심관(2차 독립 검증)이다. 내부 심사관들이 함께 놓쳤을
결함을 단서 없이 찾는 것이 임무다. 친절한 총평보다 1차 판정을 유지(uphold),
뒤집기(overturn), 불확정(uncertain) 중 하나로 판정하라.

중요: 너의 판정도 2차 의견이다. 결함 확정은 별도의 사람 또는 도구 확인이 필요하다.

## 1. 메타

- Appeal ID: {packet.appeal_id}
- 후보 ID: {packet.candidate_id}
- 도메인: {packet.domain}
- 우선순위 줄: {packet.priority_line}
- 재심 트리거: {packet.trigger}

## 2. 원 과제

목표: {packet.task_goal}

핵심 조건:
{constraints}

## 3. 후보 원문

```text
{packet.candidate_text}
```

## 4. 1차 심사 결과

```json
{reviews}
```

## 5. 하드체크

{hard_checks}

## 6. 의심 지점

{packet.suspicion}

## 7. 재심 질문

{packet.question}

## 8. 요구 출력

아래 YAML 형식으로만 답하라.

```yaml
appeal_result:
  appeal_id: "{packet.appeal_id}"
  candidate_id: "{packet.candidate_id}"
  reviewer: "external_claude"
  verdict: "uphold | overturn | uncertain"
  defects:
    - type: "..."
      where: "..."
      why: "..."
  salvageable_part: "..."
  feedback_to_thesis: "..."
  requires_human_or_tool_confirmation: true
```
"""

    @staticmethod
    def _trigger(review_batch: ReviewBatch) -> str | None:
        if review_batch.conflicting_aspects:
            return "reviewer_conflict"
        if review_batch.empty_aspects:
            return "empty_aspect"
        if any(review.verdict == "needs_human_review" for review in review_batch.reviews):
            return "needs_human_review"
        if any(
            review.dependency == "dependent_core" and review.verdict == "revise"
            for review in review_batch.reviews
        ):
            return "dependent_core_boundary"
        return None

    @staticmethod
    def _suspicion_and_question(
        review_batch: ReviewBatch,
        trigger: str,
    ) -> tuple[str, str]:
        if trigger == "reviewer_conflict":
            aspects = ", ".join(review_batch.conflicting_aspects)
            return (
                f"같은 측면의 1차 판정이 충돌함: {aspects}",
                "충돌한 판정 중 어느 쪽이 더 타당하며, 놓친 구체 결함이 있는가?",
            )
        if trigger == "empty_aspect":
            aspects = ", ".join(review_batch.empty_aspects)
            return (
                f"필수 측면을 관할한 내부 심사관이 없음: {aspects}",
                "비어 있는 측면에서 후보를 무너뜨리는 결함이 있는가?",
            )
        if trigger == "needs_human_review":
            return (
                "내부 심사관이 AI 단독 확정을 거부함",
                "단서 없이 재검했을 때 유지·뒤집기·불확정 중 무엇인가?",
            )
        return (
            "종속핵심 측면이 통과와 탈락 경계인 revise 상태임",
            "핵심 논리·정확성 결함이 실제로 존재하는가?",
        )

    def _packet_event(self, appeal_id: str) -> dict[str, Any]:
        matches = [
            event
            for event in self._read_events()
            if event.get("event_type") == "appeal_packet_created"
            and event.get("payload", {}).get("appeal_id") == appeal_id
        ]
        if not matches:
            raise ValueError(f"appeal packet을 찾을 수 없습니다: {appeal_id}")
        if len(matches) > 1:
            raise ValueError(f"중복 appeal packet: {appeal_id}")
        return matches[0]

    def _gate_packet(
        self,
        *,
        gate_flow_id: str,
        candidate_id: str,
        source_review_event_id: str,
    ) -> dict[str, Any] | None:
        matches = [
            event
            for event in self._read_events()
            if event.get("event_type") == "appeal_packet_created"
            and event.get("payload", {}).get("trigger")
            == "gate_3_needs_human_review"
            and event.get("payload", {}).get("gate_flow_id") == gate_flow_id
            and event.get("payload", {}).get("candidate_id") == candidate_id
            and event.get("payload", {}).get("source_review_event_id")
            == source_review_event_id
        ]
        if len(matches) > 1:
            raise ValueError(
                f"중복 Gate 3 appeal packet입니다: {gate_flow_id}"
            )
        return matches[0] if matches else None

    def _result_events(self, appeal_id: str) -> list[dict[str, Any]]:
        return [
            event
            for event in self._read_events()
            if event.get("event_type") == "appeal_result_recorded"
            and event.get("payload", {}).get("appeal_id") == appeal_id
        ]

    @staticmethod
    def _validate_defects(defects: list[dict[str, str]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for defect in defects:
            item = {
                "type": str(defect.get("type", "")).strip(),
                "where": str(defect.get("where", "")).strip(),
                "why": str(defect.get("why", "")).strip(),
            }
            if not all(item.values()):
                raise ValueError("각 defect에는 type, where, why가 모두 필요합니다.")
            normalized.append(item)
        return normalized

    def _read_events(self) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line_number, line in enumerate(
            self.log_path.read_text(encoding="utf-8").splitlines(),
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
