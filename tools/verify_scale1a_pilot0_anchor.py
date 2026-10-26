#!/usr/bin/env python3
"""Compatibility entry point for the verifier command specified by Task 93."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from av_trace_scale1a.core import Scale1AError, verify_trust_anchor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--anchor")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        result = verify_trust_anchor(Path(args.repo_root))
    except Scale1AError as exc:
        print(json.dumps({"passed": False, "mismatches": [str(exc)]}, sort_keys=True))
        return 2
    print(json.dumps({"passed": True, **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
