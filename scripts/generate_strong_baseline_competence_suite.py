#!/usr/bin/env python3
"""Generate or verify the public fictional strong-baseline competence suite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from av_trace_strong_baselines.competence import (
    generate_competence_suite,
    load_suite,
    write_competence_suite,
)

DEFAULT_OUTPUT = Path(
    "data/rehearsal_plan/strong_baseline_competence_suite_v1.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate or verify the source-free fictional competence suite. "
            "This script never loads or calls a model."
        )
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    destination = root / args.output
    if args.check:
        existing = load_suite(destination)
        expected = generate_competence_suite()
        if existing != expected:
            raise SystemExit("SUITE_DOES_NOT_MATCH_FROZEN_GENERATOR")
        suite = existing
    else:
        suite = write_competence_suite(destination)
    print(
        json.dumps(
            {
                "path": str(destination),
                "suite_id": suite["suite_id"],
                "suite_hash": suite["suite_hash"],
                "controller_finalizer_cases": len(
                    suite["cases"]["controller_finalizer"]
                ),
                "direct_av_substantive_cases": sum(
                    case["case_type"] == "direct_av"
                    for case in suite["cases"]["direct_av"]
                ),
                "direct_av_group_entries": len(suite["cases"]["direct_av"]),
                "model_inference_run": False,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
