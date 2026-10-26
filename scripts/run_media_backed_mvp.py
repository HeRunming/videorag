#!/usr/bin/env python3
"""Run the certified AV-TRACE media-backed MVP v2 experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace_media_pipeline import run_media_backed_experiment  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "mvp/results/media_backed_v2",
    )
    parser.add_argument(
        "--skip-mutations",
        action="store_true",
        help="Run the 96 main episodes and fixed-call canary without mutation pairs.",
    )
    args = parser.parse_args(argv)
    report = run_media_backed_experiment(
        repository_root=ROOT,
        output_root=args.output_root,
        run_mutations=not args.skip_mutations,
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "result_hash": report["result_hash"],
                "counts": report["counts"],
                "output_root": str(args.output_root),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
