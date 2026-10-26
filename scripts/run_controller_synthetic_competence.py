#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from av_trace_scale1b_agent.competence import run_synthetic_competence


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the synthetic-only learned-controller competence suite."
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--startup-timeout-s", type=float, default=240.0)
    parser.add_argument("--generation-timeout-s", type=float, default=180.0)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument(
        "--model",
        choices=("qwen1.5b", "qwen7b"),
        default="qwen1.5b",
        help="Pinned controller snapshot to run; qwen7b writes Task-114 artifacts.",
    )
    args = parser.parse_args()
    report = run_synthetic_competence(
        args.repo_root,
        startup_timeout_s=args.startup_timeout_s,
        generation_timeout_s=args.generation_timeout_s,
        threads=args.threads,
        model_key=args.model,
    )
    print(json.dumps(report["metrics"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
