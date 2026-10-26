#!/usr/bin/env python3
"""Generate deterministic validator trajectories and proof artifacts."""

from __future__ import annotations

import argparse
import json

from av_trace_validation.generator import generate_validator_artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generated-root", default="mvp/generated/full")
    parser.add_argument("--output-root", default="mvp/validator/generated")
    parser.add_argument("--fixed-call-family-id", default="syn_f08_count_status")
    parser.add_argument("--fixed-call-index", type=int, default=0)
    parser.add_argument("--no-clean", action="store_true")
    args = parser.parse_args()
    result = generate_validator_artifacts(
        generated_root=args.generated_root,
        output_root=args.output_root,
        clean=not args.no_clean,
        fixed_call_family_id=args.fixed_call_family_id,
        fixed_call_index=args.fixed_call_index,
    )
    print(json.dumps(result["counts"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

