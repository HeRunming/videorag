#!/usr/bin/env python3
"""Build and fail-closed validate Task194 audio prescreen packets."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

try:
    from .construct_validity_common import (
        exposure_event_hash,
        exposure_snapshot_hash,
        validate_reviewer_assignment_ledger,
        validate_source_exposure_ledger,
    )
    from .semantic_av_source_prescreen_common import parse_datetime
except ImportError:
    from construct_validity_common import (
        exposure_event_hash,
        exposure_snapshot_hash,
        validate_reviewer_assignment_ledger,
        validate_source_exposure_ledger,
    )
    from semantic_av_source_prescreen_common import parse_datetime

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data/rehearsal_plan/audio_candidate_prescreen_packets_v1"
TASK193_FACTS = (
    ROOT / "data/restricted/semantic_audio_discovery_v1/provisional_audio_facts.json"
)
TASK193_BINDINGS = (
    ROOT / "data/restricted/semantic_audio_discovery_v1/source_bindings.json"
)
PIVOT_V2 = ROOT / "data/rehearsal_plan/cvpr_pivot_v2_gate_registry.json"
PACKET_SCHEMA = ROOT / "docs/spec/audio_candidate_prescreen_packet_schema.json"
FORM_SCHEMA = ROOT / "docs/spec/audio_candidate_prescreen_form_schema.json"
IMPORT_SCHEMA = ROOT / "docs/spec/audio_candidate_prescreen_import_schema.json"

READY = "AUDIO_CANDIDATE_PRESCREEN_PACKETS_READY"
REPAIR = "AUDIO_CANDIDATE_PRESCREEN_PACKETS_REPAIR"
NO_GO = "AUDIO_CANDIDATE_PRESCREEN_PACKETS_NO_GO"
BLIND_ROLES = [
    "blind_alternative_evidence_finder",
    "blind_post_adjudication_saturation_auditor",
]
ALL_HUMAN_ROLES = [
    "question_claim_author_or_verifier",
    "blind_alternative_evidence_finder",
    "validator_a",
    "validator_b",
    "adjudicator",
    "blind_post_adjudication_saturation_auditor",
]
FACT_IDS = {
    "C01": "sad193.fact.cc15.blender.pulses",
    "C02": "sad193.fact.cc16.timer.beep.sequence",
    "C03": "sad193.fact.p27.wrapper.open",
    "C04": "sad193.fact.p28.peel.scrape",
}
SOURCE_GROUPS = {
    "15_29": "cc4d_p02_e02",
    "16_20": "cc4d_p01_e08",
    "P27_101": "P27",
    "P28_103": "P28",
}
ADAPTER_REFERENCES = {
    "15_29": "restricted-file://15_29_360p.mp4",
    "16_20": "restricted-file://16_20_360p.mp4",
    "P27_101": "restricted-file://media/P27/P27_101.MP4",
    "P28_103": "restricted-file://media/P28/P28_103.MP4",
}
RECURRENCE_PROBES = {
    "C01": [(676.0, 696.0), (1052.0, 1068.0), (1264.0, 1280.0)],
    "C02": [(380.0, 400.0), (984.0, 1000.0), (1328.0, 1348.0)],
    "C03": [(304.0, 324.0), (720.0, 740.0), (956.0, 980.0)],
    "C04": [(328.0, 352.0), (388.0, 412.0), (1484.0, 1500.0)],
}


class AudioCandidatePacketError(ValueError):
    """Raised when Task194 artifacts fail closed."""


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode()


def object_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise AudioCandidatePacketError(f"cannot read JSON {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))
    os.chmod(path, 0o600)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    os.chmod(path, 0o600)


def validate_instance(value: Any, schema_path: Path, label: str) -> None:
    schema = read_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(value), key=lambda error: list(error.absolute_path)
    )
    if errors:
        rendered = []
        for error in errors[:20]:
            location = ".".join(map(str, error.absolute_path)) or "$"
            rendered.append(f"{location}: {error.message}")
        raise AudioCandidatePacketError(
            f"{label} failed schema validation: " + "; ".join(rendered)
        )


def packet_hash(packet: dict[str, Any]) -> str:
    envelope = {k: v for k, v in packet.items() if k != "packet_payload_sha256"}
    return object_hash(envelope)


def validate_packet(packet: dict[str, Any]) -> None:
    validate_instance(packet, PACKET_SCHEMA, "candidate packet")
    if packet["packet_payload_sha256"] != packet_hash(packet):
        raise AudioCandidatePacketError("candidate packet hash mismatch")
    binding = packet["source_binding"]
    if not 0 <= binding["focal_start_s"] < binding["focal_end_s"]:
        raise AudioCandidatePacketError("invalid focal interval")
    if binding["focal_end_s"] > binding["source_duration_s"] + 0.001:
        raise AudioCandidatePacketError("focal interval exceeds source duration")
    requests = packet["adapter_requests"]
    if [item["inspection_order"] for item in requests] != [1, 2, 3, 4, 5]:
        raise AudioCandidatePacketError("adapter request order mismatch")
    if [item["inspection_phase"] for item in requests] != [
        "audio_only_focal",
        "synchronized_av_focal",
        "audio_only_recurrence_probes",
        "audio_only_recurrence_probes",
        "audio_only_recurrence_probes",
    ]:
        raise AudioCandidatePacketError("inspection phases are not paired/order-safe")
    if requests[0]["stream_mode"] != "audio_only":
        raise AudioCandidatePacketError("first request must be audio-only")
    if requests[1]["stream_mode"] != "synchronized_av":
        raise AudioCandidatePacketError("second request must be synchronized A/V")
    for request in requests:
        if request["adapter_reference"] != binding["adapter_reference"]:
            raise AudioCandidatePacketError("adapter reference mismatch")
        if request["source_content_sha256"] != binding["source_content_sha256"]:
            raise AudioCandidatePacketError("adapter source hash mismatch")
        if request["end_s"] <= request["start_s"]:
            raise AudioCandidatePacketError("invalid adapter interval")
        if request["end_s"] > binding["source_duration_s"] + 0.001:
            raise AudioCandidatePacketError("adapter interval exceeds source")
        expected = round(request["end_s"] - request["start_s"], 3)
        if request["bounded_duration_s"] != expected:
            raise AudioCandidatePacketError("bounded duration mismatch")
        if request["bounded_duration_s"] > 90:
            raise AudioCandidatePacketError("adapter request exceeds 90 seconds")


def blank_count() -> dict[str, Any]:
    return {
        "mode": "unknown",
        "exact_count": None,
        "minimum_count": None,
        "maximum_count": None,
        "unit_description": "",
        "confidence": "unknown",
        "notes": "",
    }


def blank_risk() -> dict[str, str]:
    return {"level": "unknown", "notes": ""}


def source_bindings() -> dict[str, dict[str, Any]]:
    data = read_json(TASK193_BINDINGS)
    return {item["source_ref"]: item for item in data["sources"]}


def selected_facts() -> dict[str, dict[str, Any]]:
    data = read_json(TASK193_FACTS)
    by_id = {item["fact_id"]: item for item in data["retained_audio_facts"]}
    selected = {}
    for code, fact_id in FACT_IDS.items():
        try:
            fact = by_id[fact_id]
        except KeyError as exc:
            raise AudioCandidatePacketError(
                f"Task193 fact missing: {fact_id}"
            ) from exc
        if fact["status"] != "RETAIN_AUDIO_FACT":
            raise AudioCandidatePacketError(f"Task193 fact not retained: {fact_id}")
        if fact["human_listening_performed"] or fact["human_reviewed"]:
            raise AudioCandidatePacketError(f"unexpected human work: {fact_id}")
        selected[code] = fact
    return selected


def prompts() -> dict[str, list[str]]:
    return {
        "audio_only": [
            "Describe every concrete non-speech event without guessing from a label.",
            "Count distinct event episodes and repeated subevents; use a range if uncertain.",
            "State the tentative source-world fact carried by sound alone.",
            "Record whether speech or music is present or dominant.",
        ],
        "synchronized_av": [
            "Identify the grounded source-world event after vision is revealed.",
            "Recount episodes and explain any count change after viewing.",
            "Judge whether sound changes answerability or merely corroborates vision.",
            "Judge speech, music, vision, and text/narration substitution risk separately.",
        ],
        "recurrence": [
            "Inspect all three bounded audio-only probes after the focal A/V pass.",
            "Record same/similar event recurrence and its authoring implication.",
            "Do not claim full-source closure from these bounded probes.",
        ],
        "privacy_safety": [
            "Record privacy concerns, including identifiable speech or sensitive content.",
            "Record safety concerns and whether high/critical concerns are unresolved.",
        ],
        "eligibility": [
            "READY only if a concrete local source-world non-speech fact is usable for authoring.",
            "REPAIR when a plausible path requires a specific interval, count, recurrence, or substitution repair.",
            "NO_GO when speech/music/substitution, ambiguity, privacy, safety, or recurrence makes the candidate unsuitable.",
        ],
    }


def make_request(
    *,
    code: str,
    order: int,
    phase: str,
    mode: str,
    adapter_reference: str,
    source_sha256: str,
    start_s: float,
    end_s: float,
) -> dict[str, Any]:
    return {
        "request_id": f"task194.{code}.request-{order:02d}",
        "inspection_phase": phase,
        "inspection_order": order,
        "stream_mode": mode,
        "adapter_reference": adapter_reference,
        "source_content_sha256": f"sha256:{source_sha256}",
        "start_s": start_s,
        "end_s": end_s,
        "bounded_duration_s": round(end_s - start_s, 3),
        "extract_media": False,
        "persist_media": False,
        "execute": False,
    }


def build_packet(
    code: str,
    fact: dict[str, Any],
    binding: dict[str, Any],
) -> dict[str, Any]:
    source_id = fact["source_ref"]
    start_s = fact["interval"]["start_s"]
    end_s = fact["interval"]["end_s"]
    adapter_reference = ADAPTER_REFERENCES[source_id]
    requests = [
        make_request(
            code=code,
            order=1,
            phase="audio_only_focal",
            mode="audio_only",
            adapter_reference=adapter_reference,
            source_sha256=binding["source_sha256"],
            start_s=start_s,
            end_s=end_s,
        ),
        make_request(
            code=code,
            order=2,
            phase="synchronized_av_focal",
            mode="synchronized_av",
            adapter_reference=adapter_reference,
            source_sha256=binding["source_sha256"],
            start_s=start_s,
            end_s=end_s,
        ),
    ]
    for order, (probe_start, probe_end) in enumerate(
        RECURRENCE_PROBES[code], start=3
    ):
        requests.append(
            make_request(
                code=code,
                order=order,
                phase="audio_only_recurrence_probes",
                mode="audio_only",
                adapter_reference=adapter_reference,
                source_sha256=binding["source_sha256"],
                start_s=probe_start,
                end_s=probe_end,
            )
        )
    packet = {
        "schema_version": "1.0.0",
        "record_type": "audio_candidate_prescreen_packet",
        "packet_id": f"task194.audio-candidate.{code}",
        "candidate_code": code,
        "packet_status": "DRAFT_NOT_DISTRIBUTABLE",
        "source_binding": {
            "source_id": source_id,
            "source_group_id": SOURCE_GROUPS[source_id],
            "source_content_sha256": f"sha256:{binding['source_sha256']}",
            "source_duration_s": binding["duration_us"] / 1_000_000,
            "adapter_reference": adapter_reference,
            "focal_start_s": start_s,
            "focal_end_s": end_s,
        },
        "inspection_order": [
            "audio_only_focal",
            "synchronized_av_focal",
            "audio_only_recurrence_probes",
        ],
        "adapter_requests": requests,
        "review_prompts": prompts(),
        "blindness_contract": {
            "machine_labels_visible": False,
            "machine_ranks_visible": False,
            "machine_scores_visible": False,
            "proposed_question_visible": False,
            "proposed_answer_visible": False,
            "proposed_profile_visible": False,
            "calibration_expected_outputs_visible_during_candidate_review": False,
        },
        "scope": {
            "media_embedded": False,
            "adapter_execution_authorized": False,
            "human_review_performed": False,
            "human_decision_recorded": False,
            "necessity_assigned": False,
            "minimality_assigned": False,
            "h1_assigned": False,
            "h2_assigned": False,
            "gate_a_eligible": False,
        },
        "packet_payload_sha256": "",
    }
    packet["packet_payload_sha256"] = packet_hash(packet)
    validate_packet(packet)
    return packet


def build_form(packet: dict[str, Any]) -> dict[str, Any]:
    probes = packet["adapter_requests"][2:]
    form = {
        "schema_version": "1.0.0",
        "record_type": "audio_candidate_prescreen_form",
        "form_id": f"{packet['packet_id']}.form",
        "packet_id": packet["packet_id"],
        "candidate_code": packet["candidate_code"],
        "packet_payload_sha256": packet["packet_payload_sha256"],
        "source_id": packet["source_binding"]["source_id"],
        "source_group_id": packet["source_binding"]["source_group_id"],
        "completion_status": "not_started",
        "reviewer": {
            "reviewer_id": None,
            "training_attested": False,
            "protocol_version": "audio-candidate-prescreen-v1",
            "started_at": None,
            "first_exposed_at": None,
            "completed_at": None,
            "source_content_exposure_attested": False,
        },
        "inspection_protocol": {
            "required_order": packet["inspection_order"],
            "phase_order_attested": None,
            "audio_only_completed_before_av_started": None,
            "audio_only_completed_at": None,
            "av_started_at": None,
            "av_completed_at": None,
            "machine_semantics_were_not_visible": None,
        },
        "audio_only_review": {
            "review_status": "not_reviewed",
            "event_descriptions": [],
            "distinct_episode_count": blank_count(),
            "repeated_subevent_count": blank_count(),
            "tentative_source_world_fact": "",
            "fact_confidence": "unknown",
            "speech_presence": "unknown",
            "music_presence": "unknown",
            "non_speech_event_salience": "unknown",
            "notes": "",
        },
        "audiovisual_review": {
            "review_status": "not_reviewed",
            "grounded_source_world_fact": "",
            "source_world_non_speech_event": "unknown",
            "dynamic_visual_evidence": "",
            "distinct_episode_count_after_vision": blank_count(),
            "count_changed_after_vision": None,
            "count_change_reason": "",
            "audio_changes_answerability": "unknown",
            "speech_substitution_risk": blank_risk(),
            "music_substitution_risk": blank_risk(),
            "vision_substitution_risk": {"level": "unknown", "notes": ""},
            "transcript_caption_ocr_narration_risk": blank_risk(),
            "notes": "",
        },
        "recurrence_review": {
            "assessment_status": "not_assessed",
            "probe_results": [
                {
                    "request_id": probe["request_id"],
                    "review_status": "not_reviewed",
                    "same_or_similar_event": "unknown",
                    "observed_episode_count": blank_count(),
                    "notes": "",
                }
                for probe in probes
            ],
            "bounded_recurrence_assessment": "unknown",
            "within_focal_recurrence_notes": "",
            "authoring_implication": "",
            "full_source_closure_claimed": False,
        },
        "privacy_review": {
            "assessment_status": "not_assessed",
            "concerns": [],
            "notes": "",
        },
        "safety_review": {
            "assessment_status": "not_assessed",
            "concerns": [],
            "notes": "",
        },
        "authoring_eligibility": {
            "decision": "UNDECIDED",
            "rationale": "",
            "repair_actions": [],
            "authoring_constraints": [],
        },
        "source_level_exposure_policy": {
            "exposure_must_flow_to_construct_ledger": True,
            "exposure_scope": "source_group",
            "excluded_future_roles": BLIND_ROLES,
        },
        "prohibited_outcomes": {
            "necessity_assigned": False,
            "minimality_assigned": False,
            "h1_assigned": False,
            "h2_assigned": False,
            "human_gold": False,
            "gate_a_result": False,
        },
    }
    validate_form(form, packet)
    return form


def validate_count(count: dict[str, Any], label: str) -> list[str]:
    errors = []
    mode = count["mode"]
    if mode == "exact":
        if count["exact_count"] is None:
            errors.append(f"{label}_EXACT_COUNT_MISSING")
        if count["minimum_count"] is not None or count["maximum_count"] is not None:
            errors.append(f"{label}_EXACT_COUNT_HAS_RANGE")
    elif mode == "range":
        lo, hi = count["minimum_count"], count["maximum_count"]
        if lo is None or hi is None or lo > hi:
            errors.append(f"{label}_INVALID_RANGE")
        if count["exact_count"] is not None:
            errors.append(f"{label}_RANGE_HAS_EXACT_COUNT")
    elif mode == "not_countable":
        if any(
            value is not None
            for value in (
                count["exact_count"],
                count["minimum_count"],
                count["maximum_count"],
            )
        ):
            errors.append(f"{label}_NOT_COUNTABLE_HAS_COUNT")
    return errors


def validate_form(form: dict[str, Any], packet: dict[str, Any]) -> None:
    validate_instance(form, FORM_SCHEMA, "candidate form")
    for key in ("packet_id", "candidate_code"):
        if form[key] != packet[key]:
            raise AudioCandidatePacketError(f"form {key} mismatch")
    if form["packet_payload_sha256"] != packet["packet_payload_sha256"]:
        raise AudioCandidatePacketError("form packet hash mismatch")
    binding = packet["source_binding"]
    if form["source_id"] != binding["source_id"]:
        raise AudioCandidatePacketError("form source_id mismatch")
    if form["source_group_id"] != binding["source_group_id"]:
        raise AudioCandidatePacketError("form source_group_id mismatch")
    expected_requests = [x["request_id"] for x in packet["adapter_requests"][2:]]
    actual_requests = [
        x["request_id"] for x in form["recurrence_review"]["probe_results"]
    ]
    if actual_requests != expected_requests:
        raise AudioCandidatePacketError("form recurrence probe set/order mismatch")


def completed_errors(form: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if form["completion_status"] != "completed":
        return ["FORM_NOT_COMPLETED"]
    reviewer = form["reviewer"]
    if not reviewer["reviewer_id"] or not reviewer["training_attested"]:
        errors.append("TRAINED_REVIEWER_REQUIRED")
    times = (
        reviewer["started_at"],
        reviewer["first_exposed_at"],
        reviewer["completed_at"],
    )
    if not all(times):
        errors.append("REVIEW_TIMESTAMPS_REQUIRED")
    elif not (
        parse_datetime(times[0])
        <= parse_datetime(times[1])
        <= parse_datetime(times[2])
    ):
        errors.append("REVIEW_TIME_ORDER_INVALID")
    if not reviewer["source_content_exposure_attested"]:
        errors.append("SOURCE_EXPOSURE_ATTESTATION_REQUIRED")

    protocol = form["inspection_protocol"]
    if protocol["phase_order_attested"] is not True:
        errors.append("PHASE_ORDER_NOT_ATTESTED")
    if protocol["audio_only_completed_before_av_started"] is not True:
        errors.append("AUDIO_ONLY_NOT_COMPLETED_BEFORE_AV")
    if protocol["machine_semantics_were_not_visible"] is not True:
        errors.append("MACHINE_SEMANTIC_BLINDNESS_NOT_ATTESTED")
    phase_times = (
        protocol["audio_only_completed_at"],
        protocol["av_started_at"],
        protocol["av_completed_at"],
    )
    if not all(phase_times):
        errors.append("PHASE_TIMESTAMPS_REQUIRED")
    elif not (
        parse_datetime(phase_times[0])
        <= parse_datetime(phase_times[1])
        <= parse_datetime(phase_times[2])
    ):
        errors.append("PHASE_TIME_ORDER_INVALID")

    audio = form["audio_only_review"]
    av = form["audiovisual_review"]
    recurrence = form["recurrence_review"]
    if audio["review_status"] != "reviewed":
        errors.append("AUDIO_ONLY_NOT_REVIEWED")
    if av["review_status"] != "reviewed":
        errors.append("AV_NOT_REVIEWED")
    if not audio["event_descriptions"]:
        errors.append("AUDIO_EVENT_DESCRIPTION_REQUIRED")
    if not audio["tentative_source_world_fact"].strip():
        errors.append("TENTATIVE_SOURCE_WORLD_FACT_REQUIRED")
    for name in ("speech_presence", "music_presence", "non_speech_event_salience"):
        if audio[name] == "unknown":
            errors.append(f"{name.upper()}_UNKNOWN")
    errors.extend(validate_count(audio["distinct_episode_count"], "AUDIO_EPISODE"))
    errors.extend(validate_count(audio["repeated_subevent_count"], "AUDIO_SUBEVENT"))
    if audio["distinct_episode_count"]["mode"] == "unknown":
        errors.append("AUDIO_EPISODE_COUNT_UNKNOWN")
    if audio["repeated_subevent_count"]["mode"] == "unknown":
        errors.append("AUDIO_SUBEVENT_COUNT_UNKNOWN")

    if not av["grounded_source_world_fact"].strip():
        errors.append("GROUNDED_SOURCE_WORLD_FACT_REQUIRED")
    if av["source_world_non_speech_event"] == "unknown":
        errors.append("SOURCE_WORLD_EVENT_UNKNOWN")
    if av["audio_changes_answerability"] == "unknown":
        errors.append("AUDIO_ANSWERABILITY_UNKNOWN")
    if av["count_changed_after_vision"] is None:
        errors.append("COUNT_CHANGE_AFTER_VISION_UNKNOWN")
    errors.extend(
        validate_count(
            av["distinct_episode_count_after_vision"], "AV_EPISODE"
        )
    )
    if av["distinct_episode_count_after_vision"]["mode"] == "unknown":
        errors.append("AV_EPISODE_COUNT_UNKNOWN")
    for name in (
        "speech_substitution_risk",
        "music_substitution_risk",
        "transcript_caption_ocr_narration_risk",
    ):
        if av[name]["level"] == "unknown":
            errors.append(f"{name.upper()}_UNKNOWN")
    if av["vision_substitution_risk"]["level"] == "unknown":
        errors.append("VISION_SUBSTITUTION_RISK_UNKNOWN")

    if recurrence["assessment_status"] != "complete":
        errors.append("RECURRENCE_NOT_ASSESSED")
    if recurrence["bounded_recurrence_assessment"] == "unknown":
        errors.append("BOUNDED_RECURRENCE_UNKNOWN")
    if not recurrence["authoring_implication"].strip():
        errors.append("RECURRENCE_AUTHORING_IMPLICATION_REQUIRED")
    for probe in recurrence["probe_results"]:
        if probe["review_status"] != "reviewed":
            errors.append("RECURRENCE_PROBE_NOT_REVIEWED")
        if probe["same_or_similar_event"] == "unknown":
            errors.append("RECURRENCE_PROBE_UNKNOWN")
        errors.extend(
            validate_count(
                probe["observed_episode_count"], "RECURRENCE_PROBE_EPISODE"
            )
        )
        if probe["observed_episode_count"]["mode"] == "unknown":
            errors.append("RECURRENCE_PROBE_COUNT_UNKNOWN")

    for field, prefix in (
        ("privacy_review", "PRIVACY"),
        ("safety_review", "SAFETY"),
    ):
        review = form[field]
        if review["assessment_status"] == "not_assessed":
            errors.append(f"{prefix}_NOT_ASSESSED")
        if review["assessment_status"] == "concern_present" and not review["concerns"]:
            errors.append(f"{prefix}_CONCERN_STATUS_WITHOUT_CONCERN")
        if review["assessment_status"] == "no_concern" and review["concerns"]:
            errors.append(f"{prefix}_NO_CONCERN_STATUS_WITH_CONCERN")

    eligibility = form["authoring_eligibility"]
    decision = eligibility["decision"]
    if decision == "UNDECIDED":
        errors.append("AUTHORING_ELIGIBILITY_UNDECIDED")
    if not eligibility["rationale"].strip():
        errors.append("DECISION_RATIONALE_REQUIRED")
    if decision == "REPAIR" and not eligibility["repair_actions"]:
        errors.append("REPAIR_ACTION_REQUIRED")
    unresolved_high = [
        concern
        for field in ("privacy_review", "safety_review")
        for concern in form[field]["concerns"]
        if concern["severity"] in {"high", "critical"}
        and concern["mitigation_status"] == "unresolved"
    ]
    if decision == "READY":
        if av["source_world_non_speech_event"] != "yes":
            errors.append("READY_REQUIRES_SOURCE_WORLD_NON_SPEECH_EVENT")
        if av["audio_changes_answerability"] not in {"yes", "uncertain"}:
            errors.append("READY_REQUIRES_AUDIO_ANSWERABILITY_SIGNAL")
        if audio["speech_presence"] == "dominant":
            errors.append("READY_DISALLOWS_SPEECH_DOMINANCE")
        if audio["music_presence"] == "dominant":
            errors.append("READY_DISALLOWS_MUSIC_DOMINANCE")
        if unresolved_high:
            errors.append("READY_WITH_UNRESOLVED_HIGH_CONCERN")
        high_or_full = any(
            (
                av["speech_substitution_risk"]["level"] == "high",
                av["music_substitution_risk"]["level"] == "high",
                av["transcript_caption_ocr_narration_risk"]["level"] == "high",
                av["vision_substitution_risk"]["level"] == "full",
            )
        )
        if high_or_full and not eligibility["authoring_constraints"]:
            errors.append("READY_HIGH_SUBSTITUTION_REQUIRES_CONSTRAINT")
    return sorted(set(errors))


def build_exposure_ledger(
    packets: list[dict[str, Any]], forms: list[dict[str, Any]]
) -> dict[str, Any]:
    by_packet = {item["packet_id"]: item for item in packets}
    events = []
    for form in forms:
        reviewer = form["reviewer"]
        exposed = (
            form["completion_status"] != "not_started"
            and reviewer["reviewer_id"] is not None
            and reviewer["first_exposed_at"] is not None
            and reviewer["source_content_exposure_attested"] is True
        )
        if not exposed:
            continue
        packet = by_packet[form["packet_id"]]
        events.append(
            {
                "event_id": f"{form['form_id']}.source-prescreen",
                "reviewer_id": form["reviewer"]["reviewer_id"],
                "source_id": form["source_id"],
                "source_group_id": form["source_group_id"],
                "candidate_codes": [form["candidate_code"]],
                "adapter_request_ids": [
                    item["request_id"] for item in packet["adapter_requests"]
                ],
                "exposure_categories": [
                    "source_content",
                    "candidate_semantic_facts",
                ],
                "first_exposed_at": reviewer["first_exposed_at"],
                "recorded_at": reviewer["completed_at"]
                or reviewer["first_exposed_at"],
                "blind_role_exclusions": BLIND_ROLES,
            }
        )
    ledger = {
        "schema_version": "1.0.0",
        "record_type": "audio_candidate_prescreen_exposure_ledger",
        "packet_set_id": "audio-candidate-prescreen-packets-v1",
        "ledger_status": "SOURCE_LEVEL_BLIND_ROLE_EXCLUSIONS",
        "events": events,
        "ledger_sha256": "",
    }
    ledger["ledger_sha256"] = object_hash(
        {k: v for k, v in ledger.items() if k != "ledger_sha256"}
    )
    return ledger


def validate_exposure_ledger(ledger: dict[str, Any]) -> None:
    expected = object_hash(
        {k: v for k, v in ledger.items() if k != "ledger_sha256"}
    )
    if ledger.get("ledger_sha256") != expected:
        raise AudioCandidatePacketError("audio exposure ledger hash mismatch")
    if ledger.get("ledger_status") != "SOURCE_LEVEL_BLIND_ROLE_EXCLUSIONS":
        raise AudioCandidatePacketError("audio exposure ledger status mismatch")
    event_ids = [item["event_id"] for item in ledger["events"]]
    if len(event_ids) != len(set(event_ids)):
        raise AudioCandidatePacketError("duplicate audio exposure event")
    for event in ledger["events"]:
        if event["blind_role_exclusions"] != BLIND_ROLES:
            raise AudioCandidatePacketError("audio exposure exclusion mismatch")
        if not event["reviewer_id"]:
            raise AudioCandidatePacketError("audio exposure identity missing")


def token_for(decision: str, errors: list[str]) -> str:
    if decision == "NO_GO":
        return NO_GO
    if errors or decision != "READY":
        return REPAIR
    return READY


def evaluate(
    packet: dict[str, Any], form: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_packet(packet)
    validate_form(form, packet)
    errors = completed_errors(form)
    decision = form["authoring_eligibility"]["decision"]
    ledger = build_exposure_ledger([packet], [form])
    validate_exposure_ledger(ledger)
    report = {
        "schema_version": "1.0.0",
        "record_type": "audio_candidate_prescreen_import",
        "packet_id": packet["packet_id"],
        "form_id": form["form_id"],
        "candidate_code": form["candidate_code"],
        "source_id": form["source_id"],
        "source_group_id": form["source_group_id"],
        "completion_status": "valid" if not errors else "incomplete",
        "authoring_eligibility": decision,
        "readiness_token": token_for(decision, errors),
        "exposure_recorded": bool(ledger["events"]),
        "construct_ledger_bridge_required": True,
        "blind_finder_eligible": False,
        "saturation_auditor_eligible": False,
        "necessity_assigned": False,
        "minimality_assigned": False,
        "h1_assigned": False,
        "h2_assigned": False,
        "errors": errors,
    }
    validate_instance(report, IMPORT_SCHEMA, "candidate import")
    return report, ledger


def source_group_map(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, set[str]]] = {}
    for packet in packets:
        binding = packet["source_binding"]
        group = grouped.setdefault(
            binding["source_group_id"], {"source_ids": set(), "family_ids": set()}
        )
        group["source_ids"].add(binding["source_id"])
        group["family_ids"].add(f"task194.candidate.{packet['candidate_code']}")
    return [
        {
            "source_group_id": group_id,
            "source_ids": sorted(value["source_ids"]),
            "family_ids": sorted(value["family_ids"]),
        }
        for group_id, value in sorted(grouped.items())
    ]


def blank_construct_ledgers(
    packets: list[dict[str, Any]],
    *,
    captured_at: str = "2026-10-10T00:00:00+08:00",
) -> tuple[dict[str, Any], dict[str, Any]]:
    groups = source_group_map(packets)
    snapshot = {"captured_at": captured_at, "events": []}
    exposure = {
        "schema_version": "1.0.0",
        "record_type": "construct_validation_source_exposure_ledger",
        "packet_id": "audio-candidate-prescreen-packets-v1",
        "ledger_status": "OPEN_APPEND_ONLY",
        "source_groups": groups,
        "pre_distribution_snapshot": snapshot,
        "pre_distribution_snapshot_sha256": exposure_snapshot_hash(snapshot),
        "review_events": [],
        "notes": (
            "Blank Task194 source-level ledger. Completed prescreener exposure "
            "must be bridged before any construct assignments are frozen."
        ),
    }
    assignments = []
    for group in groups:
        for family_id in group["family_ids"]:
            for role in ALL_HUMAN_ROLES:
                assignments.append(
                    {
                        "assignment_id": (
                            f"audio-candidate-prescreen-packets-v1."
                            f"{family_id}.{role}"
                        ),
                        "source_group_id": group["source_group_id"],
                        "family_id": family_id,
                        "role": role,
                        "reviewer_id": None,
                        "assigned_at": None,
                    }
                )
    assignment = {
        "schema_version": "1.0.0",
        "record_type": "construct_validation_reviewer_assignment_ledger",
        "packet_id": "audio-candidate-prescreen-packets-v1",
        "generated_at": captured_at,
        "assignment_status": "DRAFT_NOT_DISTRIBUTABLE",
        "frozen_at": None,
        "distribution_authorized": False,
        "pre_distribution_exposure_snapshot_sha256": exposure[
            "pre_distribution_snapshot_sha256"
        ],
        "assignment_freeze_sha256": None,
        "source_groups": groups,
        "assignments": assignments,
        "notes": (
            "Blank six-role matrix. No identities or assignments exist. "
            "Prescreener exposure bars both blind source-search roles."
        ),
    }
    validate_source_exposure_ledger(exposure)
    validate_reviewer_assignment_ledger(assignment)
    return exposure, assignment


def bridge_construct_ledgers(
    audio_ledger: dict[str, Any],
    construct_exposure: dict[str, Any],
    assignments: dict[str, Any],
    *,
    artifact_reference: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_exposure_ledger(audio_ledger)
    validate_source_exposure_ledger(construct_exposure)
    validate_reviewer_assignment_ledger(assignments)
    if assignments["assignment_status"] != "DRAFT_NOT_DISTRIBUTABLE":
        raise AudioCandidatePacketError("bridge must occur before assignment freeze")
    if construct_exposure["review_events"]:
        raise AudioCandidatePacketError("cannot rewrite snapshot after review events")
    if assignments["source_groups"] != construct_exposure["source_groups"]:
        raise AudioCandidatePacketError("construct source-group maps differ")
    known_groups = {
        item["source_group_id"] for item in construct_exposure["source_groups"]
    }
    updated = copy.deepcopy(construct_exposure)
    snapshot = updated["pre_distribution_snapshot"]
    prior = snapshot["events"][-1]["event_sha256"] if snapshot["events"] else None
    sequence = len(snapshot["events"]) + 1
    for event in audio_ledger["events"]:
        if event["source_group_id"] not in known_groups:
            raise AudioCandidatePacketError(
                f"construct ledger lacks source group {event['source_group_id']}"
            )
        suffix = hashlib.sha256(event["event_id"].encode()).hexdigest()[:32]
        bridged = {
            "event_id": f"audio-candidate-prescreen:{suffix}",
            "sequence": sequence,
            "previous_event_sha256": prior,
            "reviewer_id": event["reviewer_id"],
            "source_group_id": event["source_group_id"],
            "family_id": None,
            "role": "external_prior_work",
            "exposure_categories": ["source_content", "preferred_evidence"],
            "exposed_at": event["first_exposed_at"],
            "recorded_at": event["recorded_at"],
            "artifact_references": [artifact_reference],
            "notes": (
                "Task194 human listening/semantic prescreen exposure; reviewer "
                "is barred from both blind source-search roles."
            ),
            "event_sha256": "",
        }
        bridged["event_sha256"] = exposure_event_hash(bridged)
        snapshot["events"].append(bridged)
        prior = bridged["event_sha256"]
        sequence += 1
    if audio_ledger["events"]:
        latest = max(item["recorded_at"] for item in audio_ledger["events"])
        if parse_datetime(latest) > parse_datetime(snapshot["captured_at"]):
            snapshot["captured_at"] = latest
    updated["pre_distribution_snapshot_sha256"] = exposure_snapshot_hash(snapshot)
    updated_assignments = copy.deepcopy(assignments)
    updated_assignments["pre_distribution_exposure_snapshot_sha256"] = updated[
        "pre_distribution_snapshot_sha256"
    ]
    validate_source_exposure_ledger(updated)
    validate_reviewer_assignment_ledger(updated_assignments)
    return updated, updated_assignments


def calibration_examples() -> list[dict[str, Any]]:
    return [
        {
            "schema_version": "1.0.0",
            "record_type": "audio_candidate_prescreen_calibration",
            "calibration_id": "task194.calibration.generic-utensil-impacts",
            "title": "Generic utensil impacts",
            "scenario": (
                "An audio-only interval contains several short metallic impacts. "
                "Synchronized video later shows a utensil contacting cookware."
            ),
            "reviewer_task": [
                "Describe and count only the impacts that can be heard.",
                "Do not infer a specific ingredient, recipe step, or outcome from generic impacts.",
                "Judge whether vision fully substitutes for the action identity.",
                "Check recurrence probes before deciding authoring eligibility.",
            ],
            "expected_reasoning": (
                "Concrete non-speech events may be present, but generic impacts "
                "often require object/action binding and may support REPAIR or "
                "NO_GO rather than a forced audio-bearing question."
            ),
            "not_a_human_decision": True,
            "not_source_media": True,
            "machine_label_or_answer": False,
            "h_tier_assigned": False,
        },
        {
            "schema_version": "1.0.0",
            "record_type": "audio_candidate_prescreen_calibration",
            "calibration_id": "task194.calibration.speech-dominated-interval",
            "title": "Speech-dominated interval",
            "scenario": (
                "An interval is dominated by intelligible speech while a faint "
                "background click or hum is also audible."
            ),
            "reviewer_task": [
                "Mark speech as dominant and transcriptive substitution risk as high.",
                "Do not treat the faint background event as answer-bearing without a concrete local fact.",
                "Use NO_GO when the candidate depends on speech rather than source-world non-speech audio.",
            ],
            "expected_reasoning": (
                "Pivot v2 excludes speech, music/score, applause, and generic "
                "noise from passing the non-speech-audio prescreen."
            ),
            "not_a_human_decision": True,
            "not_source_media": True,
            "machine_label_or_answer": False,
            "h_tier_assigned": False,
        },
    ]


def build_manifest(
    output: Path,
    packets: list[dict[str, Any]],
    forms: list[dict[str, Any]],
) -> dict[str, Any]:
    files = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "packet_manifest.json":
            files.append(
                {
                    "path": path.relative_to(output).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": file_hash(path),
                }
            )
    manifest = {
        "schema_version": "1.0.0",
        "record_type": "audio_candidate_prescreen_packet_manifest",
        "packet_set_id": "audio-candidate-prescreen-packets-v1",
        "generated_at": "2026-10-10T00:00:00+08:00",
        "packet_status": "DRAFT_NOT_DISTRIBUTABLE",
        "distribution_authorized": False,
        "adapter_execution_authorized": False,
        "candidate_count": len(packets),
        "calibration_count": 2,
        "human_identity_count": 0,
        "human_decision_count": 0,
        "human_review_occurred": False,
        "exposure_event_count": 0,
        "source_group_count": len(
            {packet["source_binding"]["source_group_id"] for packet in packets}
        ),
        "input_bindings": {
            "task193_facts": {
                "path": TASK193_FACTS.relative_to(ROOT).as_posix(),
                "sha256": file_hash(TASK193_FACTS),
            },
            "task193_source_bindings": {
                "path": TASK193_BINDINGS.relative_to(ROOT).as_posix(),
                "sha256": file_hash(TASK193_BINDINGS),
            },
            "pivot_v2": {
                "path": PIVOT_V2.relative_to(ROOT).as_posix(),
                "sha256": file_hash(PIVOT_V2),
            },
        },
        "candidate_bindings": [
            {
                "candidate_code": packet["candidate_code"],
                "packet_id": packet["packet_id"],
                "packet_payload_sha256": packet["packet_payload_sha256"],
                "form_id": form["form_id"],
                "source_id": packet["source_binding"]["source_id"],
                "source_group_id": packet["source_binding"]["source_group_id"],
            }
            for packet, form in zip(packets, forms, strict=True)
        ],
        "files": files,
        "scope": {
            "media_embedded": False,
            "machine_labels_in_reviewer_packets": False,
            "machine_ranks_in_reviewer_packets": False,
            "proposed_answers_in_reviewer_packets": False,
            "identities_created": False,
            "decisions_created": False,
            "necessity_assigned": False,
            "minimality_assigned": False,
            "h1_assigned": False,
            "h2_assigned": False,
        },
        "manifest_sha256": "",
    }
    manifest["manifest_sha256"] = object_hash(
        {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    )
    return manifest


def readme() -> str:
    return """# Audio candidate prescreen packets v1

