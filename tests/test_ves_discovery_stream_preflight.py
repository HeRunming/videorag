from __future__ import annotations

import copy
import json
from pathlib import Path

import httpx
import pytest

from tools import hf_audio_stream_preflight as core
from tools import ves_discovery_stream_preflight as ves


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / ves.PLAN_PATH


def read_plan() -> dict:
    return json.loads(PLAN.read_text(encoding="utf-8"))


def write_plan(tmp_path: Path, value: dict) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def generic_result(candidate: core.Candidate) -> dict:
    result = core.base_candidate_result(candidate)
    result.update(
        {
            "identity_match": True,
            "container_parse_status": "PARSED_ISO_BMFF",
            "duration_seconds": 1300.0,
            "duration_gate": "PASS",
            "video_track_count": 1,
            "audio_track_count": 1,
            "av_timeline_relation": "PLAUSIBLY_SYNCHRONIZED",
            "decision": core.DECISION_GO,
            "range_request_count": 2,
            "response_body_bytes": 4096,
            "requests": [],
        }
    )
    return result


def test_exact_plan_maps_to_generic_candidates() -> None:
    plan, candidates, provenance = ves.load_plan(PLAN)
    assert len(candidates) == len(provenance) == ves.OBJECT_COUNT == 10
    assert [item.identity_dict() for item in candidates] == list(
        ves.EXACT_VES_OBJECTS
    )
    assert [item.candidate_id for item in candidates] == [
        item["discovery_id"] for item in plan["discovery_objects"]
    ]
    assert all(item.hash_algorithm == "sha256" for item in candidates)


def test_no_duration_conflation_in_mapping_or_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, candidates, provenance = ves.load_plan(PLAN)
    assert candidates[0].size_bytes != int(
        plan["discovery_objects"][0]["max_evidence_endpoint_s"]
    )

    captured: list[core.Candidate] = []

    def fake_run(items, client, *, window_bytes):
        captured.extend(items)
        return {
            "schema_version": core.SCHEMA_VERSION,
            "generated_at": "2026-09-09T00:00:00Z",
            "mode": "generic",
            "candidate_count": len(items),
            "limits": {},
            "aggregate": {},
            "candidates": [generic_result(item) for item in items],
            "global_limitations": [],
        }

    monkeypatch.setattr(core, "run_preflight", fake_run)
    result = ves.run_preflight(
        plan, candidates, provenance, object(), window_bytes=1024
    )
    assert captured == candidates
    first = result["discovery_objects"][0]
    assert first["duration_seconds"] == 1300.0
    assert (
        first["metadata_provenance"]["max_evidence_endpoint_s"]
        == plan["discovery_objects"][0]["max_evidence_endpoint_s"]
    )
    assert first["metadata_provenance"]["evidence_extent_is_duration"] is False
    assert "duration_seconds" not in first["metadata_provenance"]


def test_no_broad_authorization_is_accepted(tmp_path: Path) -> None:
    plan = read_plan()
    plan["authorization"]["authorized_for_full_acquisition"] = [
        "ves-discovery-01"
    ]
    with pytest.raises(core.ConfigurationError, match="AUTHORIZATION"):
        ves.load_plan(write_plan(tmp_path, plan))

    plan = read_plan()
    plan["constraints"]["full_object_range_permitted_in_later_preflight"] = True
    with pytest.raises(core.ConfigurationError, match="TRANSFER_SCOPE_TOO_BROAD"):
        ves.load_plan(write_plan(tmp_path, plan))


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("revision", "0" * 40),
        ("path", "videos/not-authorized.mp4"),
        ("size_bytes", 123),
        ("blob_id", "0" * 40),
        ("sha256", "0" * 64),
    ],
)
def test_plan_identity_mismatch_is_rejected(
    tmp_path: Path, field: str, replacement: object
) -> None:
    plan = read_plan()
    plan["discovery_objects"][0][field] = replacement
    with pytest.raises(core.ConfigurationError):
        ves.load_plan(write_plan(tmp_path, plan))


def test_aggregate_limit_cannot_exceed_128_mib() -> None:
    ves.validate_limits(
        maximum_response_bytes=ves.MAX_RESPONSE_BYTES,
        maximum_candidate_bytes=ves.MAX_CANDIDATE_BYTES,
        maximum_total_bytes=ves.MAX_AGGREGATE_BYTES,
    )
    with pytest.raises(
        core.ConfigurationError, match="AGGREGATE_LIMIT_MAY_NOT_BE_RAISED"
    ):
        ves.validate_limits(
            maximum_response_bytes=ves.MAX_RESPONSE_BYTES,
            maximum_candidate_bytes=ves.MAX_CANDIDATE_BYTES,
            maximum_total_bytes=ves.MAX_AGGREGATE_BYTES + 1,
        )
    assert ves.OBJECT_COUNT * ves.MAX_CANDIDATE_BYTES <= (
        ves.MAX_AGGREGATE_BYTES
    )


