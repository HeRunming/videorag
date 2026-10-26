from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from tools import ves_long_candidate_recon as recon
from tools import ves_wave2_plan as wave2


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / wave2.PLAN_REL
WAVE1_PLAN = ROOT / wave2.WAVE1_PLAN_REL
WAVE1_RESULT = ROOT / wave2.WAVE1_RESULT_REL


def load_joined():
    schema, rows = recon.read_parquet(ROOT / recon.PARQUET_REL)
    api = recon.load_api_snapshot(ROOT / recon.API_REL)
    objects = recon.build_object_index(api)
    joined, duration_column = recon.join_rows(
        schema, rows, objects, require_duration=False
    )
    assert duration_column is None
    return rows, joined, objects


def load_calibration():
    return wave2.load_wave1_calibration(WAVE1_PLAN, WAVE1_RESULT)


def test_selection_is_exact_deterministic_and_excludes_wave1() -> None:
    _, joined, _ = load_joined()
    calibration, excluded, _, _ = load_calibration()
    first = wave2.select_wave2_objects(joined, calibration, excluded)
    second = wave2.select_wave2_objects(
        list(reversed(joined)), calibration, excluded
    )
    assert [item.video_id for item in first] == [
        item.video_id for item in second
    ]
    assert len(first) == wave2.WAVE2_OBJECT_COUNT == 20
    assert not ({item.video_path for item in first} & excluded)
    assert Counter(item.dataset for item in first) == Counter(
        {"youtube": 18, "ego4d": 2}
    )
    assert all(item.duration_s is None for item in first)


def test_selection_has_topic_and_all_available_modality_hypotheses() -> None:
    _, joined, _ = load_joined()
    calibration, excluded, _, _ = load_calibration()
    selected = wave2.select_wave2_objects(joined, calibration, excluded)
    assert len({recon.topic_hypothesis(item.text) for item in selected}) >= 6
    assert {
        recon.modality_hypothesis(item.text) for item in selected
    } == {recon.modality_hypothesis(item.text) for item in joined}


def test_wave1_calibration_is_exact_and_transparent() -> None:
    calibration, excluded, plan_identity, result_identity = load_calibration()
    wave1_result = json.loads(WAVE1_RESULT.read_text(encoding="utf-8"))
    assert len(calibration) == len(excluded) == 10
    assert plan_identity["sha256"] == wave2.EXPECTED_WAVE1_PLAN_SHA256
    assert result_identity["sha256"] == wave2.EXPECTED_WAVE1_RESULT_SHA256
    for observed, source in zip(
        calibration, wave1_result["discovery_objects"], strict=True
    ):
        assert float(observed.duration_seconds) == source["duration_seconds"]
        assert observed.size_bytes == source["identity"]["size_bytes"]
        assert observed.audio_track_count == source["audio_track_count"]
        assert observed.video_track_count == source["video_track_count"]


def test_plan_has_exact_pinned_joins_and_no_inferred_duration(
    tmp_path: Path,
) -> None:
    output = tmp_path / "wave2-plan.json"
    result = wave2.run(ROOT, plan_path=output)
    assert result["selected_object_count"] == 20
    assert result["duration_qualified_object_count"] == 0
    plan = json.loads(output.read_text(encoding="utf-8"))
    objects = plan["wave2_objects"]
    _, _, index = load_joined()
    wave1_paths = {
        item["path"]
        for item in json.loads(WAVE1_PLAN.read_text(encoding="utf-8"))[
            "discovery_objects"
        ]
    }
    assert len(objects) == 20
    assert sum(item["dataset"] == "youtube" for item in objects) == 18
    assert not ({item["path"] for item in objects} & wave1_paths)
    for item in objects:
        exact = index[item["path"]]
        assert item["repo_id"] == recon.REPO_ID
        assert item["revision"] == recon.REVISION
        assert item["size_bytes"] == exact.size
        assert item["blob_id"] == exact.blob_id
        assert item["sha256"] == exact.sha256
        assert item["actual_duration"] == wave2.UNRESOLVED
        assert item["size_ratio_is_duration"] is False
        assert item["evidence_extent_is_duration"] is False
        assert "duration_seconds" not in item
        assert "inferred_duration" not in item
        assert "estimated_duration" not in item


def test_persisted_plan_records_wave1_provenance_and_sampling_limits() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    calibration = plan["wave1_calibration"]
    assert calibration["observation_count"] == 10
    assert len(calibration["observations"]) == 10
    assert calibration["plan_artifact"]["sha256"] == (
        wave2.EXPECTED_WAVE1_PLAN_SHA256
    )
    assert calibration["result_artifact"]["sha256"] == (
        wave2.EXPECTED_WAVE1_RESULT_SHA256
    )
    assert calibration["sampling_observations"] == {
        "youtube_tested_count": 7,
        "youtube_declared_audio_count": 7,
        "ego4d_tested_count": 3,
        "ego4d_declared_no_audio_count": 2,
        "interpretation": (
            "SOURCE PREFERENCE IS A WAVE1 SAMPLING HEURISTIC, NOT A "
            "CORPUS_LEVEL AUDIO CLAIM."
        ),
    }
    assert calibration["ratio_policy"][
        "untested_duration_inference_performed"
    ] is False
    assert calibration["ratio_policy"]["untested_duration_persisted"] is False


def test_ranking_uses_all_observed_ratios_and_ordered_tiebreaks() -> None:
    _, joined, _ = load_joined()
    calibration, excluded, _, _ = load_calibration()
    selected = wave2.select_wave2_objects(joined, calibration, excluded)
    keys = [wave2._rank_key(item, calibration) for item in selected]
    assert keys == sorted(keys)
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    for item, source in zip(selected, plan["wave2_objects"], strict=True):
        expected = wave2.gate_supporting_observations(item, calibration)
        heuristic = source["ranking_heuristic"]
        assert heuristic["gate_compatible_wave1_ratio_count"] == len(expected)
        assert heuristic["gate_compatible_wave1_observation_ids"] == list(
            expected
        )


def test_plan_authorizes_only_exact_bounded_preflight() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    authorization = plan["authorization"]
    assert authorization["authorized_actions"] == [wave2.AUTHORIZED_ACTION]
    assert authorization[
        "authorized_for_bounded_stream_container_preflight"
    ] == [item["wave2_id"] for item in plan["wave2_objects"]]
    for key in (
        "authorized_for_full_acquisition",
        "authorized_for_full_media_download",
        "authorized_for_processing",
        "authorized_for_annotation",
        "authorized_for_release",
    ):
        assert authorization[key] == []
    assert plan["constraints"]["wildcards_allowed"] is False
    assert plan["constraints"][
        "full_object_response_permitted_in_later_preflight"
    ] is False
    assert "*" not in PLAN.read_text(encoding="utf-8")


def test_validation_rejects_duration_and_broad_authority() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    plan["wave2_objects"][0]["actual_duration"] = 1300.0
    with pytest.raises(recon.ReconError, match="UNTESTED_FACT_CONFLATION"):
        wave2.validate_plan(plan)

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    plan["authorization"]["authorized_for_full_acquisition"] = [
        "ves-wave2-01"
    ]
    with pytest.raises(recon.ReconError, match="BROAD_AUTHORIZATION"):
        wave2.validate_plan(plan)


def test_planner_has_no_network_or_media_request_route() -> None:
    source = (ROOT / "tools/ves_wave2_plan.py").read_text(encoding="utf-8")
    prohibited = [
        "requests.get(",
        "httpx.get(",
        "urlopen(",
        "curl ",
        "wget ",
        "Range:",
        "Authorization:",
    ]
    assert not any(token in source for token in prohibited)

