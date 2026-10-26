from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tools import scale1b_ga_model_downloader as dl
from tools import scale1b_ga_model_preflight as pf


ROOT = Path(__file__).resolve().parents[1]


def plan() -> dict:
    return json.loads((ROOT / pf.ROOT_PLAN).read_text())


def test_plan_is_exact_and_bounded() -> None:
    value = plan()
    pf.validate_plan(value)
    assert value["expected_payload_bytes"] < pf.MODEL_CAP < pf.TOTAL_CAP


def test_plan_selects_one_unsharded_weight_representation() -> None:
    model = plan()["model"]
    names = {item["path"] for item in model["allowlist"]}
    assert names & pf.WEIGHT_NAMES == {"model.safetensors"}
    assert not names & pf.INDEX_NAMES
    assert model["weight_layout"]["shard_index_required"] is False


def test_plan_rejects_revision_drift() -> None:
    value = plan()
    value["model"]["revision"] = "0" * 40
    with pytest.raises(pf.ValidationError, match="IDENTITY"):
        pf.validate_plan(value)


def test_plan_rejects_cap_drift() -> None:
    value = plan()
    value["expected_payload_bytes"] = pf.TOTAL_CAP + 1
    with pytest.raises(pf.ValidationError, match="PAYLOAD_OR_CAP"):
        pf.validate_plan(value)


def test_strict_normal_schema() -> None:
    raw = json.dumps(
        {
            "status": "answer",
            "answer": "The marker is inside the box.",
            "claims": [
                {
                    "claim": "The marker is inside the box.",
                    "citations": ["E1"],
                }
            ],
            "reason_code": None,
        }
    )
    assert pf.parse_strict_json(raw, "normal")["status"] == "answer"


def test_strict_insufficiency_schema() -> None:
    raw = (
        '{"status":"insufficient","answer":null,"claims":[],'
        '"reason_code":"missing_evidence"}'
    )
    assert pf.parse_strict_json(raw, "insufficient")["answer"] is None


@pytest.mark.parametrize(
    "raw,case",
    [
        ('```json\\n{"status":"answer"}\\n```', "normal"),
        ('{"status":"answer","answer":"x","claims":[]}', "normal"),
        (
            '{"status":"answer","answer":"guess","claims":[],"reason_code":null}',
            "insufficient",
        ),
    ],
)
def test_strict_json_rejects_wrappers_missing_keys_and_wrong_abstention(
    raw: str, case: str
) -> None:
    with pytest.raises(pf.ValidationError):
        pf.parse_strict_json(raw, case)


def test_network_guard_blocks_and_counts() -> None:
    with pf.deny_network() as attempts:
        with pytest.raises(RuntimeError, match="NETWORK_ACCESS_FORBIDDEN"):
            __import__("socket").socket()
    assert attempts["count"] == 1


def test_exact_url_contains_full_revision() -> None:
    model = plan()["model"]
    url = dl.exact_url(model, "model.safetensors", "https://huggingface.co")
    assert model["repo_id"] in url
    assert f"/resolve/{model['revision']}/" in url


def test_plan_and_runtime_generation_budget_match() -> None:
    source = (ROOT / "tools/scale1b_ga_model_preflight.py").read_text()
    assert plan()["technical_validation"]["max_new_tokens"] == 128
    assert "max_new_tokens=128" in source


def test_atomic_json_is_restricted(tmp_path: Path) -> None:
    path = tmp_path / "private/value.json"
    pf.atomic_json(path, {"ok": True})
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert json.loads(path.read_text()) == {"ok": True}


def test_bootstrap_exact_metadata_matches_plan() -> None:
    base = ROOT / "data/restricted/scale1b/acquisition_records/ga/bootstrap"
    if not (base / "model_api.json").is_file():
        pytest.skip("live bootstrap metadata not present")
    value = plan()
    evidence = pf.validate_metadata(
        value["model"],
        json.loads((base / "model_api.json").read_text()),
        json.loads((base / "tree.json").read_text()),
        (base / "README.md").read_bytes(),
        (base / "LICENSE").read_bytes(),
    )
    assert evidence["declared_license"] == "apache-2.0"


def test_delivered_manifest_if_ready() -> None:
    manifest_path = ROOT / pf.MANIFEST
    if not manifest_path.is_file():
        pytest.skip("acquisition not executed")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("decision") != "QWEN_GROUNDED_GENERATOR_SNAPSHOT_READY":
        pytest.skip("snapshot not ready")
    value = plan()
    pf.validate_ready_manifest(value, manifest)
    pf.validate_snapshot(
        value["model"],
        ROOT / value["model"]["snapshot_dir"],
        {row["path"]: row["sha256"] for row in manifest["model"]["files"]},
    )
    assert manifest["network_used_during_finalization"] is False
    assert not (
        ROOT / "data/restricted/scale1b/models/.task109-qwen.stage"
    ).exists()
