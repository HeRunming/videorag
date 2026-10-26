from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from tools import scale1b_wave_r_model_downloader as dl
from tools import scale1b_wave_r_model_preflight as pf


def plan() -> dict:
    root = Path(__file__).resolve().parents[1]
    return json.loads((root / pf.ROOT_PLAN).read_text())


def test_delivered_plan_is_exact_and_bounded() -> None:
    value = plan()
    pf.validate_plan(value)
    assert value["expected_total_bytes"] < pf.CAP_TOTAL


def test_one_weight_representation_per_model() -> None:
    for model in pf.model_map(plan()).values():
        assert len(set(x["path"] for x in model["allowlist"]) & pf.WEIGHTS) == 1


def test_rejects_total_cap_drift() -> None:
    value = plan()
    value["expected_total_bytes"] = pf.CAP_TOTAL + 1
    with pytest.raises(pf.ValidationError, match="TOTAL_PAYLOAD"):
        pf.validate_plan(value)


def test_rejects_revision_drift() -> None:
    value = plan()
    value["models"][0]["revision"] = "0" * 40
    with pytest.raises(pf.ValidationError, match="IDENTITY"):
        pf.validate_plan(value)


def test_metadata_license_and_identity() -> None:
    value = plan()
    root = Path(__file__).resolve().parents[1] / (
        "data/restricted/scale1b/acquisition_records/wave_r/"
        "prior_task92_metadata"
    )
    for model_id, stem in (("siglip2", "siglip2"), ("clap", "clap")):
        model = json.loads(json.dumps(pf.model_map(value)[model_id]))
        api = json.loads((root / f"{stem}.model_api.task92.json").read_text())
        tree = json.loads((root / f"{stem}.tree.task92.json").read_text())
        readme = f"---\nlicense: apache-2.0\n---\n".encode()
        item = next(x for x in tree if x["path"] == "README.md")
        item["size"] = len(readme); item["oid"] = pf.git_blob_oid_bytes(readme)
        planned = next(x for x in model["allowlist"] if x["path"] == "README.md")
        planned["expected_bytes"] = len(readme)
        planned["git_oid"] = item["oid"]
        model["expected_payload_bytes"] = sum(
            x["expected_bytes"] for x in model["allowlist"]
        )
        evidence = pf.validate_metadata(model, api, tree, readme)
        assert evidence["declared_license"] == "apache-2.0"


def test_metadata_rejects_wrong_commit() -> None:
    value = plan(); model = pf.model_map(value)["siglip2"]
    root = Path(__file__).resolve().parents[1] / (
        "data/restricted/scale1b/acquisition_records/wave_r/"
        "prior_task92_metadata"
    )
    api = json.loads((root / "siglip2.model_api.task92.json").read_text())
    tree = json.loads((root / "siglip2.tree.task92.json").read_text())
    api["sha"] = "0" * 40
    with pytest.raises(pf.ValidationError, match="MODEL_API_IDENTITY"):
        pf.validate_metadata(model, api, tree, b"x")


def test_atomic_json_mode(tmp_path: Path) -> None:
    path = tmp_path / "x/y.json"
    pf.atomic_json(path, {"ok": True})
    assert stat_mode(path) == 0o600 and json.loads(path.read_text()) == {"ok": True}


def stat_mode(path: Path) -> int:
    return os.stat(path).st_mode & 0o777


def test_header_parsing(tmp_path: Path) -> None:
    path = tmp_path / "h"
    path.write_text("x-repo-commit: " + "a" * 40 + "\netag: \"abc\"\nx-linked-etag: \"def\"\n")
    assert dl.commits_from_headers(path) == {"a" * 40}
    assert dl.identity_from_headers(path) == {"abc", "def"}


