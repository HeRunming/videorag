#!/usr/bin/env python3
"""Build or preflight the restricted four-source mini-pilot timeline index."""

from __future__ import annotations

import argparse
import inspect
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

DEFAULT_PLAN = Path("data/rehearsal_plan/mini_pilot_full_timeline_v1.json")
DEFAULT_OUTPUT_ROOT = Path("data/restricted/mini_pilot_index_v1")
DEFAULT_THREADS = 8
_ALLOWED_DEVICES = ("cpu",)


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
    return candidate


def _load_plan(root: Path, plan_path: Path):
    from av_trace_mini_pilot_index.sources import load_source_plan

    return load_source_plan(root, plan_path=plan_path)


def _model_gate_checks(root: Path, plan: Any) -> list[dict[str, Any]]:
    from av_trace_mini_pilot_index.core import build_resource_manifest

    resource = build_resource_manifest(root, plan, [])
    names = {
        "speech": "whisper",
        "ambient": "ast",
        "vision_semantic": "clip",
        "vision_routing": "opencv_haar",
    }
    checks: list[dict[str, Any]] = []
    for layer, spec in plan.model_snapshots.items():
        actual = resource["models"][names[layer]]
        snapshot_key = "haar_snapshot_path" if layer == "vision_routing" else "snapshot_path"
        path = _resolve_under_repo(root, spec[snapshot_key], label="MODEL_PATH")
        weights_key = "haar_sha256" if layer == "vision_routing" else "weights_sha256"
        weight_path = path if layer == "vision_routing" else _resolve_under_repo(
            root, spec["weights_path"], label="MODEL_WEIGHTS_PATH"
        )
        checks.append(
            {
                "layer": layer,
                "model_id": spec["model_id"],
                "revision": spec["revision"],
                "snapshot_path": _relative(root, path),
                "snapshot_present": path.exists() and not path.is_symlink(),
                "weights_path": _relative(root, weight_path),
                "weights_present": weight_path.is_file() and not weight_path.is_symlink(),
                "expected_weights_sha256": spec[weights_key],
                "snapshot_hash": actual["snapshot_hash"],
                "hash_gate_passed": (
                    actual["files"][0]["sha256"] == spec["haar_sha256"]
                    if layer == "vision_routing"
                    else actual["snapshot_hash"] == spec["snapshot_hash"]
                    and any(
                        item["sha256"] == spec["weights_sha256"]
                        for item in actual["files"]
                    )
                ),
                "local_files_only": spec.get("local_files_only", True),
            }
        )
    return checks


def technical_preflight(
    repo_root: str | Path,
    *,
    plan_path: str | Path = DEFAULT_PLAN,
    output_root: str | Path | None = None,
    threads: int = DEFAULT_THREADS,
    device: str = "cpu",
) -> dict[str, Any]:
    """Validate local inputs/config without decoding media or loading models."""
    root = Path(repo_root).resolve()
    if threads < 1:
        raise ValueError("THREAD_COUNT_MUST_BE_POSITIVE")
    if device not in _ALLOWED_DEVICES:
        raise ValueError("DEVICE_NOT_SUPPORTED:only cpu is frozen for index v1")
    plan_candidate = _resolve_under_repo(root, plan_path, label="PLAN_PATH")
    plan = _load_plan(root, plan_candidate)
    output = _resolve_under_repo(
        root, output_root if output_root is not None else plan.output_root, label="OUTPUT_ROOT"
    )
    if output == plan.allowed_restricted_source_root or plan.allowed_restricted_source_root in output.parents:
        raise ValueError("OUTPUT_ROOT_OVERLAPS_SOURCE_ROOT")
    if output.exists() and output.is_symlink():
        raise ValueError("OUTPUT_ROOT_IS_SYMLINK")
    _assert_output_boundary(root, output)
    imports: dict[str, str] = {}
    for module in ("av", "cv2", "numpy", "torch", "transformers"):
        try:
            imported = __import__(module)
            imports[module] = str(getattr(imported, "__version__", "present"))
        except Exception as exc:
            raise RuntimeError(f"DEPENDENCY_IMPORT_FAILED:{module}:{exc}") from exc
    model_gates = _model_gate_checks(root, plan)
    missing = [
        item["layer"]
        for item in model_gates
        if not item["snapshot_present"]
        or not item["weights_present"]
        or not item["hash_gate_passed"]
    ]
    if missing:
        raise RuntimeError("MODEL_GATE_MISSING:" + ",".join(missing))
    forbidden = set(plan.raw["scope"]["forbidden_downstream_stages"])
    required_forbidden = {"candidate-family generation", "family migration", "evaluation"}
    if not required_forbidden <= forbidden:
        raise RuntimeError("DOWNSTREAM_STAGE_BOUNDARY_MISSING")
    return {
        "status": "READY",
        "mode": "offline_technical_preflight",
        "network_access": "disabled",
        "models_loaded": False,
        "media_decoded": False,
        "artifacts_written": False,
        "repo_root": str(root),
        "plan": _relative(root, plan.plan_path),
        "output_root": _relative(root, output),
        "source_count": len(plan.sources),
        "source_ids": [source.source_id for source in plan.sources],
        "expected_counts": dict(plan.totals),
        "expected_checkpoint_count": plan.raw["checkpointing"]["expected_checkpoint_count"],
        "threads": threads,
        "device": device,
        "dependencies": imports,
        "model_gates": model_gates,
        "downstream_stages_disabled": sorted(forbidden),
    }


