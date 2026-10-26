from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from tools import ves_discovery_preflight_plan as discovery
from tools import ves_long_candidate_recon as recon


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / discovery.PLAN_REL
TASK70_POOL = ROOT / recon.POOL_REL
TASK70_PLAN = ROOT / recon.PLAN_REL


def load_joined():
    schema, rows = recon.read_parquet(ROOT / recon.PARQUET_REL)
    api = recon.load_api_snapshot(ROOT / recon.API_REL)
    objects = recon.build_object_index(api)
    joined, duration_column = recon.join_rows(
        schema, rows, objects, require_duration=False
    )
    assert duration_column is None
    return rows, joined, objects


def test_real_selection_is_exact_deterministic_and_diverse() -> None:
    _, joined, _ = load_joined()
    first = discovery.select_discovery_objects(joined)
    second = discovery.select_discovery_objects(list(reversed(joined)))
    assert [item.video_id for item in first] == [
        item.video_id for item in second
    ]
    assert len(first) == 10
    assert {item.dataset for item in first} == {"youtube", "ego4d"}
    assert {task for item in first for task in item.tasks} == {
        "temporal_ordering",
        "event_counting",
    }
    assert discovery.REQUIRED_TASK_PROFILES.issubset(
        {item.tasks for item in first}
    )
    assert len({recon.topic_hypothesis(item.text) for item in first}) >= 6
    assert len({recon.modality_hypothesis(item.text) for item in first}) == 3
    assert first[0].max_evidence_end_s == 1080.0
    assert all(item.duration_s is None for item in first)
    assert any(
        earlier.object_identity.size > later.object_identity.size
        for earlier, later in zip(first, first[1:])
    )


def test_real_plan_has_closed_identities_and_no_duration_conflation(
    tmp_path: Path,
) -> None:
    output = tmp_path / "plan.json"
    result = discovery.run(ROOT, plan_path=output)
    assert result["selected_object_count"] == 10
    assert result["duration_qualified_candidate_count"] == 0
    plan = json.loads(output.read_text(encoding="utf-8"))
    objects = plan["discovery_objects"]
    assert len(objects) == 10
    assert len({item["path"] for item in objects}) == 10
    assert len({item["blob_id"] for item in objects}) == 10
    assert len({item["sha256"] for item in objects}) == 10
    assert all(item["repo_id"] == recon.REPO_ID for item in objects)
    assert all(item["revision"] == recon.REVISION for item in objects)
    assert all(item["metadata_evidence_rows"] for item in objects)
    assert all(
        row["evidence_intervals"]
        for item in objects
        for row in item["metadata_evidence_rows"]
    )
    assert all(
        item["max_evidence_endpoint_s"]
        == max(
            row["max_evidence_end_s"]
            for row in item["metadata_evidence_rows"]
        )
        for item in objects
    )
    assert all(item["actual_duration"] == discovery.UNRESOLVED for item in objects)
    assert all(item["audio_track"] == discovery.UNRESOLVED for item in objects)
    assert all(item["evidence_extent_is_duration"] is False for item in objects)
    assert all(
        item["duration_qualification_status"]
        == discovery.NOT_DURATION_QUALIFIED
        for item in objects
    )
    assert "metadata_duration" not in output.read_text(encoding="utf-8")
    assert "*" not in output.read_text(encoding="utf-8")


def test_plan_authorizes_only_bounded_container_preflight() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    authorization = plan["authorization"]
    assert authorization["authorized_actions"] == [
        "BOUNDED_ISO_BMFF_RANGE_PREFLIGHT_FOR_THE_TEN_EXACT_OBJECTS_ONLY"
    ]
    assert len(
        authorization["authorized_for_bounded_stream_container_preflight"]
    ) == 10
    for key in (
        "authorized_for_full_acquisition",
        "authorized_for_full_media_download",
        "authorized_for_processing",
        "authorized_for_annotation",
        "authorized_for_release",
    ):
        assert authorization[key] == []
    assert all(
        item["requested_action"] == discovery.REQUESTED_ACTION
        and item["full_acquisition_authorized"] is False
        and item["processing_authorized"] is False
        and item["annotation_authorized"] is False
        and item["release_authorized"] is False
        for item in plan["discovery_objects"]
    )


def test_task70_duration_qualified_outputs_remain_fail_closed() -> None:
    with TASK70_POOL.open(newline="", encoding="utf-8") as handle:
        assert list(csv.DictReader(handle)) == []
    task70_plan = json.loads(TASK70_PLAN.read_text(encoding="utf-8"))
    assert task70_plan["status"] == "BLOCKED"
    assert task70_plan["ranked_objects"] == []
    assert task70_plan["blocker"]["code"] == "MISSING_ITEM_DURATION_COLUMN"


def test_plan_identity_matches_exact_pinned_sibling_index() -> None:
    _, _, objects = load_joined()
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    for item in plan["discovery_objects"]:
        exact = objects[item["path"]]
        assert item["size_bytes"] == exact.size
        assert item["blob_id"] == exact.blob_id
        assert item["sha256"] == exact.sha256


def test_validation_rejects_duration_conflation_and_broad_authority() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    plan["discovery_objects"][0]["actual_duration"] = 1080.0
    with pytest.raises(recon.ReconError, match="DURATION_OR_TRACK_CONFLATION"):
        discovery.validate_plan(plan)

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    plan["authorization"]["authorized_for_full_acquisition"] = [
        "ves-discovery-01"
    ]
    with pytest.raises(
        recon.ReconError, match="ACQUISITION_AUTHORIZATION_MUST_REMAIN_EMPTY"
    ):
        discovery.validate_plan(plan)


def test_tool_has_no_network_or_media_download_route() -> None:
    source = (ROOT / "tools/ves_discovery_preflight_plan.py").read_text(
        encoding="utf-8"
    )
    prohibited = [
        "requests.get(",
        "httpx.get(",
        "urlopen(",
        "curl ",
        "wget ",
        "Range:",
        "Authorization:",
        "X-Amz-Signature",
    ]
    assert not any(token in source for token in prohibited)
