#!/usr/bin/env python3
"""Run controller-v3 on consumed synthetic development data only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from av_trace_controller_v3.development import (
    run_controller_v3_development,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run factorized controller-v3 on Task-111 consumed dev cases."
        )
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--startup-timeout-s", type=float, default=240.0)
    parser.add_argument("--generation-timeout-s", type=float, default=180.0)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    report = run_controller_v3_development(
        args.repo_root,
        startup_timeout_s=args.startup_timeout_s,
        generation_timeout_s=args.generation_timeout_s,
        threads=args.threads,
        prepare_only=args.prepare_only,
    )
    displayed = (
        report["metrics"]
        if "metrics" in report
        else {"prepared": bool(report.get("prepared"))}
    )
    print(json.dumps(displayed, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
