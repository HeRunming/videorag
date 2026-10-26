#!/usr/bin/env python3
"""Score a recorded strong-baseline competence submission offline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from av_trace_strong_baselines.competence import (
    evaluate_competence_submission,
    load_submission,
    load_suite,
)

DEFAULT_SUITE = Path(
    "data/rehearsal_plan/strong_baseline_competence_suite_v1.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate already-recorded outputs. This evaluator never invokes "
            "a model and rejects wrong snapshots or changed suite hashes."
        )
    )
    parser.add_argument("submission")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--suite", default=str(DEFAULT_SUITE))
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    report = evaluate_competence_submission(
        load_suite(root / args.suite),
        load_submission(root / args.submission),
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        destination = root / args.output
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
