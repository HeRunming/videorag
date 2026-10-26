#!/usr/bin/env python3
"""Run deterministic AV-TRACE MVP baselines over a frozen generated corpus."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace_mvp.agents import (  # noqa: E402
    AlwaysAnswerAgent,
    EvidenceBeliefStateAgent,
    ReActHeuristicAgent,
    SingleShotRAGAgent,
)
from av_trace_mvp.backend import FixedBackend  # noqa: E402
from av_trace_mvp.experiment import run_experiment  # noqa: E402
from av_trace_mvp.index import load_generated  # noqa: E402


AGENTS = {
    "always-answer": AlwaysAnswerAgent,
    "single-shot-rag": SingleShotRAGAgent,
    "react-heuristic": ReActHeuristicAgent,
    "evidence-belief-state": EvidenceBeliefStateAgent,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generated-root",
        type=Path,
        default=ROOT / "mvp/generated/full",
        help="Directory containing backend_manifest.json and its frozen artifacts.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "mvp/results/experiment",
    )
    parser.add_argument(
        "--agents",
        default="all",
        help="Comma-separated agent keys, or 'all'.",
    )
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260905)
    args = parser.parse_args(argv)

    if args.agents == "all":
        names = list(AGENTS)
    else:
        names = [item.strip() for item in args.agents.split(",") if item.strip()]
        unknown = sorted(set(names) - set(AGENTS))
        if unknown:
            parser.error(f"unknown agents: {', '.join(unknown)}")
    corpus = load_generated(args.generated_root)
    agents = [AGENTS[name]() for name in names]

    def backend_factory(family, state_role):
        return FixedBackend(
            family,
            state_role,
            corpus.index,
            corpus.manifest,
        )

    report = run_experiment(
        corpus.families,
        agents,
        backend_factory,
        output_dir=args.output_dir,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
    )
    print(
        f"Wrote {len(report['episode_metrics'])} episode results for "
        f"{len(agents)} agents to {args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

