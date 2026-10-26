#!/usr/bin/env python3
"""Select deterministic 20–90 minute AV candidates from inspection JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from av_trace_data.audit import append_audit_log, audit_event
from av_trace_data.errors import DataAdapterError
from av_trace_data.io import load_json, write_json_atomic
from av_trace_data.manifests import draft_acquisition_manifest
from av_trace_data.models import NormalizedCandidate
from av_trace_data.selection import SelectionPolicy, select_candidates


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inspections", nargs="+", help="Inspection JSON files")
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest-dir")
    parser.add_argument("--created-by", default="metadata_adapter")
    parser.add_argument("--min-minutes", type=float, default=20.0)
    parser.add_argument("--max-minutes", type=float, default=90.0)
    parser.add_argument("--target-minutes", type=float, default=40.0)
    parser.add_argument("--limit", type=_positive_int, default=30)
    parser.add_argument("--max-item-bytes", type=_positive_int)
    parser.add_argument("--max-total-bytes", type=_positive_int)
    parser.add_argument("--require-known-size", action="store_true")
    parser.add_argument("--require-media-url", action="store_true")
    parser.add_argument("--split", action="append", default=[])
    parser.add_argument("--access-mode", action="append", default=[])
    parser.add_argument("--audit-log")
    args = parser.parse_args(argv)
    try:
        candidates: list[NormalizedCandidate] = []
        source_snapshots: dict[str, str] = {}
        for path in args.inspections:
            value = load_json(path)
            if (
                isinstance(value, dict)
                and value.get("artifact_class")
                == "metadata_reconnaissance_inspection"
            ):
                raise ValueError(
                    "raw snapshot-importer reconnaissance cannot be selected "
                    "directly; an explicit reviewed conversion to a candidate "
                    "inspection with NormalizedCandidate records is required: "
                    f"{path}"
                )
            if not isinstance(value, dict) or not isinstance(value.get("candidates"), list):
                raise ValueError(f"inspection has no candidates array: {path}")
            source_key = (
                f"{value.get('provider')}:{value.get('repository_id')}"
                f"@{value.get('revision')}"
            )
            snapshot_sha256 = value.get("snapshot_sha256")
            if not isinstance(snapshot_sha256, str):
                raise ValueError(f"inspection has no snapshot_sha256: {path}")
            previous = source_snapshots.setdefault(source_key, snapshot_sha256)
            if previous != snapshot_sha256:
                raise ValueError(
                    f"conflicting snapshot hashes for inspection source {source_key}"
                )
            candidates.extend(
                NormalizedCandidate.from_dict(item) for item in value["candidates"]
            )
        policy = SelectionPolicy(
            min_duration_s=args.min_minutes * 60.0,
            max_duration_s=args.max_minutes * 60.0,
            target_duration_s=args.target_minutes * 60.0,
            limit=args.limit,
            max_item_bytes=args.max_item_bytes,
            max_total_bytes=args.max_total_bytes,
            require_known_size=args.require_known_size,
            require_media_url=args.require_media_url,
            allowed_splits=tuple(sorted(set(args.split))),
            allowed_access_modes=tuple(sorted(set(args.access_mode))),
        )
        selection = select_candidates(
            candidates,
            policy,
            source_snapshots=source_snapshots,
        )
        write_json_atomic(args.output, selection)
        manifest_paths: list[str] = []
        if args.manifest_dir:
            manifest_dir = Path(args.manifest_dir)
            for item in selection["selected"]:
                candidate = NormalizedCandidate.from_dict(item)
                manifest = draft_acquisition_manifest(
                    candidate, created_by=args.created_by
                )
                path = manifest_dir / f"{manifest['asset_id']}.json"
                write_json_atomic(path, manifest)
                manifest_paths.append(str(path))
        if args.audit_log:
            append_audit_log(
                args.audit_log,
                audit_event(
                    "rehearsal_candidates_selected",
                    selection_sha256=selection["selection_sha256"],
                    selected_count=selection["summary"]["selected_count"],
                    rejected_count=selection["summary"]["rejected_count"],
                    manifest_paths=manifest_paths,
                    network_access_performed=False,
                ),
            )
        print(json.dumps(selection, indent=2, sort_keys=True))
        return 0
    except (DataAdapterError, OSError, TypeError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
