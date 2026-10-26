from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from tools import hf_audio_stream_preflight as core
from tools import ves_wave2_stream_preflight as runner


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / runner.PLAN_PATH


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


def test_exact_plan_maps_to_code_allowlist() -> None:
    plan, candidates, provenance = runner.load_plan(PLAN)
    assert len(candidates) == len(provenance) == runner.OBJECT_COUNT == 20
    assert [item.identity_dict() for item in candidates] == list(
        runner.EXACT_VES_OBJECTS
    )
    assert [item.candidate_id for item in candidates] == [
        item["wave2_id"] for item in plan["wave2_objects"]
    ]


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
def test_identity_change_is_rejected(
    tmp_path: Path, field: str, replacement: object
) -> None:
    plan = read_plan()
    plan["wave2_objects"][0][field] = replacement
    with pytest.raises(core.ConfigurationError):
        runner.load_plan(write_plan(tmp_path, plan))


def test_added_reordered_or_broad_plan_is_rejected(tmp_path: Path) -> None:
    plan = read_plan()
    plan["wave2_objects"].append(plan["wave2_objects"][0].copy())
    with pytest.raises(core.ConfigurationError):
        runner.load_plan(write_plan(tmp_path, plan))

    plan = read_plan()
    plan["wave2_objects"][0], plan["wave2_objects"][1] = (
        plan["wave2_objects"][1],
        plan["wave2_objects"][0],
    )
    with pytest.raises(core.ConfigurationError):
        runner.load_plan(write_plan(tmp_path, plan))

    plan = read_plan()
    plan["authorization"]["authorized_for_full_media_download"] = [
        "ves-wave2-01"
    ]
    with pytest.raises(core.ConfigurationError, match="AUTHORIZATION"):
        runner.load_plan(write_plan(tmp_path, plan))


def test_unverified_object_duration_is_rejected(tmp_path: Path) -> None:
    for field in (
        "duration_seconds",
        "duration_s",
        "metadata_duration",
        "inferred_duration",
        "estimated_duration",
    ):
        plan = read_plan()
        plan["wave2_objects"][0][field] = 1300.0
        with pytest.raises(core.ConfigurationError):
            runner.load_plan(write_plan(tmp_path, plan))


def test_limits_are_non_raiseable_and_fit_aggregate() -> None:
    runner.validate_limits(
        maximum_response_bytes=runner.MAX_RESPONSE_BYTES,
        maximum_candidate_bytes=runner.MAX_CANDIDATE_BYTES,
        maximum_total_bytes=runner.MAX_AGGREGATE_BYTES,
    )
    with pytest.raises(
        core.ConfigurationError, match="PER_REQUEST_LIMIT_MAY_NOT_BE_RAISED"
    ):
        runner.validate_limits(
            maximum_response_bytes=runner.MAX_RESPONSE_BYTES + 1,
            maximum_candidate_bytes=runner.MAX_CANDIDATE_BYTES,
            maximum_total_bytes=runner.MAX_AGGREGATE_BYTES,
        )
    with pytest.raises(
        core.ConfigurationError, match="CANDIDATE_LIMIT_MAY_NOT_BE_RAISED"
    ):
        runner.validate_limits(
            maximum_response_bytes=runner.MAX_RESPONSE_BYTES,
            maximum_candidate_bytes=runner.MAX_CANDIDATE_BYTES + 1,
            maximum_total_bytes=runner.MAX_AGGREGATE_BYTES,
        )
    with pytest.raises(
        core.ConfigurationError, match="AGGREGATE_LIMIT_MAY_NOT_BE_RAISED"
    ):
        runner.validate_limits(
            maximum_response_bytes=runner.MAX_RESPONSE_BYTES,
            maximum_candidate_bytes=runner.MAX_CANDIDATE_BYTES,
            maximum_total_bytes=runner.MAX_AGGREGATE_BYTES + 1,
        )
    assert runner.OBJECT_COUNT * runner.MAX_CANDIDATE_BYTES <= (
        runner.MAX_AGGREGATE_BYTES
    )


def test_result_preserves_calibration_and_metadata_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, candidates, provenance = runner.load_plan(PLAN)

    def fake_run(items, client, *, window_bytes):
        return {
            "schema_version": core.SCHEMA_VERSION,
            "generated_at": "2026-09-09T00:00:00Z",
            "mode": "generic",
            "candidate_count": len(items),
            "limits": {
                "per_request_body_bytes": runner.MAX_RESPONSE_BYTES,
                "per_candidate_body_bytes": runner.MAX_CANDIDATE_BYTES,
                "aggregate_body_bytes": runner.MAX_AGGREGATE_BYTES,
            },
            "aggregate": {"response_body_bytes": 0},
            "candidates": [generic_result(item) for item in items],
            "global_limitations": [],
        }

    monkeypatch.setattr(core, "run_preflight", fake_run)
    result = runner.run_preflight(plan, candidates, provenance, object())
    assert result["wave2_object_count"] == 20
    assert result["plan_provenance"]["wave1_calibration"] == plan[
        "wave1_calibration"
    ]
    for source, item in zip(
        plan["wave2_objects"], result["wave2_objects"], strict=True
    ):
        assert item["wave2_id"] == source["wave2_id"]
        assert item["duration_seconds"] == 1300.0
        assert "duration_seconds" not in item["metadata_provenance"]
        for key in runner.PROVENANCE_KEYS:
            assert item["metadata_provenance"][key] == source[key]


def test_reuses_shared_http_parser_and_decision_code() -> None:
    assert runner.core.SafeHFRangeClient is core.SafeHFRangeClient
    assert runner.core.locate_and_parse is core.locate_and_parse
    assert runner.core.decide is core.decide
    source = (ROOT / "tools/ves_wave2_stream_preflight.py").read_text(
        encoding="utf-8"
    )
    assert "SafeHFRangeClient" in source
    assert "locate_and_parse(" not in source
    assert "struct.unpack" not in source
    assert "httpx.Client(" not in source


def test_shared_client_rejects_ignored_range_and_persists_no_media(
    tmp_path: Path,
) -> None:
    candidate = core.Candidate.from_mapping(runner.EXACT_VES_OBJECTS[0])
    raw = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, headers={"content-length": "10"}, content=b"x" * 10
            )
        ),
        follow_redirects=False,
    )
    client = core.SafeHFRangeClient(
        "secret",
        clients=[raw],
        budget=core.Budget(
            runner.MAX_RESPONSE_BYTES, runner.MAX_AGGREGATE_BYTES
        ),
        maximum_candidate_bytes=runner.MAX_CANDIDATE_BYTES,
    )
    with pytest.raises(
        core.TransferValidationError, match="RANGE_IGNORED_FULL_OBJECT_200"
    ):
        client.fetch_range(candidate, 0, 9, "wave2-safety-test")
    assert list(tmp_path.iterdir()) == []
    source = (ROOT / "tools/ves_wave2_stream_preflight.py").read_text(
        encoding="utf-8"
    )
    assert "open(\"wb\"" not in source
    assert ".write_bytes(" not in source


def test_validate_plan_only_does_not_load_token_or_network(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_token():
        raise AssertionError("token path must not be reached")

    monkeypatch.setattr(core, "load_hf_token", fail_token)
    assert runner.main(["--plan", str(PLAN), "--validate-plan-only"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "PASS"
    assert output["wave2_object_count"] == 20
    assert output["exact_allowlist_match"] is True

