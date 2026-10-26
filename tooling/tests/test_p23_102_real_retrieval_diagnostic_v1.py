from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/p23_102_real_retrieval_diagnostic_v1.py"
SUMMARY_PATH = (
    ROOT
    / "data/rehearsal_plan/p23_102_real_retrieval_diagnostic_v1.json"
)


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "p23_102_real_retrieval_diagnostic_v1", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_synthetic_metric_semantics_and_rrf_are_deterministic() -> None:
    tool = load_tool()
    assert tool._synthetic_self_test() == {"passed": True}
    first = tool._random_ranking("q", ["c", "a", "b"])
    second = tool._random_ranking("q", ["c", "a", "b"])
    assert first == second
    assert sorted(first[0]) == ["a", "b", "c"]


def test_exact_registry_templates_only_and_expected_query_counts() -> None:
    tool = load_tool()
    family = json.loads(
        (
            ROOT
            / "data/restricted/"
            "epic_p23_102_machine_provisional_families_v1/"
            "family_registry.json"
        ).read_text(encoding="utf-8")
    )
    evidence = json.loads(
        (
            ROOT
            / "data/restricted/"
            "epic_p23_102_machine_provisional_families_v1/"
            "evidence_registry.json"
        ).read_text(encoding="utf-8")
    )
    queries = tool.build_queries(family["families"], evidence["evidence"])
    assert len(queries) == 76
    assert sum(row["query_scope"] == "family" for row in queries) == 20
    assert sum(row["query_scope"] == "handle" for row in queries) == 56
    permitted = set()
    for row in family["families"]:
        permitted.add(row["question_template"])
        permitted.add(row["answer_template"])
        permitted.update(
            claim["template"] for claim in row["atomic_claim_templates"]
        )
    for query in queries:
        assert all(fragment in permitted for fragment in query["query_text"].split("\n"))
        assert query["machine_provisional_only"] is True


def test_input_gates_bind_exact_development_only_source() -> None:
    tool = load_tool()
    inputs = tool.load_inputs(ROOT, verify_model_files=False)
    assert inputs["source_split"]["split_boundary"][
        "evaluation_source_ids"
    ] == []
    assert inputs["index_build"]["governance"]["development_only"] is True
    assert inputs["family_registry"]["family_count"] == 20
    assert inputs["evidence_registry"]["evidence_count"] == 56


def test_cli_synthetic_self_test() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL_PATH),
            "--synthetic-self-test",
            "--repo-root",
            str(ROOT),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["passed"] is True


@pytest.mark.skipif(
    not SUMMARY_PATH.is_file(),
    reason="real diagnostic output has not been executed yet",
)
def test_real_output_validator() -> None:
    tool = load_tool()
    result = tool.validate_output(ROOT)
    assert result["passed"] is True
    assert result["status"] == tool.READY
    assert result["query_count"] == 76
    assert result["per_query_metric_row_count"] == 456
