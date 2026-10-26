"""Canonical JSON and repository-path helpers for validator artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from av_trace.util import load_json, sha256_json


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GENERATED_ROOT = PACKAGE_ROOT / "mvp" / "generated" / "full"
DEFAULT_VALIDATOR_ROOT = PACKAGE_ROOT / "mvp" / "validator" / "generated"
SCHEMA_ROOT = PACKAGE_ROOT / "mvp" / "schemas"


def write_json(path: str | Path, value: Any) -> Path:
    """Write deterministic, human-readable JSON and return its path."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def relative_path(path: str | Path, root: str | Path) -> str:
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()


def document_hash(path: str | Path) -> str:
    return sha256_json(load_json(path))

