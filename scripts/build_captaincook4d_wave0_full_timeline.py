#!/usr/bin/env python3
"""Preflight or build the CaptainCook4D Wave-0 full-timeline index."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from av_trace_captaincook4d_wave0_index.core import (
    CaptainCook4DWave0IndexError,
    build_captaincook4d_wave0_index,
)
from av_trace_captaincook4d_wave0_index.sources import (
    PLAN_RELATIVE_PATH,
    CaptainCook4DWave0SourceError,
    load_plan_definition,
    load_source_plan,
)
from av_trace_mini_pilot_index.core import build_resource_manifest

DEFAULT_THREADS = 8
ALLOWED_DEVICES = ("cpu",)


def _repo_root_default() -> Path:
    return Path(__file__).resolve().parents[1]


def _json_print(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _resolve_under_repo(root: Path, value: str | Path, *, label: str) -> Path:
    candidate = Path(value)
    candidate = candidate if candidate.is_absolute() else root / candidate
    try:
        candidate.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label}_OUTSIDE_REPOSITORY:{value}") from exc
    if ".staging" in candidate.parts:
        raise ValueError(f"{label}_STAGING_FORBIDDEN:{value}")
    return candidate


def config_from_plan_definition(
    snapshots: Mapping[str, Any],
    *,
    output_root: Path,
    threads: int,
):
    from av_trace_mini_pilot_index.core import IndexConfig

    return IndexConfig(
        output_dir=output_root,
        clip_model_path=snapshots["vision_semantic"]["snapshot_path"],
        whisper_model_path=snapshots["speech"]["snapshot_path"],
        ast_model_path=snapshots["ambient"]["snapshot_path"],
        haar_model_path=snapshots["vision_routing"]["haar_snapshot_path"],
        expected_source_count=3,
        threads=threads,
    )


def _static_preflight(
    root: Path,
    *,
    plan_path: str | Path,
    output_root: str | Path | None,
    threads: int,
    device: str,
) -> tuple[dict[str, Any], Any]:
    if threads < 1:
        raise ValueError("THREAD_COUNT_MUST_BE_POSITIVE")
    if device not in ALLOWED_DEVICES:
        raise ValueError("DEVICE_NOT_SUPPORTED:only cpu is frozen for index v1")
    plan_file, raw, source_root, acquisition_path, default_output = (
        load_plan_definition(root, plan_path=plan_path)
    )
    output = _resolve_under_repo(
        root,
        output_root if output_root is not None else default_output,
        label="OUTPUT_ROOT",
    )
    if source_root == output or source_root in output.parents:
        raise ValueError("OUTPUT_ROOT_OVERLAPS_SOURCE_ROOT")
    imports: dict[str, str] = {}
    for module in ("av", "cv2", "numpy", "torch", "transformers"):
        try:
            imported = __import__(module)
            imports[module] = str(getattr(imported, "__version__", "present"))
        except Exception as exc:
            raise RuntimeError(
                f"DEPENDENCY_IMPORT_FAILED:{module}:{exc}"
            ) from exc
    plan = load_source_plan(root, plan_path=plan_file)
    snapshots = raw["model_snapshots"]
    config = config_from_plan_definition(
        snapshots,
        output_root=output,
        threads=threads,
    )
    resource = build_resource_manifest(root, config, [])
    model_gates = {
        name: {
            "path": item["path"],
            "snapshot_hash": item["snapshot_hash"],
            "frozen": item["frozen"],
            "local_files_only": item["local_files_only"],
        }
        for name, item in resource["models"].items()
    }
    result = {
        "decision": "CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_READY",
        "status": "READY",
        "mode": "offline_dry_preflight",
        "network_access": "disabled",
        "models_loaded": False,
        "media_decoded": False,
        "artifacts_written": False,
        "staging_tree_read": False,
        "repo_root": str(root),
        "plan": _relative(root, plan_file),
        "output_root": _relative(root, output),
        "source_ids": [item["source_id"] for item in raw["sources"]],
        "expected_counts": raw["totals"],
        "expected_checkpoint_count": raw["checkpointing"][
            "expected_checkpoint_count"
        ],
        "threads": threads,
        "device": device,
        "dependencies": imports,
        "model_gates": model_gates,
        "acquisition_gate": {
            "required_decision": raw["scope"][
                "acquisition_decision_required"
            ],
            "manifest_path": _relative(root, acquisition_path),
            "manifest_present": True,
            "manifest_sha256": plan.acquisition_manifest_sha256,
            "exact_sha256_required": True,
            "source_manifest_hash_required": True,
            "passed": True,
            "source_sha256": {
                source.source_id: source.media_sha256
                for source in plan.sources
            },
        },
        "downstream_stages_disabled": sorted(
            raw["scope"]["forbidden_downstream_stages"]
        ),
    }
    return result, plan


class _BoundedPyAVMediaBackend:
    """Decode only the leading smoke interval from each complete source."""

    def __init__(self, smoke_seconds: float) -> None:
        from av_trace_mini_pilot_index.core import PyAVMediaBackend

        self._base = PyAVMediaBackend()
        self._smoke_seconds = smoke_seconds

    def iter_sampled_frames(self, path: Path, cells: Sequence[Mapping[str, Any]]):
        yield from self._base.iter_sampled_frames(path, cells)

    def decode_audio(self, path: Path, target_rate: int = 16_000):
        import av
        import numpy as np

        limit = max(1, round(self._smoke_seconds * target_rate))
        parts = []
        count = 0
        with av.open(str(path), mode="r") as container:
            stream = next(
                (item for item in container.streams if item.type == "audio"),
                None,
            )
            if stream is None:
                raise CaptainCook4DWave0IndexError(
                    f"AUDIO_STREAM_MISSING:{path.name}"
                )
            resampler = av.audio.resampler.AudioResampler(
                format="fltp", layout="mono", rate=target_rate
            )
            for frame in container.decode(stream):
                for converted in resampler.resample(frame):
                    values = (
                        converted.to_ndarray().reshape(-1).astype(np.float32)
                    )
                    remaining = limit - count
                    if remaining <= 0:
                        break
                    parts.append(values[:remaining])
                    count += min(len(values), remaining)
                if count >= limit:
                    break
        if not parts:
            raise CaptainCook4DWave0IndexError(
                f"AUDIO_DECODE_EMPTY:{path.name}"
            )
        return np.concatenate(parts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(_repo_root_default()))
    parser.add_argument("--plan", default=str(PLAN_RELATIVE_PATH))
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--mode", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--smoke-seconds", type=float, default=32.0)
    parser.add_argument(
        "--resume", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS)
    parser.add_argument("--device", choices=ALLOWED_DEVICES, default="cpu")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute smoke or full indexing; default is a no-decode preflight.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.repo_root).resolve()
    try:
        preflight, plan = _static_preflight(
            root,
            plan_path=args.plan,
            output_root=args.output_root,
            threads=args.threads,
            device=args.device,
        )
        if not args.execute:
            _json_print(preflight)
            return 0
        smoke_seconds = None
        media_backend = None
        if args.mode == "smoke":
            if args.smoke_seconds <= 0:
                raise ValueError("SMOKE_SECONDS_MUST_BE_POSITIVE")
            smoke_seconds = args.smoke_seconds
            media_backend = _BoundedPyAVMediaBackend(smoke_seconds)
        output = (
            args.output_root
            if args.output_root is not None
            else (
                Path(str(plan.output_root) + "_smoke")
                if args.mode == "smoke"
                else plan.output_root
            )
        )
        result = build_captaincook4d_wave0_index(
            root,
            plan=plan,
            output_root=output,
            resume=args.resume,
            threads=args.threads,
            device=args.device,
            smoke_seconds=smoke_seconds,
            media_backend=media_backend,
        )
        _json_print(
            {
                "decision": "CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_READY",
                "status": "COMPLETE",
                "mode": args.mode,
                "output_root": result["build_manifest"]["output_dir"],
                "checkpoint_count": result["build_manifest"][
                    "checkpoint_count"
                ],
                "build_manifest_hash": result["build_manifest"][
                    "build_manifest_hash"
                ],
            }
        )
        return 0
    except (
        CaptainCook4DWave0SourceError,
        CaptainCook4DWave0IndexError,
        RuntimeError,
        ValueError,
    ) as exc:
        _json_print(
            {
                "decision": "CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_NO_GO",
                "status": "FAILED_CLOSED",
                "error": str(exc),
            }
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
