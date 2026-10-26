#!/usr/bin/env python3
"""Verify a downloaded HF migration mirror without network or token access."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


DEFAULT_MANIFEST = Path("data/migration/hf_asset_manifest.json")
VERIFY_POLICIES = {"public_metadata_only", "private_derived_index"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe relative path: {value}")
    return path


def scan_tree(root: Path) -> tuple[dict[str, Path], list[str]]:
    files: dict[str, Path] = {}
    blockers: list[str] = []
    if root.is_symlink():
        return files, ["mirror root is a symlink"]
    if not root.exists():
        return files, ["mirror root does not exist"]
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        safe_dirs = []
        for name in sorted(dirnames):
            child = directory_path / name
            relative = child.relative_to(root).as_posix()
            if child.is_symlink():
                blockers.append(f"symlink directory: {relative}")
            else:
                safe_dirs.append(name)
        dirnames[:] = safe_dirs
        for name in sorted(filenames):
            child = directory_path / name
            relative = child.relative_to(root).as_posix()
            if child.is_symlink():
                blockers.append(f"symlink file: {relative}")
                continue
            mode = child.lstat().st_mode
            if not stat.S_ISREG(mode):
                blockers.append(f"non-regular file: {relative}")
                continue
            files[relative] = child
    return files, blockers


def expected_files_from_plan(plan: dict, policies: set[str]) -> list[dict]:
    expected = []
    for asset in plan.get("assets", []):
        if asset.get("upload_policy") not in policies or not asset.get("stageable"):
            continue
        prefix = asset.get("proposed_hf_path") or ""
        for item in asset.get("file_checks", []):
            remote = safe_relative(
                item.get("hf_path")
                or str(PurePosixPath(prefix) / PurePosixPath(item["path"]).name)
            )
            expected.append(
                {
                    "logical_id": asset["logical_id"],
                    "path": remote.as_posix(),
                    "bytes": item["bytes"],
                    "sha256": (
                        item["checksum"].removeprefix("sha256:")
                        if item.get("checksum")
                        else None
                    ),
                }
            )
    return expected


def expected_assets_from_manifest(manifest: dict, policies: set[str]) -> list[dict]:
    expected = []
    for asset in manifest.get("assets", []):
        if asset.get("upload_policy") not in policies:
            continue
        proposed = asset.get("proposed_hf_path")
        if not proposed:
            continue
        expected.append(
            {
                "logical_id": asset["logical_id"],
                "path": safe_relative(proposed).as_posix(),
                "bytes": asset["bytes"],
                "file_count": asset["file_count"],
                "identity": asset["sha256_or_manifest_hash"],
            }
        )
    return expected


def verify(
    mirror_root: Path,
    *,
    manifest: dict,
    plan: dict | None,
    policies: set[str],
    require_private_modes: bool,
    allow_extra: bool,
) -> dict:
    files, blockers = scan_tree(mirror_root)
    findings: list[dict] = [
        {"check": "tree_safety", "path": ".", "message": value}
        for value in blockers
    ]
    verified_file_count = 0
    verified_bytes = 0
    expected_paths: set[str] = set()

    if plan:
        expected_files = expected_files_from_plan(plan, policies)
        for item in expected_files:
            expected_paths.add(item["path"])
            path = files.get(item["path"])
            if path is None:
                findings.append(
                    {
                        "check": "missing_file",
                        "path": item["path"],
                        "logical_id": item["logical_id"],
                    }
                )
                continue
            info = path.lstat()
            if info.st_size != item["bytes"]:
                findings.append(
                    {
                        "check": "size_mismatch",
                        "path": item["path"],
                        "expected": item["bytes"],
                        "observed": info.st_size,
                    }
                )
                continue
            if item["sha256"]:
                observed = sha256_file(path)
                if observed != item["sha256"]:
                    findings.append(
                        {
                            "check": "sha256_mismatch",
                            "path": item["path"],
                            "expected": item["sha256"],
                            "observed": observed,
                        }
                    )
                    continue
            verified_file_count += 1
            verified_bytes += info.st_size
    else:
        # Manifest-only mode verifies exact totals under each proposed path.
        for item in expected_assets_from_manifest(manifest, policies):
            prefix = item["path"].rstrip("/")
            matching = {
                name: path
                for name, path in files.items()
                if name == prefix or name.startswith(prefix + "/")
            }
            expected_paths.update(matching)
            observed_bytes = sum(path.stat().st_size for path in matching.values())
            if len(matching) != item["file_count"] or observed_bytes != item["bytes"]:
                findings.append(
                    {
                        "check": "asset_total_mismatch",
                        "path": item["path"],
                        "logical_id": item["logical_id"],
                        "expected_file_count": item["file_count"],
                        "observed_file_count": len(matching),
                        "expected_bytes": item["bytes"],
                        "observed_bytes": observed_bytes,
                        "note": (
                            "Use --plan for per-file SHA-256 verification. "
                            "Manifest-only mode verifies counts and bytes."
                        ),
                    }
                )
            else:
                verified_file_count += len(matching)
                verified_bytes += observed_bytes

    if require_private_modes:
        for name, path in files.items():
            mode = stat.S_IMODE(path.lstat().st_mode)
            if mode & 0o077:
                findings.append(
                    {
                        "check": "permission_too_open",
                        "path": name,
                        "mode": f"{mode:04o}",
                        "required": "no group/other permission bits",
                    }
                )
        checked_dirs = {mirror_root}
        for path in files.values():
            checked_dirs.update(path.parents)
        for directory in sorted(checked_dirs):
            if directory == mirror_root.parent or not directory.exists():
                continue
            try:
                directory.relative_to(mirror_root)
            except ValueError:
                continue
            mode = stat.S_IMODE(directory.lstat().st_mode)
            if mode & 0o077:
                findings.append(
                    {
                        "check": "directory_permission_too_open",
                        "path": (
                            "."
                            if directory == mirror_root
                            else directory.relative_to(mirror_root).as_posix()
                        ),
                        "mode": f"{mode:04o}",
                        "required": "0700 or stricter",
                    }
                )

    extras = sorted(set(files) - expected_paths)
    if extras and not allow_extra:
        for name in extras:
            findings.append({"check": "unexpected_file", "path": name})

    counts = Counter(item["check"] for item in findings)
    return {
        "schema_version": "av-trace.hf-mirror-verification/1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_used": False,
        "tokens_read": False,
        "mirror_root": str(mirror_root),
        "policies": sorted(policies),
        "mode": "per_file_plan" if plan else "manifest_totals",
        "status": "pass" if not findings else "fail",
        "verified_file_count": verified_file_count,
        "verified_bytes": verified_bytes,
        "observed_file_count": len(files),
        "finding_counts": dict(sorted(counts.items())),
        "findings": findings,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("mirror_root", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--plan", type=Path)
    parser.add_argument(
        "--policy",
        action="append",
        choices=sorted(VERIFY_POLICIES),
        help="Verify one or more migrated policies.",
    )
    parser.add_argument("--require-private-modes", action="store_true")
    parser.add_argument("--allow-extra", action="store_true")
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = load_json(args.manifest)
    plan = load_json(args.plan) if args.plan else None
    report = verify(
        args.mirror_root.resolve(),
        manifest=manifest,
        plan=plan,
        policies=set(args.policy) if args.policy else VERIFY_POLICIES,
        require_private_modes=args.require_private_modes,
        allow_extra=args.allow_extra,
    )
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
