#!/usr/bin/env python3
"""Build P-tier mini-pilot proposals or inspect the deterministic dry fixture."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

DEFAULT_PLAN = Path("data/rehearsal_plan/mini_pilot_family_mining_v1.json")
DEFAULT_NEW_INDEX = Path("data/restricted/mini_pilot_index_v1")
DEFAULT_NOAA_INDEX = Path("data/restricted/noaa01/scale1a")
ALLOWED_OUTPUT_ROOT = Path("data/restricted/mini_pilot_family_candidates_v1")


def _repo_root_default() -> Path:
    return Path(__file__).resolve().parents[1]


def _print(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _resolve_under(root: Path, value: str | Path) -> Path:
    path = Path(value)
    path = path if path.is_absolute() else root / path
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise ValueError(f"PATH_OUTSIDE_REPOSITORY:{value}") from exc
    if path.is_symlink():
        raise ValueError(f"SYMLINK_PATH_FORBIDDEN:{value}")
    return path


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    payload = (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _validate_output(root: Path, output: Path) -> None:
    allowed = (root / ALLOWED_OUTPUT_ROOT).resolve(strict=False)
    try:
        output.resolve(strict=False).relative_to(allowed)
    except ValueError as exc:
        raise ValueError(
            "OUTPUT_MUST_BE_UNDER_RESTRICTED_CANDIDATE_ROOT:"
            f"{ALLOWED_OUTPUT_ROOT}"
        ) from exc
    forbidden_fragments = (
        "scale1a",
        "mini_pilot_sources_v1",
        "human",
        "annotation",
        "form",
        "controller",
        "evaluator",
    )
    lowered = output.as_posix().casefold()
    if any(fragment in lowered for fragment in forbidden_fragments):
        raise ValueError("OUTPUT_PATH_TOUCHES_PROTECTED_AREA")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(_repo_root_default()))
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--new-index-root", default=str(DEFAULT_NEW_INDEX))
    parser.add_argument("--noaa-index-root", default=str(DEFAULT_NOAA_INDEX))
    parser.add_argument("--output")
    parser.add_argument("--top-k", type=int, default=20)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the deterministic planning fixture without reading indexes.",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Mine P-tier proposals; requires a complete canonical index.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.repo_root).resolve()
    try:
        from av_trace_mini_pilot_families import (
            FrozenClipQueryEncoder,
            build_candidate_registry,
            build_dry_run_fixture_registry,
            load_mining_inputs,
            plan_from_registry,
            validate_candidate_registry,
        )

        if args.top_k < 1:
            raise ValueError("TOP_K_MUST_BE_POSITIVE")
        plan_path = _resolve_under(root, args.plan)
        committed = _load(plan_path)
        validate_candidate_registry(committed)
        generated_fixture = build_dry_run_fixture_registry()
        if committed != generated_fixture:
            raise ValueError(
                "COMMITTED_DRY_RUN_FIXTURE_DRIFT:"
                "regenerate data/rehearsal_plan/mini_pilot_family_mining_v1.json"
            )
        if args.dry_run:
            _print(generated_fixture)
            return 0

        # The normal runner path is intentionally a canonical-input preflight.
        # It therefore fails now while the full index is unfinished.
        inputs = load_mining_inputs(
            root,
            new_index_root=args.new_index_root,
            noaa_index_root=args.noaa_index_root,
        )
        if not args.execute:
            _print(
                {
                    "status": "READY",
                    "mode": "canonical_input_preflight",
                    "canonical_index_complete": True,
                    "candidate_generation_executed": False,
                    "next_action": (
                        "Use --execute --output "
                        "data/restricted/mini_pilot_family_candidates_v1/"
                        "candidate_registry.json"
                    ),
                }
            )
            return 0
        if not args.output:
            raise ValueError("EXECUTE_REQUIRES_EXPLICIT_OUTPUT")
        output = _resolve_under(root, args.output)
        _validate_output(root, output)
        registry = build_candidate_registry(
            inputs,
            plan_from_registry(committed),
            visual_encoder=FrozenClipQueryEncoder(root),
            top_k=args.top_k,
        )
        _write_json(output, registry)
        _print(
            {
                "status": "MACHINE_PROVISIONAL_CANDIDATES_WRITTEN",
                "output": output.relative_to(root).as_posix(),
                "proposed_candidate_count": registry["summary"][
                    "proposed_candidate_count"
                ],
                "unfilled_slot_count": registry["summary"]["unfilled_slot_count"],
                "human_reviewed_count": 0,
                "human_gold_count": 0,
                "final_accepted_family_count": 0,
            }
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - fail-closed JSON CLI boundary.
        _print(
            {
                "status": "NO_GO",
                "candidate_generation_executed": False,
                "human_reviewed_count": 0,
                "human_gold_count": 0,
                "final_accepted_family_count": 0,
                "error": str(exc),
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
