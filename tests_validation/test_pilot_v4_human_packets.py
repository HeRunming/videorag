from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools.pilot_v4_human_packets import (
    AUDIO_ORDER,
    PilotV4PacketError,
    build,
    validate_author_form,
    verify_packet,
)

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "data/rehearsal_plan/pilot_v4_human_packets"


def test_task199_schemas_are_valid() -> None:
    for path in sorted((ROOT / "docs/spec").glob("pilot_v4_*_schema.json")):
        Draft202012Validator.check_schema(json.loads(path.read_text()))


def test_checked_in_packet_verifies() -> None:
    result = verify_packet(PACKET)
    assert result["readiness_token"] == "PILOT_V4_HUMAN_PACKETS_READY"
    assert result["blank_import_token"] == "PILOT_V4_HUMAN_PACKETS_REPAIR"
    assert result["distribution_authorized"] is False
    assert result["gate_a_go_asserted"] is False


def test_exact_packet_counts_and_null_assignments() -> None:
    registry = json.loads(
        (PACKET / "coordinator/packet_registry.json").read_text()
    )
    assignments = json.loads(
        (PACKET / "coordinator/reviewer_assignments.json").read_text()
    )
    assert len(registry["source_prescreen_packets"]) == 6
    assert len(registry["slot_packets"]) == 12
    assert sum(item["audio_prescreen"] is not None for item in registry["slot_packets"]) == 4
    assert len(registry["excluded_calibration_packets"]) == 2
    assert len(assignments["assignments"]) == 72
    assert all(item["reviewer_id"] is None for item in assignments["assignments"])
    assert all(item["assigned_at"] is None for item in assignments["assignments"])


def test_audio_order_is_task194_order() -> None:
    registry = json.loads(
        (PACKET / "coordinator/packet_registry.json").read_text()
    )
    for slot in registry["slot_packets"]:
        audio = slot["audio_prescreen"]
        if audio is None:
            continue
        assert tuple(audio["inspection_order"]) == AUDIO_ORDER
        packet = json.loads((PACKET / audio["packet_path"]).read_text())
        assert tuple(packet["inspection_order"]) == AUDIO_ORDER


def test_author_identity_injection_fails_closed() -> None:
    matrix = json.loads(
        (ROOT / "data/rehearsal_plan/pilot_v4_candidate_matrix.json").read_text()
    )
    slot = matrix["candidate_slots"][0]
    form = json.loads(
        (PACKET / f"slots/{slot['slot_id']}/author_verifier_form.json").read_text()
    )
    form["reviewer"]["reviewer_id"] = "invented-reviewer"
    with pytest.raises(PilotV4PacketError):
        validate_author_form(form, slot)


def test_build_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    build(first)
    build(second)
    first_files = {
        path.relative_to(first): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files


def test_registry_gate_a_tamper_is_rejected() -> None:
    registry = json.loads(
        (PACKET / "coordinator/packet_registry.json").read_text()
    )
    tampered = copy.deepcopy(registry)
    tampered["construct_boundary"]["gate_a_go"] = True
    schema = json.loads(
        (
            ROOT / "docs/spec/pilot_v4_human_packet_registry_schema.json"
        ).read_text()
    )
    assert list(Draft202012Validator(schema).iter_errors(tampered))
