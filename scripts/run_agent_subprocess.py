#!/usr/bin/env python3
"""Run one AV-TRACE episode through the JSONL subprocess agent boundary."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace_agent_runtime import RuntimeConfig, run_subprocess_episode  # noqa: E402
from av_trace_agent_runtime.baseline_entrypoint import AGENTS  # noqa: E402
from av_trace_mvp.backend import FixedBackend  # noqa: E402
from av_trace_mvp.index import load_generated  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generated-root",
        type=Path,
        default=ROOT / "mvp/generated/full",
    )
    parser.add_argument("--family-id", required=True)
    parser.add_argument(
        "--state-role",
        choices=["CLEAN", "BLOCKED", "RESTORED"],
        required=True,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--baseline", choices=sorted(AGENTS))
    group.add_argument(
        "--agent-command",
        help="External agent command parsed with POSIX shell-like quoting.",
    )
    parser.add_argument("--agent-name")
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument("--timeout-s", type=float, default=10.0)
    parser.add_argument("--max-output-bytes", type=int, default=1_000_000)
    parser.add_argument("--max-message-bytes", type=int, default=256_000)
    parser.add_argument("--output", type=Path, default=Path("-"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    corpus = load_generated(args.generated_root)
    family = corpus.family(args.family_id)
    backend = FixedBackend(family, args.state_role, corpus.index, corpus.manifest)
    if args.baseline:
        command = [
            sys.executable,
            "-m",
            "av_trace_agent_runtime.baseline_entrypoint",
            "--agent",
            args.baseline,
        ]
        agent_name = args.agent_name or args.baseline
    else:
        command = shlex.split(args.agent_command)
        if not command:
            raise SystemExit("--agent-command must not be empty")
        agent_name = args.agent_name or Path(command[0]).name
    trajectory = run_subprocess_episode(
        backend=backend,
        family=family,
        state_role=args.state_role,
        agent_name=agent_name,
        command=command,
        config=RuntimeConfig(
            timeout_s=args.timeout_s,
            max_output_bytes=args.max_output_bytes,
            max_message_bytes=args.max_message_bytes,
            seed=args.seed,
        ),
    )
    rendered = json.dumps(
        trajectory,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"
    if args.output == Path("-"):
        sys.stdout.write(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
