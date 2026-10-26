#!/usr/bin/env python3
"""Verify a CaptainCook4D provisional candidate registry without mining."""

from __future__ import annotations

import argparse
import json
import stat
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

NORMAL_ROOT = PurePosixPath(
    "data/restricted/captaincook4d_family_candidates_v1"
)
DEVELOPMENT_ROOT = PurePosixPath(
    "data/restricted/captaincook4d_family_candidates_v1_dev"
)
ALLOWED_ROOTS = (NORMAL_ROOT, DEVELOPMENT_ROOT)


def _repo_root_default() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve(root: Path, value: str) -> tuple[Path, PurePosixPath]:
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or ".staging" in pure.parts:
        raise ValueError(f"UNSAFE_PATH:{value}")
    allowed_root = next(
        (
            candidate
            for candidate in ALLOWED_ROOTS
            if pure != candidate and candidate in pure.parents
        ),
        None,
    )
    if allowed_root is None:
        raise ValueError(
            "REGISTRY_MUST_BE_UNDER_RESTRICTED_CAPTAINCOOK4D_CANDIDATE_ROOT"
        )
    path = root.joinpath(*pure.parts)
    path.resolve(strict=False).relative_to(root)
    if path.is_symlink():
        raise ValueError("REGISTRY_SYMLINK_FORBIDDEN")
    return path, allowed_root


def verify_registry(repo_root: str | Path, registry_path: str) -> dict:
    root = Path(repo_root).resolve()
    path, allowed_root = _resolve(root, registry_path)
    if not path.is_file():
        return {
            "verified": False,
            "decision": "CAPTAINCOOK4D_FAMILY_MINING_REPAIR",
            "failures": ["REGISTRY_MISSING"],
        }
    failures = []
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        failures.append("REGISTRY_MODE_INVALID")
    if stat.S_IMODE(path.parent.stat().st_mode) != 0o700:
        failures.append("REGISTRY_DIRECTORY_MODE_INVALID")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        from av_trace_captaincook4d_family_mining import (
            validate_candidate_registry,
        )

        validate_candidate_registry(payload)
        expected_root = (
            DEVELOPMENT_ROOT
            if payload.get("mode") == "development_only"
            else NORMAL_ROOT
        )
        if allowed_root != expected_root:
            failures.append(
                "REGISTRY_MODE_OUTPUT_ROOT_MISMATCH:"
                f"{payload.get('mode')}:{allowed_root}"
            )
    except Exception as exc:  # noqa: BLE001
        failures.append(str(exc))
    return {
        "verified": not failures,
        "decision": (
            "CAPTAINCOOK4D_FAMILY_MINING_IMPLEMENTATION_READY"
            if not failures
            else "CAPTAINCOOK4D_FAMILY_MINING_REPAIR"
        ),
        "registry_path": path.relative_to(root).as_posix(),
        "failures": failures,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(_repo_root_default()))
    parser.add_argument("--registry", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = verify_registry(args.repo_root, args.registry)
    except Exception as exc:  # noqa: BLE001
        result = {
            "verified": False,
            "decision": "CAPTAINCOOK4D_FAMILY_MINING_REPAIR",
            "failures": [str(exc)],
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
