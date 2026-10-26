from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from tools import scale1a_model_downloader as downloader
from tools import scale1a_model_preflight as preflight


def valid_plan() -> dict:
    data = b"test"
    lfs_sha256 = hashlib.sha256(data).hexdigest()
    return {
        "repo_id": preflight.REPO_ID,
        "revision": preflight.REVISION,
        "cap_bytes": preflight.CAP_BYTES,
        "expected_payload_bytes": 4,
        "allowlist": [
            {
                "path": "pytorch_model.bin",
                "expected_bytes": 4,
                "git_oid": preflight.lfs_pointer_git_oid(lfs_sha256, len(data)),
                "lfs_sha256": lfs_sha256,
            }
        ],
    }


def test_plan_accepts_one_pytorch_weight_and_cap() -> None:
    assert preflight.validate_plan(valid_plan())[0]["path"] == "pytorch_model.bin"


def test_plan_rejects_duplicate_framework_weights() -> None:
    plan = valid_plan()
    plan["allowlist"].append(
        {
            "path": "model.safetensors",
            "expected_bytes": 1,
            "git_oid": "b" * 40,
            "lfs_sha256": "c" * 64,
        }
    )
    plan["expected_payload_bytes"] = 5
    with pytest.raises(preflight.ValidationError, match="WEIGHT_ALLOWLIST_NOT_MINIMAL"):
        preflight.validate_plan(plan)


def test_plan_rejects_cap_overflow() -> None:
    plan = valid_plan()
    plan["allowlist"][0]["expected_bytes"] = preflight.CAP_BYTES + 1
    plan["allowlist"][0]["git_oid"] = preflight.lfs_pointer_git_oid(
        plan["allowlist"][0]["lfs_sha256"], preflight.CAP_BYTES + 1
    )
    plan["expected_payload_bytes"] = preflight.CAP_BYTES + 1
    with pytest.raises(preflight.ValidationError, match="CAP_OVERFLOW"):
        preflight.validate_plan(plan)


def test_metadata_requires_exact_revision_and_file_identity() -> None:
    plan = valid_plan()
    api = {
        "id": preflight.REPO_ID,
        "sha": preflight.REVISION,
        "private": False,
        "gated": False,
        "tags": [],
        "cardData": {},
    }
    tree = [
        {
            "path": "README.md",
            "type": "file",
            "size": 1,
            "oid": "d" * 40,
        },
        {
            "path": "pytorch_model.bin",
            "type": "file",
            "size": 4,
            "oid": plan["allowlist"][0]["git_oid"],
            "lfs": {"oid": hashlib.sha256(b"test").hexdigest(), "size": 4},
        }
    ]
    readme = b"---\ntags:\n- vision\n---\ncard\n"
    tree[0]["size"] = len(readme)
    tree[0]["oid"] = preflight.git_blob_oid_bytes(readme)
    evidence = preflight.validate_metadata(plan, api, tree, readme)
    assert evidence["license_status"] == "UNDECLARED"
    api["sha"] = "0" * 40
    with pytest.raises(preflight.ValidationError, match="MODEL_API_IDENTITY_MISMATCH"):
        preflight.validate_metadata(plan, api, tree)


def test_metadata_rejects_missing_model_card() -> None:
    plan = valid_plan()
    api = {
        "id": preflight.REPO_ID,
        "sha": preflight.REVISION,
        "private": False,
        "gated": False,
        "tags": [],
        "cardData": {},
    }
    tree = [
        {
            "path": "pytorch_model.bin",
            "type": "file",
            "size": 4,
            "oid": plan["allowlist"][0]["git_oid"],
            "lfs": {"oid": hashlib.sha256(b"test").hexdigest(), "size": 4},
        }
    ]
    with pytest.raises(preflight.ValidationError, match="MODEL_CARD_MISSING"):
        preflight.validate_metadata(plan, api, tree)


def test_metadata_accepts_consistent_readme_license() -> None:
    plan = valid_plan()
    readme = b"---\nlicense: mit\n---\ncard\n"
    api = {
        "id": preflight.REPO_ID,
        "sha": preflight.REVISION,
        "private": False,
        "gated": False,
        "tags": ["license:mit"],
        "cardData": {"license": "mit"},
    }
    tree = [
        {
            "path": "README.md",
            "type": "file",
            "size": len(readme),
            "oid": preflight.git_blob_oid_bytes(readme),
        },
        {
            "path": "pytorch_model.bin",
            "type": "file",
            "size": 4,
            "oid": plan["allowlist"][0]["git_oid"],
            "lfs": {"oid": hashlib.sha256(b"test").hexdigest(), "size": 4},
        },
    ]
    evidence = preflight.validate_metadata(plan, api, tree, readme)
    assert evidence["declared_license"] == "mit"
    assert len(evidence["license_evidence"]) == 3