Task194 creates four reviewer-blind, non-distributable human listening and
semantic-prescreen packets. Each packet exposes a fixed source interval first
as audio-only, then as synchronized A/V, followed by three bounded audio-only
recurrence probes. The packet contains adapter requests only: no media is
embedded and execution is not authorized.

Reviewers must independently identify and count events, judge the grounded
source-world fact, assess speech/music/vision/text substitution, recurrence,
privacy, safety, and authoring eligibility. Candidate packets contain no
machine labels, CLAP ranks/scores, proposed question, proposed answer, or
proposed profile.

Any human exposure must be recorded at source-group level and bridged into the
construct-validity source exposure ledger before assignments are frozen. The
prescreener is thereafter ineligible for blind alternative-evidence finder and
blind post-adjudication saturation-auditor roles for that source group.

Blank imports intentionally return
`AUDIO_CANDIDATE_PRESCREEN_PACKETS_REPAIR`. No identity, human decision,
necessity/minimality result, H tier, Gate-A result, or authorization is present.
"""


def candidate_readme(packet: dict[str, Any]) -> str:
    code = packet["candidate_code"]
    return f"""# Candidate {code}

Use only `candidate_packet.json` and `reviewer_form.json` during candidate
review. Execute adapter requests outside this repository only after separate
authorization; do not persist extracted media.

