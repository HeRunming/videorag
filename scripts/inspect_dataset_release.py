#!/usr/bin/env python3
"""Inspect one local repository metadata snapshot; never use the network."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from av_trace_data.adapters import adapter_for_config
from av_trace_data.audit import append_audit_log, audit_event
from av_trace_data.configs import PRIORITY_ADAPTERS, get_adapter_config
from av_trace_data.errors import DataAdapterError
from av_trace_data.io import write_json_atomic


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", required=True, choices=sorted(PRIORITY_ADAPTERS))
    parser.add_argument("--fixture", required=True, help="Local JSON metadata snapshot")
    parser.add_argument("--output", help="Write normalized inspection JSON here")
    parser.add_argument("--audit-log", help="Append a JSONL audit event")
    args = parser.parse_args(argv)
    try:
        config = get_adapter_config(args.adapter)
        inspection = adapter_for_config(config).inspect_fixture(args.fixture)
        result = inspection.to_dict()
        if args.output:
            write_json_atomic(args.output, result)
        if args.audit_log:
            append_audit_log(
                args.audit_log,
                audit_event(
                    "dataset_release_inspected",
                    adapter_id=args.adapter,
                    fixture=str(Path(args.fixture)),
                    snapshot_sha256=inspection.snapshot_sha256,
                    revision=inspection.revision,
                    candidate_count=len(inspection.candidates),
                    network_access_performed=False,
                ),
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (DataAdapterError, KeyError, OSError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
