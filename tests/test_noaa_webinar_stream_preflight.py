from __future__ import annotations

import copy
import json
from pathlib import Path

import httpx
import pytest

from tools import hf_audio_stream_preflight as core
from tools import noaa_webinar_stream_preflight as noaa


def object_item(number: int) -> dict:
    candidate_id = f"cand-{48 + number:03d}"
    pages = {
        "cand-048": (
            "NOAA-OceanToday-webinar4",
            "Shipwrecks and Sanctuaries",
            "https://oceantoday.noaa.gov/deeperdive/webinars/webinar4-060520.html",
            "00:50:00",
            3000,
        ),
        "cand-049": (
            "NOAA-OceanToday-webinar5",
            "Beach and Bay Safe",
            "https://oceantoday.noaa.gov/deeperdive/webinars/webinar5-070220.html",
            "00:41:00",
            2460,
        ),
        "cand-050": (
            "NOAA-OceanToday-webinar6",
            "Get Into Your Sanctuary",
            "https://oceantoday.noaa.gov/deeperdive/webinars/webinar-6-getintoyoursanctuary.html",
            "00:57:00",
            3420,
        ),
        "cand-051": (
            "NOAA-OceanToday-webinar7",
            "Trash Talk",
            "https://oceantoday.noaa.gov/deeperdive/webinars/webinar7-trashtalk-1.html",
            "01:02:00",
            3720,
        ),
        "cand-052": (
            "NOAA-OceanToday-webinar8",
            "Climate Alive! Wild Weather",
            "https://oceantoday.noaa.gov/deeperdive/webinars/webinar8-climatealive.html",
            "01:03:00",
            3780,
        ),
    }
    stable_source_id, title, page_url, duration_text, duration_seconds = pages[
        candidate_id
    ]
    return {
        "candidate_id": candidate_id,
        "stable_source_id": stable_source_id,
        "page_url": page_url,
        "page_title": title,
        "observed_html_title": title,
        "metadata_duration_prior": {
            "csv_text": duration_text,
            "csv_seconds": duration_seconds,
            "page_text": "50 minutes",
            "status": "HYPOTHESIS_ONLY_NOT_CONTAINER_DURATION",
        },
        "route_evidence": {
            "origin": "source",
            "label": "360P",
            "small_rendition_hint": True,
        },
        "url": (
            "https://oceantoday.noaa.gov/deeperdive/webinars/"
            f"webinar-{number}-sm.mp4"
        ),
        "size_bytes": 10_000 + number,
        "etag": f'"etag-{number}"',
        "last_modified": "Wed, 09 Sep 2026 00:00:00 GMT",
        "content_type": "video/mp4",
        "accept_ranges": "bytes",
        "actual_duration_seconds": None,
        "declared_audio_track": None,
        "stream_facts_status": "UNRESOLVED_PENDING_BOUNDED_PREFLIGHT",
        "full_acquisition_authorized": False,
        "processing_authorized": False,
        "annotation_authorized": False,
        "release_authorized": False,
    }


def ready_plan() -> dict:
    objects = [object_item(number) for number in range(5)]
    return {
        "schema_version": "1.0.0",
        "generated_at": "2026-09-09T00:00:00Z",
        "status": "READY_FOR_BOUNDED_NOAA_STREAM_PREFLIGHT",
        "source_identity_file": "data/candidates/source_candidates.csv",
        "scope": {
            "candidate_ids": list(noaa.recon.NOAA_CANDIDATE_IDS),
            "official_page_host": "oceantoday.noaa.gov",
            "minimum_selected_objects": 5,
            "maximum_selected_objects": 8,
            "selected_object_count": 5,
            "wildcards_allowed": False,
        },
        "route_discovery_policy": {
            "page_get_body_limit_bytes": 2 * 1024 * 1024,
            "mp4_methods_allowed": ["HEAD"],
            "mp4_body_requests_performed": 0,
            "official_ocean_today_final_host_required": False,
            "official_ocean_today_landing_host_required": True,
            "official_mp4_final_hosts": [
                "cdn.oceanservice.noaa.gov",
                "oceantoday.noaa.gov",
            ],
            "noaa_only_redirects": True,
            "exact_redirect_hosts_only": True,
            "prefer_small_low_resolution_rendition": True,
        },
        "transfer_policy": {
            "per_request_body_bytes": noaa.MAX_RESPONSE_BYTES,
            "per_candidate_body_bytes": noaa.MAX_CANDIDATE_BYTES,
            "aggregate_body_bytes": noaa.MAX_AGGREGATE_BYTES,
            "maximum_object_count": noaa.MAX_OBJECTS,
            "head_and_bounded_range_get_only": True,
            "complete_object_range_prohibited": True,
            "full_object_get_prohibited": True,
            "media_byte_persistence_prohibited": True,
        },
        "authorization": {
            "authorized_action": (
                "BOUNDED_ISO_BMFF_PREFLIGHT_FOR_SELECTED_EXACT_URLS_ONLY"
            ),
            "authorized_for_bounded_stream_preflight": [
                item["candidate_id"] for item in objects
            ],
            "authorized_for_full_acquisition": [],
            "authorized_for_processing": [],
            "authorized_for_annotation": [],
            "authorized_for_release": [],
        },
        "page_results": [],
        "available_exact_objects": copy.deepcopy(objects),
        "objects": objects,
        "limitations": [],
    }


