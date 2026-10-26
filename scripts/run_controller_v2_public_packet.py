#!/usr/bin/env python3
"""Run paired or diagnostic controller arms on the public packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from av_trace_controller_v2.execution import run_public_packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Execute, but never score, AV-TRACE controller arms on the public "
            "controller-v2 packet. Only --arm paired is confirmatory."
        )
    )
    parser.add_argument(
        "--arm",
        choices=("paired", "v1", "v2"),
        required=True,
        help=(
            "Use paired for the frozen confirmatory v1-then-v2-per-case "
            "protocol. v1 and v2 alone are non-confirmatory diagnostics."
        ),
    )
    parser.add_argument("--public-packet", type=Path, required=True)
    parser.add_argument("--model-snapshot", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--implementation-attestation",
        type=Path,
        required=True,
        help=(
            "JSON attesting no evaluator-key access, no implementation-time "
            "holdout run, and no expected-output inspection."
        ),
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--startup-timeout-s", type=float, default=240.0)
    parser.add_argument("--generation-timeout-s", type=float, default=180.0)
    parser.add_argument("--threads", type=int, default=8)
    args = parser.parse_args(argv)
    report = run_public_packet(
        repo_root=args.repo_root,
        arm=args.arm,
        public_packet_path=args.public_packet,
        model_snapshot=args.model_snapshot,
        output_dir=args.output_dir,
        implementation_attestation_path=args.implementation_attestation,
        startup_timeout_s=args.startup_timeout_s,
        generation_timeout_s=args.generation_timeout_s,
        threads=args.threads,
    )
    print(
        json.dumps(
            {
                "arm": report["manifest"]["arm"],
                "confirmatory": report["manifest"]["confirmatory"],
                "execution_mode": report["manifest"]["execution_mode"],
                "case_count": report["manifest"]["case_count"],
                "correctness_scored": False,
                "evaluator_labels_loaded": False,
                "output_dir": report["output_dir"],
                "output_sealed": report["seal"]["immutable"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
