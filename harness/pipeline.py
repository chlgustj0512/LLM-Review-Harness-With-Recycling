from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from harness.adversary import AdversaryEngine, argument_test_out_of_scope
from harness.appeals import AppealService
from harness.backends import Backend
from harness.casework import CaseLedger
from harness.gates import GateLedger
from harness.logging import EventLog
from harness.model_pipeline import RoleModelPipeline
from harness.models import (
    Candidate,
    FilterEscapeCaseReport,
    Probe,
    ProbeResult,
    ReviewBatch,
    Task,
)
from harness.orchestrator import ReviewerOrchestrator
from harness.post_review_audit import PostReviewAuditService
from harness.reviewers import ReviewerRegistry


class Harness:
    def __init__(
        self,
        backend: Backend,
        log_path: Path,
        registry: ReviewerRegistry | None = None,
        reviewer_ids: list[str] | None = None,
    ) -> None:
        self.backend = backend
        self.events = EventLog(log_path)
        self.case_ledger = CaseLedger(log_path)
        self.gates = GateLedger(log_path)
        self.appeals = AppealService(log_path)
        self.registry = registry or ReviewerRegistry()
        self.reviewers = self.registry.select(reviewer_ids)
        self.orchestrator = ReviewerOrchestrator(backend, self.reviewers)
        self.adversary = AdversaryEngine(backend, self.orchestrator)
        self.last_appeal_packet = None
        self.last_gate_flow = None
        self.last_post_review_audit = None
        self.post_review_auditor = None
        if isinstance(backend, RoleModelPipeline) and backend.post_audit_enabled:
            assert backend.translator_backend is not None
            assert backend.post_audit_backend is not None
            self.post_review_auditor = PostReviewAuditService(
                translator=backend.translator_backend,  # type: ignore[arg-type]
                auditor=backend.post_audit_backend,  # type: ignore[arg-type]
                events=self.events,
            )

    def run(
        self,
        goal: str,
        constraints: list[str] | None = None,
        required_aspects: list[str] | None = None,
    ) -> tuple[Candidate, ReviewBatch]:
        task = Task(
            task_id=f"task-{uuid4().hex[:8]}",
            goal=goal.strip(),
            constraints=constraints or [],
        )
        if not task.goal:
            raise ValueError("goal은 비어 있을 수 없습니다.")

        self.events.append("task_created", asdict(task))
        active_rules = self.case_ledger.active_negative_examples()
        candidate = Candidate(
            candidate_id=f"candidate-{uuid4().hex[:8]}",
            task_id=task.task_id,
            text=self.backend.generate_candidate(task, active_rules),
        )
        if active_rules:
            self.events.append(
                "negative_example_context_applied",
                {
                    "task_id": task.task_id,
                    "case_ids": [rule.case_id for rule in active_rules],
                    "rule_count": len(active_rules),
                },
            )
        self.events.append("candidate_generated", asdict(candidate))

        review_batch = self.orchestrator.review(task, candidate, required_aspects)
        review_event = self.events.append(
            "review_batch_completed",
            review_batch.to_dict(),
        )
        gate_flow = self.gates.start(
            task_id=task.task_id,
            candidate_id=candidate.candidate_id,
            source_review_event_id=review_event["event_id"],
        )
        self.last_gate_flow = gate_flow
        appeal_packet = self.appeals.maybe_create(task, candidate, review_batch)
        self.last_appeal_packet = appeal_packet
        if appeal_packet is not None:
            self.events.append(
                "appeal_trigger_connected",
                {
                    "appeal_id": appeal_packet.appeal_id,
                    "candidate_id": candidate.candidate_id,
                    "trigger": appeal_packet.trigger,
                    "document_path": appeal_packet.document_path,
                },
            )

        self._record_review_artifacts(
            candidate_id=candidate.candidate_id,
            review_batch=review_batch,
            source_event_id=review_event["event_id"],
            source_kind="internal_review",
        )
        self._run_post_review_audit(
            task=task,
            candidate=candidate,
            source_review_event_id=review_event["event_id"],
        )
        return candidate, review_batch

    def run_adversary(
        self,
        goal: str,
        constraints: list[str] | None = None,
        required_aspects: list[str] | None = None,
    ) -> FilterEscapeCaseReport:
        task = Task(
            task_id=f"adversary-task-{uuid4().hex[:8]}",
            goal=goal.strip(),
            constraints=constraints or [],
        )
        if not task.goal:
            raise ValueError("goal은 비어 있을 수 없습니다.")
        scope_text = "\n".join([task.goal, *task.constraints])
        if argument_test_out_of_scope(scope_text):
            self.events.append(
                "argument_defect_test_out_of_scope",
                {
                    "task_id": task.task_id,
                    "goal": task.goal,
                    "constraints": task.constraints,
                    "status": "OUT_OF_SCOPE",
                    "reason": (
                        "논증·주장·유추 구조 밖의 시스템 공격 또는 조작 요청"
                    ),
                },
            )
            raise ValueError(
                "OUT_OF_SCOPE: 논증 결함 테스트 생성기는 외부 시스템 공격·"
                "권한 우회·도구 실행·메모리 변조·사용자 조작·보안 취약점 악용·"
                "사회공학을 생성하지 않습니다."
            )
        self.events.append("adversary_task_created", asdict(task))
        report = self.adversary.run(task, required_aspects)
        self.last_gate_flow = None
        report_event = self.events.append(
            "filter_escape_case_reported",
            report.to_dict(),
        )
        appeal_packet = self.appeals.maybe_create(
            task,
            report.candidate,
            report.review_batch,
        )
        self.last_appeal_packet = appeal_packet
        if appeal_packet is not None:
            self.events.append(
                "appeal_trigger_connected",
                {
                    "appeal_id": appeal_packet.appeal_id,
                    "candidate_id": report.candidate.candidate_id,
                    "trigger": appeal_packet.trigger,
                    "document_path": appeal_packet.document_path,
                },
            )
        self.events.append(
            "negative_example_case_shadowed",
            {
                "case_id": report.case_id,
                "candidate_id": report.candidate.candidate_id,
                "confirmation_status": report.confirmation_status,
                "status": report.negative_example_status,
                "activated": report.negative_example_activated,
            },
        )
        self._record_review_artifacts(
            candidate_id=report.candidate.candidate_id,
            review_batch=report.review_batch,
            source_event_id=report_event["event_id"],
            source_kind="internal_adversary_review",
        )
        if report.disposition == "review_inconclusive":
            self.events.append(
                "adversary_review_inconclusive",
                {
                    "case_id": report.case_id,
                    "candidate_id": report.candidate.candidate_id,
                    "review_status": report.review_batch.status,
                    "empty_aspects": report.review_batch.empty_aspects,
                    "conflicting_aspects": report.review_batch.conflicting_aspects,
                    "appeal_id": (
                        appeal_packet.appeal_id
                        if appeal_packet is not None
                        else ""
                    ),
                },
            )
        return report

    def submit_gate_revision(
        self,
        *,
        flow_id: str,
        revised_text: str,
        actor_id: str,
        reason: str,
        required_aspects: list[str] | None = None,
    ) -> tuple[Candidate, ReviewBatch]:
        state = self.gates.get(flow_id)
        if state.status != "awaiting_revision":
            raise ValueError(
                f"수정본을 제출할 수 없는 Gate 상태입니다: {state.status}"
            )
        if not revised_text.strip():
            raise ValueError("수정 후보 본문은 비어 있을 수 없습니다.")

        task_payload = self.gates.candidates.task(state.task_id)
        task = Task(
            task_id=state.task_id,
            goal=str(task_payload["goal"]),
            constraints=list(task_payload.get("constraints", [])),
        )
        candidate = Candidate(
            candidate_id=f"candidate-{uuid4().hex[:8]}",
            task_id=task.task_id,
            text=revised_text.strip(),
        )
        self.events.append(
            "candidate_generated",
            {
                **asdict(candidate),
                "origin": "gate_revision",
                "flow_id": flow_id,
                "previous_candidate_id": state.current_candidate_id,
            },
        )
        review_batch = self.orchestrator.review(
            task,
            candidate,
            required_aspects,
        )
        review_event = self.events.append(
            "review_batch_completed",
            review_batch.to_dict(),
        )
        self.last_gate_flow = self.gates.submit_revision(
            flow_id=flow_id,
            revised_candidate_id=candidate.candidate_id,
            source_review_event_id=review_event["event_id"],
            actor_id=actor_id,
            reason=reason,
        )
        self.last_appeal_packet = self.appeals.maybe_create(
            task,
            candidate,
            review_batch,
        )
        if self.last_appeal_packet is not None:
            self.events.append(
                "appeal_trigger_connected",
                {
                    "appeal_id": self.last_appeal_packet.appeal_id,
                    "candidate_id": candidate.candidate_id,
                    "trigger": self.last_appeal_packet.trigger,
                    "document_path": self.last_appeal_packet.document_path,
                },
            )
        self._record_review_artifacts(
            candidate_id=candidate.candidate_id,
            review_batch=review_batch,
            source_event_id=review_event["event_id"],
            source_kind="internal_revision_review",
        )
        self._run_post_review_audit(
            task=task,
            candidate=candidate,
            source_review_event_id=review_event["event_id"],
        )
        return candidate, review_batch

    def _run_post_review_audit(
        self,
        *,
        task: Task,
        candidate: Candidate,
        source_review_event_id: str,
    ) -> None:
        self.last_post_review_audit = None
        if self.post_review_auditor is None:
            return
        self.last_post_review_audit = self.post_review_auditor.audit(
            task=task,
            candidate=candidate,
            source_review_event_id=source_review_event_id,
        )

    def _record_review_artifacts(
        self,
        *,
        candidate_id: str,
        review_batch: ReviewBatch,
        source_event_id: str,
        source_kind: str,
    ) -> None:
        for review in review_batch.reviews:
            if review.feedback_to_thesis:
                self.events.append(
                    "negative_example_shadowed",
                    {
                        "candidate_id": candidate_id,
                        "reviewer": review.reviewer,
                        "aspect": review.aspect,
                        "feedback_to_thesis": review.feedback_to_thesis,
                        "mode": "shadow",
                    },
                )
            if review.salvageable_part:
                self.events.append(
                    "library_intake_candidate_recorded",
                    {
                        "content": review.salvageable_part,
                        "source_kind": source_kind,
                        "source_event_id": source_event_id,
                        "source_candidate_id": candidate_id,
                        "source_reviewer": review.reviewer,
                        "source_aspect": review.aspect,
                        "source_verdict": review.verdict,
                        "metadata_status": "incomplete",
                        "purpose_status": "missing",
                        "searchable": False,
                    },
                )

    def run_probe(self, probe: Probe) -> ProbeResult:
        task = Task(
            task_id=f"probe-task-{probe.probe_id}",
            goal=f"{probe.domain} 측면의 알려진 결함을 단서 없이 심사한다.",
            constraints=[],
        )
        candidate = Candidate(
            candidate_id=f"probe-candidate-{probe.probe_id}",
            task_id=task.task_id,
            text=probe.candidate_text,
        )
        review_batch = self.orchestrator.review(
            task,
            candidate,
            required_aspects=[probe.domain],
        )
        detecting_reviewers = [
            review.reviewer
            for review in review_batch.reviews
            if review.defect_found and review.verdict in {"reject", "revise"}
        ]
        detected = bool(detecting_reviewers)
        correct = (
            detected
            if probe.expected_detected
            else not detected and review_batch.status == "clear"
        )
        result = ProbeResult(
            probe_id=probe.probe_id,
            detected=detected,
            expected_detected=probe.expected_detected,
            correct=correct,
            expected_defect=probe.expected_defect,
            detecting_reviewers=detecting_reviewers,
            review_batch=review_batch,
        )
        self.events.append("probe_reviewed", result.to_dict())
        return result