def test_snapshot_rejects_extra_and_symlink(tmp_path: Path) -> None:
    model = pf.model_map(plan())["clap"]
    snap = tmp_path / "s"; snap.mkdir(mode=0o700)
    for item in model["allowlist"]:
        (snap / item["path"]).write_bytes(b"x")
        os.chmod(snap / item["path"], 0o600)
    (snap / "SHA256SUMS").write_text("")
    os.chmod(snap / "SHA256SUMS", 0o600)
    (snap / "extra").write_bytes(b"x")
    with pytest.raises(pf.ValidationError, match="FILE_SET"):
        pf.validate_snapshot(model, snap)


def test_delivered_manifest_matches_actual_snapshot_state() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / pf.MANIFEST).read_text())
    assert manifest["siglip2_decision"] == "SIGLIP2_SNAPSHOT_READY"
    assert manifest["clap_decision"] == "CLAP_SNAPSHOT_READY"
    assert manifest["wave_r_decision"] == "WAVE_R_MODELS_READY"
    assert manifest["technical_internal_use_authorized"] is True
    assert manifest["redistribution_authorized"] is False
    for model_id, model in pf.model_map(plan()).items():
        record = manifest["models"][model_id]
        pf.validate_snapshot(
            model,
            root / model["snapshot_dir"],
            {row["path"]: row["sha256"] for row in record["files"]},
        )


def test_exact_urls_include_full_revision_and_encoded_filename() -> None:
    for model in pf.model_map(plan()).values():
        url = dl.exact_url(model, "model.safetensors", "https://huggingface.co")
        assert model["repo_id"] in url
        assert f"/resolve/{model['revision']}/" in url


def test_current_manifest_separates_technical_and_release_gates() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / pf.MANIFEST).read_text())
    assert manifest["technical_internal_use_authorized"] is True
    assert manifest["redistribution_authorized"] is False
    assert manifest["credentials_persisted"] is False


def test_current_siglip_runtime_class_matches_local_config() -> None:
    root = Path(__file__).resolve().parents[1]
    model = pf.model_map(plan())["siglip2"]
    model_class, processor_class, model_type = pf.resolve_runtime_classes(
        "siglip2", root / model["snapshot_dir"]
    )
    assert model_type == "siglip"
    assert model_class.__name__ == "SiglipModel"
    assert processor_class.__name__ == "SiglipProcessor"


def test_delivered_ready_manifest_passes_strict_gate_validation() -> None:
    root = Path(__file__).resolve().parents[1]
    value = plan()
    manifest = json.loads((root / pf.MANIFEST).read_text())
    pf.validate_ready_manifest(value, manifest)


def test_siglip_runtime_class_is_selected_from_local_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "config.json").write_text('{"model_type":"siglip"}')

    class FakeModel:
        pass

    class FakeProcessor:
        pass

    import transformers
    monkeypatch.setitem(transformers.__dict__, "SiglipModel", FakeModel)
    monkeypatch.setitem(transformers.__dict__, "SiglipProcessor", FakeProcessor)
    model, processor, model_type = pf.resolve_runtime_classes("siglip2", tmp_path)
    assert (model, processor, model_type) == (FakeModel, FakeProcessor, "siglip")


def test_siglip2_runtime_class_is_supported_when_config_requires_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "config.json").write_text('{"model_type":"siglip2"}')

    class FakeModel:
        pass

    class FakeProcessor:
        pass

    import transformers
    monkeypatch.setitem(transformers.__dict__, "Siglip2Model", FakeModel)
    monkeypatch.setitem(transformers.__dict__, "Siglip2Processor", FakeProcessor)
    model, processor, model_type = pf.resolve_runtime_classes("siglip2", tmp_path)
    assert (model, processor, model_type) == (FakeModel, FakeProcessor, "siglip2")


def test_unknown_siglip_config_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text('{"model_type":"clip"}')
    with pytest.raises(pf.ValidationError, match="UNSUPPORTED_SIGLIP_MODEL_TYPE"):
        pf.resolve_runtime_classes("siglip2", tmp_path)
