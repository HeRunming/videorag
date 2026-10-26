from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from av_trace_scale1b_retrieval.core import (
    FORBIDDEN_SEARCH_KEYS,
    Scale1BWaveRError,
    _assert_safe_index,
    _metrics,
    _metrics_from_route_ranks,
    _normalize,
    _pool,
    _rank_vectors,
    _rrf,
    _rrf_record_details,
    _serialized_ranking,
    _temporal_bind_visual,
    verify_gates,
    verify_wave_r,
)


def test_normalize_and_pool() -> None:
    values = _normalize(np.array([[3.0, 4.0], [0.0, 2.0]], dtype=np.float32))
    assert np.allclose(np.linalg.norm(values, axis=1), 1)
    pooled = _pool(["a", "b"], {"a": values[0], "b": values[1]})
    assert np.isclose(np.linalg.norm(pooled), 1)


def test_zero_vector_fails_closed() -> None:
    with pytest.raises(Scale1BWaveRError):
        _normalize(np.zeros((1, 3), dtype=np.float32))


def test_ranking_uses_actual_vector_values() -> None:
    docs = [
        {
            "segment_id": "a", "source_ref": "s", "scale": "fine",
            "start_us": 0, "end_us": 1, "searchable": True, "dimension": 2,
            "vector_f16_hex": np.array([1, 0], dtype="<f2").tobytes().hex(),
        },
        {
            "segment_id": "b", "source_ref": "s", "scale": "fine",
            "start_us": 1, "end_us": 2, "searchable": True, "dimension": 2,
            "vector_f16_hex": np.array([0, 1], dtype="<f2").tobytes().hex(),
        },
    ]
    assert _rank_vectors(docs, np.array([0, 1], dtype=np.float32), source_ref=None)[0][
        "segment_id"
    ] == "b"


def test_rrf_fixed_math() -> None:
    result = _rrf(
        {"vision": ["a", "b"], "audio": ["b", "a"]},
        rrf_k=60, weights={"vision": 1, "audio": 2},
    )
    assert result[0] == "b"


def test_metrics_honor_alternative_support_ids() -> None:
    result = _metrics(["x", "alt", "z"], {"vision": {"gold", "alt"}})
    assert result["first_accepted_evidence_rank"] == 2
    assert result["Recall@1"] == 0
    assert result["Recall@5"] == 1
    assert result["All-Evidence@5"] == 1
    assert result["modality_necessity"] is None


def test_fused_support_requires_modality_contribution() -> None:
    result = _metrics(
        ["shared"],
        {"vision": {"shared"}, "ambient": {"shared"}},
        contributions={"shared": {"vision"}},
    )
    assert result["Recall@5"] == 0.5
    assert result["All-Evidence@5"] == 0


def test_frozen_route_rank_metrics() -> None:
    result = _metrics_from_route_ranks({"vision": 20, "ambient": 20})
    assert result["Recall@10"] == 0
    assert result["Recall@20"] == 1
    assert result["All-Evidence@20"] == 1


def test_rrf_temporal_dedup_and_modality_provenance() -> None:
    visual = {
        "segment_id": "fine-a", "source_ref": "s", "start_us": 0,
        "end_us": 8_000_000,
    }
    audio = {
        "segment_id": "fine-b", "source_ref": "s", "start_us": 0,
        "end_us": 8_000_000,
    }
    ranking, contributions = _rrf_record_details(
        {"vision": [visual], "ambient": [audio]},
        rrf_k=60, weights={"vision": 1, "ambient": 1},
    )
    assert len(ranking) == 1
    assert contributions[ranking[0]] == {"vision", "ambient"}


def test_temporal_binding_applies_without_evaluator_labels() -> None:
    direct = [{
        "segment_id": "visual-direct", "source_ref": "s",
        "start_us": 40_000_000, "end_us": 48_000_000, "scale": "fine",
    }]
    anchor = [{
        "segment_id": "audio-anchor", "source_ref": "s",
        "start_us": 8_000_000, "end_us": 16_000_000, "scale": "fine",
    }]
    visual_docs = [
        *direct,
        {
            "segment_id": "visual-bound", "source_ref": "s",
            "start_us": 8_000_000, "end_us": 16_000_000, "scale": "fine",
        },
    ]
    result = _temporal_bind_visual(
        direct, {"ambient": anchor}, visual_docs, source_ref="s"
    )
    assert [row["segment_id"] for row in result] == [
        "visual-bound", "visual-direct",
    ]
    assert result[0]["_binding_modality"] == "ambient"


def test_serialized_rankings_use_opaque_ids() -> None:
    result = _serialized_ranking("V-SIGLIP2", ["seg.private.1"], None)
    assert result["ranking_top20"][0].startswith("wr.")
    assert "seg.private.1" not in result["ranking_top20"]
    assert result["evaluator_private_ranking_segment_ids"] == ["seg.private.1"]


@pytest.mark.parametrize("key", sorted(FORBIDDEN_SEARCH_KEYS))
def test_searchable_feature_leakage_fails(key: str) -> None:
    with pytest.raises(Scale1BWaveRError):
        _assert_safe_index({"modalities": {"x": {"documents": [{key: "bad"}]}}})


def test_gate_missing_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(Scale1BWaveRError, match="PREREQUISITE_MISSING"):
        verify_gates(tmp_path)


def test_no_evaluation_tuning_marker_in_owned_source() -> None:
    text = Path("src/av_trace_scale1b_retrieval/core.py").read_text()
    assert '"evaluation_family_tuning": False' in text
    assert "logistic fusion" not in text.lower()


def test_scripts_compile() -> None:
    for path in (
        Path("scripts/build_scale1b_wave_r.py"),
        Path("scripts/run_scale1b_wave_r.py"),
        Path("scripts/verify_scale1b_wave_r.py"),
    ):
        compile(path.read_text(), str(path), "exec")


def test_current_wave_r_artifacts_if_present() -> None:
    root = Path(".").resolve()
    if not (root / "data/restricted/scale1b/wave_r/build_manifest.json").exists():
        pytest.skip("full Wave-R build is not present")
    result = verify_wave_r(root, require_results=True, spot_recompute=False)
    assert result == {"passed": True, "failures": [], "spot_recompute": None}


def test_current_comparison_matrix_if_present() -> None:
    path = Path("data/restricted/scale1b/wave_r/evaluation_manifest.json")
    if not path.exists():
        pytest.skip("full Wave-R evaluation is not present")
    rows = json.loads(path.read_text())["metric_rows"]
    expected = {
        "V-CLIP": 8, "V-SIGLIP2": 8, "A-AST": 2, "A-CLAP": 2,
        "S-BM25": 4, "F-CTRL": 10, "F-V": 10, "F-A": 10, "F-VA": 10,
    }
    observed = {
        key: sum(row["ranker"] == key for row in rows) for key in expected
    }
    assert observed == expected
    assert all(row["modality_necessity"] is None for row in rows)
    assert not any(row["family_disposition"] == "excluded" for row in rows)
