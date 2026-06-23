from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from harness.backends import OllamaBackend
from harness.cli import _make_backend, build_parser, main
from harness.model_roster import CONFIRMED_LOCAL_PROFILE
from harness.probes import DEFAULT_PROBES


class _FakeResponse:
    def __init__(self, payload: bytes = b'{"response":"ok"}') -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class OllamaCompatibilityTests(unittest.TestCase):
    def test_generate_disables_thinking_for_structured_output_compatibility(self) -> None:
        backend = OllamaBackend("qwen3.5:9b")

        with patch(
            "harness.backends.urllib.request.urlopen",
            return_value=_FakeResponse(),
        ) as mocked:
            self.assertEqual(backend._generate("prompt"), "ok")

        request = mocked.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertIs(payload["think"], False)

    def test_empty_schema_response_retries_without_format(self) -> None:
        backend = OllamaBackend("gpt-oss:20b")
        responses = [
            _FakeResponse(b'{"response":""}'),
            _FakeResponse(b'{"response":"{\\"applicable\\":true}"}'),
        ]

        with patch(
            "harness.backends.urllib.request.urlopen",
            side_effect=responses,
        ) as mocked:
            text = backend._generate(
                "prompt",
                output_format={"type": "object"},
            )

        self.assertEqual(text, '{"applicable":true}')
        first_payload = json.loads(mocked.call_args_list[0].args[0].data.decode("utf-8"))
        second_payload = json.loads(mocked.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertIn("format", first_payload)
        self.assertNotIn("format", second_payload)


class ConfirmedModelProfileTests(unittest.TestCase):
    def test_probe_cli_uses_all_registered_reviewers_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "--log",
                        str(Path(temp_dir) / "events.jsonl"),
                        "probe",
                        "--backend",
                        "mock",
                    ]
                )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["total"], len(DEFAULT_PROBES))
        self.assertTrue(payload["summary"]["all_correct"])
        self.assertEqual(payload["summary"]["correct"], len(DEFAULT_PROBES))

    def test_profile_covers_every_registered_reviewer_role(self) -> None:
        self.assertEqual(
            set(CONFIRMED_LOCAL_PROFILE.reviewer_models),
            {
                "code_reviewer",
                "logic_reviewer",
                "math_reviewer",
                "physics_reviewer",
                "scope_reviewer",
                "blindspot_reviewer",
            },
        )

    def test_cli_builds_confirmed_role_pipeline(self) -> None:
        args = build_parser().parse_args(
            [
                "run",
                "--backend",
                "ollama",
                "--model-profile",
                "confirmed-local",
                "--task",
                "검증",
            ]
        )

        pipeline = _make_backend(args)

        self.assertEqual(pipeline.thesis_backend.model, "qwen3.5:9b")
        self.assertEqual(pipeline.adversary_backend.model, "qwen2.5-coder:14b")
        self.assertEqual(pipeline.translator_backend.model, "qwen3.5:9b")
        self.assertEqual(pipeline.post_audit_backend.model, "olmo2:13b")
        self.assertEqual(
            pipeline.reviewer_backend("scope_reviewer").model,
            "ministral-3:14b",
        )
        self.assertEqual(
            pipeline.reviewer_backend("blindspot_reviewer").model,
            "qwen3.5:9b",
        )
        for reviewer_id, model in CONFIRMED_LOCAL_PROFILE.reviewer_models.items():
            with self.subTest(reviewer_id=reviewer_id):
                self.assertEqual(
                    pipeline.reviewer_backend(reviewer_id).model,
                    model,
                )

    def test_explicit_role_override_wins_over_profile(self) -> None:
        args = build_parser().parse_args(
            [
                "run",
                "--backend",
                "ollama",
                "--model-profile",
                "confirmed-local",
                "--thesis-model",
                "custom-thesis",
                "--reviewer-model",
                "logic_reviewer=custom-logic",
                "--task",
                "검증",
            ]
        )

        pipeline = _make_backend(args)

        self.assertEqual(pipeline.thesis_backend.model, "custom-thesis")
        self.assertEqual(
            pipeline.reviewer_backend("logic_reviewer").model,
            "custom-logic",
        )


if __name__ == "__main__":
    unittest.main()
