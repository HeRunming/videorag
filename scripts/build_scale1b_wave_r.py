#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from av_trace_scale1b_retrieval import build_wave_r


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--siglip-batch", type=int, default=8)
    parser.add_argument("--clap-batch", type=int, default=4)
    parser.add_argument("--source", action="append")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    result = build_wave_r(
        args.repo_root, resume=not args.no_resume, threads=args.threads,
        siglip_batch=args.siglip_batch, clap_batch=args.clap_batch,
        source_limit=args.source,
    )
    print(json.dumps(result["decisions"], indent=2))


if __name__ == "__main__":
    main()
