#!/usr/bin/env python3
"""Run the restricted LVB-01 visual + subtitle-proxy engineering rehearsal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from av_trace_real_rehearsal import RehearsalRunner, RestrictedAssetAdapter
from av_trace_real_rehearsal.protocol import write_rehearsal_report


DEFAULT_OUTPUT = Path("data/restricted/lvb01/rehearsal/lvb01_visual_subtitle_rehearsal.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    output = args.output if args.output.is_absolute() else repo_root / args.output
    adapter = RestrictedAssetAdapter(repo_root)
    report = RehearsalRunner(adapter).run_all()
    write_rehearsal_report(output, report)
    summary = report["summary"]
    print(
        json.dumps(
            {
                "rehearsal_id": report["rehearsal_id"],
                "scope_label": report["scope_label"],
                "asset_count": summary["asset_count"],
                "task_count": summary["task_count"],
                "run_count": summary["run_count"],
                "strict_engineering_go": summary["strict_engineering_go"],
                "output": output.relative_to(repo_root).as_posix(),
                "content_disclosure": "no subtitle text or raw frames printed",
            },
            sort_keys=True,
        )
    )
    return 0 if summary["strict_engineering_go"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