def test_metadata_rejects_ambiguous_license() -> None:
    plan = valid_plan()
    readme = b"---\nlicense: apache-2.0\n---\ncard\n"
    api = {
        "id": preflight.REPO_ID,
        "sha": preflight.REVISION,
        "private": False,
        "gated": False,
        "tags": ["license:mit"],
        "cardData": {},
    }
    tree = [
        {
            "path": "README.md",
            "type": "file",
            "size": len(readme),
            "oid": preflight.git_blob_oid_bytes(readme),
        },
        {
            "path": "pytorch_model.bin",
            "type": "file",
            "size": 4,
            "oid": plan["allowlist"][0]["git_oid"],
            "lfs": {"oid": hashlib.sha256(b"test").hexdigest(), "size": 4},
        },
    ]
    with pytest.raises(preflight.ValidationError, match="AMBIGUOUS_LICENSE"):
        preflight.validate_metadata(plan, api, tree, readme)


def write_fixture_snapshot(root: Path, *, symlink: bool = False) -> tuple[dict, Path]:
    plan = valid_plan()
    snapshot = root / "snapshot"
    snapshot.mkdir(mode=0o700)
    if symlink:
        target = root / "target"
        target.write_bytes(b"test")
        (snapshot / "pytorch_model.bin").symlink_to(target)
    else:
        (snapshot / "pytorch_model.bin").write_bytes(b"test")
    digest = hashlib.sha256(b"test").hexdigest()
    (snapshot / "SHA256SUMS").write_text(
        f"{digest}  pytorch_model.bin\n", encoding="utf-8"
    )
    os.chmod(snapshot / "pytorch_model.bin", 0o600)
    os.chmod(snapshot / "SHA256SUMS", 0o600)
    return plan, snapshot


def test_snapshot_file_set_hash_and_permissions(tmp_path: Path) -> None:
    plan, snapshot = write_fixture_snapshot(tmp_path)
    records = preflight.validate_snapshot(
        plan, snapshot, {"pytorch_model.bin": hashlib.sha256(b"test").hexdigest()}
    )
    assert records[0]["bytes"] == 4


def test_snapshot_rejects_symlink(tmp_path: Path) -> None:
    plan, snapshot = write_fixture_snapshot(tmp_path, symlink=True)
    with pytest.raises(preflight.ValidationError, match="SYMLINK_PROHIBITED"):
        preflight.validate_snapshot(plan, snapshot)


def test_snapshot_rejects_extra_file(tmp_path: Path) -> None:
    plan, snapshot = write_fixture_snapshot(tmp_path)
    (snapshot / "tf_model.h5").write_bytes(b"x")
    with pytest.raises(preflight.ValidationError, match="FILE_SET_MISMATCH"):
        preflight.validate_snapshot(plan, snapshot)


def test_atomic_json_is_restricted(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    preflight.atomic_json(path, {"ok": True})
    assert json.loads(path.read_text()) == {"ok": True}
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_manifest_gate_separates_technical_use_from_redistribution() -> None:
    manifest = {
        "decision": "CONDITIONAL_GO",
        "technical_inference_decision": "CLIP_SNAPSHOT_READY",
        "redistribution_decision": "NOT_AUTHORIZED",
        "restrictions": {
            "restricted": True,
            "redistribution_authorized": False,
        },
        "acquisition": {"completed": True},
        "verification": {
            "complete_file_set_verified": True,
            "local_sha256_verified": True,
            "offline_local_files_only_load": True,
            "synthetic_image_embedding": True,
            "text_embedding": True,
            "deterministic_replay": True,
        },
    }
    preflight.validate_manifest_gates(manifest)
    manifest["redistribution_decision"] = "AUTHORIZED"
    with pytest.raises(
        preflight.ValidationError, match="REDISTRIBUTION_DECISION_MISMATCH"
    ):
        preflight.validate_manifest_gates(manifest)


def test_delivered_manifest_authorizes_only_restricted_technical_inference() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = preflight.load_json(root / preflight.MANIFEST_PATH)
    preflight.validate_manifest_gates(manifest)
    assert manifest["technical_inference_decision"] == "CLIP_SNAPSHOT_READY"
    assert manifest["redistribution_decision"] == "NOT_AUTHORIZED"
    assert manifest["decision"] == "CONDITIONAL_GO"


def test_response_identity_headers_are_parsed(tmp_path: Path) -> None:
    headers = tmp_path / "headers"
    headers.write_text(
        "HTTP/2 307\n"
        f"x-repo-commit: {preflight.REVISION}\n"
        'x-linked-etag: "abc"\n'
        "x-linked-size: 4\n"
        "HTTP/2 200\n"
        'etag: "def"\n',
        encoding="ascii",
    )
    parsed = downloader.parse_identity_headers(headers)
    assert parsed["x_repo_commit"] == {preflight.REVISION}
    assert parsed["x_linked_etag"] == {"abc"}
    assert parsed["etag"] == {"def"}
    assert parsed["x_linked_size"] == {"4"}
