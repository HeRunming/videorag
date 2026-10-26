from __future__ import annotations

from pathlib import Path

import pytest

from av_trace_mvp.index import load_generated
from av_trace_media_pipeline.indexing import build_media_index


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def corpus():
    return load_generated(ROOT / "mvp/generated/full")


@pytest.fixture(scope="session")
def media_index(corpus):
    return build_media_index(
        generated_root=ROOT / "mvp/generated/full",
        families=corpus.families,
    )
