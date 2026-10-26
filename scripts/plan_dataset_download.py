#!/usr/bin/env python3
"""Create or validate a frozen dataset download plan.

The shipped CLI never transfers bytes. ``validate`` (and the compatibility
alias ``execute``) checks plan, manifest, and approval fields. Because the CLI
has no trusted detached-signature verifier, an unsigned result is explicitly
``validated_not_authorized`` and never grants execution approval.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from av_trace_data.audit import append_audit_log, audit_event
from av_trace_data.download import (
    create_download_plan,
    execute_download_plan,
    load_approval,
)
from av_trace_data.errors import DataAdapterError
from av_trace_data.io import load_json, sha256_json, write_json_atomic
from av_trace_data.models import NormalizedCandidate


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _load_selection(path: str) -> tuple[dict[str, Any], list[NormalizedCandidate]]:
    value = load_json(path)
    if not isinstance(value, dict) or not isinstance(value.get("selected"), list):
        raise ValueError("selection JSON must contain a selected array")
    expected_hash = value.get("selection_sha256")
    body = dict(value)
    body.pop("selection_sha256", None)
    if expected_hash != sha256_json(body):
        raise ValueError("selection hash does not match its complete artifact")
    return value, [NormalizedCandidate.from_dict(item) for item in value["selected"]]


def _load_authorized_signers(path: str | None) -> dict[str, list[str]] | None:
    if path is None:
        return None
    value = load_json(path)
    if not isinstance(value, dict):
        raise ValueError("authorized signers file root must be an object")
    signers = value.get("authorized_signers", value)
    if not isinstance(signers, dict):
        raise ValueError("authorized signers must be an object")
    result: dict[str, list[str]] = {}
    for signer, roles in signers.items():
        if isinstance(roles, str):
            role_list = [roles]
        elif isinstance(roles, list) and all(isinstance(role, str) for role in roles):
            role_list = roles
        else:
            raise ValueError(f"roles for authorized signer {signer!r} are malformed")
        result[str(signer)] = role_list
    return result


def _load_manifest_files(
    manifest_dir: str, candidates: list[NormalizedCandidate]
) -> dict[str, dict[str, Any]]:
    by_asset: dict[str, dict[str, Any]] = {}
    for path in sorted(Path(manifest_dir).glob("*.json")):
        value = load_json(path)
        if not isinstance(value, dict) or not value.get("asset_id"):
            raise ValueError(f"malformed manifest: {path}")
        asset_id = str(value["asset_id"])
        if asset_id in by_asset:
            raise ValueError(f"duplicate asset_id: {asset_id}")
        by_asset[asset_id] = value
    result: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        expected_asset_id = (
            f"{candidate.dataset_id}:{candidate.source_id}"
            .replace("/", "-")
            .replace(" ", "-")[:128]
        )
        manifest = by_asset.get(expected_asset_id)
        if manifest is None:
            # Robust fallback for manually reviewed records that preserve source
            # identity but use a different asset_id.
            matches = [
                value
                for value in by_asset.values()
                if value.get("dataset_id") == candidate.dataset_id
                and isinstance(value.get("source"), dict)
                and value["source"].get("source_identifier") == candidate.upstream_id
                and value["source"].get("source_revision") == candidate.revision
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"expected one manifest for "
                    f"{candidate.dataset_id}:{candidate.source_id}; found {len(matches)}"
                )
            manifest = matches[0]
        result[f"{candidate.dataset_id}:{candidate.source_id}"] = manifest
    return result


def _add_common(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--selection", required=True)
    subparser.add_argument("--manifest-dir", required=True)
    subparser.add_argument("--audit-log")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan", help="Create a plan; transfer nothing")
    _add_common(plan_parser)
    plan_parser.add_argument("--output", required=True)
    plan_parser.add_argument("--output-root", required=True)
    plan_parser.add_argument("--max-item-bytes", type=_positive_int, required=True)
    plan_parser.add_argument("--max-total-bytes", type=_positive_int, required=True)
    plan_parser.add_argument("--range-start", type=_nonnegative_int)
    plan_parser.add_argument("--range-end", type=_nonnegative_int)
    plan_parser.add_argument(
        "--mode",
        choices=("executable", "metadata-preview"),
        default="executable",
        help="Executable plans require complete source snapshot bindings.",
    )

    for command in ("validate", "execute"):
        execute_parser = subparsers.add_parser(
            command,
            help="Validate approval fields only; this CLI cannot transfer",
        )
        _add_common(execute_parser)
        execute_parser.add_argument("--plan", required=True)
        execute_parser.add_argument("--approval-file", required=True)
        execute_parser.add_argument(
            "--authorized-signers",
            required=True,
            help="Independent JSON signer-to-role allowlist.",
        )
        execute_parser.add_argument(
            "--approved-staging-root",
            action="append",
            required=True,
            help="Independently approved absolute staging root; may be repeated.",
        )
        execute_parser.add_argument("--authorization-output")
    args = parser.parse_args(argv)
    try:
        selection, candidates = _load_selection(args.selection)
        manifests = _load_manifest_files(args.manifest_dir, candidates)
        if args.command == "plan":
            plan = create_download_plan(
                selection,
                manifests,
                output_root=args.output_root,
                max_item_bytes=args.max_item_bytes,
                max_total_bytes=args.max_total_bytes,
                range_start=args.range_start,
                range_end=args.range_end,
                plan_mode=args.mode.replace("-", "_"),
            )
            write_json_atomic(args.output, plan)
            result = plan
            event_name = "dataset_download_planned"
            event_fields = {
                "plan_sha256": plan["plan_sha256"],
                "item_count": len(plan["items"]),
            }
        else:
            plan = load_json(args.plan)
            approval = load_approval(args.approval_file)
            if not isinstance(plan, dict):
                raise ValueError("download plan root must be an object")
            binding = plan.get("selection_binding")
            if (
                not isinstance(binding, dict)
                or binding.get("selection_sha256") != selection.get("selection_sha256")
                or binding.get("selection_artifact_sha256")
                != sha256_json(selection)
            ):
                raise ValueError("plan does not bind the supplied selection artifact")
            result = execute_download_plan(
                plan,
                manifests,
                approval,
                backend=None,
                authorized_signers=_load_authorized_signers(args.authorized_signers),
                approved_staging_roots=args.approved_staging_root or None,
            )
            if args.authorization_output:
                write_json_atomic(args.authorization_output, result)
            event_name = "dataset_download_validated_not_authorized"
            event_fields = {
                "plan_sha256": result["plan_sha256"],
                "asset_ids": result["asset_ids"],
                "approved_by": result["approved_by"],
            }
        if args.audit_log:
            append_audit_log(
                args.audit_log,
                audit_event(
                    event_name,
                    **event_fields,
                    network_access_performed=False,
                ),
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (DataAdapterError, OSError, TypeError, ValueError, KeyError) as exc:
        if args.audit_log:
            append_audit_log(
                args.audit_log,
                audit_event(
                    "dataset_download_refused",
                    command=args.command,
                    reason=str(exc),
                    network_access_performed=False,
                ),
            )
        print(json.dumps({"status": "REFUSED", "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
