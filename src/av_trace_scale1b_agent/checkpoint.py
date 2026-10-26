"""Per-trajectory atomic checkpoints and semantic replay."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def semantic_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def write_checkpoint(
    path: Path,
    *,
    config_hash: str,
    record: Mapping[str, Any],
) -> dict[str, Any]:
    document = {
        "schema_version": "av-trace.scale1b.ga-checkpoint/1.0",
        "config_hash": config_hash,
        "record": dict(record),
        "record_hash": semantic_hash(record),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical_bytes(document) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return document


def read_checkpoint(path: Path, *, config_hash: str) -> dict[str, Any] | None:
    if not path.is_file() or path.is_symlink():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    if (
        document.get("config_hash") != config_hash
        or document.get("record_hash") != semantic_hash(document.get("record"))
    ):
        return None
    return document
