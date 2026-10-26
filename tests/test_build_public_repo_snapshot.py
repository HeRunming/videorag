from __future__ import annotations

import json
import os
import subprocess
import sys
import ast
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "build_public_repo_snapshot.py"
)


def write_fixture(root: Path) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "src" / "clean.py").write_text("VALUE = 1\n")
    blocked = root / "tools" / "route.py"
    blocked.parent.mkdir()
    internal = "hy" + "-proxy" + "." + "woa" + ".com"
    machine_path = "/" + "jizhicfs" + "/private/work"
    private_id = "external-gateway-dev-" + "controller-123"
    blocked.write_text(
        f'PROXY = "{internal}"\nROOT = "{machine_path}"\nRUN = "{private_id}"\n'
    )
    os.chmod(blocked, 0o750)

    migration = root / "docs" / "migration"
    migration.mkdir(parents=True)
    (migration / "LICENSE_DECISION_REQUIRED.md").write_text("decision required\n")
    (migration / "THIRD_PARTY_DATA_NOTICE.md").write_text("third party notice\n")

    large = root / "data" / "rehearsal_plan"
    large.mkdir(parents=True)
    (large / "source_exposure_alias_manifest_v2.json").write_text("x" * 131072)

    policy_dir = root / "data" / "migration"
    policy_dir.mkdir(parents=True)
    policy = policy_dir / "public_repo_manifest.json"
    policy.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "required_copy_paths": [
                    "data/migration/public_repo_manifest.json"
                ],
                "strategy_rules": [
                    {
                        "path": ".",
                        "checks": ["license_boundary"],
                        "strategy": "require-owner",
                        "reason": "owner license choice",
                    },
                    {
                        "path": (
                            "data/rehearsal_plan/"
                            "source_exposure_alias_manifest_v2.json"
                        ),
                        "checks": ["large_file"],
                        "strategy": "redact-generated",
                        "replacement_path": (
                            "data/rehearsal_plan/"
                            "source_exposure_alias_manifest_v2_PUBLIC_SUMMARY.json"
                        ),
                        "reason": "large source summary only",
                    },
                    {
                        "path": "tools/*",
                        "checks": [
                            "internal_domain",
                            "absolute_machine_path",
                            "private_governance_id",
                        ],
                        "strategy": "rewrite-copy",
                        "reason": "sanitize staged tool",
                    },
                    {
                        "path": "*",
                        "checks": ["*"],
                        "strategy": "require-owner",
                        "reason": "fail closed",
                    },
                ],
            },
            indent=2,
        )
        + "\n"
    )
    return policy


