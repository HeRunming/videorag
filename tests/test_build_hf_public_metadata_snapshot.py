from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_hf_public_metadata_snapshot.py"


def load_script():
    spec = importlib.util.spec_from_file_location(
        "build_hf_public_metadata_snapshot_for_test", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = load_script()


def json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode()


def fixture_payload() -> dict[str, bytes]:
    asset_manifest = {
        "schema_version": "test.hf-assets/1",
        "generated_date": "2026-10-23",
        "repositories": {
            "public_metadata_dataset": {
                "visibility": "public",
                "repo_type": "dataset",
            },
            "private_derived_index_dataset": {
                "visibility": "private",
                "repo_type": "dataset",
            },
        },
        "assets": [
            {
                "logical_id": "public.metadata",
                "local_path": "data/hf_recon",
                "bytes": 12,
                "sha256_or_manifest_hash": "sha256:abc",
                "license_source": "project",
                "sensitivity": "public",
                "target_repo_type": "dataset_public_metadata",
                "proposed_hf_path": "metadata/",
                "upload_policy": "public_metadata_only",
                "release_review_status": "approved",
                "reconstruction_command": "python rebuild.py",
                "dependencies": ["data/restricted/private.json"],
            },
            {
                "logical_id": "model.identity",
                "local_path": "data/restricted/models/model",
                "bytes": 99,
                "sha256_or_manifest_hash": "sha256:def",
                "license_source": "upstream",
                "sensitivity": "identity only",
                "target_repo_type": "upstream_model_reference_only",
                "proposed_hf_path": None,
                "upload_policy": "redownload_upstream",
                "reconstruction_command": "download to data/restricted/models/model",
                "dependencies": [],
            },
            {
                "logical_id": "private.derived",
                "local_path": "data/restricted/private-index",
                "bytes": 100,
                "sha256_or_manifest_hash": "sha256:ghi",
                "license_source": "private",
                "sensitivity": "private",
                "target_repo_type": "dataset_private_derived",
                "proposed_hf_path": "derived/",
                "upload_policy": "private_derived_index",
                "reconstruction_command": "private",
                "dependencies": [],
            },
        ],
    }
    return {
        "docs/migration/HF_DATASET_CARD.md": (
            b"---\nlicense: apache-2.0\n---\n# Test metadata release\n"
        ),
        "LICENSE": b"Apache License test fixture.\n",
        "docs/migration/THIRD_PARTY_DATA_NOTICE.md": (
            b"# Third-party notice\nNo third-party payload is included.\n"
        ),
        "docs/overview/authoritative_cvpr_state_2026-10-23.md": (
            b"# Authoritative state\nPAPER_CLAIM_READY = false\n"
        ),
        "data/rehearsal_plan/post_migration_cvpr_work_queue.json": json_bytes(
            {"status": "SCIENTIFIC_EXECUTION_BLOCKED", "queue": ["human review"]}
        ),
        "data/migration/hf_asset_manifest.json": json_bytes(asset_manifest),
        "src/example.py": b"VALUE = 1\n",
    }


def write_public_snapshot(
    root: Path,
    *,
    status: str = "READY",
    payload: dict[str, bytes] | None = None,
) -> None:
    payload = payload or fixture_payload()
    rows = []
    checksum_lines = []
    for relative, content in sorted(payload.items()):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        rows.append(
            {
                "path": relative,
                "sha256": digest,
                "size_bytes": len(content),
                "mode": "0644",
            }
        )
        checksum_lines.append(f"{digest}  {relative}\n")
    manifest = {
        "schema_version": 1,
        "as_of_date": "2026-10-23",
        "release_status": status,
        "snapshot_content_ready": True,
        "license_choice": "Apache-2.0",
        "snapshot_summary": {"payload_file_count": len(payload)},
        "content_blockers": [],
        "owner_blockers": [],
        "files": rows,
        "policy_decisions": [
            {
                "path": "internal-only-detail",
                "strategy": "copy",
                "reason": "not needed in HF metadata release",
            }
        ],
    }
    (root / "PUBLIC_SNAPSHOT_MANIFEST.json").write_bytes(json_bytes(manifest))
    (root / "SHA256SUMS").write_text("".join(checksum_lines))


def run_builder(
    source: Path, destination: Path, *extra: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(source),
            "--destination",
            str(destination),
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_default_is_dry_run_and_does_not_create_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "public"
    source.mkdir()
    write_public_snapshot(source)
    destination = Path("/tmp") / f"hf-metadata-dry-{tmp_path.parent.name}-{tmp_path.name}"

    completed = run_builder(source, destination)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["mode"] == "dry-run"
    assert result["metadata_only"] is True
    assert result["network_access"] is False
    assert result["token_access"] is False
    assert result["upload_performed"] is False
    assert not destination.exists()


def test_execute_writes_only_allowlisted_metadata_and_valid_indexes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "public"
    source.mkdir()
    write_public_snapshot(source)
    destination = Path("/tmp") / f"hf-metadata-execute-{tmp_path.parent.name}-{tmp_path.name}"

    completed = run_builder(source, destination, "--execute")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    actual_files = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    }
    assert actual_files == {
        "README.md",
        "LICENSE",
        "THIRD_PARTY_DATA_NOTICE.md",
        "metadata/authoritative_cvpr_state_2026-10-23.md",
        "metadata/post_migration_cvpr_work_queue.json",
        "metadata/hf_asset_manifest.json",
        "metadata/PUBLIC_SNAPSHOT_MANIFEST.json",
        "metadata/PUBLIC_SNAPSHOT_SHA256SUMS",
        "HF_RELEASE_MANIFEST.json",
        "SHA256SUMS",
    }
    assert (destination / "README.md").read_bytes() == (
        source / "docs/migration/HF_DATASET_CARD.md"
    ).read_bytes()
    assert not (destination / "src/example.py").exists()
    assert not any(path.is_symlink() for path in destination.rglob("*"))

    sanitized = json.loads(
        (destination / "metadata/hf_asset_manifest.json").read_text()
    )
    assert sanitized["metadata_only"] is True
    assert {item["logical_id"] for item in sanitized["assets"]} == {
        "public.metadata",
        "model.identity",
    }
    serialized = json.dumps(sanitized)
    assert "data/restricted" not in serialized
    for asset in sanitized["assets"]:
        assert "local_path" not in asset
        assert "reconstruction_command" not in asset
        assert "dependencies" not in asset

    public_manifest = json.loads(
        (destination / "metadata/PUBLIC_SNAPSHOT_MANIFEST.json").read_text()
    )
    assert public_manifest["release_status"] == "READY"
    assert "files" not in public_manifest
    assert "policy_decisions" not in public_manifest

    builder.audit_release_directory(destination)
    checked = subprocess.run(
        ["sha256sum", "--check", "SHA256SUMS"],
        cwd=destination,
        check=False,
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr


def test_tampered_source_checksum_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "public"
    source.mkdir()
    write_public_snapshot(source)
    (source / "LICENSE").write_text("tampered after audit\n")
    destination = Path("/tmp") / f"hf-metadata-tampered-{tmp_path.parent.name}-{tmp_path.name}"

    completed = run_builder(source, destination)

    assert completed.returncode != 0
    assert "digest mismatch: LICENSE" in completed.stderr
    assert not destination.exists()


def test_non_ready_public_snapshot_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "public"
    source.mkdir()
    write_public_snapshot(source, status="BLOCKED_LICENSE")
    destination = Path("/tmp") / f"hf-metadata-not-ready-{tmp_path.parent.name}-{tmp_path.name}"

    completed = run_builder(source, destination)

    assert completed.returncode != 0
    assert "release_status must be READY" in completed.stderr
    assert not destination.exists()


def test_symlink_source_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "public"
    source.mkdir()
    write_public_snapshot(source)
    target = source / "real-license"
    target.write_text("Apache License test fixture.\n")
    (source / "LICENSE").unlink()
    (source / "LICENSE").symlink_to(target)
    destination = Path("/tmp") / f"hf-metadata-symlink-{tmp_path.parent.name}-{tmp_path.name}"

    completed = run_builder(source, destination)

    assert completed.returncode != 0
    assert "refusing source symlink: LICENSE" in completed.stderr
    assert not destination.exists()


def test_secret_in_allowlisted_metadata_is_rejected(tmp_path: Path) -> None:
    payload = fixture_payload()
    secret_name = "access_" + "token"
    secret_value = "hf" + "_" + "abcdefghijklmnopqrstuvwxyz"
    payload["docs/migration/HF_DATASET_CARD.md"] = (
        f'# Unsafe\n{secret_name} = "{secret_value}"\n'.encode()
    )
    source = tmp_path / "public"
    source.mkdir()
    write_public_snapshot(source, payload=payload)
    destination = Path("/tmp") / f"hf-metadata-secret-{tmp_path.parent.name}-{tmp_path.name}"

    completed = run_builder(source, destination)

    assert completed.returncode != 0
    assert "credential/secret material is forbidden in README.md" in completed.stderr
    assert not destination.exists()


def test_restricted_path_in_source_manifest_is_rejected(tmp_path: Path) -> None:
    payload = fixture_payload()
    payload["data/restricted/should-not-exist.json"] = b"{}\n"
    source = tmp_path / "public"
    source.mkdir()
    write_public_snapshot(source, payload=payload)
    destination = Path("/tmp") / f"hf-metadata-restricted-{tmp_path.parent.name}-{tmp_path.name}"

    completed = run_builder(source, destination)

    assert completed.returncode != 0
    assert "restricted path is forbidden" in completed.stderr
    assert not destination.exists()


def test_manifest_checksum_validation_detects_release_tamper(
    tmp_path: Path,
) -> None:
    source = tmp_path / "public"
    source.mkdir()
    write_public_snapshot(source)
    destination = Path("/tmp") / f"hf-metadata-manifest-{tmp_path.parent.name}-{tmp_path.name}"
    completed = run_builder(source, destination, "--execute")
    assert completed.returncode == 0, completed.stdout + completed.stderr

    release_manifest = json.loads(
        (destination / "HF_RELEASE_MANIFEST.json").read_text()
    )
    readme_row = next(
        item for item in release_manifest["files"] if item["path"] == "README.md"
    )
    assert readme_row["sha256"] == hashlib.sha256(
        (destination / "README.md").read_bytes()
    ).hexdigest()
    checksum_rows = (destination / "SHA256SUMS").read_text().splitlines()
    assert any(row.endswith("  HF_RELEASE_MANIFEST.json") for row in checksum_rows)
    (destination / "README.md").write_text("tampered release\n")

    try:
        builder.audit_release_directory(destination)
    except ValueError as error:
        assert "HF release manifest checksum mismatch: README.md" in str(error)
    else:
        raise AssertionError("release tamper should fail manifest checksum audit")


def test_execute_refuses_nonempty_or_non_tmp_destination(tmp_path: Path) -> None:
    source = tmp_path / "public"
    source.mkdir()
    write_public_snapshot(source)
    nonempty = Path("/tmp") / f"hf-metadata-nonempty-{tmp_path.parent.name}-{tmp_path.name}"
    nonempty.mkdir()
    (nonempty / "existing.txt").write_text("keep\n")

    completed = run_builder(source, nonempty, "--execute")
    assert completed.returncode != 0
    assert "destination must be new and absent" in completed.stderr
    assert (nonempty / "existing.txt").read_text() == "keep\n"

    outside = Path("/var/tmp") / f"test-hf-metadata-outside-{os.getpid()}"
    rejected = run_builder(source, outside, "--execute")
    assert rejected.returncode != 0
    assert "destination must be under /tmp" in rejected.stderr
    assert not outside.exists()
