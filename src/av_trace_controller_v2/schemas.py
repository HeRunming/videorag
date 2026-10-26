"""Dynamic grammar schemas for controller-v2 constrained decoding."""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

from .parser import HOPS, MODALITIES


def _load_schema(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"schema is not an object: {path}")
    return value


def _canonical_subsets(values: list[str] | tuple[str, ...]) -> list[list[str]]:
    return [
        list(combo)
        for length in range(len(values) + 1)
        for combo in itertools.combinations(values, length)
    ]


def _strip_annotations(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_annotations(item)
            for key, item in value.items()
            if not key.startswith("x-av-trace-")
            and key not in {"$schema", "$id", "title", "description"}
        }
    if isinstance(value, list):
        return [_strip_annotations(item) for item in value]
    return value


def action_grammar_schema(
    base_schema_path: Path,
    *,
    allowed_action_indices: list[int],
) -> dict[str, Any]:
    schema = _strip_annotations(copy.deepcopy(_load_schema(base_schema_path)))
    schema["properties"]["action_index"]["enum"] = list(allowed_action_indices)
    return schema


def state_grammar_schema(
    base_schema_path: Path,
    *,
    allowed_claim_handles: list[str],
) -> dict[str, Any]:
    schema = _strip_annotations(copy.deepcopy(_load_schema(base_schema_path)))
    properties = schema["properties"]
    properties["covered_claim_handles"] = {
        "type": "array",
        "enum": _canonical_subsets(allowed_claim_handles),
    }
    properties["missing_modalities"] = {
        "type": "array",
        "enum": _canonical_subsets(MODALITIES),
    }
    properties["missing_hops"] = {
        "type": "array",
        "enum": _canonical_subsets(HOPS),
    }
    return schema


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()
