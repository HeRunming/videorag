#!/usr/bin/env python3
"""Isolated-process resource probe for one pinned Wave-R model."""
from __future__ import annotations

import argparse
import json
import resource
import time
from pathlib import Path

from av_trace_scale1b_retrieval.core import (
    MODEL_MANIFEST_REL,
    SCALE1A_ROOT_REL,
    _WaveRModels,
    _decode_audio,
    _find_model,
    _iter_frames,
    _load,
    _slice_audio,
    verify_gates,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--model", choices=("siglip2", "clap"), required=True)
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    gates = verify_gates(root)
    segment = _load(root / SCALE1A_ROOT_REL / "segment_manifest.json")
    source_ref = "cand-045"
    acquisition = _load(
        root / "data/restricted/noaa01/manifests/noaa01_acquisition_manifest.json"
    )
    asset = next(x for x in acquisition["assets"] if x["candidate_id"] == source_ref)
    media = root / "data/restricted/noaa01/raw" / asset["basename"]
    started = time.perf_counter()
    if args.model == "siglip2":
        path, _ = _find_model(root, gates["models"], kind="siglip2")
        model = _WaveRModels(path, None, threads=8)
        cell = next(x for x in segment["base_cells"] if x["source_ref"] == source_ref)
        _, frame = next(_iter_frames(media, [cell]))
        vector = model.siglip_images([frame])[0]
        unit = cell["cell_id"]
    else:
        path, _ = _find_model(root, gates["models"], kind="clap")
        model = _WaveRModels(None, path, threads=8)
        fine = next(
            x for x in segment["segments"]
            if x["source_ref"] == source_ref and x["scale"] == "fine"
        )
        waveform = _decode_audio(media, 48_000)
        vector = model.clap_audio([
            _slice_audio(waveform, fine["start_us"], fine["end_us"], 48_000)
        ], 48_000)[0]
        unit = fine["segment_id"]
    print(json.dumps({
        "model": args.model,
        "source_ref": source_ref,
        "unit_id": unit,
        "dimension": int(vector.shape[0]),
        "norm": float((vector * vector).sum() ** 0.5),
        "elapsed_seconds": time.perf_counter() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "isolated_child_process": True,
        "media_derivative_persisted": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
