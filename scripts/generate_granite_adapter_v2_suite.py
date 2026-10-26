#!/usr/bin/env python3
"""Prospective CLI for the Granite adapter v2 sealed-suite GENERATOR.

Task 175 installs this command but intentionally does not invoke generation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace_strong_baselines_v2.suite_generator import (
    FutureSealedSuiteGenerator,
    generator_contract,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--suite-id")
    parser.add_argument("--freeze-label")
    parser.add_argument("--generated-date", default="2026-10-02")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.describe:
        print(json.dumps(generator_contract(), indent=2, sort_keys=True))
        return 0
    required = {
        "--seed": args.seed,
        "--suite-id": args.suite_id,
        "--freeze-label": args.freeze_label,
        "--output-dir": args.output_dir,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error("generation requires " + ", ".join(missing))
    generator = FutureSealedSuiteGenerator(
        seed=args.seed,
        suite_id=args.suite_id,
        freeze_label=args.freeze_label,
        generated_date=args.generated_date,
    )
    seal = generator.seal_to(args.output_dir)
    print(json.dumps(seal, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
