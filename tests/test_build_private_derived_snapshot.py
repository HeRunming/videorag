from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_private_derived_snapshot.py"


def load_script():
    spec = importlib.util.spec_from_file_location(
        "build_private_derived_snapshot_for_test", SCRIPT
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
    ).encode("utf-8")


def write_fixture_repository(
    root: Path,
    *,
    payload: dict[str, bytes] | None = None,
    regenerable_old_paths: list[str] | None = None,
    explicit_exclusions: list[dict[str, str]] | None = None,
) -> None:
    payload = payload or {
        "data/restricted/demo/index.json": json_bytes(
            {"candidate": "cand-001", "score": 0.75}
        ),
        "data/restricted/demo/windows.jsonl": (
            b'{"start": 1, "end": 2}\n{"start": 3, "end": 5}\n'
        ),
        "data/restricted/demo/timing.txt": b"duration_seconds=12.5\n",
    }
    for relative, content in payload.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    assets = {
        "schema_version": "test.hf-assets/1",
        "assets": [
            {
                "logical_id": "derived.demo",
                "local_path": "data/restricted/demo",
                "upload_policy": "private_derived_index",
            },
            {
                "logical_id": "derived.omitted",
                "local_path": "data/restricted/omitted",
                "upload_policy": "private_derived_index",
            },
            {
                "logical_id": "media.blocked",
                "local_path": "data/restricted/media",
                "upload_policy": "never_upload",
            },
        ],
    }
    release = {
        "schema_version": "av-trace.private-derived-release/1.0",
        "generated_date": "2026-10-28",
        "allowlist": [
            {
                "logical_asset": "derived.demo",
                "roots": [
                    {
                        "path": "data/restricted/demo",
                        "reason": "test restoration surface",
                    }
                ],
            }
        ],
        "global_exclusions": {"purpose": "test policy"},
        "explicit_exclusions": explicit_exclusions or [],
        "regenerable_old_path_exclusions": regenerable_old_paths or [],
    }
    migration = root / "data/migration"
    migration.mkdir(parents=True, exist_ok=True)
    (migration / "hf_asset_manifest.json").write_bytes(json_bytes(assets))
    (migration / "private_derived_release_manifest.json").write_bytes(
        json_bytes(release)
    )


