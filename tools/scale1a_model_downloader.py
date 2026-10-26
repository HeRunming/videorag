#!/usr/bin/env python3
"""Exact-revision, bounded, resumable downloader for Task 94."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

try:
    from tools.scale1a_model_preflight import (
        CAP_BYTES,
        FINAL_DIR,
        MANIFEST_PATH,
        OVERALL_DECISION,
        PLAN_PATH,
        REDISTRIBUTION_DECISION,
        REVISION,
        TECHNICAL_INFERENCE_DECISION,
        ValidationError,
        atomic_json,
        git_blob_oid,
        lfs_pointer_git_oid,
        load_json,
        offline_smoke,
        sha256_file,
        utc_now,
        validate_metadata,
        validate_plan,
        validate_snapshot,
    )
except ModuleNotFoundError:
    from scale1a_model_preflight import (  # type: ignore[no-redef]
        CAP_BYTES,
        FINAL_DIR,
        MANIFEST_PATH,
        OVERALL_DECISION,
        PLAN_PATH,
        REDISTRIBUTION_DECISION,
        REVISION,
        TECHNICAL_INFERENCE_DECISION,
        ValidationError,
        atomic_json,
        git_blob_oid,
        lfs_pointer_git_oid,
        load_json,
        offline_smoke,
        sha256_file,
        utc_now,
        validate_metadata,
        validate_plan,
        validate_snapshot,
    )

MODEL_API_URL = (
    "https://huggingface.co/api/models/openai/clip-vit-base-patch32/revision/"
    + REVISION
)
TREE_API_URL = (
    "https://huggingface.co/api/models/openai/clip-vit-base-patch32/tree/"
    + REVISION
    + "?recursive=true&expand=false"
)


def safe_proxy_label(value: str | None) -> str:
    if not value:
        return "environment-or-direct"
    parsed = urlsplit(value)
    return f"{parsed.hostname or 'configured-proxy'}:{parsed.port or 80}"


def curl(
    url: str,
    output: Path,
    *,
    proxy: str | None,
    resume: bool = False,
    headers: Path | None = None,
) -> None:
    command = [
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--location",
        "--retry",
        "5",
        "--connect-timeout",
        "30",
        "--max-time",
        "3600",
    ]
    if proxy:
        command += ["--proxy", proxy]
    if resume:
        command += ["--continue-at", "-"]
    if headers is not None:
        command += ["--dump-header", str(headers)]
    command += ["--output", str(output), url]
    clean_env = dict(os.environ)
    for key in list(clean_env):
        if key.upper() in {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"}:
            clean_env.pop(key, None)
    subprocess.run(command, check=True, env=clean_env)


def parse_commit_headers(path: Path) -> set[str]:
    commits: set[str] = set()
    for line in path.read_text(encoding="iso-8859-1").splitlines():
        if line.lower().startswith("x-repo-commit:"):
            value = line.split(":", 1)[1].strip().lower()
            if re.fullmatch(r"[0-9a-f]{40}", value):
                commits.add(value)
    return commits


def parse_identity_headers(path: Path) -> dict[str, set[str]]:
    values = {
        "x_repo_commit": set(),
        "etag": set(),
        "x_linked_etag": set(),
        "x_linked_size": set(),
    }
    for line in path.read_text(encoding="iso-8859-1").splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        normalized_key = key.strip().lower().replace("-", "_")
        if normalized_key in values:
            values[normalized_key].add(value.strip().strip('"'))
    return values


def exact_url(filename: str) -> str:
    return (
        "https://huggingface.co/openai/clip-vit-base-patch32/resolve/"
        f"{REVISION}/{quote(filename, safe='')}"
    )


def write_sha256sums(snapshot: Path, records: list[dict[str, Any]]) -> None:
    text = "".join(f"{item['sha256']}  {item['path']}\n" for item in records)
    path = snapshot / "SHA256SUMS"
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)


def acquire(root: Path, proxy: str | None) -> dict[str, Any]:
    plan = load_json(root / PLAN_PATH)
    allowlist = validate_plan(plan)
    expected_total = sum(item["expected_bytes"] for item in allowlist)
    if expected_total > CAP_BYTES:
        raise ValidationError("CAP_OVERFLOW_BEFORE_NETWORK")
    models_dir = (root / FINAL_DIR).parent
    models_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(models_dir, 0o700)
    final_dir = root / FINAL_DIR
    if final_dir.exists() or final_dir.is_symlink():
        raise ValidationError("FINAL_DIRECTORY_ALREADY_EXISTS")
    stage = models_dir / ".clip-task94-stage"
    if stage.exists() or stage.is_symlink():
        raise ValidationError("STAGING_DIRECTORY_ALREADY_EXISTS")
    stage.mkdir(mode=0o700)
    promoted = False
    try:
        metadata_dir = stage / ".metadata"
        metadata_dir.mkdir(mode=0o700)
        model_api_path = metadata_dir / "model_api.json"
        tree_path = metadata_dir / "tree.json"
        curl(MODEL_API_URL, model_api_path, proxy=proxy)
        curl(TREE_API_URL, tree_path, proxy=proxy)
        model_api = load_json(model_api_path)
        tree = load_json(tree_path)
        readme_item = next(
            (
                item
                for item in allowlist
                if item["path"] == "README.md"
            ),
            None,
        )
        if readme_item is None:
            raise ValidationError("MODEL_CARD_NOT_ALLOWLISTED")
        readme_headers = metadata_dir / "README.md.headers"
        readme_path = metadata_dir / "README.md"
        curl(
            exact_url("README.md"),
            readme_path,
            proxy=proxy,
            headers=readme_headers,
        )
        readme_commits = parse_commit_headers(readme_headers)
        if readme_commits != {REVISION}:
            raise ValidationError("README_RESPONSE_IDENTITY_MISSING_OR_MISMATCH")
        evidence = validate_metadata(
            plan, model_api, tree, readme=readme_path.read_bytes()
        )
        metadata_hashes = {
            "model_api_sha256": sha256_file(model_api_path),
            "tree_sha256": sha256_file(tree_path),
            "readme_sha256": sha256_file(readme_path),
        }
        records: list[dict[str, Any]] = []
        response_identity: list[dict[str, Any]] = []
        for item in allowlist:
            name = item["path"]
            destination = stage / name
            header_path = metadata_dir / f"{name}.headers"
            curl(
                exact_url(name),
                destination,
                proxy=proxy,
                resume=True,
                headers=header_path,
            )
            os.chmod(destination, 0o600)
            if destination.stat().st_size != item["expected_bytes"]:
                raise ValidationError(f"DOWNLOADED_SIZE_MISMATCH:{name}")
            digest = sha256_file(destination)
            git_oid = (
                lfs_pointer_git_oid(item["lfs_sha256"], destination.stat().st_size)
                if item["lfs_sha256"]
                else git_blob_oid(destination)
            )
            if git_oid != item["git_oid"]:
                raise ValidationError(f"DOWNLOADED_GIT_OID_MISMATCH:{name}")
            if item["lfs_sha256"] and digest != item["lfs_sha256"]:
                raise ValidationError(f"DOWNLOADED_LFS_HASH_MISMATCH:{name}")
            commits = parse_commit_headers(header_path)
            if commits != {REVISION}:
                raise ValidationError(
                    f"RESPONSE_REVISION_MISSING_OR_MISMATCH:{name}"
                )
            identity_headers = parse_identity_headers(header_path)
            etags = (
                identity_headers["etag"] | identity_headers["x_linked_etag"]
            )
            if item["git_oid"] not in etags and (
                item["lfs_sha256"] is None
                or item["lfs_sha256"] not in etags
            ):
                raise ValidationError(f"RESPONSE_OBJECT_ID_MISMATCH:{name}")
            linked_sizes = identity_headers["x_linked_size"]
            if linked_sizes and str(item["expected_bytes"]) not in linked_sizes:
                raise ValidationError(f"RESPONSE_LINKED_SIZE_MISMATCH:{name}")
            records.append(
                {
                    "path": name,
                    "bytes": destination.stat().st_size,
                    "sha256": digest,
                    "git_oid": git_oid,
                    "expected_lfs_sha256": item["lfs_sha256"],
                }
            )
            response_identity.append(
                {
                    "path": name,
                    "exact_revision_url": exact_url(name),
                    "x_repo_commit_values": sorted(commits),
                    "object_identity_values": sorted(etags),
                    "x_linked_size_values": sorted(linked_sizes),
                    "size_matched": True,
                }
            )
        shutil.rmtree(metadata_dir)
        write_sha256sums(stage, records)
        validate_snapshot(
            plan,
            stage,
            {item["path"]: item["sha256"] for item in records},
        )
        smoke = offline_smoke(stage)
        # Technical readiness and redistribution are deliberately independent.
        # Exact-revision integrity plus offline smoke authorizes only restricted
        # internal inference. Acquisition never grants redistribution.
        manifest = {
            "schema_version": "1.1",
            "task_id": 94,
            "created_at": utc_now(),
            "repo_id": plan["repo_id"],
            "revision": REVISION,
            "cap_bytes": CAP_BYTES,
            "payload_bytes": expected_total,
            "cap_passed": expected_total <= CAP_BYTES,
            "allowlist_minimal": True,
            "duplicate_weight_files": [],
            "source_metadata": {
                "model_api_url": MODEL_API_URL,
                "tree_api_url": TREE_API_URL,
                **metadata_hashes,
                "model_card_present": evidence["model_card_present"],
                "model_card_git_oid": evidence["model_card_git_oid"],
                "declared_license": evidence["declared_license"],
                "license_status": evidence["license_status"],
                "license_evidence": evidence["license_evidence"],
            },
            "network": {
                "transport": "curl_exact_revision_urls",
                "proxy": safe_proxy_label(proxy),
                "credentials_persisted": False,
            },
            "response_identity": response_identity,
            "files": records,
            "offline_smoke": smoke,
            "acquisition": {
                "completed": True,
                "final_snapshot_present": True,
                "resumable_download": True,
                "atomic_promotion": True,
                "restricted_staging_mode": "0700",
                "file_mode": "0600",
                "temporary_metadata_removed": True,
            },
            "verification": {
                "official_exact_revision_metadata": True,
                "response_identity_verified": True,
                "git_object_identity_verified": True,
                "expected_sizes_verified": True,
                "complete_file_set_verified": True,
                "local_sha256_verified": True,
                "sha256sums_written_and_verified": True,
                "symlinks_absent": True,
                "offline_local_files_only_load": True,
                "synthetic_image_embedding": True,
                "text_embedding": True,
                "normalized_similarity": True,
                "deterministic_replay": True,
            },
            "restrictions": {
                "restricted": True,
                "redistribution_authorized": False,
                "license_release_gate_passed": evidence["license_status"] == "DECLARED",
            },
            "technical_inference_decision": TECHNICAL_INFERENCE_DECISION,
            "redistribution_decision": REDISTRIBUTION_DECISION,
            "decision": OVERALL_DECISION,
        }
        os.replace(stage, final_dir)
        promoted = True
        validate_snapshot(
            plan, final_dir, {item["path"]: item["sha256"] for item in records}
        )
        atomic_json(root / MANIFEST_PATH, manifest)
        return manifest
    finally:
        if not promoted:
            shutil.rmtree(stage, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--proxy")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    plan = load_json(root / PLAN_PATH)
    validate_plan(plan)
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "PREFLIGHT_ONLY",
                    "repo_id": plan["repo_id"],
                    "revision": plan["revision"],
                    "payload_bytes": plan["expected_payload_bytes"],
                    "cap_bytes": plan["cap_bytes"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    manifest = acquire(root, args.proxy)
    print(manifest["technical_inference_decision"])
    print(manifest["redistribution_decision"])
    print(manifest["decision"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidationError, subprocess.CalledProcessError) as error:
        print(f"NO_GO:{error}", file=sys.stderr)
        raise SystemExit(2)
