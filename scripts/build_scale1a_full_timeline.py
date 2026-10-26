#!/usr/bin/env python3
"""Build the restartable restricted Scale-1A full-timeline index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from av_trace_scale1a.core import Scale1AError, build_scale1a


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--source", action="append", dest="sources")
    parser.add_argument("--smoke-seconds", type=float)
    args = parser.parse_args()
    try:
        result = build_scale1a(
            Path(args.repo_root), resume=args.resume, threads=args.threads,
            source_limit=args.sources, smoke_seconds=args.smoke_seconds,
        )
    except Scale1AError as exc:
        print(json.dumps({"status": "NO_GO", "error": str(exc)}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "status": "complete" if result["complete"] else "partial",
                "segment_counts": result["segment_manifest"]["totals"],
                "observation_counts": result["observation_manifest"]["counts"],
                "clip_decision": result["observation_manifest"]["model_snapshots"]["clip"]["decision"],
                "resume_command": "python scripts/build_scale1a_full_timeline.py --repo-root . --resume",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
