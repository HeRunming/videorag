#!/usr/bin/env python3
"""Generate the AV-TRACE synthetic MVP corpus without network access."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from av_trace_mvp.index import build_generated_backend
from av_trace_mvp.synthetic_data import generate_corpus, probe_mp4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("quick", "full"), default="full")
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--config", type=Path, default=ROOT / "mvp/config/synthetic_scenarios.json")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--no-clean", action="store_true", help="Do not remove the output directory before generation.")
    parser.add_argument("--probe", action="store_true", help="Decode-probe every generated MP4.")
    args = parser.parse_args()
    output = args.output or ROOT / "mvp/generated" / args.mode
    result = generate_corpus(
        config_path=args.config,
        output_dir=output,
        mode=args.mode,
        seed=args.seed,
        clean=not args.no_clean,
        repository_root=ROOT,
    )
    corpus = build_generated_backend(output)
    probes = []
    if args.probe:
        for source_id in sorted(result.mp4_hashes):
            probes.append(probe_mp4(output / "media" / f"{source_id}.mp4"))
    print(
        json.dumps(
            {
                "output_dir": str(result.output_dir),
                "sources": result.source_count,
                "families": result.family_count,
                "episodes": result.episode_count,
                "total_bytes": result.total_bytes,
                "metadata_sha256": result.metadata_sha256,
                "backend_manifest_sha256": corpus.manifest.manifest_hash,
                "backend_index_sha256": corpus.index.index_hash,
                "backend_records": len(corpus.index.records),
                "elapsed_s": round(result.elapsed_s, 3),
                "mp4_sha256": result.mp4_hashes,
                "probes": probes,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
