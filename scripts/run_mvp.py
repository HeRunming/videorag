#!/usr/bin/env python3
"""Unified offline AV-TRACE MVP command."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace_mvp.integration import generate, run, run_all, validate  # noqa: E402


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--generated-root",
        type=Path,
        default=ROOT / "mvp/generated/full",
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=ROOT / "mvp/results/latest",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    generation = sub.add_parser("generate", help="Generate the full corpus and freeze its backend.")
    _common(generation)
    generation.add_argument("--seed", type=int, default=20260905)
    generation.add_argument("--probe", action="store_true")
    validation = sub.add_parser("validate", help="Validate corpus, backend, and any emitted trajectories.")
    _common(validation)
    execution = sub.add_parser("run", help="Run all four agents over the 24 frozen episodes.")
    _common(execution)
    execution.add_argument("--bootstrap-samples", type=int, default=1000)
    execution.add_argument("--bootstrap-seed", type=int, default=20260905)
    all_command = sub.add_parser("all", help="Generate, validate, run, validate, and report.")
    _common(all_command)
    all_command.add_argument("--seed", type=int, default=20260905)
    all_command.add_argument("--bootstrap-samples", type=int, default=1000)
    all_command.add_argument("--bootstrap-seed", type=int, default=20260905)
    all_command.add_argument("--probe", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "generate":
        result, corpus, probes = generate(
            repository_root=ROOT,
            generated_root=args.generated_root,
            seed=args.seed,
            probe=args.probe,
        )
        output = {
            "status": "PASS",
            "generated_root": str(args.generated_root),
            "sources": result.source_count,
            "families": result.family_count,
            "episodes": result.episode_count,
            "metadata_sha256": result.metadata_sha256,
            "backend_manifest_sha256": corpus.manifest.manifest_hash,
            "backend_index_sha256": corpus.index.index_hash,
            "probes": probes,
        }
    elif args.command == "validate":
        output = validate(
            repository_root=ROOT,
            generated_root=args.generated_root,
            results_root=args.results_root,
        )
    elif args.command == "run":
        report = run(
            generated_root=args.generated_root,
            results_root=args.results_root,
            bootstrap_samples=args.bootstrap_samples,
            bootstrap_seed=args.bootstrap_seed,
        )
        output = {
            "status": "PASS",
            "results_root": str(args.results_root),
            "agent_episodes": len(report["episode_metrics"]),
            "result_hash": report["result_hash"],
        }
    else:
        output = run_all(
            repository_root=ROOT,
            generated_root=args.generated_root,
            results_root=args.results_root,
            seed=args.seed,
            bootstrap_samples=args.bootstrap_samples,
            bootstrap_seed=args.bootstrap_seed,
            probe=args.probe,
        )
    print(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if output.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
