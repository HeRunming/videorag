"""Small deterministic helpers; no media or network access lives here."""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any

MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_JSON_DEPTH = 256
MAX_JSON_NODES = 1_000_000


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> None:
    raise ValueError(f"Non-finite JSON number is not permitted: {token}")


def load_json(path: str | Path) -> Any:
    source = Path(path)
    size = source.stat().st_size
    if size > MAX_JSON_BYTES:
        raise ValueError(f"JSON input exceeds the {MAX_JSON_BYTES}-byte safety limit: {source}")
    with source.open("r", encoding="utf-8") as handle:
        return json.load(
            handle,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def safe_sha256_json(value: Any) -> str | None:
    try:
        return sha256_json(value)
    except (TypeError, ValueError, RecursionError):
        return None


def json_value_error(value: Any) -> str | None:
    """Return a deterministic reason when a Python value is unsafe/non-JSON."""
    stack: list[tuple[Any, int, bool]] = [(value, 0, False)]
    active: set[int] = set()
    nodes = 0
    while stack:
        current, depth, leaving = stack.pop()
        if leaving:
            active.remove(id(current))
            continue
        nodes += 1
        if nodes > MAX_JSON_NODES:
            return f"JSON value exceeds the {MAX_JSON_NODES}-node safety limit"
        if depth > MAX_JSON_DEPTH:
            return f"JSON value exceeds the {MAX_JSON_DEPTH}-level nesting safety limit"
        if current is None or isinstance(current, (str, bool, int)):
            continue
        if isinstance(current, float):
            if not math.isfinite(current):
                return "JSON value contains a non-finite number"
            continue
        if isinstance(current, (dict, list)):
            identity = id(current)
            if identity in active:
                return "JSON value contains a cyclic container"
            active.add(identity)
            stack.append((current, depth, True))
            if isinstance(current, dict):
                for key, child in current.items():
                    if not isinstance(key, str):
                        return "JSON object keys must be strings"
                    stack.append((child, depth + 1, False))
            else:
                stack.extend((child, depth + 1, False) for child in current)
            continue
        return f"JSON value contains unsupported type {type(current).__name__}"
    return None


def response_content_hash(response: dict[str, Any]) -> str:
    """Hash a response envelope without its self-referential response_hash field."""
    content = dict(response)
    content.pop("response_hash", None)
    return sha256_json(content)


def trajectory_content_hash(trajectory: dict[str, Any]) -> str:
    """Hash a trajectory without its self-referential replay.trajectory_hash field."""
    content = deepcopy(trajectory)
    replay = content.get("replay")
    if isinstance(replay, dict):
        replay.pop("trajectory_hash", None)
    return sha256_json(content)


def is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
