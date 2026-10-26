#!/usr/bin/env python3
"""Run Scale-1A matched deterministic experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from av_trace_scale1a.core import Scale1AError, replay_scale1a, run_scale1a


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    try:
        if args.replay:
            result = replay_scale1a(Path(args.repo_root))
        else:
            result = run_scale1a(Path(args.repo_root))["report"]
    except Scale1AError as exc:
        print(json.dumps({"status": "NO_GO", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
