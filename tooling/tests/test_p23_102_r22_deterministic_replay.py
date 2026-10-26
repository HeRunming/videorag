from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/p23_102_r22_deterministic_replay.py"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "p23_102_r22_deterministic_replay", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_r22_deterministic_replay_reconstructs_and_remains_no_go(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    report = tool.run_replay(
        ROOT,
        audit_path=tool.DEFAULT_AUDIT,
        capsule_path=tool.DEFAULT_CAPSULE,
    )
    assert report["decision"] == "NO-GO"
    assert report["r23_status"] == "R23_A_IMPLEMENTATION_READY"
    assert report["reconstruction"]["accepted_factor_count"] == 13
    assert report["reconstruction"]["bound_final_row_count"] == 26
    assert report["reconstruction"][
        "accepted_factor_manifest_payload_sha256"
    ] == "sha256:6577877038c23a7a87a2dbde92b3b11ca8dff1c3d3cc33d0fedcdc7491f27594"
    collision = report["deterministic_gates"][
        "lexical_exact_and_near_collision"
    ]
    assert collision["status"] == "FAIL_BLOCKING"
    assert collision["exact_duplicate_count"] == 3
    assert collision["near_collision_count"] == 4
    assert report["deterministic_gates"]["standalone_reference"][
        "status"
    ] == "PASS"
    assert report["deterministic_gates"]["query_description_identity"][
        "status"
    ] == "PASS"
    assert report["deterministic_gates"]["far_ordered_query_coverage"][
        "status"
    ] == "PASS"
    retained_local = report["reconstruction"]["component_local_results"][
        "family-004"
    ]["component_clauses"][0]["continuity"]
    assert retained_local["unsupported"] is False
    assert retained_local["local_visual_pronoun_coreference_exemptions"] == [
        {
            "term": "it",
            "antecedent": "a table",
            "antecedent_noun": "table",
            "preposition": "on",
            "clause": (
                "A kitchen with a pot on the stove and a table with "
                "various items on it"
            ),
        }
    ]
    assert report["scope"]["asr_executed"] is False
    assert report["scope"]["embedding_executed"] is False
    assert report["scope"]["clap_executed"] is False
    assert report["scope"]["inference_from_unexecuted_models"] is False

    output = tmp_path / "report.json"
    first = tool.write_report(output, report)
    second = tool.write_report(output, report)
    assert first == second
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["report_payload_sha256"] == tool.semantic_hash(
        {
            key: value
            for key, value in written.items()
            if key != "report_payload_sha256"
        }
    )


def test_r22_deterministic_replay_rejects_capsule_tamper(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    source = ROOT / tool.DEFAULT_CAPSULE
    copied = tmp_path / "capsule"
    shutil.copytree(source, copied)
    attempts = copied / "raw_attempts.jsonl"
    attempts.write_bytes(attempts.read_bytes() + b"\n")

    with pytest.raises(tool.ReplayError, match="R22_REPLAY_HASH_MISMATCH"):
        tool.run_replay(
            ROOT,
            audit_path=tool.DEFAULT_AUDIT,
            capsule_path=copied,
        )