def test_result_preserves_discovery_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, candidates, provenance = ves.load_plan(PLAN)

    def fake_run(items, client, *, window_bytes):
        return {
            "schema_version": core.SCHEMA_VERSION,
            "generated_at": "2026-09-09T00:00:00Z",
            "mode": "generic",
            "candidate_count": len(items),
            "limits": {
                "per_request_body_bytes": ves.MAX_RESPONSE_BYTES,
                "per_candidate_body_bytes": ves.MAX_CANDIDATE_BYTES,
                "aggregate_body_bytes": ves.MAX_AGGREGATE_BYTES,
            },
            "aggregate": {"response_body_bytes": 0},
            "candidates": [generic_result(item) for item in items],
            "global_limitations": [],
        }

    monkeypatch.setattr(core, "run_preflight", fake_run)
    result = ves.run_preflight(plan, candidates, provenance, object())
    assert result["discovery_object_count"] == 10
    assert result["plan_provenance"]["metadata_snapshots"] == plan[
        "metadata_snapshots"
    ]
    for source, item in zip(
        plan["discovery_objects"], result["discovery_objects"], strict=True
    ):
        assert item["discovery_id"] == source["discovery_id"]
        for key in ves.PROVENANCE_KEYS:
            assert item["metadata_provenance"][key] == source[key]
        for required in (
            "identity_match",
            "duration_seconds",
            "duration_gate",
            "video_track_count",
            "audio_track_count",
            "av_timeline_relation",
            "decision",
            "range_request_count",
            "response_body_bytes",
        ):
            assert required in item


def test_reuses_existing_parser_and_range_safety() -> None:
    assert ves.core.locate_and_parse is core.locate_and_parse
    assert ves.core.SafeHFRangeClient is core.SafeHFRangeClient
    assert ves.core.decide is core.decide

    candidate = core.Candidate.from_mapping(ves.EXACT_VES_OBJECTS[0])
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, headers={"content-length": "10"}, content=b"x" * 10
        )
    )
    raw = httpx.Client(transport=transport, follow_redirects=False)
    client = ves.core.SafeHFRangeClient(
        "secret",
        clients=[raw],
        budget=core.Budget(ves.MAX_RESPONSE_BYTES, ves.MAX_AGGREGATE_BYTES),
        maximum_candidate_bytes=ves.MAX_CANDIDATE_BYTES,
    )
    with pytest.raises(
        core.TransferValidationError, match="RANGE_IGNORED_FULL_OBJECT_200"
    ):
        client.fetch_range(candidate, 0, 9, "ves-safety-test")


def test_no_media_persistence_and_redaction(tmp_path: Path) -> None:
    source = (ROOT / "tools/ves_discovery_stream_preflight.py").read_text(
        encoding="utf-8"
    )
    assert "SafeHFRangeClient" in source
    assert "locate_and_parse(" not in source
    assert "open(\"wb\"" not in source
    assert ".write_bytes(" not in source

    candidate = core.Candidate.from_mapping(ves.EXACT_VES_OBJECTS[0])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "huggingface.co":
            return httpx.Response(
                302,
                headers={
                    "content-length": "0",
                    "location": (
                        "https://cdn-lfs.huggingface.co/object"
                        "?Policy=secret&Signature=secret"
                    ),
                },
            )
        return httpx.Response(
            206,
            headers={
                "content-length": "10",
                "content-range": f"bytes 0-9/{candidate.size_bytes}",
            },
            content=b"0123456789",
        )

    raw = httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )
    client = core.SafeHFRangeClient(
        "unit-test-secret-token",
        clients=[raw],
        budget=core.Budget(ves.MAX_RESPONSE_BYTES, ves.MAX_AGGREGATE_BYTES),
        maximum_candidate_bytes=ves.MAX_CANDIDATE_BYTES,
    )
    assert client.fetch_range(candidate, 0, 9, "redaction") == b"0123456789"
    serialized = json.dumps([record.as_dict() for record in client.records])
    assert "unit-test-secret-token" not in serialized
    assert "Policy" not in serialized
    assert "Signature" not in serialized
    assert "secret" not in serialized
    assert list(tmp_path.iterdir()) == []


def test_added_candidate_limit_is_enforced_by_shared_client() -> None:
    candidate = core.Candidate.from_mapping(ves.EXACT_VES_OBJECTS[0])

    def handler(request: httpx.Request) -> httpx.Response:
        start, end = map(
            int, request.headers["range"].removeprefix("bytes=").split("-")
        )
        return httpx.Response(
            206,
            headers={
                "content-length": str(end - start + 1),
                "content-range": (
                    f"bytes {start}-{end}/{candidate.size_bytes}"
                ),
            },
            content=b"x" * (end - start + 1),
        )

    raw = httpx.Client(transport=httpx.MockTransport(handler))
    client = core.SafeHFRangeClient(
        "secret",
        clients=[raw],
        budget=core.Budget(100, 100),
        maximum_candidate_bytes=15,
    )
    assert client.fetch_range(candidate, 0, 9, "first") == b"x" * 10
    with pytest.raises(
        core.TransferValidationError, match="CANDIDATE_BODY_LIMIT_EXCEEDED"
    ):
        client.fetch_range(candidate, 10, 19, "second")