def run_builder(
    repository: Path, destination: Path, *extra: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repository-root",
            str(repository),
            "--destination",
            str(destination),
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_default_is_dry_run_and_writes_nothing(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    write_fixture_repository(repository)
    destination = tmp_path / "dry-run-snapshot"

    completed = run_builder(repository, destination)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["mode"] == "dry-run"
    assert result["classification"] == "PRIVATE"
    assert result["selected_file_count"] == 3
    assert result["selected_bytes"] == sum(
        path.stat().st_size
        for path in (repository / "data/restricted/demo").iterdir()
    )
    assert result["network_access"] is False
    assert result["token_access"] is False
    assert result["upload_performed"] is False
    assert result["out_of_scope_private_derived_logical_assets"] == [
        "derived.omitted"
    ]
    assert not destination.exists()


def test_execute_preserves_exact_paths_and_builds_complete_checksums(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    write_fixture_repository(repository)
    destination = tmp_path / "private-snapshot"

    completed = run_builder(repository, destination, "--execute")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload_relative = "data/restricted/demo/index.json"
    assert (destination / payload_relative).read_bytes() == (
        repository / payload_relative
    ).read_bytes()
    assert not (destination / "restricted/demo/index.json").exists()

    manifest = json.loads(
        (destination / "PRIVATE_DERIVED_MANIFEST.json").read_text()
    )
    assert manifest["classification"] == "PRIVATE"
    assert manifest["public_release_suitable"] is False
    rows = {item["path"]: item for item in manifest["files"]}
    assert set(rows) == {
        "data/restricted/demo/index.json",
        "data/restricted/demo/timing.txt",
        "data/restricted/demo/windows.jsonl",
    }
    row = rows[payload_relative]
    assert row["source_logical_asset"] == "derived.demo"
    assert row["reason"] == "test restoration surface"
    assert row["bytes"] == (repository / payload_relative).stat().st_size
    assert row["sha256"] == hashlib.sha256(
        (repository / payload_relative).read_bytes()
    ).hexdigest()
    restore = (destination / "RESTORE.md").read_text()
    assert "PRIVATE" in restore
    assert "not suitable for a public repository" in restore
    assert "reacquired separately" in restore
    assert "non-executable" in restore

    builder.audit_snapshot(destination)
    checked = subprocess.run(
        ["sha256sum", "--check", "SHA256SUMS"],
        cwd=destination,
        check=False,
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr


def test_source_symlink_is_rejected_without_following_it(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    write_fixture_repository(repository)
    target = repository / "outside.json"
    target.write_text('{"outside": true}\n')
    link = repository / "data/restricted/demo/link.json"
    link.symlink_to(target)
    destination = tmp_path / "symlink-snapshot"

    completed = run_builder(repository, destination)

    assert completed.returncode != 0
    assert "refusing source symlink" in completed.stderr
    assert not destination.exists()


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        (
            "secret.txt",
            ("access_" + "token = \"" + "hf" + "_abcdefghijklmnopqrstuvwxyz\"\n").encode(),
            "known_credential_pattern",
        ),
        (
            "key.pem",
            ("-----BEGIN " + "PRIVATE KEY-----\nnot-a-real-key\n").encode(),
            "private_key_material",
        ),
        (
            "internal.txt",
            b"endpoint=https://service.example.internal/v1\n",
            "internal_proxy_or_domain",
        ),
        (
            "old-path.txt",
            ("root=" + "/" + "jizhicfs" + "/karonhe/AV-TRACE/data/restricted/demo\n").encode(),
            "old_absolute_machine_path",
        ),
    ],
    ids=["secret", "private-key", "internal-domain", "old-machine-path"],
)
def test_forbidden_content_is_rejected(
    tmp_path: Path, filename: str, content: bytes, message: str
) -> None:
    repository = tmp_path / "repository"
    write_fixture_repository(
        repository,
        payload={f"data/restricted/demo/{filename}": content},
    )
    destination = tmp_path / "forbidden-content-snapshot"

    completed = run_builder(repository, destination)

    assert completed.returncode != 0
    assert message in completed.stderr
    assert not destination.exists()


def test_old_path_may_only_be_excluded_when_manifest_marks_it_regenerable(
    tmp_path: Path,
) -> None:
    relative = "data/restricted/demo/regenerable.json"
    repository = tmp_path / "repository"
    write_fixture_repository(
        repository,
        payload={
            "data/restricted/demo/keep.json": b'{"keep": true}\n',
            relative: ('{"path": "' + "/" + "jizhicfs" + '/karonhe/AV-TRACE/old"}\n').encode(),
        },
        regenerable_old_paths=[relative],
    )
    destination = tmp_path / "regenerable-snapshot"

    completed = run_builder(repository, destination, "--execute")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (destination / "data/restricted/demo/keep.json").is_file()
    assert not (destination / relative).exists()
    manifest = json.loads(
        (destination / "PRIVATE_DERIVED_MANIFEST.json").read_text()
    )
    exclusions = manifest["exclusions_summary"]["within_allowlisted_roots"]
    assert exclusions["by_reason"] == {
        "manifest_classified_regenerable_old_absolute_path": 1
    }


def test_raw_media_models_runtime_authorization_and_caches_are_excluded(
    tmp_path: Path,
) -> None:
    payload = {
        "data/restricted/demo/keep.json": b'{"keep": true}\n',
        "data/restricted/demo/raw/clip.mp4": b"media bytes",
        "data/restricted/demo/models/weights.bin": b"model bytes",
        "data/restricted/demo/staging/state.json": b"{}\n",
        "data/restricted/demo/acquisition_records/record.json": b"{}\n",
        "data/restricted/demo/runtime_authorization.json": b"{}\n",
        "data/restricted/demo/cache.pyc": b"cache",
        "data/restricted/demo/report.headers": b"HTTP/1.1 200 OK\n",
    }
    repository = tmp_path / "repository"
    write_fixture_repository(repository, payload=payload)
    destination = tmp_path / "exclusion-snapshot"

    completed = run_builder(repository, destination, "--execute")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (destination / "data/restricted/demo/keep.json").is_file()
    for relative in set(payload) - {"data/restricted/demo/keep.json"}:
        assert not (destination / relative).exists()
    manifest = json.loads(
        (destination / "PRIVATE_DERIVED_MANIFEST.json").read_text()
    )
    exclusions = manifest["exclusions_summary"]["within_allowlisted_roots"]
    assert exclusions["file_count"] == 7
    assert set(item["path"] for item in exclusions["files"]) == set(payload) - {
        "data/restricted/demo/keep.json"
    }


def test_invalid_json_and_jsonl_are_rejected(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    write_fixture_repository(
        repository,
        payload={"data/restricted/demo/broken.jsonl": b'{"ok": 1}\nnot-json\n'},
    )
    destination = tmp_path / "invalid-json-snapshot"

    completed = run_builder(repository, destination)

    assert completed.returncode != 0
    assert "invalid JSONL" in completed.stderr
    assert not destination.exists()


def test_execute_destination_guard_rejects_existing_and_non_tmp(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    write_fixture_repository(repository)
    existing = tmp_path / "existing"
    existing.mkdir()
    marker = existing / "keep.txt"
    marker.write_text("keep\n")

    completed = run_builder(repository, existing, "--execute")
    assert completed.returncode != 0
    assert "destination must be new and absent" in completed.stderr
    assert marker.read_text() == "keep\n"

    outside = Path("/var/tmp") / f"private-derived-test-{os.getpid()}"
    rejected = run_builder(repository, outside, "--execute")
    assert rejected.returncode != 0
    assert "destination must be under /tmp" in rejected.stderr
    assert not outside.exists()


def test_tamper_detection_checks_manifest_and_sha256sums(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    write_fixture_repository(repository)
    destination = tmp_path / "tamper-snapshot"
    completed = run_builder(repository, destination, "--execute")
    assert completed.returncode == 0, completed.stdout + completed.stderr

    payload = destination / "data/restricted/demo/index.json"
    payload.write_text('{"tampered": true}\n')

    with pytest.raises(ValueError, match="manifest (?:byte-count|checksum) mismatch"):
        builder.audit_snapshot(destination)
    checked = subprocess.run(
        ["sha256sum", "--check", "SHA256SUMS"],
        cwd=destination,
        check=False,
        capture_output=True,
        text=True,
    )
    assert checked.returncode != 0


def test_manifest_completeness_rejects_unmanifested_file_and_cache(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    write_fixture_repository(repository)
    destination = tmp_path / "complete-snapshot"
    completed = run_builder(repository, destination, "--execute")
    assert completed.returncode == 0, completed.stdout + completed.stderr

    extra = destination / "data/restricted/demo/extra.json"
    extra.write_text("{}\n")
    with pytest.raises(ValueError, match="manifest completeness failure"):
        builder.audit_snapshot(destination)

    extra.unlink()
    cache = destination / "data/restricted/demo/__pycache__"
    cache.mkdir()
    (cache / "extra.pyc").write_bytes(b"cache")
    with pytest.raises(ValueError, match="forbidden directory"):
        builder.audit_snapshot(destination)
