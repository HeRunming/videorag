from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
FULL = ROOT / "mvp/generated/full"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="session")
def corpus_index() -> dict:
    return json.loads((FULL / "corpus_index.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def registered(corpus_index):
    return {
        item["source_id"]: (FULL / item["media_path"], item["media_sha256"])
        for item in corpus_index["sources"]
    }

