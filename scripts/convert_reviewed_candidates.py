#!/usr/bin/env python3
"""Convert a local importer artifact under a signed local reviewer decision."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

from av_trace_data.io import load_json, write_json_atomic
from av_trace_data.reviewed_conversion import (
    ReviewedConversionError,
    convert_reviewed_candidates,
)


def _local_file(value: str) -> Path:
    parsed = urlparse(value)
    if parsed.scheme or value.startswith("//"):
        raise argparse.ArgumentTypeError("only local filesystem paths are accepted")
    path = Path(value)
    if path.is_symlink():
        raise argparse.ArgumentTypeError("symbolic-link inputs are not accepted")
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"not a regular local file: {value}")
    return path


def _utc_timestamp(value: str) -> datetime:
    if not value.endswith("Z"):
        raise argparse.ArgumentTypeError("timestamp must be UTC RFC3339 ending in Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("invalid RFC3339 timestamp") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspection", required=True, type=_local_file)
    parser.add_argument("--decision", required=True, type=_local_file)
    parser.add_argument("--reviewer-registry", required=True, type=_local_file)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--as-of",
        type=_utc_timestamp,
        help="Deterministic UTC conversion time; defaults to the current UTC time",
    )
    parser.add_argument("--max-decision-age-days", type=int, default=30)
    args = parser.parse_args(argv)
    if args.max_decision_age_days <= 0:
        parser.error("--max-decision-age-days must be positive")
    try:
        output_path = Path(args.output)
        if urlparse(args.output).scheme or args.output.startswith("//"):
            raise ReviewedConversionError(
                "output must be a local filesystem path"
            )
        artifact = convert_reviewed_candidates(
            load_json(args.inspection),
            load_json(args.decision),
            load_json(args.reviewer_registry),
            as_of=args.as_of,
            max_decision_age=timedelta(days=args.max_decision_age_days),
        )
        write_json_atomic(output_path, artifact)
        print(json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    except (OSError, TypeError, ValueError, KeyError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "error": str(exc),
                    "network_access_performed": False,
                    "contains_media": False,
                    "acquisition_authorization": "none",
                },
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

