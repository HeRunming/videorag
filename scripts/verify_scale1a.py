#!/usr/bin/env python3
"""Verify the Task-93 trust anchor and generated Scale-1A artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from av_trace_scale1a.core import verify_scale1a, verify_trust_anchor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--trust-anchor-only", action="store_true")
    parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    try:
        result = (
            verify_trust_anchor(Path(args.repo_root))
            if args.trust_anchor_only
            else verify_scale1a(Path(args.repo_root), strict=args.strict)
        )
    except Exception as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("verified", result.get("passed", False)) else 2


if __name__ == "__main__":
    raise SystemExit(main())
