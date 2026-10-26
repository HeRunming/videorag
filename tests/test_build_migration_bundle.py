from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_migration_bundle.py"


def load_script():
    spec = importlib.util.spec_from_file_location(
        "build_migration_bundle", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bundle = load_script()


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_fake_public_builder(root: Path) -> None:
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "build_public_repo_snapshot.py").write_text(
        """
from dataclasses import dataclass
import hashlib
import json

@dataclass(frozen=True)
class Item:
    destination: str
    content: bytes
    mode: int = 0o644
    @property
    def sha256(self):
        return hashlib.sha256(self.content).hexdigest()
    @property
    def size_bytes(self):
        return len(self.content)

def build_plan(root, policy, **kwargs):
    return {"root": str(root), "policy": str(policy)}

def sanitize_public_content(path, content):
    return content

def audit_contents(files, *, large_file_bytes):
    return []

def _python_ast_findings(files):
    return []

def audit_snapshot_manifest_files(files):
    return []

def _assemble_snapshot_files(plan):
    payload = Item("README.md", b"public\\n")
    path_manifest = Item(
        "data/migration/path_rebinding_manifest.json", b"{}\\n"
    )
    asset_manifest = Item(
        "data/migration/hf_asset_manifest.json", b"{}\\n"
    )
    sums = Item(
        "SHA256SUMS",
        (
            payload.sha256 + "  README.md\\n"
            + path_manifest.sha256
            + "  data/migration/path_rebinding_manifest.json\\n"
            + asset_manifest.sha256
            + "  data/migration/hf_asset_manifest.json\\n"
        ).encode(),
    )
    manifest = Item(
        "PUBLIC_SNAPSHOT_MANIFEST.json",
        (json.dumps({
            "release_status": "BLOCKED_LICENSE",
            "snapshot_content_ready": True,
            "quality_gates": {"fixture": {"status": "PASS"}},
        }, sort_keys=True) + "\\n").encode(),
    )
    return {
        payload.destination: payload,
        path_manifest.destination: path_manifest,
        asset_manifest.destination: asset_manifest,
        sums.destination: sums,
        manifest.destination: manifest,
    }
""".lstrip()
    )


