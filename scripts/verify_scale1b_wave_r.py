#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from av_trace_scale1b_retrieval import verify_wave_r


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--spot-recompute", action="store_true")
    args = parser.parse_args()
    result = verify_wave_r(
        args.repo_root, require_results=not args.build_only,
        spot_recompute=args.spot_recompute,
    )
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
