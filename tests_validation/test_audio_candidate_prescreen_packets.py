from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools.audio_candidate_prescreen_packets import (
    FORM_SCHEMA,
    IMPORT_SCHEMA,
    NO_GO,
    PACKET_SCHEMA,
    READY,
    REPAIR,
    AudioCandidatePacketError,
    bridge_construct_ledgers,
    build_exposure_ledger,
    completed_errors,
    evaluate,
    generate,
    read_json,
    verify,
)
from tools.construct_validity_common import (
    freeze_reviewer_assignment_ledger,
    source_level_assignment_conflicts,
)

ROOT = Path(__file__).resolve().parents[1]
CHECKED_IN = ROOT / "data/rehearsal_plan/audio_candidate_prescreen_packets_v1"


def packet_form(root: Path, code: str = "C01") -> tuple[dict, dict]:
    directory = root / "candidates" / code
    return (
        read_json(directory / "candidate_packet.json"),
        read_json(directory / "reviewer_form.json"),
    )


def reviewed_count(count: dict, value: int = 1) -> None:
    count.update(
        mode="exact",
        exact_count=value,
        minimum_count=None,
        maximum_count=None,
        unit_description="distinct audible episode",
        confidence="high",
        notes="Counted from the interval.",
    )


def complete_form(form: dict, *, decision: str = "READY") -> dict:
    form = copy.deepcopy(form)
    form["completion_status"] = "completed"
    form["reviewer"].update(
        reviewer_id="trained-prescreener-194",
        training_attested=True,
        started_at="2026-10-10T01:00:00+08:00",
        first_exposed_at="2026-10-10T01:05:00+08:00",
        completed_at="2026-10-10T01:40:00+08:00",
        source_content_exposure_attested=True,
    )
    form["inspection_protocol"].update(
        phase_order_attested=True,
        audio_only_completed_before_av_started=True,
        audio_only_completed_at="2026-10-10T01:15:00+08:00",
        av_started_at="2026-10-10T01:16:00+08:00",
        av_completed_at="2026-10-10T01:25:00+08:00",
        machine_semantics_were_not_visible=True,
    )
    audio = form["audio_only_review"]
    audio.update(
        review_status="reviewed",
        event_descriptions=["A concrete repeated mechanical event is audible."],
        tentative_source_world_fact="A local mechanical event repeats.",
        fact_confidence="high",
        speech_presence="absent",
        music_presence="absent",
        non_speech_event_salience="clear",
        notes="Independent audio-only observation.",
    )
    reviewed_count(audio["distinct_episode_count"], 3)
    reviewed_count(audio["repeated_subevent_count"], 3)
    av = form["audiovisual_review"]
    av.update(
        review_status="reviewed",
        grounded_source_world_fact="The audible event is grounded in a visible local action.",
        source_world_non_speech_event="yes",
        dynamic_visual_evidence="A visible object changes state during the event.",
        count_changed_after_vision=False,
        count_change_reason="The count remained stable.",
        audio_changes_answerability="yes",
        notes="A/V grounding completed after audio-only review.",
    )
    reviewed_count(av["distinct_episode_count_after_vision"], 3)
    av["speech_substitution_risk"].update(level="none", notes="No speech.")
    av["music_substitution_risk"].update(level="none", notes="No music.")
    av["vision_substitution_risk"].update(
        level="partial", notes="Vision identifies context but not the full sound pattern."
    )
    av["transcript_caption_ocr_narration_risk"].update(
        level="none", notes="No text substitute observed."
    )
    recurrence = form["recurrence_review"]
    recurrence.update(
        assessment_status="complete",
        bounded_recurrence_assessment="possible",
        within_focal_recurrence_notes="Repeated episodes occur in the focal interval.",
        authoring_implication="Bind any later authoring to the local interval.",
    )
    for probe in recurrence["probe_results"]:
        probe.update(
            review_status="reviewed",
            same_or_similar_event="possible",
            notes="A bounded probe was inspected without claiming full-source closure.",
        )
        reviewed_count(probe["observed_episode_count"], 1)
    form["privacy_review"].update(
        assessment_status="no_concern", notes="No sampled privacy concern."
    )
    form["safety_review"].update(
        assessment_status="no_concern", notes="No sampled safety concern."
    )
    form["authoring_eligibility"].update(
        decision=decision,
        rationale="All required listening and A/V checks were completed.",
    )
    if decision == "REPAIR":
        form["authoring_eligibility"]["repair_actions"] = [
            "Narrow the focal interval and repeat the count."
        ]
    return form


def test_schemas_are_valid_draft_2020_12():
    for path in (PACKET_SCHEMA, FORM_SCHEMA, IMPORT_SCHEMA):
        schema = json.loads(path.read_text())
        Draft202012Validator.check_schema(schema)
        assert schema["$id"].startswith(
            "urn:av-trace:schema:audio-candidate-prescreen-"
        )


def test_checked_in_packet_set_is_ready_and_blank_imports_fail_closed():
    result = verify(CHECKED_IN)
    assert result == {"readiness_token": READY, "errors": []}
    manifest = read_json(CHECKED_IN / "coordinator" / "packet_manifest.json")
    assert manifest["candidate_count"] == 4
    assert manifest["calibration_count"] == 2
    assert manifest["human_identity_count"] == 0
    assert manifest["human_decision_count"] == 0
    assert manifest["exposure_event_count"] == 0
    for code in ("C01", "C02", "C03", "C04"):
        packet, form = packet_form(CHECKED_IN, code)
        report, exposure = evaluate(packet, form)
        assert report["readiness_token"] == REPAIR
        assert report["completion_status"] == "incomplete"
        assert exposure["events"] == []
        assert all(
            request["extract_media"] is False
            and request["persist_media"] is False
            and request["execute"] is False
            for request in packet["adapter_requests"]
        )


