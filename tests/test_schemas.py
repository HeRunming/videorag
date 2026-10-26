from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from av_trace.schemas import SCHEMA_FILES, SchemaRegistry

from tests.helpers import ROOT, fixture


class SchemaRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = SchemaRegistry(ROOT)

    def test_all_normative_schemas_are_valid_draft_2020_12(self) -> None:
        self.assertTrue(self.registry.check_schemas().ok)
        self.assertEqual(len(self.registry.names), 6)

    def test_all_positive_schema_fixtures_validate(self) -> None:
        cases = {
            "final-answer": "docs/spec/fixtures/positive_final_answer.json",
            "agent-action": "docs/spec/fixtures/positive_agent_action.json",
            "tool-response": "docs/spec/fixtures/positive_tool_response.json",
            "trajectory": "docs/spec/fixtures/positive_trajectory.json",
            "episode-family": "docs/spec/fixtures/positive_episode_family.json",
            "acquisition-manifest": "docs/data/fixtures/positive_acquisition_manifest.json",
        }
        for schema_name, path in cases.items():
            with self.subTest(schema=schema_name):
                self.assertTrue(self.registry.validate(schema_name, fixture(path)).ok)

    def test_unknown_tool_action_is_rejected(self) -> None:
        report = self.registry.validate(
            "agent-action",
            fixture("docs/spec/fixtures/negative_agent_action_unknown_tool.json"),
        )
        self.assertFalse(report.ok)
        self.assertEqual(report.issues[0].code, "SCHEMA-VALIDATION")

    def test_invalid_finalize_arguments_are_rejected(self) -> None:
        action = fixture("docs/spec/fixtures/positive_agent_action.json")
        action["action"] = {
            "tool": "finalize",
            "arguments": {
                "p_sufficient": 0.9,
                "verdict": "sufficient",
                "answer_mode": "answer",
                "claims": [],
                "diagnosis": {
                    "modality_probabilities": {"vision": 0.1, "speech": 0.1, "ambient": 0.1},
                    "hop_types": [],
                    "cause_probabilities": {
                        "source_evidence_absent": 0.0,
                        "evidence_in_source_but_inaccessible": 0.0,
                        "evidence_accessible_but_not_found": 0.0,
                        "not_missing": 1.0,
                        "uncertain": 0.0,
                    },
                    "recovery_route_declared": False,
                    "description": "",
                },
                "natural_language_answer": "unsupported",
                "termination_reason": "sufficient_evidence",
            },
        }
        report = self.registry.validate("agent-action", action)
        self.assertFalse(report.ok)

    def test_schema_hash_is_stable(self) -> None:
        first = self.registry.schema_hash("episode-family")
        second = self.registry.schema_hash("episode-family")
        self.assertEqual(first, second)
        self.assertRegex(first, r"^sha256:[a-f0-9]{64}$")

    def test_check_schemas_reports_unresolvable_reference(self) -> None:
        registry = SchemaRegistry(ROOT)
        registry.schemas["trajectory"]["properties"]["final_output"]["$ref"] = "urn:av-trace:schema:missing:0.2.0"
        self.assertIn("SCHEMA-004", {issue.code for issue in registry.check_schemas().issues})

    def test_installed_data_root_can_be_discovered_outside_repo(self) -> None:
        with TemporaryDirectory() as temp:
            installed = Path(temp) / "av_trace_data"
            for relative in SCHEMA_FILES.values():
                target = installed / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / relative).read_bytes())
            fake_entry = type("Entry", (), {"__str__": lambda self: "av_trace_data/docs/spec/episode_schema.json", "locate": lambda self: installed / "docs/spec/episode_schema.json"})()
            with (
                patch("av_trace.schemas.metadata.files", return_value=[fake_entry]),
                patch("av_trace.schemas.Path.cwd", return_value=Path("/tmp")),
                patch("av_trace.schemas.__file__", "/tmp/site-packages/av_trace/schemas.py"),
            ):
                registry = SchemaRegistry()
            self.assertEqual(registry.root, installed)


if __name__ == "__main__":
    unittest.main()
