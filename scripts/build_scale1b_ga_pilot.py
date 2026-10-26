#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from av_trace_scale1b_agent import build_ga_pilot, freeze_ga_contract


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    result = (
        freeze_ga_contract(args.repo_root)
        if args.freeze_only
        else build_ga_pilot(args.repo_root)
    )
    print(
        json.dumps(
            {
                "hash": result.get("config_hash", result.get("contract_hash")),
                "cases": len(result["matrix"]),
                "status": result.get("contract_status", "GATES_BOUND"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