def test_generation_is_deterministic(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate(first)
    generate(second)
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


def test_reviewer_packet_is_machine_semantic_blind():
    packet, _ = packet_form(CHECKED_IN, "C02")
    serialized = json.dumps(packet).lower()
    for forbidden in (
        "clap",
        "sad193",
        "blender",
        "beep",
        "wrapper",
        "potato",
        "peeling",
        "three clusters",
        "three bursts",
        "question_template",
        "answer_template",
        "recommended_profile",
    ):
        assert forbidden not in serialized


def test_tampered_interval_or_form_binding_fails_closed():
    packet, form = packet_form(CHECKED_IN, "C03")
    tampered = copy.deepcopy(packet)
    tampered["adapter_requests"][0]["end_s"] += 1
    with pytest.raises(AudioCandidatePacketError, match="hash mismatch"):
        evaluate(tampered, form)
    tampered_form = copy.deepcopy(form)
    tampered_form["packet_payload_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(AudioCandidatePacketError, match="form packet hash mismatch"):
        evaluate(packet, tampered_form)


def test_completed_ready_repair_and_no_go_tokens():
    packet, blank = packet_form(CHECKED_IN, "C01")
    ready, exposure = evaluate(packet, complete_form(blank, decision="READY"))
    assert ready["readiness_token"] == READY
    assert ready["completion_status"] == "valid"
    assert len(exposure["events"]) == 1
    repair, _ = evaluate(packet, complete_form(blank, decision="REPAIR"))
    assert repair["readiness_token"] == REPAIR
    no_go, _ = evaluate(packet, complete_form(blank, decision="NO_GO"))
    assert no_go["readiness_token"] == NO_GO


def test_exposure_is_recorded_at_first_view_even_before_completion():
    packet, blank = packet_form(CHECKED_IN, "C02")
    form = copy.deepcopy(blank)
    form["completion_status"] = "in_progress"
    form["reviewer"].update(
        reviewer_id="in-progress-prescreener-194",
        training_attested=True,
        started_at="2026-10-10T01:00:00+08:00",
        first_exposed_at="2026-10-10T01:05:00+08:00",
        source_content_exposure_attested=True,
    )
    report, exposure = evaluate(packet, form)
    assert report["readiness_token"] == REPAIR
    assert report["completion_status"] == "incomplete"
    assert report["exposure_recorded"] is True
    assert len(exposure["events"]) == 1
    assert exposure["events"][0]["recorded_at"] == "2026-10-10T01:05:00+08:00"


def test_ready_fails_closed_for_speech_dominance_and_missing_order():
    packet, blank = packet_form(CHECKED_IN, "C04")
    form = complete_form(blank)
    form["audio_only_review"]["speech_presence"] = "dominant"
    form["inspection_protocol"]["phase_order_attested"] = False
    errors = completed_errors(form)
    assert "READY_DISALLOWS_SPEECH_DOMINANCE" in errors
    assert "PHASE_ORDER_NOT_ATTESTED" in errors
    report, _ = evaluate(packet, form)
    assert report["readiness_token"] == REPAIR


def test_exposure_bridge_bars_both_blind_roles():
    packets, completed_forms = [], []
    for code in ("C01", "C02", "C03", "C04"):
        packet, blank = packet_form(CHECKED_IN, code)
        packets.append(packet)
        completed_forms.append(complete_form(blank))
    audio_ledger = build_exposure_ledger(packets, completed_forms)
    construct_exposure = read_json(
        CHECKED_IN / "coordinator" / "source_exposure_ledger.json"
    )
    assignments = read_json(
        CHECKED_IN / "coordinator" / "reviewer_assignments.json"
    )
    bridged_exposure, bridged_assignments = bridge_construct_ledgers(
        audio_ledger,
        construct_exposure,
        assignments,
        artifact_reference="task194-completed-exposure.json",
    )
    assert len(bridged_exposure["pre_distribution_snapshot"]["events"]) == 4
    for assignment in bridged_assignments["assignments"]:
        assignment["reviewer_id"] = f"reviewer-{assignment['assignment_id']}"
        assignment["assigned_at"] = "2026-10-10T02:00:00+08:00"
    target_group = packets[0]["source_binding"]["source_group_id"]
    target_family = next(
        group["family_ids"][0]
        for group in bridged_assignments["source_groups"]
        if group["source_group_id"] == target_group
    )
    for role in (
        "blind_alternative_evidence_finder",
        "blind_post_adjudication_saturation_auditor",
    ):
        trial = copy.deepcopy(bridged_assignments)
        for assignment in trial["assignments"]:
            if (
                assignment["source_group_id"] == target_group
                and assignment["family_id"] == target_family
                and assignment["role"] == role
            ):
                assignment["reviewer_id"] = "trained-prescreener-194"
        frozen = freeze_reviewer_assignment_ledger(
            trial, frozen_at="2026-10-10T02:30:00+08:00"
        )
        conflicts = source_level_assignment_conflicts(frozen, bridged_exposure)
        assert "SOURCE_GROUP_BLIND_ROLE_EXPOSURE_CONFLICT" in conflicts[target_family]


def test_permissions_are_fail_closed():
    assert CHECKED_IN.stat().st_mode & 0o077 == 0
    for path in CHECKED_IN.rglob("*"):
        assert path.stat().st_mode & 0o077 == 0