def write_plan(tmp_path: Path, plan: dict) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


def generic_result(candidate: core.DirectURLCandidate) -> dict:
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


def test_loads_exact_direct_url_identities(tmp_path: Path) -> None:
    plan, candidates, provenance = noaa.load_plan(
        write_plan(tmp_path, ready_plan())
    )
    assert len(candidates) == len(provenance) == 5
    assert candidates[0].url.endswith("webinar-0-sm.mp4")
    assert candidates[0].etag == '"etag-0"'
    assert provenance[0]["metadata_duration_prior"]["status"].startswith(
        "HYPOTHESIS_ONLY"
    )
    assert plan["authorization"]["authorized_for_full_acquisition"] == []


def test_load_plan_accepts_exact_ocean_service_cdn_final_url(
    tmp_path: Path,
) -> None:
    plan = ready_plan()
    cdn_url = (
        "https://cdn.oceanservice.noaa.gov/oceantodayprod/media/"
        "deeperdive/webinars/webinar-0-sm.mp4"
    )
    plan["objects"][0]["url"] = cdn_url
    plan["available_exact_objects"][0]["url"] = cdn_url
    _, candidates, _ = noaa.load_plan(write_plan(tmp_path, plan))
    assert candidates[0].url == cdn_url


def test_direct_client_sends_no_bearer_and_redacts_redirect_query() -> None:
    seen: list[tuple[str, str | None]] = []
    candidate = core.DirectURLCandidate.from_mapping(object_item(0))

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, request.headers.get("authorization")))
        if request.url.host == "oceantoday.noaa.gov":
            return httpx.Response(
                302,
                headers={
                    "content-length": "0",
                    "location": (
                        "https://cdn.oceanservice.noaa.gov/object.mp4"
                        "?Signature=secret&Policy=secret"
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
    client = core.SafeDirectURLRangeClient(
        allowed_host=noaa.noaa_stream_host_allowed,
        clients=[raw],
        budget=core.Budget(1024, 4096),
    )
    assert client.fetch_range(candidate, 0, 9, "test") == b"0123456789"
    assert seen == [
        ("oceantoday.noaa.gov", None),
        ("cdn.oceanservice.noaa.gov", None),
    ]
    serialized = json.dumps([record.as_dict() for record in client.records])
    assert "Signature" not in serialized
    assert "Policy" not in serialized
    assert "secret" not in serialized


def test_direct_head_validates_exact_route_and_headers() -> None:
    candidate = core.DirectURLCandidate.from_mapping(object_item(0))

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-length": str(candidate.size_bytes),
                "etag": candidate.etag,
                "last-modified": candidate.last_modified,
                "content-type": "video/mp4; charset=binary",
                "accept-ranges": "bytes",
            },
        )

    raw = httpx.Client(transport=httpx.MockTransport(handler))
    client = core.SafeDirectURLRangeClient(
        allowed_host=noaa.noaa_stream_host_allowed,
        clients=[raw],
        budget=core.Budget(1024, 4096),
    )
    identity = client.head(candidate)
    assert identity.matches
    assert identity.observed_effective_url == candidate.url


def test_full_media_get_and_complete_range_are_impossible() -> None:
    candidate = core.DirectURLCandidate.from_mapping(object_item(0))
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    raw = httpx.Client(transport=httpx.MockTransport(handler))
    client = core.SafeDirectURLRangeClient(
        allowed_host=noaa.noaa_stream_host_allowed,
        clients=[raw],
        budget=core.Budget(1024, 4096),
    )
    with pytest.raises(
        core.TransferValidationError,
        match="COMPLETE_OBJECT_RANGE_PROHIBITED",
    ):
        client.fetch_range(candidate, 0, candidate.size_bytes - 1, "bad")
    assert not called


def test_reuses_shared_parser_and_range_safety() -> None:
    assert noaa.core.locate_and_parse is core.locate_and_parse
    assert noaa.core.SafeDirectURLRangeClient is core.SafeDirectURLRangeClient
    assert noaa.core.decide is core.decide


def test_no_duration_or_audio_conflation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, candidates, provenance = noaa.load_plan(
        write_plan(tmp_path, ready_plan())
    )

    def fake_run(items, client, *, window_bytes):
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
    result = noaa.run_preflight(
        plan, candidates, provenance, object(), window_bytes=1024
    )
    first = result["objects"][0]
    assert first["duration_seconds"] == 1300.0
    assert first["audio_track_count"] == 1
    assert (
        first["noaa_provenance"]["metadata_duration_prior"]["csv_seconds"]
        == 3000
    )
    assert "duration_seconds" not in first["noaa_provenance"]
    assert "audio_track_count" not in first["noaa_provenance"]


def test_limits_cannot_be_raised() -> None:
    noaa.validate_limits(
        maximum_response_bytes=noaa.MAX_RESPONSE_BYTES,
        maximum_candidate_bytes=noaa.MAX_CANDIDATE_BYTES,
        maximum_total_bytes=noaa.MAX_AGGREGATE_BYTES,
    )
    with pytest.raises(
        core.ConfigurationError, match="AGGREGATE_LIMIT_MAY_NOT_BE_RAISED"
    ):
        noaa.validate_limits(
            maximum_response_bytes=noaa.MAX_RESPONSE_BYTES,
            maximum_candidate_bytes=noaa.MAX_CANDIDATE_BYTES,
            maximum_total_bytes=noaa.MAX_AGGREGATE_BYTES + 1,
        )
    assert noaa.MAX_OBJECTS * noaa.MAX_CANDIDATE_BYTES == (
        noaa.MAX_AGGREGATE_BYTES
    )


def test_no_media_persistence_code_path() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "tools/noaa_webinar_stream_preflight.py"
    ).read_text(encoding="utf-8")
    assert "SafeDirectURLRangeClient" in source
    assert "locate_and_parse(" not in source
    assert 'open("wb"' not in source
    assert ".write_bytes(" not in source


