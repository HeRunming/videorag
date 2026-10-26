from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / name
    scripts = str(path.parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bootstrap = load_script("bootstrap_new_machine.py")
readiness = load_script("verify_migration_readiness.py")


def minimal_path_manifest() -> dict:
    return {
        "source_root": "/old/AV-TRACE",
        "scan": {
            "text_suffixes": [".py", ".json", ".md"],
            "skip_directories": [".git", "__pycache__"],
            "max_text_file_bytes": 1024 * 1024,
        },
        "rules": [
            {
                "id": "metadata",
                "classification": "migration_metadata",
                "patterns": ["data/migration/manifest.json"],
                "rewrite_policy": "never",
            },
            {
                "id": "code",
                "classification": "public_code_blocker",
                "patterns": ["scripts/**"],
                "rewrite_policy": "code_change_required",
            },
            {
                "id": "history",
                "classification": "historical_audit_immutable",
                "patterns": ["docs/review/**"],
                "rewrite_policy": "never",
            },
        ],
        "acceptance": {
            "required_repo_files": ["pyproject.toml"],
            "restricted_roots": ["data/restricted"],
            "new_machine_forbidden_authority_patterns": [
                "data/restricted/**/*authorization*.json",
                "data/restricted/**/*attempt*.json",
            ],
            "r22_audit_archive": "data/migration/audit_archive/r22",
            "key_model_free_tests": ["tests/test_migration_bootstrap.py"],
        },
    }


def test_bootstrap_plan_is_inert_and_contains_no_real_secret(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.11"\ndependencies=[]\n'
    )
    manifest = minimal_path_manifest()
    path = tmp_path / "data/migration/manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest))

    report = bootstrap.build_report(
        tmp_path,
        manifest,
        mode="plan",
        new_root="/srv/av-trace",
        repo_url="git@github.com:ORG/AV-TRACE.git",
        python_command="python3.11",
    )

    assert report["dry_run"] is True
    assert all(value is False for value in report["safety"].values())
    assert report["path_rebinding"]["status"] == "PASS"
    rendered = json.dumps(report)
    assert "pip install" in rendered
    assert "INJECT_FROM_SECRET_MANAGER" in rendered
    assert "hf auth login" in rendered


def test_path_scan_blocks_code_but_preserves_history(tmp_path: Path) -> None:
    manifest = minimal_path_manifest()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/run.py").write_text("ROOT = '/old/AV-TRACE'\n")
    (tmp_path / "docs/review").mkdir(parents=True)
    (tmp_path / "docs/review/old.md").write_text("ran in /old/AV-TRACE\n")
    (tmp_path / "data/migration").mkdir(parents=True)
    (tmp_path / "data/migration/manifest.json").write_text(
        json.dumps({"source_root": "/old/AV-TRACE"})
    )

    report = bootstrap.scan_path_references(tmp_path, manifest)
    by_path = {item["path"]: item for item in report["findings"]}

    assert report["status"] == "BLOCKED"
    assert by_path["scripts/run.py"]["classification"] == "public_code_blocker"
    assert by_path["docs/review/old.md"]["classification"] == "historical_audit_immutable"
    assert by_path["data/migration/manifest.json"]["classification"] == "migration_metadata"
    assert report["mutations_performed"] is False


def test_private_tree_requires_exact_modes_and_no_symlinks(tmp_path: Path) -> None:
    restricted = tmp_path / "data/restricted"
    restricted.mkdir(parents=True)
    payload = restricted / "payload.json"
    payload.write_text("{}")
    restricted.chmod(0o700)
    payload.chmod(0o600)

    assert readiness.verify_private_tree(restricted)["status"] == "PASS"

    payload.chmod(0o644)
    failed = readiness.verify_private_tree(restricted)
    assert failed["status"] == "BLOCKED"
    assert "expected 0600" in failed["findings"][0]["reason"]


def test_old_authorization_and_attempts_are_not_reusable(tmp_path: Path) -> None:
    manifest = minimal_path_manifest()
    restricted = tmp_path / "data/restricted/run"
    restricted.mkdir(parents=True)
    (restricted / "new_authorization.json").write_text("{}")
    (restricted / "x.attempt-R22.json").write_text("{}")
    (restricted.parent / "root.attempt-R22.json").write_text("{}")

    report = readiness.verify_no_reused_authority(tmp_path, manifest)

    assert report["status"] == "BLOCKED"
    assert len(report["matches"]) == 3


def test_r22_archive_must_be_read_only(tmp_path: Path) -> None:
    manifest = minimal_path_manifest()
    archive = tmp_path / manifest["acceptance"]["r22_audit_archive"]
    archive.mkdir(parents=True)
    capsule = archive / "capsule.json"
    capsule.write_text("{}")
    archive.chmod(0o500)
    capsule.chmod(0o400)

    assert readiness.verify_r22_archive(tmp_path, manifest)["status"] == "PASS"

    capsule.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert readiness.verify_r22_archive(tmp_path, manifest)["status"] == "BLOCKED"


def test_asset_verifier_checks_supporting_manifest_hash(tmp_path: Path) -> None:
    source = tmp_path / "data/restricted/example"
    source.mkdir(parents=True)
    payload = source / "payload.bin"
    payload.write_bytes(b"abc")
    evidence = source / "manifest.json"
    evidence.write_text('{"sha256": "example"}\n')
    declared = "sha256:" + readiness.sha256_file(evidence)
    asset = {
        "logical_id": "media.example",
        "upload_policy": "redownload_upstream",
        "local_path": "data/restricted/example",
        "file_count": 2,
        "bytes": payload.stat().st_size + evidence.stat().st_size,
        "sha256_or_manifest_hash": declared,
        "hash_basis": (
            "manifest hash of data/restricted/example/manifest.json "
            f"({evidence.stat().st_size} bytes)"
        ),
        "reconstruction_command": "redownload",
    }

    result = readiness.verify_asset(
        tmp_path, asset, hash_limit=1024, full_hash=False
    )

    assert result["status"] == "PASS"
    evidence.write_text("{}\n")
    assert (
        readiness.verify_asset(
            tmp_path, asset, hash_limit=1024, full_hash=False
        )["status"]
        == "BLOCKED"
    )


def test_nonrequired_historical_asset_drift_is_informational(tmp_path: Path) -> None:
    source = tmp_path / "data/restricted/history"
    source.mkdir(parents=True)
    (source / "extra.json").write_text("{}")
    asset = {
        "logical_id": "media.history",
        "upload_policy": "never_upload",
        "local_path": "data/restricted/history",
        "file_count": 0,
        "bytes": 0,
        "sha256_or_manifest_hash": "sha256:" + "0" * 64,
        "hash_basis": "existing verified file hashes and small-file SHA-256 identities",
        "reconstruction_command": "reacquire",
    }

    result = readiness.verify_asset(
        tmp_path, asset, hash_limit=1024, full_hash=False
    )

    assert result["status"] == "INFO"
    assert result["checks"][0]["status"] == "INFO"


def test_model_revision_can_be_parsed_from_license_record() -> None:
    assert (
        readiness._model_revision(
            {
                "reconstruction_command": "python downloader.py --execute",
                "license_source": (
                    "owner/model exact revision "
                    "a09a35458c702b33eeacc393d103063234e8bc28; Apache-2.0"
                ),
            }
        )
        == "a09a35458c702b33eeacc393d103063234e8bc28"
    )


def test_repository_path_manifest_is_well_formed() -> None:
    manifest = bootstrap.load_json(
        ROOT / "data/migration/path_rebinding_manifest.json"
    )
    assert manifest["source_root"] == "/path/to/av-trace"
    assert manifest["safe_rewrite_plan"]["default_mode"] == "dry-run"
    assert manifest["safe_rewrite_plan"][
        "automatic_in_place_rewrites_currently_allowed"
    ] == []
    assert {
        "public_code_blocker",
        "restricted_runtime_config",
        "historical_audit_immutable",
    } <= manifest["classification_definitions"].keys()
