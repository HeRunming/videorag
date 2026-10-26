from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.epic_dev_authoring_packets import (
    IMPORT_SCHEMA,
    READY,
    REGISTRY_SCHEMA,
    ROLE_FORM_SCHEMA,
    build,
    evaluate_packet_dir,
    read_json,
    validate_role_form,
)

ROOT = Path(__file__).resolve().parents[1]
CHECKED_IN = ROOT / "data/rehearsal_plan/epic_dev_authoring_packets_v1"


def test_task171_schemas_are_valid_draft_2020_12():
    for path in (REGISTRY_SCHEMA, ROLE_FORM_SCHEMA, IMPORT_SCHEMA):
        schema = read_json(path)
        Draft202012Validator.check_schema(schema)
        assert schema["$id"].startswith(
            "urn:av-trace:schema:epic-dev-authoring-"
        )


def test_checked_in_packet_validates_ready_and_contains_no_human_work():
    report = evaluate_packet_dir(CHECKED_IN)
    assert report["readiness_token"] == READY
    assert report["human_review_occurred"] is False
    assert report["identity_count"] == 0
    assert report["human_decision_count"] == 0
    assert report["proposal_count"] == 5
    assert report["calibration_rejection_count"] == 2
    assert report["future_test_eligible"] is False
    assert report["gate_a_eligible"] is False
    assert report["h1_assigned"] is False
    assert report["h2_assigned"] is False
    assert all(
        item["task153_readiness_token"]
        == "SEMANTIC_AV_SOURCE_PRESCREEN_REPAIR"
        for item in report["prescreen_results"]
    )


def test_rebuild_is_deterministic(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert build(first)["readiness_token"] == READY
    assert build(second)["readiness_token"] == READY
    first_files = {
        str(path.relative_to(first)): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_files = {
        str(path.relative_to(second)): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files


def test_import_fails_closed_on_task153_interval_tamper(tmp_path: Path):
    packet = tmp_path / "packet"
    shutil.copytree(CHECKED_IN, packet)
    registry_path = packet / "coordinator/packet_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["proposal_packets"][0]["task153_prescreen_binding"][
        "sample_intervals"
    ][0]["start_s"] += 0.25
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    report = evaluate_packet_dir(packet)
    assert report["readiness_token"] != READY
    assert report["schema_validation_pass"] is False


def test_import_fails_closed_on_identity_or_finding(tmp_path: Path):
    packet = tmp_path / "packet"
    shutil.copytree(CHECKED_IN, packet)
    registry = read_json(packet / "coordinator/packet_registry.json")
    form_path = packet / registry["proposal_packets"][0][
        "author_verifier_form_path"
    ]
    form = read_json(form_path)
    form["reviewer"]["reviewer_id"] = "invented-reviewer"
    form_path.write_text(json.dumps(form), encoding="utf-8")
    report = evaluate_packet_dir(packet)
    assert report["readiness_token"] != READY
    assert report["schema_validation_pass"] is False
    assert report["errors"]
    Draft202012Validator(read_json(IMPORT_SCHEMA)).validate(report)


def test_role_form_schema_and_hash_reject_mutated_assignment():
    registry = read_json(CHECKED_IN / "coordinator/packet_registry.json")
    form = read_json(
        CHECKED_IN
        / registry["proposal_packets"][0]["author_verifier_form_path"]
    )
    validate_role_form(form)
    tampered = copy.deepcopy(form)
    tampered["immutable_assignment"]["answer_hypothesis"] += " altered"
    try:
        validate_role_form(tampered)
    except ValueError as exc:
        assert "hash mismatch" in str(exc)
    else:
        raise AssertionError("tampered immutable assignment was accepted")
