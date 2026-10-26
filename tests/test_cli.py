from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from av_trace.cli import main

from tests.helpers import ROOT


class CliTests(unittest.TestCase):
    def invoke(self, *args: str) -> tuple[int, dict]:
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["--repo-root", str(ROOT), *args])
        return status, json.loads(output.getvalue())

    def test_schemas_command(self) -> None:
        status, result = self.invoke("schemas")
        self.assertEqual(status, 0)
        self.assertEqual(result["status"], "PASS")

    def test_family_command(self) -> None:
        status, result = self.invoke(
            "family",
            str(ROOT / "docs/spec/fixtures/positive_episode_family.json"),
            "--manifest",
            str(ROOT / "docs/data/fixtures/positive_acquisition_manifest.json"),
        )
        self.assertEqual(status, 0)
        self.assertEqual(result["status"], "PASS")

    def test_negative_action_command_returns_one(self) -> None:
        status, result = self.invoke(
            "action",
            str(ROOT / "docs/spec/fixtures/negative_agent_action_unknown_tool.json"),
        )
        self.assertEqual(status, 1)
        self.assertEqual(result["status"], "FAIL")

    def test_invalid_explicit_repo_root_fails_instead_of_falling_back(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["--repo-root", "/tmp/definitely-missing-av-trace", "schemas"])
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "FAIL")

    def test_repo_relative_input_paths_work_outside_repo(self) -> None:
        with TemporaryDirectory() as temp, patch("pathlib.Path.cwd", return_value=Path(temp)):
            output = io.StringIO()
            with redirect_stdout(output):
                status = main([
                    "--repo-root",
                    str(ROOT),
                    "manifest",
                    "docs/data/fixtures/positive_acquisition_manifest.json",
                    "--gate",
                    "public_release",
                ])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "PASS")

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "duplicate.json"
            path.write_text('{"protocol_version":"0.2.0","protocol_version":"0.2.0"}', encoding="utf-8")
            status, result = self.invoke("action", str(path))
        self.assertEqual(status, 2)
        self.assertIn("Duplicate JSON object key", result["issues"][0]["message"])

    def test_non_finite_json_numbers_are_rejected(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "nan.json"
            path.write_text('{"value":NaN}', encoding="utf-8")
            status, result = self.invoke("action", str(path))
        self.assertEqual(status, 2)
        self.assertIn("Non-finite JSON number", result["issues"][0]["message"])

    def test_argument_errors_use_json_envelope(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = main([])
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(output.getvalue())["issues"][0]["code"], "CLI-INPUT")


if __name__ == "__main__":
    unittest.main()
