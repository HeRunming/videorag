#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from av_trace_scale1b_agent import run_ga_pilot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--startup-timeout-s", type=float, default=240.0)
    parser.add_argument("--generation-timeout-s", type=float, default=180.0)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--max-cases", type=int)
    args = parser.parse_args()
    report = run_ga_pilot(
        args.repo_root,
        startup_timeout_s=args.startup_timeout_s,
        generation_timeout_s=args.generation_timeout_s,
        threads=args.threads,
        max_cases=args.max_cases,
    )
    print(json.dumps(report["decisions"], indent=2))


if __name__ == "__main__":
    main()
