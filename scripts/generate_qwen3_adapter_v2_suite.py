#!/usr/bin/env python3
"""Generate and pre-execution-seal the Task-182 Qwen3 adapter-v2 suite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace_strong_baselines_v2.qwen3_suite_generator import (
    EXPECTED_GENERATED_DATE,
    Qwen3FutureSealedSuiteGenerator,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--seed-recorded-at", required=True)
    parser.add_argument("--suite-id", required=True)
    parser.add_argument("--freeze-label", required=True)
    parser.add_argument(
        "--generated-date",
        default=EXPECTED_GENERATED_DATE,
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    generator = Qwen3FutureSealedSuiteGenerator(
        seed=args.seed,
        seed_recorded_at=args.seed_recorded_at,
        suite_id=args.suite_id,
        freeze_label=args.freeze_label,
        generated_date=args.generated_date,
    )
    print(
        json.dumps(
            generator.seal_to(args.output_dir),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
