#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from av_trace_real_av import build_mvp


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    print(json.dumps(build_mvp(args.repo_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
