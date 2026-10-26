#!/usr/bin/env python3
"""Import bounded local metadata snapshots into versioned inspection JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from av_trace_data.errors import DataAdapterError
from av_trace_data.snapshot_importer import (
    DEFAULT_MAX_SOURCE_BYTES,
    SnapshotImporter,
    SnapshotInput,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="LOCAL_PATH",
        help="Local JSON, JSONL, CSV, or metadata-only Parquet input",
    )
    parser.add_argument("--output", required=True, help="Inspection JSON destination")
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
        help=f"Per-input byte cap (default: {DEFAULT_MAX_SOURCE_BYTES})",
    )
    parser.add_argument(
        "--allow-unpromoted",
        action="store_true",
        help=(
            "Allow reconnaissance with absent/non-immutable repository revisions; "
            "the output remains explicitly unpromoted"
        ),
    )
    parser.add_argument(
        "--provider",
        help="Provider override applied to inputs not identified by an API snapshot",
    )
    parser.add_argument(
        "--repository-id",
        help="Repository override applied to inputs not identified by an API snapshot",
    )
    parser.add_argument(
        "--repository-revision",
        help="Full immutable repository revision override",
    )
    parser.add_argument(
        "--repository-revision-kind",
        default="git_commit",
        help="Revision kind for --repository-revision (default: git_commit)",
    )
    parser.add_argument(
        "--repository-path",
        help="Repository-relative path override (valid only with one input)",
    )
    parser.add_argument(
        "--source-family",
        help="Parser override, for example longshot or generic_metadata",
    )
    args = parser.parse_args(argv)

    if args.repository_path and len(args.inputs) != 1:
        parser.error("--repository-path is valid only with exactly one input")
    try:
        specs = [
            SnapshotInput(
                path=path,
                provider=args.provider,
                repository_id=args.repository_id,
                repository_revision=args.repository_revision,
                repository_revision_kind=args.repository_revision_kind,
                repository_path=args.repository_path,
                source_family=args.source_family,
            )
            for path in args.inputs
        ]
        artifact = SnapshotImporter(
            max_file_bytes=args.max_file_bytes
        ).build_to_path(
            specs,
            Path(args.output),
            promote=not args.allow_unpromoted,
        )
        print(json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    except (DataAdapterError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "error": str(exc),
                    "network_access_performed": False,
                },
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
