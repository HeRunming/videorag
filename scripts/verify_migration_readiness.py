#!/usr/bin/env python3
"""Model-free, fail-closed AV-TRACE migration readiness verifier."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import bootstrap_new_machine as bootstrap


DEFAULT_REBIND_MANIFEST = Path("data/migration/path_rebinding_manifest.json")
DEFAULT_ASSET_MANIFEST = Path("data/migration/hf_asset_manifest.json")
REQUIRED_EXECUTABLES = ("git", "git_lfs", "ffmpeg", "ffprobe")
REQUIRED_CORE_DISTRIBUTIONS = ("av", "jsonschema", "numpy", "Pillow")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_check(
    checks: list[dict[str, Any]],
    *,
    check_id: str,
    status: str,
    summary: str,
    details: Any = None,
    blocking: bool = True,
) -> None:
    checks.append(
        {
            "id": check_id,
            "status": status,
            "blocking": blocking,
            "summary": summary,
            "details": details,
        }
    )


def verify_repo_files(root: Path, rebind_manifest: dict[str, Any]) -> dict[str, Any]:
    required = rebind_manifest["acceptance"]["required_repo_files"]
    missing = [path for path in required if not (root / path).is_file()]
    return {"status": "PASS" if not missing else "BLOCKED", "required": required, "missing": missing}


def _is_private_mode(mode: int, *, directory: bool) -> bool:
    expected = 0o700 if directory else 0o600
    return stat.S_IMODE(mode) == expected


def verify_private_tree(path: Path) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    if path.is_symlink():
        return {"status": "BLOCKED", "findings": [{"path": str(path), "reason": "root is a symlink"}]}
    if not path.exists():
        return {"status": "NOT_PRESENT", "findings": []}
    for directory, dirnames, filenames in os.walk(path, followlinks=False):
        directory_path = Path(directory)
        try:
            mode = directory_path.lstat().st_mode
        except OSError as exc:
            findings.append({"path": str(directory_path), "reason": str(exc)})
            continue
        if not _is_private_mode(mode, directory=True):
            findings.append(
                {
                    "path": str(directory_path),
                    "reason": f"directory mode is {stat.S_IMODE(mode):04o}, expected 0700",
                }
            )
        safe_dirs = []
        for name in dirnames:
            child = directory_path / name
            if child.is_symlink():
                findings.append({"path": str(child), "reason": "symlink directory is forbidden"})
            else:
                safe_dirs.append(name)
        dirnames[:] = safe_dirs
        for name in filenames:
            child = directory_path / name
            try:
                info = child.lstat()
            except OSError as exc:
                findings.append({"path": str(child), "reason": str(exc)})
                continue
            if stat.S_ISLNK(info.st_mode):
                findings.append({"path": str(child), "reason": "symlink file is forbidden"})
            elif not stat.S_ISREG(info.st_mode):
                findings.append({"path": str(child), "reason": "non-regular file is forbidden"})
            elif not _is_private_mode(info.st_mode, directory=False):
                findings.append(
                    {
                        "path": str(child),
                        "reason": f"file mode is {stat.S_IMODE(info.st_mode):04o}, expected 0600",
                    }
                )
    return {"status": "PASS" if not findings else "BLOCKED", "findings": findings}


def verify_restricted_permissions(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    results = {}
    for relative in manifest["acceptance"]["restricted_roots"]:
        results[relative] = verify_private_tree(root / relative)
    blocked = any(item["status"] == "BLOCKED" for item in results.values())
    return {"status": "BLOCKED" if blocked else "PASS", "roots": results}


def verify_no_reused_authority(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    matches: list[str] = []
    patterns = manifest["acceptance"]["new_machine_forbidden_authority_patterns"]
    for path in root.rglob("*"):
        if ".git" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        if any(bootstrap._matches(relative, pattern) for pattern in patterns):
            matches.append(relative)
    return {
        "status": "PASS" if not matches else "BLOCKED",
        "matches": sorted(set(matches)),
        "reason": "Old attempts and authorization records are audit evidence only and cannot authorize new-machine execution.",
    }


def verify_r22_archive(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    archive = root / manifest["acceptance"]["r22_audit_archive"]
    if not archive.exists():
        return {"status": "NOT_PRESENT", "path": str(archive), "findings": []}
    findings = []
    for path in [archive, *archive.rglob("*")]:
        info = path.lstat()
        if path.is_symlink():
            findings.append({"path": str(path), "reason": "symlink forbidden"})
        elif info.st_mode & stat.S_IWUSR:
            findings.append({"path": str(path), "reason": "R22 audit archive must be owner-read-only"})
    return {"status": "PASS" if not findings else "BLOCKED", "path": str(archive), "findings": findings}


def _concrete_path(value: str) -> bool:
    return not any(char in value for char in "*{}<>") and " and " not in value


def _manifest_hash_source(hash_basis: str) -> str | None:
    match = re.search(r"manifest hash of ([^ ]+) \(", hash_basis)
    return match.group(1) if match else None


def _model_revision(asset: dict[str, Any]) -> str | None:
    fields = (
        str(asset.get("reconstruction_command", "")),
        str(asset.get("license_source", "")),
    )
    patterns = (
        r"revision=['\"]([0-9a-f]{7,64})['\"]",
        r"\brevision ([0-9a-f]{7,64})\b",
    )
    for field in fields:
        for pattern in patterns:
            match = re.search(pattern, field)
            if match:
                return match.group(1)
    return None


def verify_asset(
    root: Path,
    asset: dict[str, Any],
    *,
    hash_limit: int,
    full_hash: bool,
) -> dict[str, Any]:
    policy = asset["upload_policy"]
    local_path = asset["local_path"]
    result: dict[str, Any] = {
        "logical_id": asset["logical_id"],
        "policy": policy,
        "local_path": local_path,
        "declared_identity": asset.get("sha256_or_manifest_hash"),
        "status": "PASS",
        "checks": [],
    }
    if not _concrete_path(local_path):
        result["status"] = "INFO"
        result["checks"].append({"check": "logical_group", "status": "INFO"})
        return result
    path = root / local_path
    if policy == "delete_after_verified_migration":
        present = path.exists()
        result["checks"].append({"check": "staging_absent", "status": "BLOCKED" if present else "PASS"})
        result["status"] = "BLOCKED" if present else "PASS"
        return result
    required = policy == "redownload_upstream"
    if not path.exists():
        result["checks"].append({"check": "path_present", "status": "BLOCKED" if required else "INFO"})
        result["status"] = "BLOCKED" if required else "INFO"
        return result
    if path.is_symlink():
        result["checks"].append({"check": "no_symlink", "status": "BLOCKED"})
        result["status"] = "BLOCKED"
        return result

    if path.is_file():
        files = [path]
    else:
        files = [candidate for candidate in path.rglob("*") if candidate.is_file() and not candidate.is_symlink()]
    actual_bytes = sum(candidate.stat().st_size for candidate in files)
    stats_ok = len(files) == asset["file_count"] and actual_bytes == asset["bytes"]
    inventory_status = "PASS" if stats_ok else ("BLOCKED" if required else "INFO")
    result["checks"].append(
        {
            "check": "inventory",
            "status": inventory_status,
            "expected_files": asset["file_count"],
            "actual_files": len(files),
            "expected_bytes": asset["bytes"],
            "actual_bytes": actual_bytes,
            "note": (
                None
                if stats_ok
                else "Non-required local asset differs from the point-in-time migration inventory; review before relying on it."
            ),
        }
    )
    if not stats_ok and required:
        result["status"] = "BLOCKED"
    elif not stats_ok:
        result["status"] = "INFO"

    declared = str(asset.get("sha256_or_manifest_hash", ""))
    hash_source = _manifest_hash_source(str(asset.get("hash_basis", "")))
    if hash_source:
        source = root / hash_source
        actual = f"sha256:{sha256_file(source)}" if source.is_file() else None
        ok = actual == declared
        result["checks"].append(
            {
                "check": "supporting_manifest_sha256",
                "status": "PASS" if ok else "BLOCKED",
                "path": hash_source,
                "actual": actual,
            }
        )
        if not ok:
            result["status"] = "BLOCKED"
    elif path.is_file() and (full_hash or path.stat().st_size <= hash_limit):
        actual = f"sha256:{sha256_file(path)}"
        ok = actual == declared
        result["checks"].append({"check": "direct_sha256", "status": "PASS" if ok else "BLOCKED", "actual": actual})
        if not ok:
            result["status"] = "BLOCKED"
    else:
        identity_ok = bool(re.fullmatch(r"sha256:[0-9a-f]{64}", declared))
        result["checks"].append(
            {
                "check": "declared_manifest_identity",
                "status": "PASS" if identity_ok else "BLOCKED",
                "note": "Aggregate directory identity is accepted with exact file/byte inventory; use source-specific manifests for per-file hashes.",
            }
        )
        if not identity_ok:
            result["status"] = "BLOCKED"
    return result


def verify_assets(
    root: Path,
    manifest: dict[str, Any],
    *,
    hash_limit: int,
    full_hash: bool,
) -> dict[str, Any]:
    assets = [
        verify_asset(root, asset, hash_limit=hash_limit, full_hash=full_hash)
        for asset in manifest["assets"]
    ]
    blocked = [asset for asset in assets if asset["status"] == "BLOCKED"]
    revisions = []
    for asset in manifest["assets"]:
        if not asset["logical_id"].startswith("model."):
            continue
        command = asset.get("reconstruction_command", "")
        revisions.append(
            {
                "logical_id": asset["logical_id"],
                "local_path": asset["local_path"],
                "revision": _model_revision(asset),
                "redownload_policy": asset["upload_policy"],
                "command": command,
            }
        )
    missing_revisions = [
        item["logical_id"]
        for item in revisions
        if item["logical_id"] != "model.misc.noaa_fallback" and not item["revision"]
    ]
    return {
        "status": "BLOCKED" if blocked or missing_revisions else "PASS",
        "assets": assets,
        "model_snapshots_and_redownload_revisions": revisions,
        "model_revision_blockers": missing_revisions,
        "summary": dict(Counter(asset["status"] for asset in assets)),
    }


def run_key_tests(root: Path, tests: list[str]) -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", "-q", *tests]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    output = "\n".join((result.stdout + "\n" + result.stderr).splitlines()[-80:])
    return {
        "status": "PASS" if result.returncode == 0 else "BLOCKED",
        "command": command,
        "returncode": result.returncode,
        "tail": output,
        "model_free_contract": True,
    }


def build_report(
    root: Path,
    *,
    rebind_manifest: dict[str, Any],
    asset_manifest: dict[str, Any],
    hf_authenticated: bool,
    require_gpu: bool,
    run_tests: bool,
    hash_limit: int,
    full_hash: bool,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    repo_files = verify_repo_files(root, rebind_manifest)
    add_check(
        checks,
        check_id="repo_files",
        status=repo_files["status"],
        summary="Required repository migration files are present.",
        details=repo_files,
    )

    path_scan = bootstrap.scan_path_references(root, rebind_manifest)
    add_check(
        checks,
        check_id="path_rebinding",
        status=path_scan["status"],
        summary="No public-code or unclassified source-root literal remains.",
        details=path_scan,
    )

    environment = bootstrap.system_inventory()
    python_ok = environment["python"]["supported_by_pyproject"]
    add_check(
        checks,
        check_id="python",
        status="PASS" if python_ok else "BLOCKED",
        summary="Python satisfies pyproject >=3.11.",
        details=environment["python"],
    )
    executable_failures = [
        name for name in REQUIRED_EXECUTABLES if not environment["executables"][name]["available"]
    ]
    add_check(
        checks,
        check_id="system_executables",
        status="PASS" if not executable_failures else "BLOCKED",
        summary="git, git-lfs, ffmpeg, and ffprobe are available.",
        details={"missing_or_failed": executable_failures, "probes": environment["executables"]},
    )
    core = {
        item["distribution"]: item
        for item in environment["packages"]["pyproject_core"]
        if item["distribution"] in REQUIRED_CORE_DISTRIBUTIONS
    }
    missing_core = [name for name in REQUIRED_CORE_DISTRIBUTIONS if not core[name]["installed"]]
    add_check(
        checks,
        check_id="python_core_dependencies",
        status="PASS" if not missing_core else "BLOCKED",
        summary="Core pyproject dependencies are installed.",
        details={"missing": missing_core, "packages": core},
    )
    gpu_ok = environment["executables"]["nvidia_smi"]["available"]
    add_check(
        checks,
        check_id="gpu",
        status="PASS" if gpu_ok else ("BLOCKED" if require_gpu else "INFO"),
        summary="GPU driver visibility via nvidia-smi.",
        details=environment["executables"]["nvidia_smi"],
        blocking=require_gpu,
    )
    add_check(
        checks,
        check_id="hf_authentication_attestation",
        status="PASS" if hf_authenticated else "BLOCKED",
        summary="Operator attests that fresh-machine HF authentication succeeded; no token was read by this verifier.",
        details={"attested": hf_authenticated, "token_read": False},
    )

    assets = verify_assets(root, asset_manifest, hash_limit=hash_limit, full_hash=full_hash)
    add_check(
        checks,
        check_id="assets_hashes_and_revisions",
        status=assets["status"],
        summary="Required upstream-redownload assets and declared media/index identities are present.",
        details=assets,
    )

    permissions = verify_restricted_permissions(root, rebind_manifest)
    add_check(
        checks,
        check_id="restricted_permissions",
        status=permissions["status"],
        summary="Restricted directories/files use exact 0700/0600 modes and contain no symlinks.",
        details=permissions,
    )
    authority = verify_no_reused_authority(root, rebind_manifest)
    add_check(
        checks,
        check_id="fresh_authorization_boundary",
        status=authority["status"],
        summary="Old attempt markers and authorization records were not restored as executable authority.",
        details=authority,
    )
    r22 = verify_r22_archive(root, rebind_manifest)
    add_check(
        checks,
        check_id="r22_audit_archive",
        status=r22["status"],
        summary="R22 audit copies, if present, are read-only and separate from runtime authorization.",
        details=r22,
        blocking=r22["status"] == "BLOCKED",
    )

    tests = rebind_manifest["acceptance"]["key_model_free_tests"]
    test_report = run_key_tests(root, tests) if run_tests else {
        "status": "BLOCKED",
        "reason": "Key model-free tests were not run; omit --skip-tests for a readiness decision.",
        "tests": tests,
    }
    add_check(
        checks,
        check_id="key_model_free_tests",
        status=test_report["status"],
        summary="Focused migration and core model-free tests pass.",
        details=test_report,
    )

    blocked = [check for check in checks if check["blocking"] and check["status"] == "BLOCKED"]
    return {
        "schema_version": "av-trace.migration-readiness/1.0",
        "status": "BLOCKED" if blocked else "READY",
        "repo_root": str(root),
        "model_free": True,
        "network_performed": False,
        "token_read": False,
        "model_loaded": False,
        "checks": checks,
        "blockers": [{"id": item["id"], "summary": item["summary"]} for item in blocked],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--path-manifest", type=Path, default=DEFAULT_REBIND_MANIFEST)
    parser.add_argument("--asset-manifest", type=Path, default=DEFAULT_ASSET_MANIFEST)
    parser.add_argument("--hf-authenticated", action="store_true")
    parser.add_argument("--require-gpu", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--hash-limit-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--full-hash", action="store_true")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def print_text(report: dict[str, Any]) -> None:
    print(f"MIGRATION READINESS: {report['status']}")
    for check in report["checks"]:
        print(f"[{check['status']}] {check['id']}: {check['summary']}")
    if report["blockers"]:
        print("\nCurrent blockers:")
        for blocker in report["blockers"]:
            print(f"- {blocker['id']}: {blocker['summary']}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.repo_root.resolve()
    path_manifest_path = args.path_manifest if args.path_manifest.is_absolute() else root / args.path_manifest
    asset_manifest_path = args.asset_manifest if args.asset_manifest.is_absolute() else root / args.asset_manifest
    report = build_report(
        root,
        rebind_manifest=bootstrap.load_json(path_manifest_path),
        asset_manifest=bootstrap.load_json(asset_manifest_path),
        hf_authenticated=args.hf_authenticated,
        require_gpu=args.require_gpu,
        run_tests=not args.skip_tests,
        hash_limit=args.hash_limit_bytes,
        full_hash=args.full_hash,
    )
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2) + "\n")
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print_text(report)
    return 0 if report["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
