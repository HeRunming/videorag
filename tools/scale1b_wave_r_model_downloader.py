#!/usr/bin/env python3
"""Exact-revision, bounded and resumable acquisition for Task 102."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.scale1b_wave_r_model_preflight import (
    MANIFEST, ROOT_PLAN, ValidationError, atomic_json, load_json, model_map,
    offline_smoke, sha256_file, validate_metadata, validate_plan, validate_snapshot,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def curl(
    url: str,
    output: Path,
    *,
    proxy: str | None,
    headers: Path | None = None,
    resume: bool = False,
    max_time: int = 1800,
) -> None:
    command = ["curl", "--fail", "--location", "--retry", "3", "--retry-delay", "2",
               "--connect-timeout", "20", "--max-time", str(max_time)]
    if proxy:
        command += ["--proxy", proxy]
    if headers:
        command += ["--dump-header", str(headers)]
    if resume and output.exists():
        command += ["--continue-at", "-"]
    command += ["--output", str(output), url]
    subprocess.run(command, check=True)


def exact_url(model: dict, name: str, endpoint: str) -> str:
    repo = "/".join(quote(part, safe="") for part in model["repo_id"].split("/"))
    return f"{endpoint.rstrip('/')}/{repo}/resolve/{model['revision']}/{quote(name, safe='')}"


def api_urls(model: dict) -> tuple[str, str]:
    repo = model["repo_id"]
    rev = model["revision"]
    return (f"https://huggingface.co/api/models/{repo}/revision/{rev}",
            f"https://huggingface.co/api/models/{repo}/tree/{rev}?recursive=true&expand=true")


def commits_from_headers(path: Path) -> set[str]:
    found = set()
    for line in path.read_text("iso-8859-1").splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip().lower() == "x-repo-commit" and re.fullmatch(r"[0-9a-f]{40}", value.strip()):
            found.add(value.strip())
    return found


def identity_from_headers(path: Path) -> set[str]:
    found = set()
    for line in path.read_text("iso-8859-1").splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip().lower() in {"etag", "x-linked-etag"}:
            found.add(value.strip().strip('"'))
    return found


def write_sums(stage: Path, rows: list[dict]) -> None:
    path = stage / "SHA256SUMS"
    path.write_text("".join(f"{r['sha256']}  {r['path']}\n" for r in rows), encoding="utf-8")
    os.chmod(path, 0o600)


def current_decisions(result: dict) -> None:
    siglip_ready = "siglip2" in result["models"]
    clap_ready = "clap" in result["models"]
    result["siglip2_decision"] = (
        "SIGLIP2_SNAPSHOT_READY" if siglip_ready else "SIGLIP2_CONDITIONAL"
    )
    result["clap_decision"] = (
        "CLAP_SNAPSHOT_READY" if clap_ready else "CLAP_CONDITIONAL"
    )
    result["wave_r_decision"] = (
        "WAVE_R_MODELS_READY"
        if siglip_ready and clap_ready
        else "WAVE_R_MODELS_CONDITIONAL"
    )
    result["technical_internal_use_authorized"] = siglip_ready and clap_ready
    result["redistribution_authorized"] = False
    result["status"] = (
        "ACQUISITION_COMPLETE"
        if siglip_ready and clap_ready
        else "PARTIAL_ACQUISITION"
    )


def staged_file_complete(path: Path, item: dict) -> bool:
    """Allow safe resume without issuing a range request for complete files."""
    if not path.is_file() or path.is_symlink():
        return False
    if path.stat().st_size != item["expected_bytes"]:
        return False
    if item["lfs_sha256"]:
        return sha256_file(path) == item["lfs_sha256"]
    from tools.scale1b_wave_r_model_preflight import git_blob_oid
    return git_blob_oid(path) == item["git_oid"]


def acquire(
    root: Path,
    proxy: str | None,
    endpoint: str,
    *,
    selected_models: set[str] | None = None,
    max_time: int = 1800,
) -> dict:
    plan = load_json(root / ROOT_PLAN)
    validate_plan(plan)
    restricted = root / "data/restricted/scale1b"
    models_root = restricted / "models"
    records_root = restricted / "acquisition_records/wave_r"
    manifests_root = restricted / "manifests"
    for path in (restricted, models_root, records_root, manifests_root):
        path.mkdir(parents=True, exist_ok=True); os.chmod(path, 0o700)
    existing = {}
    manifest_path = root / MANIFEST
    if manifest_path.is_file():
        candidate = load_json(manifest_path)
        if isinstance(candidate.get("models"), dict):
            existing = candidate["models"]
    result = {
        "schema_version": "1.1",
        "task": 102,
        "created_at": utc_now(),
        "credentials_persisted": False,
        "models": existing,
        "total_payload_bytes": sum(
            m["expected_payload_bytes"] for m in model_map(plan).values()
        ),
    }
    for model_id, model in model_map(plan).items():
        if selected_models is not None and model_id not in selected_models:
            continue
        final = root / model["snapshot_dir"]
        stage = models_root / f".task102-{model_id}.stage"
        if final.exists() and stage.exists():
            raise ValidationError(f"FINAL_AND_STAGE_BOTH_EXIST:{model_id}")
        if stage.is_symlink() or (stage.exists() and not stage.is_dir()):
            raise ValidationError(f"INVALID_STAGING_PATH:{model_id}")
        record_dir = records_root / model_id
        record_dir.mkdir(parents=True, exist_ok=True); os.chmod(record_dir, 0o700)
        api_url, tree_url = api_urls(model)
        api_path, tree_path = record_dir / "model_api.json", record_dir / "tree.json"
        readme_path = record_dir / "README.md"
        readme_headers = record_dir / "README.headers"
        # Reuse only an already validated exact metadata archive. Otherwise
        # fetch it with bounded curl before touching weights.
        metadata_reused = False
        if all(path.is_file() for path in (api_path, tree_path, readme_path, readme_headers)):
            if commits_from_headers(readme_headers) == {model["revision"]}:
                license_evidence = validate_metadata(
                    model, load_json(api_path), load_json(tree_path),
                    readme_path.read_bytes()
                )
                metadata_reused = True
        if not metadata_reused:
            curl(api_url, api_path, proxy=proxy, max_time=max_time)
            curl(tree_url, tree_path, proxy=proxy, max_time=max_time)
            curl(
                exact_url(model, "README.md", endpoint),
                readme_path,
                proxy=proxy,
                headers=readme_headers,
                max_time=max_time,
            )
            if commits_from_headers(readme_headers) != {model["revision"]}:
                raise ValidationError(f"README_REVISION_IDENTITY:{model_id}")
            license_evidence = validate_metadata(model, load_json(api_path), load_json(tree_path), readme_path.read_bytes())
        rows, identities = [], []
        source = final if final.exists() else stage
        if final.exists():
            snapshot_rows = validate_snapshot(model, final)
            rows = [
                {
                    "path": row["path"],
                    "bytes": row["bytes"],
                    "sha256": row["sha256"],
                    "git_oid": row["git_oid"],
                }
                for row in snapshot_rows
            ]
            for item in model["allowlist"]:
                headers = record_dir / f"{item['path']}.headers"
                if not headers.is_file() or commits_from_headers(headers) != {model["revision"]}:
                    raise ValidationError(f"MISSING_FINAL_RESPONSE_IDENTITY:{model_id}:{item['path']}")
                object_ids = identity_from_headers(headers)
                if item["git_oid"] not in object_ids and (
                    not item["lfs_sha256"] or item["lfs_sha256"] not in object_ids
                ):
                    raise ValidationError(f"FINAL_RESPONSE_OBJECT_ID:{model_id}:{item['path']}")
                identities.append({
                    "path": item["path"],
                    "x_repo_commit": model["revision"],
                    "object_identity_values": sorted(object_ids),
                    "reused_complete_stage_file": True,
                })
            smoke = offline_smoke(model_id, final)
        else:
            stage.mkdir(mode=0o700, exist_ok=True)
            os.chmod(stage, 0o700)
            allowed_stage_names = {
                item["path"] for item in model["allowlist"]
            } | {"SHA256SUMS"}
            unexpected = {
                entry.name for entry in stage.iterdir()
            } - allowed_stage_names
            if unexpected:
                raise ValidationError(
                    f"UNEXPECTED_STAGING_FILES:{model_id}:{sorted(unexpected)}"
                )
            for item in model["allowlist"]:
                destination = stage / item["path"]
                headers = record_dir / f"{item['path']}.headers"
                reused_complete_stage_file = staged_file_complete(destination, item)
                if not reused_complete_stage_file:
                    # A prior interrupted resume can leave an overlong file if
                    # the remote endpoint honored a stale local offset. A
                    # full-sized hash mismatch is likewise not resumable.
                    if destination.exists() and (
                        destination.stat().st_size >= item["expected_bytes"]
                    ):
                        destination.unlink()
                    curl(
                        exact_url(model, item["path"], endpoint),
                        destination,
                        proxy=proxy,
                        headers=headers,
                        resume=True,
                        max_time=max_time,
                    )
                os.chmod(destination, 0o600)
                if not headers.is_file() or commits_from_headers(headers) != {model["revision"]}:
                    raise ValidationError(f"RESPONSE_REVISION:{model_id}:{item['path']}")
                object_ids = identity_from_headers(headers)
                if item["git_oid"] not in object_ids and (not item["lfs_sha256"] or item["lfs_sha256"] not in object_ids):
                    raise ValidationError(f"RESPONSE_OBJECT_ID:{model_id}:{item['path']}")
                rows.append({"path": item["path"], "bytes": destination.stat().st_size,
                             "sha256": sha256_file(destination), "git_oid": item["git_oid"]})
                identities.append({"path": item["path"], "x_repo_commit": model["revision"],
                                   "object_identity_values": sorted(object_ids),
                                   "reused_complete_stage_file": reused_complete_stage_file})
            write_sums(stage, rows)
            validate_snapshot(model, stage, {r["path"]: r["sha256"] for r in rows})
            smoke = offline_smoke(model_id, stage)
            final.parent.mkdir(parents=True, exist_ok=True); os.chmod(final.parent, 0o700)
            os.replace(stage, final)
            validate_snapshot(
                model, final, {row["path"]: row["sha256"] for row in rows}
            )
        result["models"][model_id] = {
            "repo_id": model["repo_id"],
            "revision": model["revision"],
            "snapshot_dir": model["snapshot_dir"],
            "files": rows,
            "response_identity": identities,
            "license": license_evidence,
            "metadata_archive": str(record_dir.relative_to(root)),
            "metadata_reused_after_exact_validation": metadata_reused,
            "offline_smoke": smoke,
            "technical_inference_decision": (
                "SIGLIP2_SNAPSHOT_READY"
                if model_id == "siglip2"
                else "CLAP_SNAPSHOT_READY"
            ),
            "redistribution_decision": "NOT_AUTHORIZED_PENDING_RELEASE_REVIEW",
        }
        for path in record_dir.iterdir():
            os.chmod(path, 0o600)
        current_decisions(result)
        atomic_json(root / MANIFEST, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--proxy")
    parser.add_argument("--endpoint", default="https://huggingface.co")
    parser.add_argument(
        "--model",
        action="append",
        choices=("siglip2", "clap"),
        help="Process only the selected model; may be repeated.",
    )
    parser.add_argument("--max-time", type=int, default=1800)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    plan = load_json(root / ROOT_PLAN); validate_plan(plan)
    if not args.execute:
        print(json.dumps({"status": "PREFLIGHT_ONLY", "total_bytes": plan["expected_total_bytes"]}, indent=2))
        return 0
    result = acquire(
        root,
        args.proxy,
        args.endpoint,
        selected_models=set(args.model) if args.model else None,
        max_time=args.max_time,
    )
    print(result["siglip2_decision"]); print(result["clap_decision"]); print(result["wave_r_decision"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidationError, subprocess.CalledProcessError) as exc:
        print(f"NO_GO:{exc}", file=sys.stderr)
        raise SystemExit(2)
