from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_public_release.py"
SPEC = importlib.util.spec_from_file_location("audit_public_release", SCRIPT)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


def write_release_notices(root: Path) -> None:
    migration = root / "docs" / "migration"
    migration.mkdir(parents=True)
    (migration / "LICENSE_DECISION_REQUIRED.md").write_text("decision\n")
    (migration / "THIRD_PARTY_DATA_NOTICE.md").write_text("notice\n")
    (root / "LICENSE").write_text("approved test license\n")


def test_boundary_keeps_public_rehearsal_plan_and_excludes_private_artifacts(
    tmp_path: Path,
) -> None:
    write_release_notices(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "module.py").write_text("VALUE = 1\n")
    plan = tmp_path / "data" / "rehearsal_plan"
    plan.mkdir(parents=True)
    (plan / "public_plan.json").write_text("{}\n")
    (plan / "raw_attempts.json").write_text("{}\n")
    (plan / "run_authorization.json").write_text("{}\n")
    restricted = tmp_path / "data" / "restricted"
    restricted.mkdir(parents=True)
    (restricted / "payload.mp4").write_bytes(b"not scanned")

    report = audit.audit_repository(tmp_path)
    candidates = {item["path"] for item in report["candidate_public_files"]}
    excluded = {item["path"] for item in report["excluded_entries"]}

    assert "data/rehearsal_plan/public_plan.json" in candidates
    assert "data/rehearsal_plan/raw_attempts.json" in excluded
    assert "data/rehearsal_plan/run_authorization.json" in excluded
    assert "data/restricted" in excluded
    assert report["summary"]["status"] == "pass"


def test_scanner_reports_and_redacts_sensitive_candidate_content(tmp_path: Path) -> None:
    write_release_notices(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    fake_key = "gh" + "p_" + ("A" * 24)
    machine_path = "/" + "jizhicfs" + "/private/work"
    internal_domain = "hy" + "-proxy" + "." + "woa" + ".com"
    (docs / "unsafe.md").write_text(
        f"key={fake_key}\npath={machine_path}\nproxy={internal_domain}\n"
    )

    report = audit.audit_repository(tmp_path)
    blockers = report["blockers"]
    checks = {item["check"] for item in blockers}

    assert {"secret_pattern", "absolute_machine_path", "internal_domain"} <= checks
    secret = next(item for item in blockers if item["check"] == "secret_pattern")
    assert fake_key not in json.dumps(secret)
    assert "[REDACTED]" in secret["excerpt"]


def test_allowlist_is_applied_and_reported(tmp_path: Path) -> None:
    write_release_notices(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "architecture.md").write_text(
        "legacy path: /" + "root" + "/documented/example\n"
    )
    entry = audit.AllowlistEntry(
        path="docs/architecture.md",
        check="absolute_machine_path",
        reason="historical example reviewed for publication",
    )

    report = audit.audit_repository(tmp_path, allowlist=[entry])

    assert report["summary"]["status"] == "pass"
    assert report["summary"]["allowlisted_finding_count"] == 1
    assert report["allowlisted_findings"][0]["allowlist_reason"] == entry.reason


def test_binary_large_file_and_symlink_are_fail_closed(tmp_path: Path) -> None:
    write_release_notices(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "binary.dat").write_bytes(b"\x00\x01\x02")
    (docs / "large.txt").write_text("x" * 128)
    (docs / "target.txt").write_text("target\n")
    (docs / "link.txt").symlink_to("target.txt")

    report = audit.audit_repository(tmp_path, large_file_bytes=64)
    blockers = {(item["check"], item["path"]) for item in report["blockers"]}

    assert ("binary_file", "docs/binary.dat") in blockers
    assert ("large_file", "docs/large.txt") in blockers
    assert "docs/link.txt" in report["symlinks"]
    assert all(
        item["path"] != "docs/link.txt" for item in report["candidate_public_files"]
    )


def test_missing_code_license_is_a_release_blocker(tmp_path: Path) -> None:
    migration = tmp_path / "docs" / "migration"
    migration.mkdir(parents=True)
    (migration / "LICENSE_DECISION_REQUIRED.md").write_text("decision\n")
    (migration / "THIRD_PARTY_DATA_NOTICE.md").write_text("notice\n")

    report = audit.audit_repository(tmp_path)

    assert report["summary"]["status"] == "blocked"
    assert any(item["check"] == "license_boundary" for item in report["blockers"])


def test_check_cli_passes_clean_fixture_and_writes_manifest(tmp_path: Path) -> None:
    write_release_notices(tmp_path)
    (tmp_path / "README.md").write_text("# clean\n")
    output = tmp_path / "audit.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(tmp_path),
            "--check",
            "--json-output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text())
    assert report["summary"]["status"] == "pass"
    assert any(item["path"] == "README.md" for item in report["candidate_public_files"])
