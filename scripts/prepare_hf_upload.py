#!/usr/bin/env python3
"""Produce a fail-closed Hugging Face migration dry-run plan.

This script never uploads, copies, chmods, deletes, authenticates, or reads a
Hugging Face token. It inspects only manifest-declared paths under the supplied
repository root and emits reviewable commands for a later, separately approved
operator action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import stat
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable


DEFAULT_MANIFEST = Path("data/migration/hf_asset_manifest.json")
DEFAULT_HASH_LIMIT = 64 * 1024 * 1024
DEFAULT_LARGE_FILE = 50 * 1024 * 1024
DEFAULT_RECOMMENDED_PART = 5 * 1024 * 1024 * 1024

STAGEABLE_POLICIES = {"public_metadata_only", "private_derived_index"}
NEVER_STAGE_POLICIES = {
    "never_upload",
    "delete_after_verified_migration",
    "redownload_upstream",
    "rebuild_from_code",
}
REQUIRED_FIELDS = {
    "logical_id",
    "local_path",
    "bytes",
    "sha256_or_manifest_hash",
    "license_source",
    "sensitivity",
    "target_repo_type",
    "proposed_hf_path",
    "upload_policy",
    "reconstruction_command",
    "dependencies",
}
REPOSITORY_ALIASES = {
    "dataset_public_metadata": "public_metadata_dataset",
    "dataset_private_restricted_media": "private_restricted_media_dataset",
    "dataset_private_derived": "private_derived_index_dataset",
}


def load_manifest(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or not isinstance(value.get("assets"), list):
        raise ValueError("manifest must be an object with an assets array")
    logical_ids: set[str] = set()
    for index, asset in enumerate(value["assets"]):
        if not isinstance(asset, dict):
            raise ValueError(f"asset {index} is not an object")
        missing = REQUIRED_FIELDS - asset.keys()
        if missing:
            raise ValueError(
                f"asset {index} is missing required fields: {sorted(missing)}"
            )
        logical_id = asset["logical_id"]
        if not isinstance(logical_id, str) or not logical_id:
            raise ValueError(f"asset {index} has invalid logical_id")
        if logical_id in logical_ids:
            raise ValueError(f"duplicate logical_id: {logical_id}")
        logical_ids.add(logical_id)
        if asset["upload_policy"] not in STAGEABLE_POLICIES | NEVER_STAGE_POLICIES:
            raise ValueError(
                f"{logical_id}: unknown upload_policy {asset['upload_policy']!r}"
            )
    for asset in value["assets"]:
        unknown = set(asset["dependencies"]) - logical_ids
        # File-path evidence dependencies are allowed; logical-ID dependencies
        # are validated when they do not look like repository paths.
        unknown = {item for item in unknown if "/" not in item}
        if unknown:
            raise ValueError(
                f"{asset['logical_id']}: unknown dependencies {sorted(unknown)}"
            )
    return value


def _is_concrete_local_path(value: str) -> bool:
    return not any(char in value for char in "*{}<>") and " and " not in value


def _is_below(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _path_has_symlink_component(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        try:
            if cursor.is_symlink():
                return True
        except OSError:
            return True
    return False


def inspect_path(root: Path, local_path: str) -> dict:
    """Inspect a concrete manifest path without following symlinks."""

    if not _is_concrete_local_path(local_path):
        return {
            "status": "logical_path_only",
            "local_path": local_path,
            "file_count": None,
            "bytes": None,
            "files": [],
            "blockers": ["path is a logical grouping, not a concrete stage source"],
        }
    pure = PurePosixPath(local_path)
    if pure.is_absolute() or ".." in pure.parts:
        return {
            "status": "blocked",
            "local_path": local_path,
            "file_count": None,
            "bytes": None,
            "files": [],
            "blockers": ["absolute paths and '..' components are prohibited"],
        }
    candidate = root.joinpath(*pure.parts)
    if not _is_below(candidate.absolute(), root):
        return {
            "status": "blocked",
            "local_path": local_path,
            "file_count": None,
            "bytes": None,
            "files": [],
            "blockers": ["path escapes repository root"],
        }
    if not candidate.exists() and not candidate.is_symlink():
        return {
            "status": "missing",
            "local_path": local_path,
            "file_count": 0,
            "bytes": 0,
            "files": [],
            "blockers": ["path does not exist"],
        }
    if _path_has_symlink_component(candidate, root):
        return {
            "status": "blocked",
            "local_path": local_path,
            "file_count": None,
            "bytes": None,
            "files": [],
            "blockers": ["path contains a symlink component"],
        }

    blockers: list[str] = []
    files: list[dict] = []
    if candidate.is_file():
        candidates: Iterable[Path] = (candidate,)
    elif candidate.is_dir():
        found: list[Path] = []
        for directory, dirnames, filenames in os.walk(candidate, followlinks=False):
            directory_path = Path(directory)
            safe_dirs: list[str] = []
            for name in sorted(dirnames):
                child = directory_path / name
                if child.is_symlink():
                    blockers.append(
                        f"symlink directory rejected: {child.relative_to(root)}"
                    )
                else:
                    safe_dirs.append(name)
            dirnames[:] = safe_dirs
            for name in sorted(filenames):
                child = directory_path / name
                if child.is_symlink():
                    blockers.append(
                        f"symlink file rejected: {child.relative_to(root)}"
                    )
                    continue
                found.append(child)
        candidates = found
    else:
        return {
            "status": "blocked",
            "local_path": local_path,
            "file_count": None,
            "bytes": None,
            "files": [],
            "blockers": ["path is not a regular file or directory"],
        }

    for path in candidates:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            blockers.append(f"non-regular file rejected: {path.relative_to(root)}")
            continue
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": info.st_size,
                "mode": f"{stat.S_IMODE(info.st_mode):04o}",
            }
        )
    return {
        "status": "blocked" if blockers else "ok",
        "local_path": local_path,
        "file_count": len(files),
        "bytes": sum(item["bytes"] for item in files),
        "files": files,
        "blockers": blockers,
    }


def asset_members(asset: dict) -> list[str]:
    members = asset.get("local_members")
    if members is None:
        return [asset["local_path"]]
    if not isinstance(members, list) or not all(
        isinstance(item, str) and item for item in members
    ):
        raise ValueError(f"{asset['logical_id']}: local_members must be strings")
    return members


def inspect_asset(root: Path, asset: dict) -> dict:
    inspections = [inspect_path(root, member) for member in asset_members(asset)]
    blockers = [
        f"{inspection['local_path']}: {message}"
        for inspection in inspections
        for message in inspection["blockers"]
    ]
    if any(item["status"] == "blocked" for item in inspections):
        status = "blocked"
    elif any(item["status"] == "missing" for item in inspections):
        status = "missing"
    elif any(item["status"] == "logical_path_only" for item in inspections):
        status = "logical_path_only"
    else:
        status = "ok"
    return {
        "status": status,
        "local_path": asset["local_path"],
        "members": inspections,
        "file_count": (
            sum(item["file_count"] for item in inspections)
            if all(item["file_count"] is not None for item in inspections)
            else None
        ),
        "bytes": (
            sum(item["bytes"] for item in inspections)
            if all(item["bytes"] is not None for item in inspections)
            else None
        ),
        "files": [
            {**file, "member_root": inspection["local_path"]}
            for inspection in inspections
            for file in inspection["files"]
        ],
        "blockers": blockers,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def commands_for_asset(asset: dict, repositories: dict, root: Path) -> list[str]:
    repository_key = REPOSITORY_ALIASES.get(
        asset["target_repo_type"], asset["target_repo_type"]
    )
    repo = repositories.get(repository_key) or repositories.get(
        asset["target_repo_type"]
    )
    if not repo or not asset.get("proposed_hf_path"):
        return []
    repo_id = repo.get("repo_id", repo["repo_id_placeholder"])
    repo_type = repo["repo_type"]
    members = asset_members(asset)
    basename_counts = Counter(PurePosixPath(member).name for member in members)
    commands = []
    for member in members:
        local_path = root / member
        destination = PurePosixPath(asset["proposed_hf_path"])
        if len(members) > 1:
            member_path = PurePosixPath(member)
            label = PurePosixPath(member_path.name)
            if basename_counts[member_path.name] > 1:
                label = PurePosixPath(member_path.parent.name) / member_path.name
            destination /= label
        if local_path.is_file():
            commands.append(
                "hf upload "
                f"--repo-type {shlex.quote(repo_type)} "
                f"{shlex.quote(repo_id)} "
                f"{shlex.quote(str(local_path))} "
                f"{shlex.quote(destination.as_posix())}"
            )
        else:
            commands.append(
                "hf upload "
                f"--repo-type {shlex.quote(repo_type)} "
                f"{shlex.quote(repo_id)} "
                f"{shlex.quote(str(local_path))} "
                f"{shlex.quote(destination.as_posix())}"
            )
    return commands


def build_plan(
    manifest: dict,
    *,
    manifest_path: Path,
    root: Path,
    policies: set[str] | None = None,
    hash_limit: int = DEFAULT_HASH_LIMIT,
    large_file_bytes: int = DEFAULT_LARGE_FILE,
    recommended_part_bytes: int = DEFAULT_RECOMMENDED_PART,
) -> dict:
    selected = []
    totals = defaultdict(lambda: {"asset_count": 0, "bytes": 0, "file_count": 0})
    for asset in manifest["assets"]:
        if policies and asset["upload_policy"] not in policies:
            continue
        inspection = inspect_asset(root, asset)
        blockers = list(inspection["blockers"])
        stageable = asset["upload_policy"] in STAGEABLE_POLICIES
        if not stageable:
            blockers.append(f"policy {asset['upload_policy']} is not stageable")
        if (
            asset["upload_policy"] == "public_metadata_only"
            and asset.get("release_review_status") != "approved"
        ):
            blockers.append(
                "public metadata requires release_review_status=approved"
            )
        if (
            asset["upload_policy"] == "private_derived_index"
            and asset.get("staging_review_status") == "pending"
        ):
            blockers.append(
                "private derived asset requires a narrower owner-approved allowlist"
            )
        if stageable and inspection["status"] != "ok":
            blockers.append("stageable asset requires a concrete, safe local path")
        if (
            stageable
            and inspection["bytes"] is not None
            and inspection["bytes"] != asset["bytes"]
        ):
            blockers.append(
                f"manifest bytes {asset['bytes']} != observed bytes "
                f"{inspection['bytes']}"
            )

        file_checks = []
        large_files = []
        if inspection["status"] == "ok" and stageable and not blockers:
            members = asset_members(asset)
            basename_counts = Counter(
                PurePosixPath(member).name for member in members
            )
            for item in inspection["files"]:
                file_path = root / item["path"]
                destination = None
                if asset.get("proposed_hf_path"):
                    member_root = PurePosixPath(item["member_root"])
                    local_file = PurePosixPath(item["path"])
                    member_is_file = (root / item["member_root"]).is_file()
                    suffix = (
                        PurePosixPath(local_file.name)
                        if member_is_file
                        else local_file.relative_to(member_root)
                    )
                    destination = PurePosixPath(asset["proposed_hf_path"])
                    if len(members) > 1:
                        label = PurePosixPath(member_root.name)
                        if basename_counts[member_root.name] > 1:
                            label = (
                                PurePosixPath(member_root.parent.name)
                                / member_root.name
                            )
                        destination /= label
                        if not member_is_file:
                            destination /= suffix
                    elif not member_is_file:
                        destination /= suffix
                if item["bytes"] <= hash_limit:
                    checksum = "sha256:" + sha256_file(file_path)
                    checksum_status = "computed"
                else:
                    checksum = None
                    checksum_status = (
                        "deferred_to_manifest_or_existing_verified_hash"
                    )
                file_checks.append(
                    {
                        **item,
                        "hf_path": destination.as_posix() if destination else None,
                        "checksum": checksum,
                        "checksum_status": checksum_status,
                    }
                )
                if item["bytes"] >= large_file_bytes:
                    large_files.append(
                        {
                            "path": item["path"],
                            "bytes": item["bytes"],
                            "recommended_part_bytes": recommended_part_bytes,
                            "suggested_part_count": max(
                                1,
                                (item["bytes"] + recommended_part_bytes - 1)
                                // recommended_part_bytes,
                            ),
                            "note": (
                                "Prefer native HF Xet/LFS upload and resumable "
                                "large-folder state; do not manually split unless "
                                "the receiving format requires archives."
                            ),
                        }
                    )

        commands = (
            commands_for_asset(asset, manifest["repositories"], root)
            if stageable and not blockers
            else []
        )
        selected.append(
            {
                "logical_id": asset["logical_id"],
                "upload_policy": asset["upload_policy"],
                "target_repo_type": asset["target_repo_type"],
                "proposed_hf_path": asset["proposed_hf_path"],
                "declared_bytes": asset["bytes"],
                "declared_file_count": asset["file_count"],
                "declared_identity": asset["sha256_or_manifest_hash"],
                "inspection": {
                    key: inspection[key]
                    for key in ("status", "local_path", "file_count", "bytes")
                },
                "file_checks": file_checks,
                "large_files": large_files,
                "stageable": stageable and not blockers,
                "blockers": blockers,
                "proposed_commands": commands,
                "reconstruction_command": asset["reconstruction_command"],
            }
        )
        bucket = totals[asset["upload_policy"]]
        bucket["asset_count"] += 1
        bucket["bytes"] += asset["bytes"]
        bucket["file_count"] += asset["file_count"]

    commands = [
        {
            "logical_id": item["logical_id"],
            "command": command,
        }
        for item in selected
        for command in item["proposed_commands"]
    ]
    return {
        "schema_version": "av-trace.hf-upload-dry-run/1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dry_run": True,
        "safety": {
            "uploads_performed": False,
            "files_copied": False,
            "permissions_changed": False,
            "tokens_read": False,
            "symlinks_followed": False,
            "network_used": False,
        },
        "manifest": str(manifest_path),
        "repository_root": str(root),
        "selected_policies": sorted(policies) if policies else "all",
        "summary_by_policy": dict(sorted(totals.items())),
        "stageable_asset_count": sum(item["stageable"] for item in selected),
        "blocked_or_nonstageable_asset_count": sum(
            not item["stageable"] for item in selected
        ),
        "assets": selected,
        "commands": commands,
        "operator_note": (
            "Commands are inert text. Review repository visibility, rights, "
            "path mapping, ignore rules, and a generated verify plan before "
            "executing any command in a separate approved session. Replace "
            "every ORG/... placeholder; commands retaining placeholders are "
            "intentionally non-executable migration templates."
        ),
    }


def print_text(plan: dict) -> None:
    print("HF migration dry-run; no upload/copy/chmod/token/network action performed")
    print(f"stageable assets: {plan['stageable_asset_count']}")
    print(
        "blocked or non-stageable assets: "
        f"{plan['blocked_or_nonstageable_asset_count']}"
    )
    for policy, values in plan["summary_by_policy"].items():
        print(
            f"{policy}: {values['asset_count']} assets, "
            f"{values['file_count']} files, {values['bytes']} bytes"
        )
    if plan["commands"]:
        print("\nProposed commands (DO NOT RUN WITHOUT SEPARATE APPROVAL):")
        for item in plan["commands"]:
            print(f"# {item['logical_id']}")
            print(item["command"])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--policy",
        action="append",
        choices=sorted(STAGEABLE_POLICIES | NEVER_STAGE_POLICIES),
        help="Limit output to one or more policies.",
    )
    parser.add_argument("--hash-limit-bytes", type=int, default=DEFAULT_HASH_LIMIT)
    parser.add_argument("--large-file-bytes", type=int, default=DEFAULT_LARGE_FILE)
    parser.add_argument(
        "--recommended-part-bytes", type=int, default=DEFAULT_RECOMMENDED_PART
    )
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.repo_root.resolve()
    manifest_path = (
        args.manifest
        if args.manifest.is_absolute()
        else (root / args.manifest).resolve()
    )
    if not _is_below(manifest_path, root):
        raise SystemExit("manifest must be inside repository root")
    manifest = load_manifest(manifest_path)
    plan = build_plan(
        manifest,
        manifest_path=manifest_path,
        root=root,
        policies=set(args.policy) if args.policy else None,
        hash_limit=args.hash_limit_bytes,
        large_file_bytes=args.large_file_bytes,
        recommended_part_bytes=args.recommended_part_bytes,
    )
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(plan, indent=2) + "\n")
    if args.format == "json":
        print(json.dumps(plan, indent=2))
    else:
        print_text(plan)
    return 0


if __name__ == "__main__":
    sys.exit(main())
