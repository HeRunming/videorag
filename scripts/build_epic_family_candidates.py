#!/usr/bin/env python3
"""Preflight or emit EPIC machine P-tier event-centric candidate leads."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

DEFAULT_PLAN = Path("data/rehearsal_plan/epic_family_mining_v1.json")
DEFAULT_INDEX = Path("data/restricted/epic_wave1_index_v1")
NORMAL_OUTPUT_ROOT = Path("data/restricted/epic_family_candidates_v1")
DEVELOPMENT_OUTPUT_ROOT = Path(
    "data/restricted/epic_family_candidates_v1_dev"
)


def _repo_root_default() -> Path:
    return Path(__file__).resolve().parents[1]


def _print(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _resolve_under(root: Path, value: str | Path) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        path = raw
    else:
        path = root / raw
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise ValueError(f"PATH_OUTSIDE_REPOSITORY:{value}") from exc
    if path.is_symlink() or ".staging" in path.parts:
        raise ValueError(f"UNSAFE_PATH:{value}")
    return path


def _validate_output(root: Path, output: Path, *, mode: str) -> None:
    allowed_relative = (
        DEVELOPMENT_OUTPUT_ROOT
        if mode == "development_only"
        else NORMAL_OUTPUT_ROOT
    )
    allowed = (root / allowed_relative).resolve(strict=False)
    try:
        output.resolve(strict=False).relative_to(allowed)
    except ValueError as exc:
        raise ValueError(
            "OUTPUT_MUST_BE_UNDER_MODE_SPECIFIC_RESTRICTED_EPIC_CANDIDATE_ROOT:"
            f"{allowed_relative}"
        ) from exc
    lowered = output.as_posix().casefold()
    if any(
        fragment in lowered
        for fragment in (
            "epic_wave1_index_v1",
            "epic_wave1_sources_v1",
            "annotation",
            "vault",
            "checkpoint",
        )
    ):
        raise ValueError("OUTPUT_PATH_TOUCHES_PROTECTED_EPIC_AREA")


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(_repo_root_default()))
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--index-root", default=str(DEFAULT_INDEX))
    parser.add_argument("--prescreen-plan")
    parser.add_argument("--prescreen-form")
    parser.add_argument("--prescreen-report")
    parser.add_argument("--output")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Emit normal candidate-input proposals; requires a complete "
            "canonical index and human-complete READY prescreen."
        ),
    )
    mode.add_argument(
        "--development-only",
        action="store_true",
        help=(
            "Emit development-only proposals after the canonical index is "
            "complete; output is structurally barred from Gate A."
        ),
    )
    mode.add_argument(
        "--show-plan",
        action="store_true",
        help="Print the deterministic implementation plan without reading indexes.",
    )
    return parser


def _prescreen_args(args: argparse.Namespace) -> tuple[str, str, str] | None:
    values = (
        args.prescreen_plan,
        args.prescreen_form,
        args.prescreen_report,
    )
    if not any(values):
        return None
    if not all(values):
        raise ValueError("ALL_THREE_PRESCREEN_PATHS_REQUIRED")
    return values  # type: ignore[return-value]


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.repo_root).resolve()
    try:
        from av_trace_epic_family_mining import (
            FrozenClipQueryEncoder,
            build_candidate_registry,
            build_rehearsal_plan,
            load_canonical_epic_index,
            load_human_complete_prescreen,
            mine_initial_machine_leads,
            validate_candidate_registry,
        )

        plan_path = _resolve_under(root, args.plan)
        committed = _load(plan_path)
        generated = build_rehearsal_plan()
        if committed != generated:
            raise ValueError(
                "COMMITTED_EPIC_MINING_PLAN_DRIFT:"
                "regenerate data/rehearsal_plan/epic_family_mining_v1.json"
            )
        if args.show_plan:
            _print(generated)
            return 0

        inputs = load_canonical_epic_index(root, index_root=args.index_root)
        prescreen_paths = _prescreen_args(args)
        prescreen = None
        if prescreen_paths is not None:
            prescreen = load_human_complete_prescreen(
                root,
                plan_path=prescreen_paths[0],
                form_path=prescreen_paths[1],
                report_path=prescreen_paths[2],
                source_groups=inputs.source_groups,
            )

        if not args.execute and not args.development_only:
            if prescreen is None:
                raise ValueError("HUMAN_COMPLETE_PRESCREEN_REQUIRED")
            _print(
                {
                    "status": "EPIC_FAMILY_MINING_READY_FOR_EXPLICIT_EXECUTION",
                    "canonical_index_complete": True,
                    "human_prescreen_complete": True,
                    "candidate_generation_executed": False,
                    "active_interventions": False,
                    "next_action": (
                        "Use --execute with all three prescreen paths and an "
                        "explicit restricted output path."
                    ),
                }
            )
            return 0

        if not args.output:
            raise ValueError("MINING_MODE_REQUIRES_EXPLICIT_OUTPUT")
        mode = (
            "development_only"
            if args.development_only
            else "gate_a_candidate_input"
        )
        output = _resolve_under(root, args.output)
        _validate_output(root, output, mode=mode)
        if args.execute and prescreen is None:
            raise ValueError("HUMAN_COMPLETE_PRESCREEN_REQUIRED")

        # Initial mining is intentionally completed from the canonical index
        # before human semantic prescreen information is joined.
        machine_leads = mine_initial_machine_leads(
            inputs,
            visual_encoder=FrozenClipQueryEncoder(root),
        )
        registry = build_candidate_registry(
            inputs,
            machine_leads,
            mode=mode,
            prescreen=prescreen,
            created_date="2026-09-28",
        )
        validate_candidate_registry(registry)
        _write_json(output, registry)
        _print(
            {
                "status": "EPIC_MACHINE_P_TIER_PROPOSALS_WRITTEN",
                "mode": mode,
                "output": output.relative_to(root).as_posix(),
                "source_count": 2,
                "candidate_lead_count": 4,
                "exactly_two_leads_per_source": True,
                "eligible_to_enter_gate_a": registry["gate_a_boundary"][
                    "eligible_to_enter_gate_a"
                ],
                "gate_a_decision_asserted": False,
                "h_tier_count": 0,
                "active_intervention_count": 0,
            }
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - fail-closed CLI boundary.
        _print(
            {
                "status": "EPIC_FAMILY_MINING_REPAIR",
                "candidate_generation_executed": False,
                "candidate_artifact_written": False,
                "h_tier_count": 0,
                "active_intervention_count": 0,
                "error": str(exc),
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
