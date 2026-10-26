#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from av_trace_scale1b_retrieval import run_wave_r


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    result = run_wave_r(args.repo_root)
    print(json.dumps(result["decisions"], indent=2))


if __name__ == "__main__":
    main()
