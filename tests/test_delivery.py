from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from harness.backends import MockBackend
from harness.delivery import DeliveryLedger
from harness.logging import EventLog
from harness.pipeline import Harness
from harness.post_review_audit import PostReviewAuditService


class CompletionModel:
    def __init__(self, model: str, outputs: list[str]) -> None:
        self.model = model
        self.outputs = list(outputs)

    def complete(
        self,
        prompt: str,
        *,
        output_format: str | dict[str, Any] | None = None,
    ) -> str:
        if not self.outputs:
            raise RuntimeError("completion exhausted")
        return self.outputs.pop(0)


def audit_review(*, defect: bool) -> str:
    return json.dumps(
        {
            "reviewer": "post_review_blindspot_auditor",
            "verdict": "revise" if defect else "pass_to_next_gate",
            "defect_found": defect,
            "defect_type": "privacy" if defect else "",
            "defect_where": "로그 정책" if defect else "",
            "reasoning": "민감 정보가 노출된다." if defect else "추가 결함이 없다.",
            "required_revision": "민감 정보를 제거한다." if defect else "",
            "confidence": 91,
            "feedback_to_thesis": "",
            "salvageable_part": "",
        },
        ensure_ascii=False,
    )


class DeliveryLedgerTests(unittest.TestCase):
    def test_delivery_requires_gate_3_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            harness = Harness(MockBackend(), log_path)
            harness.run("승인 전 제출 금지")
            assert harness.last_gate_flow is not None
            with self.assertRaisesRegex(ValueError, "Gate 3"):
                DeliveryLedger(log_path).create(
                    flow_id=harness.last_gate_flow.flow_id,
                    auditor=self._auditor(
                        log_path,
                        translator_outputs=["English"],
                        audit_outputs=[audit_review(defect=False)],
                    ),
                    output_dir=Path(temp_dir) / "deliveries",
                )

    def test_clear_delivery_preserves_final_korean_text_and_exports_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "events.jsonl"
            harness = Harness(MockBackend(), log_path)
            candidate, _ = harness.run("최종 제출 시험")
            flow_id = self._accept(harness)
            packet = DeliveryLedger(log_path).create(
                flow_id=flow_id,
                auditor=self._auditor(
                    log_path,
                    translator_outputs=["English final candidate"],
                    audit_outputs=[audit_review(defect=False)],
                ),
                output_dir=root / "deliveries",
            )

            self.assertEqual(packet.status, "ready_clear")
            self.assertEqual(packet.korean_final_text, candidate.text)
            self.assertEqual(packet.audit_status, "clear")
            self.assertTrue(Path(packet.json_path).exists())
            self.assertTrue(Path(packet.markdown_path).exists())
            self.assertIn(
                candidate.text,
                Path(packet.markdown_path).read_text(encoding="utf-8"),
            )
            loaded = DeliveryLedger(log_path).get(delivery_id=packet.delivery_id)
            self.assertEqual(loaded.to_dict(), packet.to_dict())
            with self.assertRaisesRegex(ValueError, "이미"):
                DeliveryLedger(log_path).create(
                    flow_id=flow_id,
                    auditor=self._auditor(
                        log_path,
                        translator_outputs=["unused"],
                        audit_outputs=["unused"],
                    ),
                    output_dir=root / "deliveries",
                )

    def test_advisory_is_separate_from_final_body(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "events.jsonl"
            harness = Harness(MockBackend(), log_path)
            candidate, _ = harness.run("보강 보고서 포함 제출")
            packet = DeliveryLedger(log_path).create(
                flow_id=self._accept(harness),
                auditor=self._auditor(
                    log_path,
                    translator_outputs=[
                        "English final candidate",
                        "문제 유형: 개인정보\n보강 제안: 로그에서 제거",
                    ],
                    audit_outputs=[audit_review(defect=True)],
                ),
                output_dir=root / "deliveries",
            )

            self.assertEqual(packet.status, "ready_with_advisory")
            self.assertEqual(packet.korean_final_text, candidate.text)
            self.assertIn("문제 유형", packet.audit_advisory_korean)
            self.assertNotIn(
                packet.audit_advisory_korean,
                packet.korean_final_text,
            )

    def test_failed_audit_still_exports_approved_body_with_failure_notice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "events.jsonl"
            harness = Harness(MockBackend(), log_path)
            candidate, _ = harness.run("감사 실패 제출")
            packet = DeliveryLedger(log_path).create(
                flow_id=self._accept(harness),
                auditor=self._auditor(
                    log_path,
                    translator_outputs=["English final candidate"],
                    audit_outputs=["not-json"],
                ),
                output_dir=root / "deliveries",
            )

            self.assertEqual(packet.status, "ready_audit_failed")
            self.assertEqual(packet.korean_final_text, candidate.text)
            self.assertTrue(packet.audit_error)
            self.assertIn(
                "감사 실패:",
                Path(packet.markdown_path).read_text(encoding="utf-8"),
            )

    def test_file_write_failure_does_not_record_completed_delivery(self) -> None:
        original_write_text = Path.write_text

        def flaky_write(path: Path, data: str, **kwargs: Any) -> int:
            if path.suffix == ".md":
                raise OSError("simulated markdown write failure")
            return original_write_text(path, data, **kwargs)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "events.jsonl"
            harness = Harness(MockBackend(), log_path)
            harness.run("파일 실패 원자성 시험")
            flow_id = self._accept(harness)
            with patch("pathlib.Path.write_text", new=flaky_write):
                with self.assertRaisesRegex(OSError, "simulated"):
                    DeliveryLedger(log_path).create(
                        flow_id=flow_id,
                        auditor=self._auditor(
                            log_path,
                            translator_outputs=["English final candidate"],
                            audit_outputs=[audit_review(defect=False)],
                        ),
                        output_dir=root / "deliveries",
                    )

            events = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertNotIn(
                "final_delivery_packet_created",
                [event["event_type"] for event in events],
            )
            self.assertEqual(list((root / "deliveries").glob("*")), [])

    @staticmethod
    def _auditor(
        log_path: Path,
        *,
        translator_outputs: list[str],
        audit_outputs: list[str],
    ) -> PostReviewAuditService:
        return PostReviewAuditService(
            translator=CompletionModel("translator", translator_outputs),
            auditor=CompletionModel("olmo2:13b", audit_outputs),
            events=EventLog(log_path),
        )

    @staticmethod
    def _accept(harness: Harness) -> str:
        assert harness.last_gate_flow is not None
        state = harness.last_gate_flow
        for decision in (
            "pass_to_next_gate",
            "pass_to_next_gate",
            "accepted_synthesis",
        ):
            state = harness.gates.record_decision(
                flow_id=state.flow_id,
                decision=decision,
                actor_type="human",
                actor_id="test",
                reason="최종 제출 시험 승인",
            )
        return state.flow_id


if __name__ == "__main__":
    unittest.main()