def _config_for(plan: Any, output_root: Path, threads: int):
    from av_trace_mini_pilot_index.core import IndexConfig

    snapshots = plan.model_snapshots
    return IndexConfig(
        source_manifest_paths=tuple(
            source.source_manifest_path.relative_to(plan.repo_root)
            for source in plan.sources
        ),
        output_dir=output_root.relative_to(plan.repo_root),
        clip_model_path=snapshots["vision_semantic"]["snapshot_path"],
        whisper_model_path=snapshots["speech"]["snapshot_path"],
        ast_model_path=snapshots["ambient"]["snapshot_path"],
        haar_model_path=snapshots["vision_routing"]["haar_snapshot_path"],
        expected_source_count=len(plan.sources),
        threads=threads,
        derived_artifacts_hard_fail_cap_mib=plan.raw["storage_caps"][
            "derived_artifacts_hard_fail_cap_mib"
        ],
    )


def _invoke_build(
    root: Path,
    *,
    plan: Any,
    output_root: Path,
    resume: bool,
    threads: int,
    device: str,
    smoke_seconds: float | None,
) -> dict[str, Any]:
    from av_trace_mini_pilot_index.core import build_mini_pilot_index

    kwargs: dict[str, Any] = {"resume": resume}
    signature = inspect.signature(build_mini_pilot_index)
    if "threads" in signature.parameters:
        kwargs["threads"] = threads
    if "device" in signature.parameters:
        kwargs["device"] = device
    if "smoke_seconds" in signature.parameters:
        kwargs["smoke_seconds"] = smoke_seconds
    elif smoke_seconds is not None:
        raise RuntimeError(
            "SMOKE_NOT_SUPPORTED_BY_CORE:refusing to substitute a full build"
        )
    config = _config_for(plan, output_root, threads)
    if smoke_seconds is not None and "media_backend" in signature.parameters:
        kwargs["media_backend"] = _BoundedPyAVMediaBackend(smoke_seconds)
    return build_mini_pilot_index(root, config, **kwargs)


class _BoundedPyAVMediaBackend:
    """PyAV backend that never decodes audio beyond the smoke duration."""

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
                (item for item in container.streams if item.type == "audio"), None
            )
            if stream is None:
                raise RuntimeError(f"AUDIO_STREAM_MISSING:{path.name}")
            resampler = av.audio.resampler.AudioResampler(
                format="fltp", layout="mono", rate=target_rate
            )
            for frame in container.decode(stream):
                for converted in resampler.resample(frame):
                    values = converted.to_ndarray().reshape(-1).astype(np.float32)
                    remaining = limit - count
                    if remaining <= 0:
                        break
                    parts.append(values[:remaining])
                    count += min(len(values), remaining)
                if count >= limit:
                    break
        if not parts:
            raise RuntimeError(f"AUDIO_DECODE_EMPTY:{path.name}")
        return np.concatenate(parts)


def _assert_output_boundary(root: Path, output_root: Path) -> None:
    media_suffixes = {
        ".aac", ".avi", ".flac", ".gif", ".jpeg", ".jpg", ".m4a", ".m4v",
        ".mkv", ".mov", ".mp3", ".mp4", ".ogg", ".png", ".wav", ".webm",
    }
    forbidden_terms = (
        "famil", "negative", "intervention", "trajectory", "evaluation",
        "metric", "controller", "agent_run",
    )
    bad_media = []
    bad_downstream = []
    if output_root.exists():
        for path in output_root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if path.suffix.casefold() in media_suffixes:
                bad_media.append(relative)
            if any(term in path.name.casefold() for term in forbidden_terms):
                bad_downstream.append(relative)
    if bad_media:
        raise RuntimeError("PERSISTED_MEDIA_DERIVATIVE:" + ",".join(sorted(bad_media)))
    if bad_downstream:
        raise RuntimeError("DOWNSTREAM_ARTIFACT_PRESENT:" + ",".join(sorted(bad_downstream)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(_repo_root_default()))
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS)
    parser.add_argument("--device", choices=_ALLOWED_DEVICES, default="cpu")
    parser.add_argument("--smoke-seconds", type=float)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the index build. Without this flag only offline technical preflight runs.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.repo_root).resolve()
    try:
        preflight = technical_preflight(
            root,
            plan_path=args.plan,
            output_root=args.output_root,
            threads=args.threads,
            device=args.device,
        )
        if args.smoke_seconds is not None and args.smoke_seconds <= 0:
            raise ValueError("SMOKE_SECONDS_MUST_BE_POSITIVE")
        if not args.execute:
            _json_print(
                {
                    **preflight,
                    "next_action": "add --execute for a bounded smoke or full build",
                    "full_build_command": (
                        "python scripts/build_mini_pilot_full_timeline.py "
                        "--execute --resume --threads 8 --device cpu"
                    ),
                }
            )
            return 0
        plan = _load_plan(root, _resolve_under_repo(root, args.plan, label="PLAN_PATH"))
        default_output = plan.output_root
        if args.smoke_seconds is not None and args.output_root is None:
            default_output = Path(str(plan.output_root) + "_smoke")
        output = _resolve_under_repo(
            root, args.output_root if args.output_root is not None else default_output,
            label="OUTPUT_ROOT",
        )
        result = _invoke_build(
            root,
            plan=plan,
            output_root=output,
            resume=args.resume,
            threads=args.threads,
            device=args.device,
            smoke_seconds=args.smoke_seconds,
        )
        _assert_output_boundary(root, output)
        observation = result.get("observation_manifest", {})
        _json_print(
            {
                "status": "complete",
                "mode": "bounded_smoke" if args.smoke_seconds is not None else "full_build",
                "output_root": _relative(root, output),
                "source_count": observation.get("source_count"),
                "checkpoint_count": len(observation.get("checkpoints", [])),
                "counts": observation.get("counts", {}),
                "downstream_stages_triggered": False,
                "no_persisted_media_derivatives": True,
            }
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI converts fail-closed errors to JSON.
        _json_print({"status": "NO_GO", "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