Required order:

1. audio-only focal interval;
2. synchronized A/V focal interval;
3. three audio-only recurrence probes.

Do not reveal Task193 labels, retrieval concepts, ranks, scores, proposed
question, proposed answer, or proposed modality profile. Record exposure in
the source-level ledger. This blank packet contains no human result.
"""


def generate(output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    facts = selected_facts()
    bindings = source_bindings()
    packets = [
        build_packet(code, facts[code], bindings[facts[code]["source_ref"]])
        for code in sorted(facts)
    ]
    forms = [build_form(packet) for packet in packets]
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, mode=0o700)
    os.chmod(output, 0o700)
    write_text(output / "README.md", readme())
    for packet, form in zip(packets, forms, strict=True):
        directory = output / "candidates" / packet["candidate_code"]
        write_text(directory / "README.md", candidate_readme(packet))
        write_json(directory / "candidate_packet.json", packet)
        write_json(directory / "reviewer_form.json", form)
        report, _ = evaluate(packet, form)
        write_json(directory / "blank_import.json", report)
    for index, calibration in enumerate(calibration_examples(), start=1):
        write_json(output / "calibrations" / f"calibration_{index:02d}.json", calibration)
    exposure_ledger = build_exposure_ledger(packets, forms)
    validate_exposure_ledger(exposure_ledger)
    construct_exposure, assignments = blank_construct_ledgers(packets)
    write_json(output / "coordinator" / "blank_prescreener_exposure_ledger.json", exposure_ledger)
    write_json(output / "coordinator" / "source_exposure_ledger.json", construct_exposure)
    write_json(output / "coordinator" / "reviewer_assignments.json", assignments)
    manifest = build_manifest(output, packets, forms)
    write_json(output / "coordinator" / "packet_manifest.json", manifest)
    chmod_tree(output)
    return manifest


def chmod_tree(output: Path) -> None:
    for directory in [output, *[p for p in output.rglob("*") if p.is_dir()]]:
        os.chmod(directory, 0o700)
    for path in output.rglob("*"):
        if path.is_file():
            os.chmod(path, 0o600)


def verify(output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    errors: list[str] = []
    try:
        for schema in (PACKET_SCHEMA, FORM_SCHEMA, IMPORT_SCHEMA):
            Draft202012Validator.check_schema(read_json(schema))
        manifest = read_json(output / "coordinator" / "packet_manifest.json")
        expected_manifest_hash = object_hash(
            {k: v for k, v in manifest.items() if k != "manifest_sha256"}
        )
        if manifest["manifest_sha256"] != expected_manifest_hash:
            errors.append("MANIFEST_HASH_MISMATCH")
        if manifest["human_identity_count"] != 0:
            errors.append("IDENTITY_COUNT_NONZERO")
        if manifest["human_decision_count"] != 0:
            errors.append("HUMAN_DECISION_COUNT_NONZERO")
        if manifest["exposure_event_count"] != 0:
            errors.append("EXPOSURE_EVENT_COUNT_NONZERO")
        if manifest["input_bindings"]["task193_facts"]["sha256"] != file_hash(
            TASK193_FACTS
        ):
            errors.append("TASK193_FACTS_BINDING_MISMATCH")
        if manifest["input_bindings"]["task193_source_bindings"][
            "sha256"
        ] != file_hash(TASK193_BINDINGS):
            errors.append("TASK193_SOURCE_BINDING_MISMATCH")
        if manifest["input_bindings"]["pivot_v2"]["sha256"] != file_hash(PIVOT_V2):
            errors.append("PIVOT_V2_BINDING_MISMATCH")
        packets, forms = [], []
        for binding in manifest["candidate_bindings"]:
            directory = output / "candidates" / binding["candidate_code"]
            packet = read_json(directory / "candidate_packet.json")
            form = read_json(directory / "reviewer_form.json")
            validate_packet(packet)
            validate_form(form, packet)
            report, ledger = evaluate(packet, form)
            if report["readiness_token"] != REPAIR:
                errors.append(f"{binding['candidate_code']}:BLANK_IMPORT_NOT_REPAIR")
            if report["completion_status"] != "incomplete":
                errors.append(f"{binding['candidate_code']}:BLANK_IMPORT_NOT_INCOMPLETE")
            if ledger["events"]:
                errors.append(f"{binding['candidate_code']}:BLANK_EXPOSURE_NONEMPTY")
            if report != read_json(directory / "blank_import.json"):
                errors.append(f"{binding['candidate_code']}:BLANK_IMPORT_MISMATCH")
            packets.append(packet)
            forms.append(form)
        exposure = read_json(
            output / "coordinator" / "blank_prescreener_exposure_ledger.json"
        )
        validate_exposure_ledger(exposure)
        if exposure["events"]:
            errors.append("BLANK_PRESCREENER_EXPOSURE_NONEMPTY")
        construct_exposure = read_json(
            output / "coordinator" / "source_exposure_ledger.json"
        )
        assignments = read_json(
            output / "coordinator" / "reviewer_assignments.json"
        )
        validate_source_exposure_ledger(construct_exposure)
        validate_reviewer_assignment_ledger(assignments)
        if any(
            assignment["reviewer_id"] is not None
            or assignment["assigned_at"] is not None
            for assignment in assignments["assignments"]
        ):
            errors.append("BLANK_ASSIGNMENT_HAS_IDENTITY")
        if construct_exposure["pre_distribution_snapshot"]["events"]:
            errors.append("BLANK_CONSTRUCT_EXPOSURE_NONEMPTY")
        for item in manifest["files"]:
            path = output / item["path"]
            if not path.is_file():
                errors.append(f"MISSING_FILE:{item['path']}")
                continue
            if file_hash(path) != item["sha256"]:
                errors.append(f"FILE_HASH_MISMATCH:{item['path']}")
            if path.stat().st_mode & 0o077:
                errors.append(f"FILE_PERMISSION_TOO_OPEN:{item['path']}")
        for directory in [output, *[p for p in output.rglob("*") if p.is_dir()]]:
            if directory.stat().st_mode & 0o077:
                errors.append(
                    f"DIRECTORY_PERMISSION_TOO_OPEN:{directory.relative_to(output)}"
                )
        expected_paths = {
            path.relative_to(output).as_posix()
            for path in output.rglob("*")
            if path.is_file() and path.name != "packet_manifest.json"
        }
        if expected_paths != {item["path"] for item in manifest["files"]}:
            errors.append("MANIFEST_FILE_SET_MISMATCH")
    except (AudioCandidatePacketError, KeyError, TypeError, OSError) as exc:
        errors.append(f"VALIDATION_EXCEPTION:{exc}")
    return {
        "readiness_token": READY if not errors else REPAIR,
        "errors": sorted(set(errors)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if not args.generate and not args.verify:
        parser.error("choose --generate and/or --verify")
    if args.generate:
        generate(args.output)
    result = verify(args.output) if args.verify else {"readiness_token": READY, "errors": []}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["readiness_token"] == READY else 1


if __name__ == "__main__":
    raise SystemExit(main())
