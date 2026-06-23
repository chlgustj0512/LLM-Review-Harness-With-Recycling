from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class EventContractValidator:
    """append-only 사건을 원본과 전이 규칙에서 다시 검증한다."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def event(self, event_id: str, event_type: str | None = None) -> dict[str, Any]:
        matches = [
            event
            for event in self.read_events()
            if event.get("event_id") == event_id
        ]
        if len(matches) != 1:
            raise ValueError(f"source event가 없거나 중복입니다: {event_id}")
        event = matches[0]
        if event_type and event.get("event_type") != event_type:
            raise ValueError(
                f"source event type 불일치: expected={event_type}, "
                f"actual={event.get('event_type')}"
            )
        return event

    @staticmethod
    def gate_transition(stage: int, status: str, decision: str) -> tuple[int, str]:
        if status == "awaiting_human_review":
            allowed = (
                {"pass_to_next_gate", "reject", "revise"}
                if stage in {1, 2}
                else {"accepted_synthesis", "reject", "revise"}
            )
        elif stage in {1, 2}:
            allowed = {
                "pass_to_next_gate",
                "needs_human_review",
                "revise",
                "reject",
            }
        elif stage == 3:
            allowed = {
                "accepted_synthesis",
                "needs_human_review",
                "revise",
                "reject",
            }
        else:
            raise ValueError(f"유효하지 않은 Gate stage입니다: {stage}")
        if decision not in allowed:
            raise ValueError(
                f"Gate {stage} / {status}에서 허용되지 않는 decision: {decision}"
            )
        if decision == "pass_to_next_gate":
            return stage + 1, "awaiting_review"
        if decision == "revise":
            return stage, "awaiting_revision"
        if decision == "reject":
            return stage, "terminated_rejected"
        if decision == "needs_human_review":
            return stage, "awaiting_human_review"
        return stage, "completed_accepted"

    def validate_gate_decision(
        self,
        payload: dict[str, Any],
        *,
        flow_id: str,
        task_id: str,
        candidate_id: str,
        stage: int,
        status: str,
        source_review_event_id: str,
        source_review_status: str,
    ) -> tuple[int, str]:
        expected_stage, expected_status = self.gate_transition(
            stage,
            status,
            str(payload.get("decision", "")),
        )
        expected = {
            "flow_id": flow_id,
            "task_id": task_id,
            "candidate_id": candidate_id,
            "stage": stage,
            "previous_status": status,
            "next_stage": expected_stage,
            "next_status": expected_status,
            "source_review_event_id": source_review_event_id,
            "source_review_status": source_review_status,
        }
        self._require_equal(payload, expected, "Gate decision")
        self._require_actor(payload)
        return expected_stage, expected_status

    def validate_gate_revision(
        self,
        payload: dict[str, Any],
        *,
        flow_id: str,
        previous_candidate_id: str,
        stage: int,
        expected_next_status: str,
    ) -> None:
        expected = {
            "flow_id": flow_id,
            "previous_candidate_id": previous_candidate_id,
            "stage": stage,
            "next_status": expected_next_status,
        }
        self._require_equal(payload, expected, "Gate revision")
        for key in ("revised_candidate_id", "source_review_event_id", "actor_id", "reason"):
            if not str(payload.get(key, "")).strip():
                raise ValueError(f"Gate revision의 {key}가 비어 있습니다.")

    def validate_library_approval(
        self,
        proposed: dict[str, Any],
        approval: dict[str, Any],
    ) -> None:
        expected = {
            "part_id": proposed["part_id"],
            "previous_status": "proposed_unapproved",
            "new_status": "approved",
            "source_event_id": proposed["source_event_id"],
        }
        self._require_equal(approval, expected, "Library purpose approval")
        self._require_actor(approval)

    def validate_library_source(
        self,
        source_event_id: str,
        source_candidate_id: str,
    ) -> None:
        event = self.event(source_event_id)
        event_type = str(event.get("event_type", ""))
        payload = event.get("payload", {})
        extractors = {
            "review_batch_completed": lambda item: item.get("candidate_id"),
            "gate_decision_recorded": lambda item: item.get("candidate_id"),
            "appeal_packet_created": lambda item: item.get("candidate_id"),
            "appeal_result_recorded": lambda item: item.get("candidate_id"),
            "filter_escape_case_reported": lambda item: item.get(
                "candidate", {}
            ).get("candidate_id"),
            "appeal_overturn_case_reported": lambda item: item.get(
                "candidate", {}
            ).get("candidate_id"),
            "library_intake_candidate_recorded": lambda item: item.get(
                "source_candidate_id"
            ),
        }
        extractor = extractors.get(event_type)
        if extractor is None:
            raise ValueError(
                f"library 출처로 지원하지 않는 event type입니다: {event_type}"
            )
        bound_candidate_id = str(extractor(payload) or "").strip()
        if bound_candidate_id != source_candidate_id.strip():
            raise ValueError(
                "source event와 source_candidate_id가 일치하지 않습니다: "
                f"{bound_candidate_id} != {source_candidate_id.strip()}"
            )
        if event_type == "library_intake_candidate_recorded":
            self._validate_library_intake(payload)

    def validate_candidate_translation(
        self,
        payload: dict[str, Any],
    ) -> None:
        source = self.event(
            str(payload.get("source_review_event_id", "")),
            "review_batch_completed",
        )
        source_candidate_id = str(
            source.get("payload", {}).get("candidate_id", "")
        ).strip()
        expected = {
            "candidate_id": source_candidate_id,
            "source_language": "ko",
            "target_language": "en",
        }
        self._require_equal(payload, expected, "Candidate translation")
        for key in (
            "audit_id",
            "task_id",
            "source_text",
            "translated_text",
            "translator_model",
        ):
            if not str(payload.get(key, "")).strip():
                raise ValueError(f"Candidate translation의 {key}가 비어 있습니다.")

    def validate_post_review_audit(
        self,
        payload: dict[str, Any],
    ) -> None:
        translation = self.event(
            str(payload.get("translation_event_id", "")),
            "candidate_translation_recorded",
        )
        translated = translation.get("payload", {})
        expected = {
            "audit_id": translated.get("audit_id"),
            "candidate_id": translated.get("candidate_id"),
            "source_review_event_id": translated.get("source_review_event_id"),
            "english_candidate": translated.get("translated_text"),
            "non_blocking": True,
        }
        self._require_equal(payload, expected, "Post-review audit")
        if str(payload.get("status", "")) not in {"clear", "advisory"}:
            raise ValueError("완료된 사후 감사 상태는 clear 또는 advisory여야 합니다.")
        if not str(payload.get("auditor_model", "")).strip():
            raise ValueError("Post-review audit의 auditor_model이 비어 있습니다.")

    def validate_post_review_advisory(
        self,
        payload: dict[str, Any],
    ) -> None:
        source = self.event(
            str(payload.get("source_audit_event_id", "")),
            "post_review_audit_completed",
        )
        audit = source.get("payload", {})
        expected = {
            "audit_id": audit.get("audit_id"),
            "candidate_id": audit.get("candidate_id"),
            "language": "ko",
            "report": audit.get("korean_report"),
            "non_blocking": True,
        }
        self._require_equal(payload, expected, "Post-review advisory")

    def validate_final_delivery_packet(
        self,
        payload: dict[str, Any],
    ) -> None:
        all_events = self.read_events()
        gate_event = self.event(
            str(payload.get("source_gate_decision_event_id", "")),
            "gate_decision_recorded",
        )
        gate = gate_event.get("payload", {})
        expected_gate = {
            "flow_id": payload.get("flow_id"),
            "task_id": payload.get("task_id"),
            "candidate_id": payload.get("candidate_id"),
            "source_review_event_id": payload.get("source_review_event_id"),
            "stage": 3,
            "decision": "accepted_synthesis",
            "next_status": "completed_accepted",
        }
        self._require_equal(gate, expected_gate, "Final delivery Gate")
        review = self.event(
            str(payload.get("source_review_event_id", "")),
            "review_batch_completed",
        )
        if review.get("payload", {}).get("candidate_id") != payload.get(
            "candidate_id"
        ):
            raise ValueError("최종 제출 Review와 candidate 결속이 다릅니다.")
        expected_review_summary = [
            {
                "reviewer": item["reviewer"],
                "aspect": item["aspect"],
                "verdict": item["verdict"],
                "defect_found": item["defect_found"],
                "reasoning": item["reasoning"],
            }
            for item in review.get("payload", {}).get("reviews", [])
        ]
        expected_review = {
            "review_status": review.get("payload", {}).get("status"),
            "review_summary": expected_review_summary,
        }
        self._require_equal(payload, expected_review, "Final delivery Review")
        audit = self.event(str(payload.get("source_final_audit_event_id", "")))
        if audit.get("event_type") not in {
            "post_review_audit_completed",
            "post_review_audit_failed",
        }:
            raise ValueError("최종 제출 감사 사건 유형이 잘못됐습니다.")
        audit_payload = audit.get("payload", {})
        expected_audit = {
            "candidate_id": payload.get("candidate_id"),
            "source_review_event_id": payload.get("source_review_event_id"),
            "status": payload.get("audit_status"),
        }
        self._require_equal(audit_payload, expected_audit, "Final delivery audit")
        expected_audit_output = {
            "audit_advisory_korean": audit_payload.get("korean_report", ""),
            "audit_error": audit_payload.get("error", ""),
        }
        self._require_equal(
            payload,
            expected_audit_output,
            "Final delivery audit output",
        )
        gate_index = all_events.index(gate_event)
        audit_index = all_events.index(audit)
        if gate_index >= audit_index:
            raise ValueError(
                "최종 제출 감사는 accepted_synthesis 이후 새로 실행되어야 합니다."
            )
        candidate_events = [
            event
            for event in self.read_events()
            if event.get("event_type") == "candidate_generated"
            and event.get("payload", {}).get("candidate_id")
            == payload.get("candidate_id")
        ]
        if len(candidate_events) != 1:
            raise ValueError("최종 제출 후보가 없거나 중복입니다.")
        if candidate_events[0].get("payload", {}).get("text") != payload.get(
            "korean_final_text"
        ):
            raise ValueError("최종 제출 본문이 승인 후보 원문과 다릅니다.")
        status_map = {
            "clear": "ready_clear",
            "advisory": "ready_with_advisory",
            "failed": "ready_audit_failed",
        }
        if payload.get("status") != status_map.get(payload.get("audit_status")):
            raise ValueError("최종 제출 상태와 감사 상태가 일치하지 않습니다.")

    def validate_case_confirmation(
        self,
        payload: dict[str, Any],
        *,
        case_id: str,
        previous_status: str,
        source_event_id: str,
    ) -> None:
        new_status = str(payload.get("new_status", ""))
        if new_status not in {"confirmed", "dismissed"}:
            raise ValueError(f"유효하지 않은 case 확인 상태입니다: {new_status}")
        expected = {
            "case_id": case_id,
            "previous_status": previous_status,
            "source_event_id": source_event_id,
            "negative_example_status": (
                "eligible_pending_approval"
                if new_status == "confirmed"
                else "ineligible_dismissed"
            ),
            "negative_example_activated": False,
        }
        self._require_equal(payload, expected, "Case confirmation")
        self._require_actor(payload)
        for key in ("evidence", "reason"):
            if not str(payload.get(key, "")).strip():
                raise ValueError(f"Case confirmation의 {key}가 비어 있습니다.")

    def validate_activation(
        self,
        payload: dict[str, Any],
        *,
        case_id: str,
        source_event_id: str,
        expected_block_rule: str,
    ) -> None:
        expected = {
            "case_id": case_id,
            "source_event_id": source_event_id,
            "block_rule": expected_block_rule,
            "negative_example_status": "active_approved",
            "negative_example_activated": True,
        }
        self._require_equal(payload, expected, "Negative example activation")
        for key in ("readiness_id", "actor_id", "reason"):
            if not str(payload.get(key, "")).strip():
                raise ValueError(f"Negative example activation의 {key}가 비어 있습니다.")

    def validate_appeal_case(
        self,
        report: dict[str, Any],
    ) -> None:
        result_event = self.event(
            str(report.get("source_appeal_result_event_id", "")),
            "appeal_result_recorded",
        )
        result = result_event["payload"]
        packet_event = self.event(
            str(result.get("source_event_id", "")),
            "appeal_packet_created",
        )
        packet = packet_event["payload"]
        expected = {
            "source_appeal_id": result.get("appeal_id"),
            "source_appeal_result_event_id": result_event.get("event_id"),
            "task_id": packet.get("task_id"),
            "disposition": "appeal_overturn_candidate",
            "confirmation_status": "unconfirmed",
            "negative_example_status": "shadow_unconfirmed",
            "negative_example_activated": False,
        }
        self._require_equal(report, expected, "Appeal overturn case")
        if report.get("appeal_result") != result:
            raise ValueError("Appeal case의 내장 result가 원본과 다릅니다.")
        candidate = report.get("candidate", {})
        if candidate != {
            "candidate_id": packet.get("candidate_id"),
            "task_id": packet.get("task_id"),
            "text": packet.get("candidate_text"),
        }:
            raise ValueError("Appeal case의 candidate가 packet 원본과 다릅니다.")

    def validate_snapshot(
        self,
        payload: dict[str, Any],
        *,
        session_state: Any,
    ) -> None:
        finalize_matches = [
            event
            for event in session_state.history
            if event.get("event_id") == payload.get("source_finalize_event_id")
            and event.get("event_type") == "ratchet_candidate_finalized"
            and event.get("payload", {}).get("overall_result")
            != "bootstrap_champion"
        ]
        if len(finalize_matches) != 1:
            raise ValueError("Snapshot의 source finalize 사건이 없거나 잘못됐습니다.")
        expected = {
            "session_id": session_state.session_id,
            "purpose": session_state.purpose,
            "priority_line": session_state.priority_line,
            "overall_champion_candidate_id": (
                session_state.overall_champion_candidate_id
            ),
            "aspect_champions": session_state.aspect_champions,
            "status": "active",
        }
        self._require_equal(payload, expected, "Champion snapshot")
        if payload.get("actor_type") not in {"human", "tool"}:
            raise ValueError(
                f"유효하지 않은 actor_type: {payload.get('actor_type')}"
            )
        if not str(payload.get("actor_id", "")).strip():
            raise ValueError("Snapshot actor_id가 비어 있습니다.")
        if not str(payload.get("termination_reason", "")).strip():
            raise ValueError("Snapshot 종료 근거가 비어 있습니다.")

    def validate_ratchet_admission(
        self,
        payload: dict[str, Any],
        *,
        session_id: str,
        gate_state: Any,
        source_gate_event_id: str,
        bootstrap: bool,
    ) -> None:
        expected = {
            "session_id": session_id,
            "candidate_id": gate_state.current_candidate_id,
            "gate_flow_id": gate_state.flow_id,
            "source_gate_event_id": source_gate_event_id,
            "bootstrap": bootstrap,
            "task_id": gate_state.task_id,
        }
        self._require_equal(payload, expected, "Ratchet admission")
        if not str(payload.get("actor_id", "")).strip():
            raise ValueError("Ratchet admission actor_id가 비어 있습니다.")

    def validate_ratchet_comparison(
        self,
        payload: dict[str, Any],
        *,
        session_id: str,
        candidate_id: str,
        baseline_candidate_id: str,
        aspect: str,
    ) -> None:
        expected = {
            "session_id": session_id,
            "candidate_id": candidate_id,
            "baseline_candidate_id": baseline_candidate_id,
            "aspect": aspect,
        }
        self._require_equal(payload, expected, "Ratchet comparison")
        if payload.get("result") not in {
            "improved",
            "no_meaningful_change",
            "regressed",
        }:
            raise ValueError("Ratchet comparison result가 유효하지 않습니다.")
        self._require_actor(payload)

    def ratchet_finalization(
        self,
        *,
        candidate_id: str,
        priority_line: list[str],
        comparisons: dict[str, str],
        bootstrap: bool,
    ) -> tuple[dict[str, Any], list[tuple[str, str]]]:
        if bootstrap:
            expected = {
                "candidate_id": candidate_id,
                "overall_result": "bootstrap_champion",
                "decisive_aspect": "",
                "overall_promoted": True,
            }
            updates = [(aspect, "초기 챔피언") for aspect in priority_line]
            updates.append(("__overall__", "초기 전체 챔피언"))
            return expected, updates
        if set(comparisons) != set(priority_line):
            raise ValueError("Ratchet finalize 전에 모든 측면 비교가 필요합니다.")
        decisive_aspect = ""
        overall_result = "no_meaningful_change"
        overall_promoted = False
        for aspect in priority_line:
            result = comparisons[aspect]
            if result == "no_meaningful_change":
                continue
            decisive_aspect = aspect
            overall_result = result
            overall_promoted = result == "improved"
            break
        expected = {
            "candidate_id": candidate_id,
            "overall_result": overall_result,
            "decisive_aspect": decisive_aspect,
            "overall_promoted": overall_promoted,
        }
        updates = [
            (aspect, "측면 상대 개선")
            for aspect in priority_line
            if comparisons[aspect] == "improved"
        ]
        if overall_promoted:
            updates.append(
                ("__overall__", f"사전식 첫 결정 측면: {decisive_aspect}")
            )
        return expected, updates

    def validate_ratchet_finalize(
        self,
        payload: dict[str, Any],
        *,
        session_id: str,
        expected: dict[str, Any],
        bootstrap: bool,
    ) -> None:
        self._require_equal(
            payload,
            {"session_id": session_id, **expected},
            "Ratchet finalize",
        )
        if not bootstrap and not str(payload.get("actor_id", "")).strip():
            raise ValueError("Ratchet finalize actor_id가 비어 있습니다.")

    def validate_champion_update(
        self,
        payload: dict[str, Any],
        *,
        session_id: str,
        aspect: str,
        previous_candidate_id: str,
        new_candidate_id: str,
        reason: str,
    ) -> None:
        self._require_equal(
            payload,
            {
                "session_id": session_id,
                "aspect": aspect,
                "previous_candidate_id": previous_candidate_id,
                "new_candidate_id": new_candidate_id,
                "reason": reason,
            },
            "Ratchet champion update",
        )

    def _validate_library_intake(self, payload: dict[str, Any]) -> None:
        expected = {
            "metadata_status": "incomplete",
            "purpose_status": "missing",
            "searchable": False,
        }
        self._require_equal(payload, expected, "Library intake")
        content = str(payload.get("content", "")).strip()
        if not content:
            raise ValueError("Library intake content가 비어 있습니다.")
        source_kind = str(payload.get("source_kind", ""))
        source = self.event(str(payload.get("source_event_id", "")))
        source_payload = source.get("payload", {})
        if source_kind == "external_appeal":
            if (
                source.get("event_type") != "appeal_result_recorded"
                or source_payload.get("candidate_id")
                != payload.get("source_candidate_id")
                or str(source_payload.get("salvageable_part", "")).strip()
                != content
            ):
                raise ValueError("외부 Appeal 입고 출처가 원본과 다릅니다.")
            return
        if source_kind in {"internal_review", "internal_revision_review"}:
            if source.get("event_type") != "review_batch_completed":
                raise ValueError("내부 Review 입고의 source event type이 잘못됐습니다.")
            reviews = source_payload.get("reviews", [])
        elif source_kind == "internal_adversary_review":
            if source.get("event_type") != "filter_escape_case_reported":
                raise ValueError("궤변 Review 입고의 source event type이 잘못됐습니다.")
            reviews = source_payload.get("review_batch", {}).get("reviews", [])
        else:
            raise ValueError(f"지원하지 않는 library intake source_kind: {source_kind}")
        matches = [
            review
            for review in reviews
            if str(review.get("salvageable_part", "")).strip() == content
            and review.get("reviewer") == payload.get("source_reviewer")
            and review.get("aspect") == payload.get("source_aspect")
            and review.get("verdict") == payload.get("source_verdict")
            and review.get("verdict") in {"reject", "revise"}
            and review.get("defect_found") is True
        ]
        if len(matches) != 1:
            raise ValueError("내부 Review 입고 출처가 원본 심사와 다릅니다.")

    @staticmethod
    def _require_actor(payload: dict[str, Any]) -> None:
        if payload.get("actor_type") not in {"human", "tool"}:
            raise ValueError(f"유효하지 않은 actor_type: {payload.get('actor_type')}")
        if not str(payload.get("actor_id", "")).strip():
            raise ValueError("actor_id가 비어 있습니다.")
        if not str(payload.get("reason", "")).strip():
            raise ValueError("reason이 비어 있습니다.")

    @staticmethod
    def _require_equal(
        payload: dict[str, Any],
        expected: dict[str, Any],
        label: str,
    ) -> None:
        for key, value in expected.items():
            if payload.get(key) != value:
                raise ValueError(
                    f"{label} 계약 위반: {key} expected={value!r}, "
                    f"actual={payload.get(key)!r}"
                )

    def read_events(self) -> list[dict[str, Any]]:
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
            if not str(event.get("event_id", "")).strip():
                raise ValueError(f"event_id가 비어 있습니다: line {line_number}")
            events.append(event)
        return events
