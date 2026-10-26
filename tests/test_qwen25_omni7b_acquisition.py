from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from tools import qwen25_omni7b_acquisition as omni

ROOT = Path(__file__).resolve().parents[1]


def plan() -> dict:
    return json.loads((ROOT / omni.PLAN).read_text(encoding="utf-8"))


def test_plan_is_exact_minimal_and_bounded() -> None:
    value = plan()
    omni.validate_plan(value)
    assert value["model"]["repo_id"] == omni.REPO_ID
    assert value["model"]["revision"] == omni.REVISION
    assert value["model"]["expected_weight_bytes"] == 22_362_861_192
    assert value["model"]["expected_payload_bytes"] == 22_374_798_886
    names = {item["path"] for item in value["model"]["allowlist"]}
    assert "merges.txt" not in names
    assert "vocab.json" not in names
    assert "spk_dict.pt" in names
    assert sum(name.endswith(".safetensors") for name in names) == 5


def test_plan_rejects_revision_drift() -> None:
    value = copy.deepcopy(plan())
    value["model"]["revision"] = "0" * 40
    with pytest.raises(omni.AcquisitionError, match="IDENTITY"):
        omni.validate_plan(value)


def test_task148_official_api_snapshot_matches_plan() -> None:
    archived = (
        ROOT
        / "data/restricted/strong_baselines/acquisition_records/"
        "qwen25-omni7b-ae9e1690543f/task148_model_api.json"
    )
    api = json.loads(archived.read_text(encoding="utf-8"))
    review = omni.validate_task148_api_snapshot(plan(), api)
    assert review["repo_id"] == omni.REPO_ID
    assert review["revision"] == omni.REVISION
    assert review["declared_license"] == "apache-2.0"
    assert review["risky_code_or_pickle_files"] == []
    assert review["pt_file_present"] is True


def test_exact_url_contains_full_revision_and_endpoint() -> None:
    url = omni.exact_url(
        plan()["model"], "config.json", "https://hf-mirror.com"
    )
    assert url.startswith("https://hf-mirror.com/")
    assert f"/resolve/{omni.REVISION}/" in url


def test_network_guard_blocks_and_counts() -> None:
    with omni.deny_network() as attempts, pytest.raises(
        RuntimeError, match="NETWORK_ACCESS_FORBIDDEN_DURING_LOCAL_SMOKE"
    ):
        __import__("socket").socket()
    assert attempts["count"] == 1


def test_synthetic_fixture_and_strict_contract(tmp_path: Path) -> None:
    fixture = omni.generate_synthetic_av_clip(tmp_path / "fixture.mp4")
    assert fixture["scientific_media"] is False
    assert fixture["video_stream_count"] == 1
    assert fixture["audio_stream_count"] == 1
    assert os.stat(tmp_path / "fixture.mp4").st_mode & 0o777 == 0o600
    contract = omni.validate_fixture_contract(str(tmp_path / "fixture.mp4"))
    assert contract["question_independent_packing"] is True
    assert contract["strict_final_schema_example_valid"] is True
    assert contract["model_inference_executed"] is False


def test_current_exact_metadata_validates_offline() -> None:
    value = plan()
    records = ROOT / value["model"]["metadata_dir"]
    review = omni.validate_current_metadata(value, records)
    assert review["complete"] is True
    assert review["validated_offline"] is True
    assert review["repo_id"] == omni.REPO_ID
    assert review["revision"] == omni.REVISION
    assert review["declared_license"] == "apache-2.0"
    assert review["risky_code_files"] == []


def test_existing_snapshot_index_and_tensor_set_validate() -> None:
    value = plan()
    rows = omni.validate_snapshot(
        value,
        ROOT / value["model"]["snapshot_dir"],
    )
    assert len(rows) == 15
    shards = [row for row in rows if row["path"].endswith(".safetensors")]
    assert len(shards) == 5
    assert all(row["sha256"] == row["upstream_identity"] for row in shards)


def test_strict_canary_prompt_is_single_output_and_contract_bound() -> None:
    prompt = omni.strict_canary_prompt()
    assert "exactly one JSON object" in prompt
    assert "no markdown" in prompt
    assert "exposure.task196.synthetic.0" in prompt
    assert "public.task197.synthetic_signal" in prompt
    assert "repairing" in prompt


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('{"a":1}', 7),
        ('  {"a":{"b":"}"}}', 17),
        ('{"a":1}\n', 7),
        ('{"a":1} trailing', None),
        ('prefix {"a":1}', None),
        ('{"a":1', None),
    ],
)
def test_complete_json_object_end_is_strict(
    value: str, expected: int | None
) -> None:
    assert omni.complete_json_object_end(value) == expected


def test_delivered_manifest_is_honest_technical_result() -> None:
    manifest = json.loads((ROOT / omni.MANIFEST).read_text(encoding="utf-8"))
    assert manifest["decision"] in {omni.READY, omni.REPAIR}
    assert manifest["task_id"] == 197
    assert manifest["repairs_task_id"] == 196
    assert manifest["competence_claimed"] is False
    assert manifest["scientific_media_read"] is False
    assert manifest["gpu_used_or_reserved"] is False
    assert manifest["unrelated_ray_or_h20_jobs_touched"] is False
    assert manifest["model"]["snapshot_acquired"] is True
    assert manifest["model"]["snapshot_hash_verified"] is True
    assert manifest["model"]["redownloaded_by_task197"] is False
    assert manifest["model"]["safetensors_index_tensor_set_validated"] is True
    assert manifest["cpu_load_smoke"]["local_files_only"] is True
    assert manifest["cpu_load_smoke"]["trust_remote_code"] is False
    assert manifest["cpu_load_smoke"]["competence_claimed"] is False
    assert (
        manifest["archived_evidence"][
            "current_exact_metadata_card_license_tree"
        ]["complete"]
        is True
    )
    if manifest["decision"] == omni.READY:
        assert manifest["local_model_inference_executed"] is True
        assert manifest["cpu_load_smoke"]["forward_pass_succeeded"] is True
        assert manifest["blockers"] == []
    else:
        assert manifest["blockers"]
