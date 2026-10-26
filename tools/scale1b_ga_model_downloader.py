#!/usr/bin/env python3
"""Exact-revision bounded Qwen acquisition for Scale-1B Wave G/A."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.scale1b_ga_model_preflight import (
    MANIFEST,
    ROOT_PLAN,
    ValidationError,
    atomic_json,
    git_blob_oid,
    load_json,
    offline_smoke,
    sha256_file,
    validate_metadata,
    validate_plan,
    validate_snapshot,
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def curl(
    url: str,
    output: Path,
    *,
    proxy: str | None,
    headers: Path | None = None,
    resume: bool = False,
    max_time: int = 7200,
) -> None:
    command = [
        "curl",
        "--fail",
        "--location",
        "--silent",
        "--show-error",
        "--retry",
        "3",
        "--retry-delay",
        "2",
        "--connect-timeout",
        "20",
        "--max-time",
        str(max_time),
    ]
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
    return (
        f"{endpoint.rstrip('/')}/{repo}/resolve/{model['revision']}/"
        f"{quote(name, safe='')}"
    )


def api_urls(model: dict) -> tuple[str, str]:
    repo, revision = model["repo_id"], model["revision"]
    return (
        f"https://huggingface.co/api/models/{repo}/revision/{revision}",
        f"https://huggingface.co/api/models/{repo}/tree/{revision}"
        "?recursive=true&expand=true",
    )


def header_values(path: Path, names: set[str]) -> set[str]:
    values: set[str] = set()
    for line in path.read_text("iso-8859-1").splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip().lower() in names:
            values.add(value.strip().strip('"'))
    return values


def commits_from_headers(path: Path) -> set[str]:
    return {
        value
        for value in header_values(path, {"x-repo-commit"})
        if re.fullmatch(r"[0-9a-f]{40}", value)
    }


def identity_from_headers(path: Path) -> set[str]:
    return header_values(path, {"etag", "x-linked-etag"})


def staged_file_complete(path: Path, item: dict) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    if path.stat().st_size != item["expected_bytes"]:
        return False
    if item["lfs_sha256"]:
        return sha256_file(path) == item["lfs_sha256"]
    return git_blob_oid(path) == item["git_oid"]


def write_sums(stage: Path, rows: list[dict]) -> None:
    path = stage / "SHA256SUMS"
    path.write_text(
        "".join(f"{row['sha256']}  {row['path']}\n" for row in rows),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def write_report(root: Path, manifest: dict) -> None:
    report = root / "docs/review/scale1b_ga_model_acquisition.md"
    ready = manifest.get("decision") == "QWEN_GROUNDED_GENERATOR_SNAPSHOT_READY"
    smoke = manifest.get("offline_smoke") or {}
    cases = smoke.get("cases") or {}
    lines = [
        "# Scale-1B Wave G/A Qwen acquisition",
        "",
        f"**Decision:** `{manifest.get('decision')}`",
        "",
        "## Exact identity",
        "",
        "- Repository: `Qwen/Qwen2.5-1.5B-Instruct`",
        "- Revision: `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`",
        f"- Payload bytes: `{manifest.get('total_payload_bytes')}`",
        "- Selected weights: one unsharded `model.safetensors` representation",
        "- Exact-revision tree contains no shard index; the complete shard set is the single selected file.",
        f"- Snapshot promoted: `{str(ready).lower()}`",
        "",
        "## Offline CPU smoke",
        "",
        f"- `local_files_only=True`: `{smoke.get('local_files_only')}`",
        f"- Network attempts observed: `{smoke.get('network_attempt_count')}`",
        f"- Model/tokenizer: `{smoke.get('model_class')}` / `{smoke.get('tokenizer_class')}`",
        f"- dtype/device: `{smoke.get('dtype')}` / `{smoke.get('device')}`",
        f"- Context length: `{smoke.get('context_length')}`",
        f"- Load latency: `{smoke.get('load_latency_seconds')}` seconds",
        f"- Peak RSS: `{smoke.get('peak_rss_kib')}` KiB",
        "- Deterministic decoding: `do_sample=False`, `max_new_tokens=128`",
        "- At most one schema-repair generation is allowed per case.",
        "",
        "| Case | Attempts | Repair used | Input tokens | Output tokens | Latency (s) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for case_id in ("normal", "insufficient"):
        case = cases.get(case_id, {})
        lines.append(
            f"| {case_id} | {case.get('attempts')} | "
            f"{case.get('repair_used')} | {case.get('input_tokens_total')} | "
            f"{case.get('output_tokens_total')} | "
            f"{case.get('generation_latency_seconds')} |"
        )
    lines += [
        "",
        "The prompts and outputs use only synthetic objects and contain no project "
        "transcript, source-media content, or restricted benchmark annotations.",
        "",
        "## Release boundary",
        "",
        "- Restricted internal inference is authorized only when the technical gate is ready.",
        "- Model redistribution is **not authorized** pending a separate release review.",
        "- Snapshot readiness does not imply learned-generation or learned-agent benchmark readiness.",
        "",
        "## Compatibility note",
        "",
        "The installed Transformers import path reaches SciPy modules that still "
        "reference removed NumPy scalar aliases. The offline loader applies the "
        "same local `np.long`/`np.ulong` compatibility shim already used by the "
        "project's audited Whisper/AST loaders; no dependency or model file was modified.",
        "",
    ]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8")


def acquire(
    root: Path, proxy: str | None, endpoint: str, max_time: int = 7200
) -> dict:
    plan = load_json(root / ROOT_PLAN)
    validate_plan(plan)
    model = plan["model"]
    restricted = root / "data/restricted/scale1b"
    models_root = restricted / "models"
    records = restricted / "acquisition_records/ga/qwen"
    manifests = restricted / "manifests"
    for path in (restricted, models_root, records, manifests):
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    final = root / model["snapshot_dir"]
    stage = models_root / ".task109-qwen.stage"
    if final.exists() and stage.exists():
        raise ValidationError("FINAL_AND_STAGE_BOTH_EXIST")
    if stage.is_symlink() or (stage.exists() and not stage.is_dir()):
        raise ValidationError("INVALID_STAGING_PATH")

    manifest = {
        "schema_version": "1.0",
        "task": 109,
        "created_at": utc_now(),
        "status": "ACQUISITION_IN_PROGRESS",
        "decision": "QWEN_GROUNDED_GENERATOR_CONDITIONAL",
        "technical_internal_use_authorized": False,
        "redistribution_authorized": False,
        "redistribution_decision": "NOT_AUTHORIZED_PENDING_RELEASE_REVIEW",
        "credentials_persisted": False,
        "total_payload_bytes": plan["expected_payload_bytes"],
    }
    atomic_json(root / MANIFEST, manifest)

    api_url, tree_url = api_urls(model)
    api_path, tree_path = records / "model_api.json", records / "tree.json"
    readme_path, license_path = records / "README.md", records / "LICENSE"
    readme_headers = records / "README.headers"
    license_headers = records / "LICENSE.headers"
    curl(api_url, api_path, proxy=proxy, max_time=max_time)
    curl(tree_url, tree_path, proxy=proxy, max_time=max_time)
    curl(
        exact_url(model, "README.md", endpoint),
        readme_path,
        proxy=proxy,
        headers=readme_headers,
        max_time=max_time,
    )
    curl(
        exact_url(model, "LICENSE", endpoint),
        license_path,
        proxy=proxy,
        headers=license_headers,
        max_time=max_time,
    )
    if (
        commits_from_headers(readme_headers) != {model["revision"]}
        or commits_from_headers(license_headers) != {model["revision"]}
    ):
        raise ValidationError("METADATA_RESPONSE_REVISION")
    license_evidence = validate_metadata(
        model,
        load_json(api_path),
        load_json(tree_path),
        readme_path.read_bytes(),
        license_path.read_bytes(),
    )

    rows: list[dict] = []
    identities: list[dict] = []
    if final.exists():
        rows = validate_snapshot(model, final)
        for item in model["allowlist"]:
            headers = records / f"{item['path']}.headers"
            if (
                not headers.is_file()
                or commits_from_headers(headers) != {model["revision"]}
            ):
                raise ValidationError(
                    f"MISSING_FINAL_RESPONSE_IDENTITY:{item['path']}"
                )
            object_ids = identity_from_headers(headers)
            if item["git_oid"] not in object_ids and (
                not item["lfs_sha256"]
                or item["lfs_sha256"] not in object_ids
            ):
                raise ValidationError(f"FINAL_RESPONSE_OBJECT_ID:{item['path']}")
            identities.append(
                {
                    "path": item["path"],
                    "x_repo_commit": model["revision"],
                    "object_identity_values": sorted(object_ids),
                    "reused_complete_file": True,
                }
            )
    else:
        stage.mkdir(mode=0o700, exist_ok=True)
        os.chmod(stage, 0o700)
        allowed = {item["path"] for item in model["allowlist"]} | {"SHA256SUMS"}
        extras = {entry.name for entry in stage.iterdir()} - allowed
        if extras:
            raise ValidationError(f"UNEXPECTED_STAGING_FILES:{sorted(extras)}")
        for item in model["allowlist"]:
            destination = stage / item["path"]
            headers = records / f"{item['path']}.headers"
            reused = staged_file_complete(destination, item)
            if not reused:
                if (
                    destination.exists()
                    and destination.stat().st_size >= item["expected_bytes"]
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
            if (
                not headers.is_file()
                or commits_from_headers(headers) != {model["revision"]}
            ):
                raise ValidationError(f"RESPONSE_REVISION:{item['path']}")
            ids = identity_from_headers(headers)
            if item["git_oid"] not in ids and (
                not item["lfs_sha256"] or item["lfs_sha256"] not in ids
            ):
                raise ValidationError(f"RESPONSE_OBJECT_ID:{item['path']}")
            rows.append(
                {
                    "path": item["path"],
                    "bytes": destination.stat().st_size,
                    "sha256": sha256_file(destination),
                    "git_oid": item["git_oid"],
                }
            )
            identities.append(
                {
                    "path": item["path"],
                    "x_repo_commit": model["revision"],
                    "object_identity_values": sorted(ids),
                    "reused_complete_file": reused,
                }
            )
        write_sums(stage, rows)
        validate_snapshot(
            model, stage, {row["path"]: row["sha256"] for row in rows}
        )

    smoke_path = final if final.exists() else stage
    smoke = offline_smoke(smoke_path)
    if not final.exists():
        final.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(final.parent, 0o700)
        os.replace(stage, final)
    rows = validate_snapshot(
        model, final, {row["path"]: row["sha256"] for row in rows}
    )
    for path in records.iterdir():
        os.chmod(path, 0o600)
    manifest.update(
        {
            "completed_at": utc_now(),
            "status": "ACQUISITION_COMPLETE",
            "decision": "QWEN_GROUNDED_GENERATOR_SNAPSHOT_READY",
            "technical_internal_use_authorized": True,
            "model": {
                "repo_id": model["repo_id"],
                "revision": model["revision"],
                "snapshot_dir": model["snapshot_dir"],
                "weight_layout": model["weight_layout"],
                "files": rows,
                "response_identity": identities,
                "license": license_evidence,
                "metadata_archive": str(records.relative_to(root)),
            },
            "offline_smoke": smoke,
        }
    )
    atomic_json(root / MANIFEST, manifest)
    write_report(root, manifest)
    return manifest


def finalize_existing_staging(root: Path) -> dict:
    """Validate archived exact-revision evidence and promote without network.

    This path is intentionally separate from ``acquire`` so an interrupted
    network phase can be completed offline once every allowlisted byte and
    response header is already present.
    """
    plan = load_json(root / ROOT_PLAN)
    validate_plan(plan)
    model = plan["model"]
    restricted = root / "data/restricted/scale1b"
    models_root = restricted / "models"
    records = restricted / "acquisition_records/ga/qwen"
    manifests = restricted / "manifests"
    for path in (restricted, models_root, records, manifests):
        if not path.is_dir() or path.is_symlink():
            raise ValidationError(f"MISSING_OR_INVALID_DIRECTORY:{path}")
        os.chmod(path, 0o700)
    final = root / model["snapshot_dir"]
    stage = models_root / ".task109-qwen.stage"
    if final.exists():
        raise ValidationError("FINAL_ALREADY_EXISTS")
    if not stage.is_dir() or stage.is_symlink():
        raise ValidationError("COMPLETE_STAGING_NOT_FOUND")

    required_metadata = {
        "model_api.json",
        "tree.json",
        "README.md",
        "LICENSE",
        "README.headers",
        "LICENSE.headers",
    }
    if not required_metadata.issubset({path.name for path in records.iterdir()}):
        raise ValidationError("ARCHIVED_METADATA_INCOMPLETE")
    if (
        commits_from_headers(records / "README.headers") != {model["revision"]}
        or commits_from_headers(records / "LICENSE.headers") != {model["revision"]}
    ):
        raise ValidationError("ARCHIVED_METADATA_RESPONSE_REVISION")
    license_evidence = validate_metadata(
        model,
        load_json(records / "model_api.json"),
        load_json(records / "tree.json"),
        (records / "README.md").read_bytes(),
        (records / "LICENSE").read_bytes(),
    )

    rows = validate_snapshot(model, stage)
    identities: list[dict] = []
    for item in model["allowlist"]:
        headers = records / f"{item['path']}.headers"
        if (
            not headers.is_file()
            or commits_from_headers(headers) != {model["revision"]}
        ):
            raise ValidationError(
                f"MISSING_STAGED_RESPONSE_IDENTITY:{item['path']}"
            )
        object_ids = identity_from_headers(headers)
        if item["git_oid"] not in object_ids and (
            not item["lfs_sha256"] or item["lfs_sha256"] not in object_ids
        ):
            raise ValidationError(f"STAGED_RESPONSE_OBJECT_ID:{item['path']}")
        identities.append(
            {
                "path": item["path"],
                "x_repo_commit": model["revision"],
                "object_identity_values": sorted(object_ids),
                "reused_complete_file": True,
            }
        )

    # This is the only expensive step. It has no network fallback and must
    # succeed before the atomic directory rename below.
    smoke = offline_smoke(stage)
    final.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(final.parent, 0o700)
    os.replace(stage, final)
    rows = validate_snapshot(
        model, final, {row["path"]: row["sha256"] for row in rows}
    )
    for path in records.iterdir():
        if path.is_file():
            os.chmod(path, 0o600)
    manifest = {
        "schema_version": "1.0",
        "task": 109,
        "created_at": utc_now(),
        "completed_at": utc_now(),
        "status": "ACQUISITION_COMPLETE",
        "decision": "QWEN_GROUNDED_GENERATOR_SNAPSHOT_READY",
        "technical_internal_use_authorized": True,
        "redistribution_authorized": False,
        "redistribution_decision": "NOT_AUTHORIZED_PENDING_RELEASE_REVIEW",
        "credentials_persisted": False,
        "network_used_during_finalization": False,
        "total_payload_bytes": plan["expected_payload_bytes"],
        "model": {
            "repo_id": model["repo_id"],
            "revision": model["revision"],
            "snapshot_dir": model["snapshot_dir"],
            "weight_layout": model["weight_layout"],
            "files": rows,
            "response_identity": identities,
            "license": license_evidence,
            "metadata_archive": str(records.relative_to(root)),
        },
        "offline_smoke": smoke,
    }
    atomic_json(root / MANIFEST, manifest)
    write_report(root, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--finalize-existing-staging", action="store_true")
    parser.add_argument("--proxy")
    parser.add_argument("--endpoint", default="https://huggingface.co")
    parser.add_argument("--max-time", type=int, default=7200)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    plan = load_json(root / ROOT_PLAN)
    validate_plan(plan)
    if args.execute and args.finalize_existing_staging:
        raise ValidationError("CHOOSE_EXECUTE_OR_OFFLINE_FINALIZE")
    if args.finalize_existing_staging:
        result = finalize_existing_staging(root)
        print(result["decision"])
        return 0
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "PREFLIGHT_ONLY",
                    "payload_bytes": plan["expected_payload_bytes"],
                },
                indent=2,
            )
        )
        return 0
    result = acquire(root, args.proxy, args.endpoint, args.max_time)
    print(result["decision"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidationError, subprocess.CalledProcessError) as exc:
        print(f"QWEN_GROUNDED_GENERATOR_NO_GO:{exc}", file=sys.stderr)
        raise SystemExit(2)
