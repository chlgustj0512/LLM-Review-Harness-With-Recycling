from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness.appeals import AppealService
from harness.library import LibraryLedger
from harness.logging import EventLog
from harness.models import Candidate, ReviewBatch, Task


class LibraryLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.log_path = Path(self.temp_dir.name) / "events.jsonl"
        self.source_event = EventLog(self.log_path).append(
            "review_batch_completed",
            {"candidate_id": "candidate-1"},
        )
        self.ledger = LibraryLedger(self.log_path)

    def add_part(self, purpose: str = "실패 원인 설명"):
        return self.ledger.add_part(
            content="입력과 출력 사이의 인과 경로를 분리해 기록한다.",
            premises=["관찰 가능한 입력이 있다", "출력 차이를 비교할 수 있다"],
            verification_context="논리 심사에서 하위 구조가 보존됨",
            works_when=["변경을 되돌릴 수 있다", "외부 변수를 기록한다"],
            fails_when=["외부 변수를 전혀 관찰할 수 없다"],
            purpose=purpose,
            verification_status="salvaged_unverified",
            source_event_id=self.source_event["event_id"],
            source_candidate_id="candidate-1",
            created_by="user",
        )

    def test_unapproved_purpose_is_not_searchable(self) -> None:
        part = self.add_part()
        self.assertEqual(part.purpose_status, "proposed_unapproved")
        self.assertEqual(
            self.ledger.query(purpose="실패 원인 설명"),
            [],
        )

    def test_approved_part_matches_purpose_then_conditions(self) -> None:
        part = self.add_part()
        approved = self.ledger.approve_purpose(
            part_id=part.part_id,
            actor_type="human",
            actor_id="user",
            reason="원 후보의 실제 사용 의도와 일치함",
        )
        self.assertEqual(approved.purpose_status, "approved")

        matches = self.ledger.query(
            purpose="실패 원인 설명",
            conditions=["변경을 되돌릴 수 있다"],
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].part.part_id, part.part_id)
        self.assertEqual(
            matches[0].part.verification_status,
            "salvaged_unverified",
        )

    def test_purpose_mismatch_skips_before_condition_match(self) -> None:
        part = self.add_part()
        self.ledger.approve_purpose(
            part_id=part.part_id,
            actor_type="tool",
            actor_id="purpose-reviewer",
            reason="목적 주석 승인",
        )
        matches = self.ledger.query(
            purpose="처리 속도 향상",
            conditions=["변경을 되돌릴 수 있다"],
        )
        self.assertEqual(matches, [])

    def test_condition_mismatch_excludes_part(self) -> None:
        part = self.add_part()
        self.ledger.approve_purpose(
            part_id=part.part_id,
            actor_type="human",
            actor_id="user",
            reason="목적 주석 승인",
        )
        self.assertEqual(
            self.ledger.query(
                purpose="실패 원인 설명",
                conditions=["실시간 센서가 반드시 있다"],
            ),
            [],
        )

    def test_missing_provenance_event_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.ledger.add_part(
                content="부품",
                premises=["전제"],
                verification_context="맥락",
                works_when=["조건"],
                fails_when=["실패"],
                purpose="목적",
                verification_status="preserved_verified",
                source_event_id="event-missing",
                source_candidate_id="candidate-1",
                created_by="user",
            )

    def test_source_event_candidate_mismatch_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.ledger.add_part(
                content="부품",
                premises=["전제"],
                verification_context="맥락",
                works_when=["조건"],
                fails_when=["실패"],
                purpose="목적",
                verification_status="preserved_verified",
                source_event_id=self.source_event["event_id"],
                source_candidate_id="candidate-other",
                created_by="user",
            )

    def test_event_without_candidate_provenance_is_rejected(self) -> None:
        unrelated = EventLog(self.log_path).append(
            "feedback_readiness_approved",
            {"readiness_id": "readiness-1"},
        )
        with self.assertRaises(ValueError):
            self.ledger.add_part(
                content="부품",
                premises=["전제"],
                verification_context="맥락",
                works_when=["조건"],
                fails_when=["실패"],
                purpose="목적",
                verification_status="preserved_verified",
                source_event_id=unrelated["event_id"],
                source_candidate_id="candidate-1",
                created_by="user",
            )

    def test_nested_case_candidate_provenance_is_accepted(self) -> None:
        case_event = EventLog(self.log_path).append(
            "filter_escape_case_reported",
            {
                "case_id": "case-1",
                "candidate": {"candidate_id": "candidate-case"},
            },
        )
        part = self.ledger.add_part(
            content="사건에서 보존한 부품",
            premises=["전제"],
            verification_context="사건 검토",
            works_when=["조건"],
            fails_when=["실패"],
            purpose="사건 재사용",
            verification_status="salvaged_unverified",
            source_event_id=case_event["event_id"],
            source_candidate_id="candidate-case",
            created_by="user",
        )
        self.assertEqual(part.source_candidate_id, "candidate-case")

    def test_tampered_stored_part_binding_is_rejected_on_read(self) -> None:
        EventLog(self.log_path).append(
            "library_part_proposed",
            {
                "part_id": "library-part-tampered",
                "content": "변조 부품",
                "premises": ["전제"],
                "verification_context": "맥락",
                "works_when": ["조건"],
                "fails_when": ["실패"],
                "purpose": "목적",
                "purpose_status": "proposed_unapproved",
                "verification_status": "salvaged_unverified",
                "source_event_id": self.source_event["event_id"],
                "source_candidate_id": "candidate-other",
                "created_by": "tampered",
            },
        )
        with self.assertRaises(ValueError):
            self.ledger.get("library-part-tampered")

    def test_forged_purpose_approval_is_rejected_on_read(self) -> None:
        part = self.add_part()
        EventLog(self.log_path).append(
            "library_purpose_approved",
            {
                "part_id": part.part_id,
                "previous_status": "proposed_unapproved",
                "new_status": "approved",
                "actor_type": "human",
                "actor_id": "tampered",
                "reason": "원장 수동 변조",
                "source_event_id": "event-forged",
            },
        )
        with self.assertRaises(ValueError):
            self.ledger.get(part.part_id)

    def test_forged_internal_intake_source_is_rejected(self) -> None:
        intake_event = EventLog(self.log_path).append(
            "library_intake_candidate_recorded",
            {
                "content": "원본 심사에 없는 보존 부품",
                "source_kind": "internal_review",
                "source_event_id": self.source_event["event_id"],
                "source_candidate_id": "candidate-1",
                "source_reviewer": "logic-reviewer",
                "source_aspect": "logic",
                "source_verdict": "revise",
                "metadata_status": "incomplete",
                "purpose_status": "missing",
                "searchable": False,
            },
        )
        with self.assertRaises(ValueError):
            self.ledger.add_part(
                content="원본 심사에 없는 보존 부품",
                premises=["전제"],
                verification_context="변조 입고",
                works_when=["조건"],
                fails_when=["실패"],
                purpose="변조 방지",
                verification_status="salvaged_unverified",
                source_event_id=intake_event["event_id"],
                source_candidate_id="candidate-1",
                created_by="tampered",
            )

    def test_duplicate_purpose_approval_is_rejected(self) -> None:
        part = self.add_part()
        self.ledger.approve_purpose(
            part_id=part.part_id,
            actor_type="human",
            actor_id="user",
            reason="승인",
        )
        with self.assertRaises(ValueError):
            self.ledger.approve_purpose(
                part_id=part.part_id,
                actor_type="human",
                actor_id="user",
                reason="중복 승인",
            )

    def test_appeal_salvage_enters_incomplete_intake_only(self) -> None:
        service = AppealService(self.log_path)
        task = Task("task-appeal", "재심 과제")
        candidate = Candidate("candidate-appeal", task.task_id, "후보")
        batch = ReviewBatch(
            candidate_id=candidate.candidate_id,
            required_aspects=["logic"],
            jurisdictions=[],
            reviews=[],
            empty_aspects=["logic"],
            conflicting_aspects=[],
            dependent_core_blocked=[],
            status="empty_aspect",
        )
        packet = service.create(task, candidate, batch, "empty_aspect")
        service.import_result(
            appeal_id=packet.appeal_id,
            candidate_id=candidate.candidate_id,
            verdict="uphold",
            actor_id="user",
            salvageable_part="독립적으로 보존할 하위 구조",
        )

        intake = self.ledger.intake_candidates()
        self.assertEqual(len(intake), 1)
        self.assertFalse(intake[0]["searchable"])
        self.assertEqual(intake[0]["metadata_status"], "incomplete")
        self.assertEqual(self.ledger.query(purpose="아무 목적"), [])

    def test_internal_review_intake_can_be_formalized_with_same_candidate(self) -> None:
        source_event = EventLog(self.log_path).append(
            "review_batch_completed",
            {
                "candidate_id": "candidate-1",
                "reviews": [
                    {
                        "reviewer": "logic-reviewer",
                        "aspect": "logic",
                        "verdict": "revise",
                        "defect_found": True,
                        "salvageable_part": "내부 심사 보존 부품",
                    }
                ],
            },
        )
        intake_event = EventLog(self.log_path).append(
            "library_intake_candidate_recorded",
            {
                "content": "내부 심사 보존 부품",
                "source_kind": "internal_review",
                "source_event_id": source_event["event_id"],
                "source_candidate_id": "candidate-1",
                "source_reviewer": "logic-reviewer",
                "source_aspect": "logic",
                "source_verdict": "revise",
                "metadata_status": "incomplete",
                "purpose_status": "missing",
                "searchable": False,
            },
        )
        part = self.ledger.add_part(
            content="내부 심사 보존 부품",
            premises=["전제"],
            verification_context="내부 심사에서 보존됨",
            works_when=["조건"],
            fails_when=["실패"],
            purpose="재사용 목적",
            verification_status="salvaged_unverified",
            source_event_id=intake_event["event_id"],
            source_candidate_id="candidate-1",
            created_by="user",
        )
        self.assertEqual(part.source_candidate_id, "candidate-1")


if __name__ == "__main__":
    unittest.main()