def write_fixture(root: Path) -> Path:
    write_fake_public_builder(root)
    (root / "data/migration").mkdir(parents=True)
    (root / "data/migration/public_repo_manifest.json").write_text(
        '{"schema_version": 1}\n'
    )
    (root / "data/migration/path_rebinding_manifest.json").write_text("{}\n")
    (root / "data/migration/hf_asset_manifest.json").write_text("{}\n")
    (root / "README.md").write_text("handoff\n")
    builder = root / "scripts/build_public_repo_snapshot.py"
    policy = root / "data/migration/public_repo_manifest.json"
    source = root / "README.md"
    manifest = {
        "schema_version": "av-trace.migration-bundle-manifest/1.0",
        "as_of_date": "2026-10-23",
        "safety": {"max_file_bytes": 1024 * 1024},
        "public_snapshot": {
            "builder": "scripts/build_public_repo_snapshot.py",
            "policy": "data/migration/public_repo_manifest.json",
            "bundle_prefix": "public_snapshot",
            "large_file_bytes": 1024 * 1024,
            "expected_release_status": "BLOCKED_LICENSE",
            "bindings": {
                "builder": {
                    "bytes": builder.stat().st_size,
                    "sha256": sha256(builder),
                },
                "policy": {
                    "bytes": policy.stat().st_size,
                    "sha256": sha256(policy),
                },
            },
        },
        "source_files": [
            {
                "path": "README.md",
                "role": "handoff",
                "bytes": source.stat().st_size,
                "sha256": sha256(source),
            },
            {
                "path": "data/migration/path_rebinding_manifest.json",
                "role": "path_rebinding",
                "bytes": (
                    root / "data/migration/path_rebinding_manifest.json"
                ).stat().st_size,
                "sha256": sha256(
                    root / "data/migration/path_rebinding_manifest.json"
                ),
            },
            {
                "path": "data/migration/hf_asset_manifest.json",
                "role": "hf_asset_manifest",
                "bytes": (
                    root / "data/migration/hf_asset_manifest.json"
                ).stat().st_size,
                "sha256": sha256(
                    root / "data/migration/hf_asset_manifest.json"
                ),
            },
        ],
    }
    path = root / "data/migration/migration_bundle_manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def run_builder(
    root: Path, manifest: Path, destination: Path, *extra: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(root),
            "--manifest",
            str(manifest),
            "--destination",
            str(destination),
            "--as-of-date",
            "2026-10-23",
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_dry_run_does_not_create_destination(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    manifest = write_fixture(root)
    destination = tmp_path / "bundle"
    result_path = tmp_path / "result.json"

    completed = run_builder(
        root,
        manifest,
        destination,
        "--json-output",
        str(result_path),
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(result_path.read_text())
    assert result["mode"] == "dry-run"
    assert result["safety"]["model_calls"] == 0
    assert result["safety"]["tokens_read"] is False
    assert not destination.exists()


def test_execute_writes_two_checksum_layers(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    manifest = write_fixture(root)
    destination = tmp_path / "bundle"

    completed = run_builder(root, manifest, destination, "--execute")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (destination / "BUNDLE_MANIFEST.json").is_file()
    assert (destination / "BUNDLE_SHA256SUMS").is_file()
    assert (
        destination / "public_snapshot/PUBLIC_SNAPSHOT_MANIFEST.json"
    ).is_file()
    assert (destination / "public_snapshot/SHA256SUMS").is_file()

    checked = subprocess.run(
        ["sha256sum", "--check", "BUNDLE_SHA256SUMS"],
        cwd=destination,
        check=False,
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr
    public_checked = subprocess.run(
        ["sha256sum", "--check", "SHA256SUMS"],
        cwd=destination / "public_snapshot",
        check=False,
        capture_output=True,
        text=True,
    )
    assert (
        public_checked.returncode == 0
    ), public_checked.stdout + public_checked.stderr
    assert not list(destination.rglob("__pycache__"))
    assert not list(destination.rglob("*.pyc"))


def test_rejects_restricted_source_path(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    manifest_path = write_fixture(root)
    restricted = root / "data/restricted/payload.json"
    restricted.parent.mkdir(parents=True)
    restricted.write_text("{}")
    manifest = json.loads(manifest_path.read_text())
    manifest["source_files"] = [
        {
            "path": "data/restricted/payload.json",
            "bytes": restricted.stat().st_size,
            "sha256": sha256(restricted),
        }
    ]
    manifest_path.write_text(json.dumps(manifest))

    completed = run_builder(
        root,
        manifest_path,
        tmp_path / "bundle",
    )

    assert completed.returncode != 0
    assert "restricted source path is forbidden" in completed.stderr


def test_rejects_symlink_and_token_pattern(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    manifest_path = write_fixture(root)
    outside = tmp_path / "outside.txt"
    outside.write_text("safe")
    link = root / "linked.txt"
    link.symlink_to(outside)
    manifest = json.loads(manifest_path.read_text())
    manifest["source_files"] = [
        {
            "path": "linked.txt",
            "bytes": outside.stat().st_size,
            "sha256": sha256(outside),
        }
    ]
    manifest_path.write_text(json.dumps(manifest))
    destination = tmp_path / "bundle"

    symlink_result = run_builder(root, manifest_path, destination)
    assert symlink_result.returncode != 0
    assert "source symlink" in symlink_result.stderr

    link.unlink()
    token_file = root / "token.txt"
    token_file.write_text("hf_" + "a" * 32)
    manifest["source_files"] = [
        {
            "path": "token.txt",
            "bytes": token_file.stat().st_size,
            "sha256": sha256(token_file),
        }
    ]
    manifest_path.write_text(json.dumps(manifest))
    token_result = run_builder(root, manifest_path, destination)
    assert token_result.returncode != 0
    assert "possible secret material" in token_result.stderr


def test_repository_manifest_bindings_match_current_files() -> None:
    manifest_path = ROOT / "data/migration/migration_bundle_manifest.json"
    if not manifest_path.is_file():
        pytest.skip(
            "the public repository snapshot intentionally omits the "
            "source-machine migration-bundle manifest"
        )
    manifest = bundle.load_manifest(manifest_path)
    assert manifest["as_of_date"] == "2026-10-26"
    assert manifest["safety"]["include_restricted_files"] is False
    for row in manifest["source_files"]:
        path = ROOT / row["path"]
        assert path.is_file()
        assert row["bytes"] == path.stat().st_size
        assert row["sha256"] == sha256(path)
        assert not row["path"].startswith("data/restricted/")
