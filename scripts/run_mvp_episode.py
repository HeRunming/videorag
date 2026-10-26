#!/usr/bin/env python3
"""Run one deterministic scripted MVP episode and emit a trajectory JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace.util import load_json  # noqa: E402
from av_trace_mvp.backend import FixedBackend  # noqa: E402
from av_trace_mvp.index import load_generated  # noqa: E402
from av_trace_mvp.runner import run_scripted_episode  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-root", type=Path, default=ROOT / "mvp/generated")
    parser.add_argument("--family-id", required=True)
    parser.add_argument("--state-role", choices=["CLEAN", "BLOCKED", "RESTORED"], required=True)
    parser.add_argument(
        "--script",
        type=Path,
        required=True,
        help="JSON action array, or an object containing an 'actions' array.",
    )
    parser.add_argument("--output", type=Path, default=Path("-"))
    args = parser.parse_args(argv)

    corpus = load_generated(args.generated_root)
    family = corpus.family(args.family_id)
    script = load_json(args.script)
    actions = script.get("actions") if isinstance(script, dict) else script
    if not isinstance(actions, list):
        parser.error("--script must contain a JSON action array")
    backend = FixedBackend(family, args.state_role, corpus.index, corpus.manifest)
    trajectory = run_scripted_episode(backend, actions)
    serialized = json.dumps(trajectory, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output == Path("-"):
        sys.stdout.write(serialized)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