def run_builder(
    root: Path, policy: Path, *extra: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(root),
            "--manifest",
            str(policy),
            "--as-of-date",
            "2026-10-23",
            "--large-file-bytes",
            "65536",
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_dry_run_is_default_and_does_not_create_destination(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    policy = write_fixture(root)
    destination = tmp_path / "snapshot"
    result_path = tmp_path / "result.json"

    completed = run_builder(
        root,
        policy,
        "--destination",
        str(destination),
        "--json-output",
        str(result_path),
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(result_path.read_text())
    assert result["mode"] == "dry-run"
    assert result["release_status"] == "BLOCKED_LICENSE"
    assert result["snapshot_content_ready"] is True
    assert not destination.exists()


def test_execute_builds_clean_snapshot_with_modes_and_indexes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    policy = write_fixture(root)
    destination = tmp_path / "snapshot"
    result_path = tmp_path / "result.json"

    completed = run_builder(
        root,
        policy,
        "--execute",
        "--destination",
        str(destination),
        "--json-output",
        str(result_path),
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (destination / "LICENSE_DECISION_REQUIRED").is_file()
    assert not (destination / "LICENSE").exists()
    assert not (
        destination
        / "data/rehearsal_plan/source_exposure_alias_manifest_v2.json"
    ).exists()
    assert (
        destination
        / "data/rehearsal_plan/source_exposure_alias_manifest_v2_PUBLIC_SUMMARY.json"
    ).is_file()
    rewritten = (destination / "tools/route.py").read_text()
    assert "https://proxy.example.invalid:3128" in rewritten
    assert "/path/to/av-trace" in rewritten
    assert "PUBLIC_REDACTED_IDENTIFIER" in rewritten
    assert (destination / "tools/route.py").stat().st_mode & 0o777 == 0o750

    manifest = json.loads(
        (destination / "PUBLIC_SNAPSHOT_MANIFEST.json").read_text()
    )
    assert manifest["release_status"] == "BLOCKED_LICENSE"
    assert manifest["snapshot_content_ready"] is True
    assert manifest["snapshot_summary"]["content_blocker_count"] == 0

    checked = subprocess.run(
        ["sha256sum", "--check", "SHA256SUMS"],
        cwd=destination,
        check=False,
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr


def test_python_sanitizer_changes_only_literals_and_comments() -> None:
    spec = __import__("importlib.util").util.spec_from_file_location(
        "snapshot_builder_for_test", SCRIPT
    )
    assert spec and spec.loader
    module = __import__("importlib.util").util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    internal = "star" + "-proxy" + "." + "oa" + ".com"
    private_identifier = "star" + "_proxy"
    source = (
        f"{private_identifier} = 1\n"
        f'URL = "http://{internal}:3128"\n'
        f"# fallback {internal}:3128\n"
    ).encode()

    rewritten = module._sanitize_copy(
        "tool.py", source, {"internal_domain"}
    ).decode()

    ast.parse(rewritten)
    assert "primary_proxy = 1" in rewritten
    assert private_identifier not in rewritten.lower()
    assert internal not in rewritten
    assert rewritten.count("https://proxy.example.invalid:3128") == 2


def test_python_identifier_sanitizer_is_idempotent() -> None:
    spec = __import__("importlib.util").util.spec_from_file_location(
        "snapshot_builder_idempotency_test", SCRIPT
    )
    assert spec and spec.loader
    module = __import__("importlib.util").util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    source = (
        "primary_proxy = 'example'\n"
        "fallback_proxy = 'example'\n"
        "primary_proxy = primary_proxy\n"
        "fallback_proxy = fallback_proxy\n"
    ).encode()

    once = module._sanitize_copy(
        "tool.py", source, {"internal_domain"}
    )
    twice = module._sanitize_copy(
        "tool.py", once, {"internal_domain"}
    )

    assert twice == once


def test_json_sanitizer_parse_transform_dump() -> None:
    spec = __import__("importlib.util").util.spec_from_file_location(
        "snapshot_builder_json_test", SCRIPT
    )
    assert spec and spec.loader
    module = __import__("importlib.util").util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    internal = "star" + "-proxy" + "." + "oa" + ".com"
    rewritten = module._sanitize_copy(
        "manifest.json",
        json.dumps({"proxy": f"http://{internal}:3128", "count": 3}).encode(),
        {"internal_domain"},
    )
    value = json.loads(rewritten)
    assert value["proxy"] == "https://proxy.example.invalid:3128"
    assert value["count"] == 3


def test_invalid_python_blocks_content_ready(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    policy = write_fixture(root)
    (root / "src" / "broken.py").write_text("def broken(:\n")
    result_path = tmp_path / "result.json"

    completed = run_builder(
        root,
        policy,
        "--json-output",
        str(result_path),
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(result_path.read_text())
    assert result["snapshot_content_ready"] is False
    assert result["release_status"] == "BLOCKED_CONTENT"


def test_owner_license_interface_can_produce_ready_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    policy = write_fixture(root)
    destination = tmp_path / "snapshot"
    license_file = tmp_path / "OWNER_LICENSE.txt"
    license_file.write_text("Owner-approved test license text.\n")

    completed = run_builder(
        root,
        policy,
        "--execute",
        "--destination",
        str(destination),
        "--license-choice",
        "OWNER-APPROVED-TEST",
        "--license-file",
        str(license_file),
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (destination / "LICENSE").read_text() == license_file.read_text()
    assert not (destination / "LICENSE_DECISION_REQUIRED").exists()
    manifest = json.loads(
        (destination / "PUBLIC_SNAPSHOT_MANIFEST.json").read_text()
    )
    assert manifest["release_status"] == "READY"
    assert manifest["owner_blockers"] == []


def test_execute_refuses_nonempty_destination(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    policy = write_fixture(root)
    destination = tmp_path / "snapshot"
    destination.mkdir()
    (destination / "existing.txt").write_text("do not overwrite\n")

    completed = run_builder(
        root,
        policy,
        "--execute",
        "--destination",
        str(destination),
    )

    assert completed.returncode != 0
    assert "refusing overwrite" in completed.stderr
    assert (destination / "existing.txt").read_text() == "do not overwrite\n"


def test_destination_must_be_outside_source_repository(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    policy = write_fixture(root)
    destination = root / "public-snapshot"

    completed = run_builder(
        root,
        policy,
        "--execute",
        "--destination",
        str(destination),
    )

    assert completed.returncode != 0
    assert "outside the source repository" in completed.stderr
    assert not destination.exists()