def test_broad_authorization_and_non_noaa_url_rejected(tmp_path: Path) -> None:
    plan = ready_plan()
    plan["authorization"]["authorized_for_full_acquisition"] = ["cand-048"]
    with pytest.raises(core.ConfigurationError, match="AUTHORIZATION"):
        noaa.load_plan(write_plan(tmp_path, plan))

    plan = ready_plan()
    plan["objects"][0]["url"] = "https://example.com/object.mp4"
    plan["available_exact_objects"][0]["url"] = plan["objects"][0]["url"]
    with pytest.raises(core.ConfigurationError):
        noaa.load_plan(write_plan(tmp_path, plan))


@pytest.mark.parametrize(
    "host",
    [
        "media.noaa.gov",
        "cdn.noaa.gov",
        "cdn.oceanservice.noaa.gov.evil.example",
    ],
)
def test_plan_rejects_arbitrary_and_lookalike_final_hosts(
    tmp_path: Path, host: str
) -> None:
    plan = ready_plan()
    plan["objects"][0]["url"] = f"https://{host}/object.mp4"
    plan["available_exact_objects"][0]["url"] = plan["objects"][0]["url"]
    with pytest.raises(
        core.ConfigurationError,
        match="NOAA_PLAN_INVALID_NON_OFFICIAL_NOAA_HOST",
    ):
        noaa.load_plan(write_plan(tmp_path, plan))
