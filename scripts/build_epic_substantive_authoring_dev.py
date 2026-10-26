#!/usr/bin/env python3
"""Build Task 167's development-only substantive EPIC authoring registry.

The authored semantics in this file come only from Task 166's machine leads,
the canonical local Whisper/AST/CLIP/OpenCV index, and bounded inspection of
the two local raw videos. The script has no annotation-vault input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "av-trace.epic-substantive-authoring-dev/1.0"
ARTIFACT_CLASS = "MACHINE_EXPERT_PROVISIONAL_DEVELOPMENT_ONLY"
DECISION = "EPIC_SUBSTANTIVE_DEV_READY"
DEFAULT_OUTPUT = Path(
    "data/restricted/epic_family_candidates_v2_dev/candidate_registry.json"
)
V1_REGISTRY = Path(
    "data/restricted/epic_family_candidates_v1_dev/candidate_registry.json"
)
INDEX_ROOT = Path("data/restricted/epic_wave1_index_v1")
MEDIA_PATHS = {
    "P27_101": Path(
        "data/restricted/epic_wave1_sources_v1/media/P27/P27_101.MP4"
    ),
    "P28_103": Path(
        "data/restricted/epic_wave1_sources_v1/media/P28/P28_103.MP4"
    ),
}
SOURCE_GROUPS = {"P27_101": "P27", "P28_103": "P28"}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def json_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def interval(start_s: float, end_s: float) -> dict[str, float]:
    return {"start_s": start_s, "end_s": end_s}


def evidence(
    evidence_id: str,
    start_s: float,
    end_s: float,
    modality: str,
    carrier_class: str,
    observation: str,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "interval": interval(start_s, end_s),
        "modality": modality,
        "carrier_class": carrier_class,
        "observation": observation,
        "semantic_basis": (
            "bounded_local_raw_media_machine_expert_inspection"
        ),
        "human_semantic_validation_status": "NOT_PERFORMED",
        "record_references": [],
    }


def claim(claim_id: str, text: str) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "text": text,
        "status": ARTIFACT_CLASS,
        "human_validated": False,
    }


def ses(
    ses_id: str,
    evidence_ids: list[str],
    claim_ids: list[str],
    sufficiency_hypothesis: str,
    minimality_hypothesis: str,
) -> dict[str, Any]:
    return {
        "ses_id": ses_id,
        "status": (
            "MACHINE_EXPERT_PROVISIONAL_DEVELOPMENT_ONLY_NOT_ACCEPTED"
        ),
        "evidence_ids": evidence_ids,
        "claim_ids": claim_ids,
        "sufficiency_hypothesis": sufficiency_hypothesis,
        "minimality_hypothesis": minimality_hypothesis,
        "leave_one_out_executed": False,
        "human_validator_count": 0,
        "accepted": False,
    }


def route(
    route_id: str,
    route_type: str,
    description: str,
    status: str = "OPEN_REQUIRES_HUMAN_FULL_SOURCE_VALIDATION",
) -> dict[str, str]:
    return {
        "route_id": route_id,
        "route_type": route_type,
        "description": description,
        "status": status,
    }


COMMON_HUMAN_REQUIREMENTS = [
    "trained-human Task-153 semantic source prescreen for the source",
    "frame-accurate review of every cited interval against the full-resolution source",
    "human listening review for every audio-bearing evidence hypothesis",
    "full-source recurrence and near-duplicate search",
    "OCR, package-label, transcript, ASR, and narration-substitute challenge",
    "participant-lineage and kitchen-identity leakage review",
    "independent SES sufficiency and leave-one-out minimality validation",
    "blind alternative-route search and post-adjudication saturation audit",
]


def proposals() -> list[dict[str, Any]]:
    return [
        {
            "proposal_id": "EPIC-DEV-P27-CLEANER-FROM-CUPBOARD",
            "source_id": "P27_101",
            "source_group_id": "P27",
            "origin": {
                "kind": "TASK166_LEAD",
                "candidate_lead_id": "epic.lead.4c60d048f41a9e26",
            },
            "disposition": "KEEP",
            "disposition_rationale": (
                "The bounded sequence supports a concrete object-retrieval "
                "question, although recurrence and product-appearance routes "
                "remain open."
            ),
            "question": (
                "After opening the lower cupboard beside the sink, what item "
                "does the wearer bring back toward the stove?"
            ),
            "answer": "A pink-and-blue spray bottle of cleaner.",
            "qa_status": ARTIFACT_CLASS,
            "primary_interval": interval(1204.0, 1212.0),
            "hop_structure": {
                "hop_stratum": "one_hop",
                "temporal_stratum": "near_local",
                "composition": None,
            },
            "atomic_claims": [
                claim(
                    "c.p27.cleaner.1",
                    "The wearer opens the lower cupboard beside the sink.",
                ),
                claim(
                    "c.p27.cleaner.2",
                    "The wearer retrieves a pink-and-blue spray-cleaner bottle "
                    "and returns it toward the stove.",
                ),
            ],
            "evidence_graph": {
                "evidence_units": [
                    evidence(
                        "e.p27.cleaner.v1",
                        1205.5,
                        1212.0,
                        "vision",
                        "dynamic_nontext_visual",
                        "The wearer opens the lower cupboard, reaches inside, "
                        "takes a pink-and-blue spray bottle, and returns toward "
                        "the hob.",
                    )
                ],
                "support_map": [
                    {
                        "evidence_id": "e.p27.cleaner.v1",
                        "claim_ids": [
                            "c.p27.cleaner.1",
                            "c.p27.cleaner.2",
                        ],
                    }
                ],
            },
            "modality_assessment": {
                "dynamic_visual": "PRIMARY_PROVISIONAL",
                "non_speech_audio": (
                    "CORROBORATING_ONLY_AST_DOOR_SLAM_CUPBOARD_HYPOTHESES"
                ),
                "speech": "NO_RELIABLE_SPEECH",
                "board_ocr_static_overlay": "NO_PRIMARY_ROLE",
                "environmental_audio": "HUMAN_LISTENING_REQUIRED",
            },
            "provisional_ses_ledger": [
                ses(
                    "ses.p27.cleaner.v1",
                    ["e.p27.cleaner.v1"],
                    ["c.p27.cleaner.1", "c.p27.cleaner.2"],
                    "The bounded visual sequence appears sufficient for the "
                    "retrieved-object answer.",
                    "Unvalidated; object appearance and repeated cleaning "
                    "sequences may provide substitutes.",
                )
            ],
            "alternative_route_ledger": [
                route(
                    "alt.p27.cleaner.repeat",
                    "same_source_recurrence",
                    "The later 1252-1268 cleaning/cupboard sequence may reveal "
                    "the same products and action context.",
                ),
                route(
                    "alt.p27.cleaner.appearance",
                    "question_only_or_single_frame_shortcut",
                    "Distinctive bottle colors and package appearance may make "
                    "the temporal opening/retrieval sequence unnecessary.",
                ),
                route(
                    "alt.p27.cleaner.audio",
                    "non_speech_audio",
                    "AST door/slam/cupboard observations may locate the event "
                    "but do not identify the retrieved bottle.",
                    "BOUNDED_MACHINE_REVIEW_SUGGESTS_PARTIAL_ONLY",
                ),
            ],
        },
        {
            "proposal_id": "EPIC-DEV-P27-LONG-HANDLED-CLEANING-TOOL",
            "source_id": "P27_101",
            "source_group_id": "P27",
            "origin": {
                "kind": "TASK166_LEAD",
                "candidate_lead_id": "epic.lead.b8cb83fc059ba74e",
            },
            "disposition": "REJECT",
            "disposition_rationale": (
                "A question can be drafted, but the event is part of the same "
                "cleaning/cupboard cluster as the retained P27 lead and the "
                "tool identity remains too visually underspecified."
            ),
            "question": (
                "What long-handled item does the wearer remove from the lower "
                "cupboard before leaving the sink area?"
            ),
            "answer": "A green-and-pink long-handled cleaning tool.",
            "qa_status": (
                "MACHINE_EXPERT_PROVISIONAL_DEVELOPMENT_ONLY_REJECTED_DRAFT"
            ),
            "primary_interval": interval(1260.0, 1268.0),
            "hop_structure": {
                "hop_stratum": "one_hop",
                "temporal_stratum": "near_local",
                "composition": None,
            },
            "atomic_claims": [
                claim(
                    "c.p27.tool.1",
                    "The wearer opens the lower cupboard and removes a "
                    "green-and-pink long-handled cleaning tool.",
                )
            ],
            "evidence_graph": {
                "evidence_units": [
                    evidence(
                        "e.p27.tool.v1",
                        1261.0,
                        1267.0,
                        "vision",
                        "dynamic_nontext_visual",
                        "The cupboard opens and a green-and-pink long-handled "
                        "cleaning item is removed before the wearer walks away.",
                    )
                ],
                "support_map": [
                    {
                        "evidence_id": "e.p27.tool.v1",
                        "claim_ids": ["c.p27.tool.1"],
                    }
                ],
            },
            "modality_assessment": {
                "dynamic_visual": "PRIMARY_BUT_UNDERSPECIFIED",
                "non_speech_audio": "DOOR_CUPBOARD_ONLY_NOT_OBJECT_IDENTITY",
                "speech": "NO_RELIABLE_SPEECH",
                "board_ocr_static_overlay": "NO_PRIMARY_ROLE",
                "environmental_audio": "HUMAN_LISTENING_REQUIRED",
            },
            "provisional_ses_ledger": [
                ses(
                    "ses.p27.tool.v1",
                    ["e.p27.tool.v1"],
                    ["c.p27.tool.1"],
                    "The visual sequence supports a generic long-handled "
                    "cleaning-tool answer.",
                    "Not pursued because the candidate is rejected as "
                    "duplicate-prone and semantically underspecified.",
                )
            ],
            "alternative_route_ledger": [
                route(
                    "alt.p27.tool.cluster",
                    "same_source_recurrence",
                    "The retained 1204-1212 cupboard/cleaner lead and the wider "
                    "cleaning sequence disclose the same task context.",
                ),
                route(
                    "alt.p27.tool.single_frame",
                    "single_frame_shortcut",
                    "A single frame after removal may show the colored tool "
                    "without requiring the cupboard action.",
                ),
            ],
        },
        {
            "proposal_id": "EPIC-DEV-P28-DRY-HANDS-WITH-TOWEL",
            "source_id": "P28_103",
            "source_group_id": "P28",
            "origin": {
                "kind": "TASK166_LEAD",
                "candidate_lead_id": "epic.lead.d8480ee4d0ed5d4d",
            },
            "disposition": "KEEP",
            "disposition_rationale": (
                "Narrowing to the final part of the lead yields a concrete "
                "post-sink action distinct from the recurrent water sound."
            ),
            "question": (
                "After moving away from the sink, what does the wearer use on "
                "both hands?"
            ),
            "answer": "A white towel.",
            "qa_status": ARTIFACT_CLASS,
            "primary_interval": interval(32.0, 40.0),
            "hop_structure": {
                "hop_stratum": "one_hop",
                "temporal_stratum": "near_local",
                "composition": None,
            },
            "atomic_claims": [
                claim(
                    "c.p28.towel.1",
                    "The wearer leaves the sink and dries or wipes both hands "
                    "with a white towel.",
                )
            ],
            "evidence_graph": {
                "evidence_units": [
                    evidence(
                        "e.p28.towel.v1",
                        36.5,
                        39.5,
                        "vision",
                        "dynamic_nontext_visual",
                        "A white towel is held around and moved over both hands "
                        "after the wearer steps away from the sink.",
                    )
                ],
                "support_map": [
                    {
                        "evidence_id": "e.p28.towel.v1",
                        "claim_ids": ["c.p28.towel.1"],
                    }
                ],
            },
            "modality_assessment": {
                "dynamic_visual": "PRIMARY_PROVISIONAL",
                "non_speech_audio": (
                    "WATER_AST_PRECEDES_ANSWER_ACTION_AND_IS_NOT_SUFFICIENT"
                ),
                "speech": "NO_RELIABLE_SPEECH",
                "board_ocr_static_overlay": "NO_PRIMARY_ROLE",
                "environmental_audio": "HUMAN_LISTENING_REQUIRED",
            },
            "provisional_ses_ledger": [
                ses(
                    "ses.p28.towel.v1",
                    ["e.p28.towel.v1"],
                    ["c.p28.towel.1"],
                    "The narrowed visual interval appears sufficient for the "
                    "towel answer.",
                    "Unvalidated; a single clear frame may be sufficient and "
                    "therefore the sequence may not be minimal as drafted.",
                )
            ],
            "alternative_route_ledger": [
                route(
                    "alt.p28.towel.single_frame",
                    "single_frame_shortcut",
                    "A still image of the towel around both hands may answer "
                    "without the preceding sink context.",
                ),
                route(
                    "alt.p28.towel.repeat",
                    "same_source_recurrence",
                    "Other sink and hand-drying sequences must be searched in "
                    "the full source by a blinded reviewer.",
                ),
            ],
        },
        {
            "proposal_id": "EPIC-DEV-P28-YELLOW-PACKET-AFTER-RINSE",
            "source_id": "P28_103",
            "source_group_id": "P28",
            "origin": {
                "kind": "TASK166_LEAD",
                "candidate_lead_id": "epic.lead.8f2a283d462000e4",
            },
            "disposition": "REJECT",
            "disposition_rationale": (
                "The drafted answer is visible, but the lead repeats the "
                "source's sink/water cluster and depends on an OCR/package-"
                "appearance-prone object."
            ),
            "question": (
                "Immediately after the rinsing motion at the sink, what does "
                "the wearer lift from the counter?"
            ),
            "answer": "A yellow food packet.",
            "qa_status": (
                "MACHINE_EXPERT_PROVISIONAL_DEVELOPMENT_ONLY_REJECTED_DRAFT"
            ),
            "primary_interval": interval(496.0, 504.0),
            "hop_structure": {
                "hop_stratum": "one_hop",
                "temporal_stratum": "near_local",
                "composition": None,
            },
            "atomic_claims": [
                claim(
                    "c.p28.packet.1",
                    "The wearer performs a rinsing motion at the sink and then "
                    "lifts a yellow food packet from the counter.",
                )
            ],
            "evidence_graph": {
                "evidence_units": [
                    evidence(
                        "e.p28.packet.v1",
                        496.5,
                        504.0,
                        "vision",
                        "dynamic_nontext_visual",
                        "The wearer approaches the sink, performs a rinsing "
                        "motion, and then lifts a yellow packet.",
                    )
                ],
                "support_map": [
                    {
                        "evidence_id": "e.p28.packet.v1",
                        "claim_ids": ["c.p28.packet.1"],
                    }
                ],
            },
            "modality_assessment": {
                "dynamic_visual": "PRIMARY_BUT_REJECTED",
                "non_speech_audio": "RECURRENT_WATER_ROUTE",
                "speech": "NO_RELIABLE_SPEECH",
                "board_ocr_static_overlay": "PACKAGE_TEXT_RISK",
                "environmental_audio": "HUMAN_LISTENING_REQUIRED",
            },
            "provisional_ses_ledger": [
                ses(
                    "ses.p28.packet.v1",
                    ["e.p28.packet.v1"],
                    ["c.p28.packet.1"],
                    "The visual sequence appears sufficient for a generic "
                    "yellow-packet answer.",
                    "Not pursued because the source repeats sink activity and "
                    "package appearance creates a strong shortcut.",
                )
            ],
            "alternative_route_ledger": [
                route(
                    "alt.p28.packet.water_repeat",
                    "same_source_recurrence",
                    "The source contains many water/sink intervals, including "
                    "32-40, 252-268, 520-528, and 1752-1772 seconds.",
                ),
                route(
                    "alt.p28.packet.ocr",
                    "ocr_or_package_identity",
                    "Readable branding or distinctive package appearance may "
                    "answer without the rinsing sequence.",
                ),
            ],
        },
        {
            "proposal_id": "EPIC-DEV-P27-UNWRAP-FROZEN-ITEM",
            "source_id": "P27_101",
            "source_group_id": "P27",
            "origin": {
                "kind": "TASK167_FULL_TIMELINE_ADDITIONAL_LEAD",
                "selection_basis": (
                    "AST crumpling/crinkling peak plus bounded frame review"
                ),
            },
            "disposition": "KEEP",
            "disposition_rationale": (
                "This sequence is distinct from dishwashing and cupboard "
                "cleaning and has a temporally aligned crinkling hypothesis."
            ),
            "question": (
                "Where does the wearer get the small item, and what do they "
                "do to it before walking back toward the sink?"
            ),
            "answer": (
                "They take it from the freezer and peel off or open its "
                "wrapper."
            ),
            "qa_status": ARTIFACT_CLASS,
            "primary_interval": interval(1284.0, 1301.0),
            "hop_structure": {
                "hop_stratum": "multi_hop",
                "temporal_stratum": "near_local",
                "composition": {
                    "operator": "visible_action_then_resulting_state",
                    "component_1_interval": interval(1284.0, 1290.0),
                    "component_2_interval": interval(1292.0, 1299.5),
                    "minimum_nonoverlap_gap_s": 2.0,
                    "composed_claim": (
                        "The item removed from cold storage is the same item "
                        "whose wrapper is opened before the wearer leaves."
                    ),
                    "semantic_relation_human_validated": False,
                },
            },
            "atomic_claims": [
                claim(
                    "c.p27.wrapper.1",
                    "The wearer removes a small wrapped item from the freezer.",
                ),
                claim(
                    "c.p27.wrapper.2",
                    "The wearer peels or opens the item's wrapper before "
                    "walking away.",
                ),
            ],
            "evidence_graph": {
                "evidence_units": [
                    evidence(
                        "e.p27.wrapper.v1",
                        1284.0,
                        1290.0,
                        "vision",
                        "dynamic_nontext_visual",
                        "The freezer drawer is open and a small wrapped item is "
                        "removed.",
                    ),
                    evidence(
                        "e.p27.wrapper.v2",
                        1292.0,
                        1299.5,
                        "vision",
                        "dynamic_nontext_visual",
                        "The wearer manipulates and peels away the wrapper.",
                    ),
                    evidence(
                        "e.p27.wrapper.a1",
                        1292.0,
                        1300.0,
                        "audio",
                        "non_speech_machine_hypothesis",
                        "AST assigns crumpling/crinkling with a peak weight of "
                        "0.40372; human listening has not been performed.",
                    ),
                ],
                "support_map": [
                    {
                        "evidence_id": "e.p27.wrapper.v1",
                        "claim_ids": ["c.p27.wrapper.1"],
                    },
                    {
                        "evidence_id": "e.p27.wrapper.v2",
                        "claim_ids": ["c.p27.wrapper.2"],
                    },
                    {
                        "evidence_id": "e.p27.wrapper.a1",
                        "claim_ids": ["c.p27.wrapper.2"],
                        "role": "corroborating_only",
                    },
                ],
            },
            "modality_assessment": {
                "dynamic_visual": "PRIMARY_PROVISIONAL",
                "non_speech_audio": "PLAUSIBLE_CORROBORATING_CRINKLE",
                "speech": "NO_RELIABLE_SPEECH",
                "board_ocr_static_overlay": "WRAPPER_TEXT_RISK",
                "environmental_audio": "HUMAN_LISTENING_REQUIRED",
            },
            "provisional_ses_ledger": [
                ses(
                    "ses.p27.wrapper.v12",
                    ["e.p27.wrapper.v1", "e.p27.wrapper.v2"],
                    ["c.p27.wrapper.1", "c.p27.wrapper.2"],
                    "Both separated visual components support the composed "
                    "freezer-to-unwrapping relation.",
                    "Plausible but unvalidated; v2 may answer the action while "
                    "v1 is required for the source-location part of the "
                    "question.",
                ),
                ses(
                    "ses.p27.wrapper.va",
                    ["e.p27.wrapper.v1", "e.p27.wrapper.a1"],
                    ["c.p27.wrapper.1", "c.p27.wrapper.2"],
                    "The freezer retrieval plus a human-confirmed wrapper "
                    "sound could form an alternative route.",
                    "Audio sufficiency is unresolved and cannot be accepted "
                    "without human listening.",
                ),
            ],
            "alternative_route_ledger": [
                route(
                    "alt.p27.wrapper.visual_only",
                    "visual_alternative",
                    "The wrapper manipulation may be visually sufficient "
                    "without audio.",
                ),
                route(
                    "alt.p27.wrapper.audio_only",
                    "audio_alternative",
                    "Crinkling may indicate packaging but cannot identify that "
                    "the same item came from the freezer.",
                    "BOUNDED_MACHINE_REVIEW_SUGGESTS_INSUFFICIENT_ALONE",
                ),
                route(
                    "alt.p27.wrapper.ocr",
                    "ocr_or_package_identity",
                    "Wrapper text or package appearance may leak the object or "
                    "action context.",
                ),
            ],
        },
        {
            "proposal_id": "EPIC-DEV-P28-PEEL-POTATO",
            "source_id": "P28_103",
            "source_group_id": "P28",
            "origin": {
                "kind": "TASK167_FULL_TIMELINE_ADDITIONAL_LEAD",
                "selection_basis": (
                    "AST scissors peak plus CLIP food-preparation retrieval "
                    "and bounded frame review"
                ),
            },
            "disposition": "KEEP",
            "disposition_rationale": (
                "The direct visual sequence is a distinct preparation action. "
                "It also demonstrates that the AST scissors class is a routing "
                "error rather than semantic evidence."
            ),
            "question": (
                "What preparation does the wearer apply to the potato while "
                "the other vegetables remain on the blue board?"
            ),
            "answer": "Peels it with a handheld peeler.",
            "qa_status": ARTIFACT_CLASS,
            "primary_interval": interval(196.0, 212.0),
            "hop_structure": {
                "hop_stratum": "one_hop",
                "temporal_stratum": "near_local",
                "composition": None,
            },
            "atomic_claims": [
                claim(
                    "c.p28.peel.1",
                    "The wearer repeatedly draws a handheld peeler over a "
                    "potato while other vegetables remain on the board.",
                )
            ],
            "evidence_graph": {
                "evidence_units": [
                    evidence(
                        "e.p28.peel.v1",
                        196.0,
                        211.5,
                        "vision",
                        "dynamic_nontext_visual",
                        "Repeated strokes remove the potato skin with a "
                        "handheld peeler.",
                    ),
                    evidence(
                        "e.p28.peel.a1",
                        196.0,
                        212.0,
                        "audio",
                        "non_speech_machine_hypothesis_rejected",
                        "AST strongly predicts scissors, but the bounded frames "
                        "show peeling; the class is not used as answer evidence.",
                    ),
                ],
                "support_map": [
                    {
                        "evidence_id": "e.p28.peel.v1",
                        "claim_ids": ["c.p28.peel.1"],
                    }
                ],
            },
            "modality_assessment": {
                "dynamic_visual": "PRIMARY_PROVISIONAL",
                "non_speech_audio": "AST_SCISSORS_FALSE_POSITIVE",
                "speech": "NO_RELIABLE_SPEECH",
                "board_ocr_static_overlay": "NO_PRIMARY_ROLE",
                "environmental_audio": "HUMAN_LISTENING_REQUIRED",
            },
            "provisional_ses_ledger": [
                ses(
                    "ses.p28.peel.v1",
                    ["e.p28.peel.v1"],
                    ["c.p28.peel.1"],
                    "The visual action appears sufficient for peeling.",
                    "Unvalidated; a shorter subinterval or still-image object "
                    "shortcut may be sufficient.",
                )
            ],
            "alternative_route_ledger": [
                route(
                    "alt.p28.peel.single_frame",
                    "single_frame_shortcut",
                    "A clear still showing peeler contact may answer without "
                    "the repeated stroke sequence.",
                ),
                route(
                    "alt.p28.peel.ast",
                    "machine_label_route",
                    "The AST scissors label conflicts with the visual action "
                    "and is rejected as semantic support.",
                    "REJECTED_BY_BOUNDED_FRAME_INSPECTION",
                ),
                route(
                    "alt.p28.peel.repeat",
                    "same_source_recurrence",
                    "Other vegetable-peeling or cutting sequences require a "
                    "blind full-source duplicate search.",
                ),
            ],
        },
        {
            "proposal_id": "EPIC-DEV-P28-ADD-ADJUST-STIR",
            "source_id": "P28_103",
            "source_group_id": "P28",
            "origin": {
                "kind": "TASK167_FULL_TIMELINE_ADDITIONAL_LEAD",
                "selection_basis": (
                    "whole-source AST frying/sizzle/stir peak plus bounded "
                    "frame review"
                ),
            },
            "disposition": "KEEP",
            "disposition_rationale": (
                "This is a coherent, temporally ordered cooking sequence with "
                "a strong non-speech cooking-sound hypothesis and a concrete "
                "intervening control action."
            ),
            "question": (
                "What sequence links the bowl of chopped vegetables to the "
                "next round of stirring?"
            ),
            "answer": (
                "The wearer tips the vegetables into the saucepan, adjusts a "
                "stove burner control knob, and then resumes stirring."
            ),
            "qa_status": ARTIFACT_CLASS,
            "primary_interval": interval(938.0, 960.0),
            "hop_structure": {
                "hop_stratum": "multi_hop",
                "temporal_stratum": "near_local",
                "composition": {
                    "operator": "visible_action_then_resulting_state",
                    "component_intervals": [
                        interval(938.0, 944.5),
                        interval(949.5, 954.5),
                        interval(955.0, 959.5),
                    ],
                    "minimum_nonoverlap_gap_s": 0.5,
                    "composed_claim": (
                        "The knob adjustment occurs between adding the "
                        "vegetables and the resumed stirring."
                    ),
                    "semantic_relation_human_validated": False,
                },
            },
            "atomic_claims": [
                claim(
                    "c.p28.cook.1",
                    "The wearer tips chopped vegetables from a bowl into a "
                    "saucepan.",
                ),
                claim(
                    "c.p28.cook.2",
                    "The wearer adjusts a stove burner control knob.",
                ),
                claim(
                    "c.p28.cook.3",
                    "The wearer resumes stirring the saucepan after the knob "
                    "adjustment.",
                ),
            ],
            "evidence_graph": {
                "evidence_units": [
                    evidence(
                        "e.p28.cook.v1",
                        938.0,
                        944.5,
                        "vision",
                        "dynamic_nontext_visual",
                        "Chopped vegetables are tipped from a bowl into the "
                        "saucepan.",
                    ),
                    evidence(
                        "e.p28.cook.v2",
                        949.5,
                        954.5,
                        "vision",
                        "dynamic_nontext_visual",
                        "The wearer's hand turns a stove control knob.",
                    ),
                    evidence(
                        "e.p28.cook.v3",
                        955.0,
                        959.5,
                        "vision",
                        "dynamic_nontext_visual",
                        "The wearer returns to stirring the saucepan.",
                    ),
                    evidence(
                        "e.p28.cook.a1",
                        940.0,
                        960.0,
                        "audio",
                        "non_speech_machine_hypothesis",
                        "Across overlapping windows AST assigns frying, "
                        "sizzle, and stir with peak weights 0.89492, 0.78190, "
                        "and 0.92433; human listening has not been performed.",
                    ),
                ],
                "support_map": [
                    {
                        "evidence_id": "e.p28.cook.v1",
                        "claim_ids": ["c.p28.cook.1"],
                    },
                    {
                        "evidence_id": "e.p28.cook.v2",
                        "claim_ids": ["c.p28.cook.2"],
                    },
                    {
                        "evidence_id": "e.p28.cook.v3",
                        "claim_ids": ["c.p28.cook.3"],
                    },
                    {
                        "evidence_id": "e.p28.cook.a1",
                        "claim_ids": ["c.p28.cook.1", "c.p28.cook.3"],
                        "role": "corroborating_only",
                    },
                ],
            },
            "modality_assessment": {
                "dynamic_visual": "PRIMARY_PROVISIONAL",
                "non_speech_audio": (
                    "STRONG_PLAUSIBLE_FRYING_SIZZLE_STIR_CORROBORATION"
                ),
                "speech": "NO_RELIABLE_SPEECH",
                "board_ocr_static_overlay": "NO_PRIMARY_ROLE",
                "environmental_audio": "HUMAN_LISTENING_REQUIRED",
            },
            "provisional_ses_ledger": [
                ses(
                    "ses.p28.cook.v123",
                    ["e.p28.cook.v1", "e.p28.cook.v2", "e.p28.cook.v3"],
                    [
                        "c.p28.cook.1",
                        "c.p28.cook.2",
                        "c.p28.cook.3",
                    ],
                    "The three separated visual components support the "
                    "ordered intervening-control answer.",
                    "Plausible but unvalidated; the middle knob frame may "
                    "be over-weighted unless all three sequence claims are "
                    "jointly enforced.",
                )
            ],
            "alternative_route_ledger": [
                route(
                    "alt.p28.cook.middle_only",
                    "single_component_shortcut",
                    "A model may name the knob from the middle component while "
                    "failing to recover the full add-adjust-stir sequence.",
                ),
                route(
                    "alt.p28.cook.audio",
                    "non_speech_audio",
                    "Frying/sizzle audio can establish ongoing cooking but "
                    "cannot identify the adjusted control.",
                    "BOUNDED_MACHINE_REVIEW_SUGGESTS_PARTIAL_ONLY",
                ),
                route(
                    "alt.p28.cook.repeat",
                    "same_source_recurrence",
                    "The source contains repeated stirring/frying windows near "
                    "1080-1104, 1296-1336, and 1472-1500 seconds.",
                ),
            ],
        },
    ]


def overlap(left: dict[str, float], right: dict[str, Any]) -> bool:
    return max(left["start_s"] * 1_000_000, int(right["start_us"])) < min(
        left["end_s"] * 1_000_000, int(right["end_us"])
    )


def attach_index_references(
    authored: list[dict[str, Any]], index: dict[str, Any]
) -> None:
    documents = {
        modality: index["modalities"][modality]["documents"]
        for modality in ("ambient", "speech", "vision")
    }
    for proposal in authored:
        source_id = proposal["source_id"]
        for unit in proposal["evidence_graph"]["evidence_units"]:
            refs = []
            for modality, records in documents.items():
                if unit["modality"] == "vision" and modality != "vision":
                    continue
                if unit["modality"] == "audio" and modality != "ambient":
                    continue
                for record in records:
                    if (
                        record["source_ref"] == source_id
                        and overlap(unit["interval"], record)
                    ):
                        refs.append(str(record["record_id"]))
            unit["record_references"] = sorted(refs)


def task166_map(v1: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        lead["candidate_lead_id"]: lead
        for source in v1["sources"]
        for lead in source["candidate_leads"]
    }


def build_registry(root: Path) -> dict[str, Any]:
    v1_path = root / V1_REGISTRY
    index_path = root / INDEX_ROOT / "full_timeline_index.json"
    segment_path = root / INDEX_ROOT / "segment_manifest.json"
    observation_path = root / INDEX_ROOT / "observation_manifest.json"
    v1 = read_json(v1_path)
    index = read_json(index_path)
    segment = read_json(segment_path)
    observation = read_json(observation_path)
    authored = proposals()
    attach_index_references(authored, index)
    prior = task166_map(v1)
    for proposal in authored:
        origin = proposal["origin"]
        lead_id = origin.get("candidate_lead_id")
        if lead_id:
            lead = prior[lead_id]
            origin["task166_machine_snapshot"] = {
                "primary_interval": lead["primary_interval"],
                "primary_segment_id": lead["primary_segment_id"],
                "event_score": lead["event_score"],
                "current_tier": lead["current_tier"],
                "observation_hypotheses": lead["observation_hypotheses"],
                "possible_repetition_count": len(
                    lead["risk_flags"]["possible_repetitions"]
                ),
            }
        proposal["artifact_classification"] = ARTIFACT_CLASS
        proposal["future_test_eligible"] = False
        proposal["eligible_to_enter_gate_a"] = False
        proposal["human_semantic_prescreen_complete"] = False
        proposal["human_reviewed"] = False
        proposal["human_gold"] = False
        proposal["human_minimality_asserted"] = False
        proposal["human_necessity_asserted"] = False
        proposal["h1_assigned"] = False
        proposal["h2_assigned"] = False
        proposal["final_accepted"] = False
        proposal["required_human_actions"] = list(COMMON_HUMAN_REQUIREMENTS)
        proposal["proposal_payload_sha256"] = json_hash(proposal)

    counts = Counter(item["disposition"] for item in authored)
    source_durations = {
        item["source_ref"]: item["duration_us"] / 1_000_000
        for item in segment["sources"]
    }
    registry = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": "epic-family-candidates-v2-development-only",
        "created_date": "2026-10-02",
        "decision": DECISION,
        "artifact_classification": ARTIFACT_CLASS,
        "scope": {
            "development_only": True,
            "future_test_eligible": False,
            "gate_a_authority_conferred": False,
            "scientific_execution_authorized": False,
            "human_semantic_prescreen_complete": False,
            "human_review_performed": False,
            "h1_assigned": False,
            "h2_assigned": False,
            "necessity_claimed": False,
            "minimality_claimed": False,
        },
        "annotation_firewall": {
            "allowed_inputs_used": [
                "local raw P27_101 and P28_103 media",
                "canonical local Whisper observations",
                "canonical local AST AudioSet observations",
                "canonical local CLIP embeddings and local text queries",
                "canonical local OpenCV routing observations",
                "bounded PyAV frame and audio decoding",
            ],
            "epic_action_annotations_opened": False,
            "epic_narration_annotations_opened": False,
            "epic_sounds_annotations_opened": False,
            "existing_annotation_vault_opened": False,
            "official_semantic_labels_used": False,
        },
        "input_bindings": {
            "task166_registry": {
                "path": V1_REGISTRY.as_posix(),
                "sha256": file_hash(v1_path),
                "registry_hash": v1["registry_hash"],
            },
            "canonical_index": {
                "root": INDEX_ROOT.as_posix(),
                "full_timeline_index_sha256": file_hash(index_path),
                "index_hash": index["index_hash"],
                "segment_manifest_sha256": file_hash(segment_path),
                "segment_manifest_hash": segment["segment_manifest_hash"],
                "observation_manifest_sha256": file_hash(observation_path),
                "observation_manifest_hash": observation[
                    "observation_manifest_hash"
                ],
            },
            "raw_sources": {
                source_id: {
                    "path": path.as_posix(),
                    "sha256": index["source_hashes"][source_id],
                    "duration_s": source_durations[source_id],
                }
                for source_id, path in MEDIA_PATHS.items()
            },
        },
        "complete_timeline_search": {
            "coverage": {
                "source_count": 2,
                "source_ids": ["P27_101", "P28_103"],
                "durations_s": source_durations,
                "fine_ast_windows_searched": observation["counts"][
                    "ast_fine_calls"
                ],
                "clip_cells_searched": observation["counts"]["clip_cells"],
                "opencv_routing_cells_searched": observation["counts"][
                    "routing_cells"
                ],
                "whisper_chunks_searched": observation["counts"][
                    "whisper_chunks"
                ],
            },
            "local_clip_query_count": 15,
            "local_clip_query_scope": (
                "All searchable fine visual windows in both sources"
            ),
            "direct_media_audit": {
                "broad_bounded_frame_inspections": 17,
                "detail_bounded_frame_inspections": 7,
                "sampled_frame_observations": 419,
                "bounded_audio_decodes": 24,
                "bounded_whisper_reruns": 10,
                "bounded_audio_metric_intervals": 14,
                "temporary_media_derivatives_persisted_in_repository": False,
                "human_listening_performed": False,
                "method_note": (
                    "Frames were decoded with local PyAV and inspected in "
                    "temporary contact sheets under /tmp. Audio was decoded "
                    "locally for frozen Whisper reruns and waveform/spectral "
                    "metrics. No audio semantic conclusion is human-validated."
                ),
            },
            "speech_search": {
                "p27_quality_gate_pass_chunks": 0,
                "p28_quality_gate_pass_chunks": 1,
                "only_quality_gate_pass_observation": {
                    "source_id": "P28_103",
                    "interval": interval(630.0, 660.0),
                    "text": "Mm-hmm.",
                    "bounded_rerun_reproduced": True,
                },
                "promoted_substantive_speech_leads": 0,
                "reason": (
                    "The only repeatable quality-passing speech observation is "
                    "a short acknowledgment with no defensible substantive "
                    "source-world question."
                ),
            },
            "additional_leads_promoted": 3,
            "additional_lead_ids": [
                "EPIC-DEV-P27-UNWRAP-FROZEN-ITEM",
                "EPIC-DEV-P28-PEEL-POTATO",
                "EPIC-DEV-P28-ADD-ADJUST-STIR",
            ],
            "not_promoted_machine_routes": [
                {
                    "source_id": "P28_103",
                    "interval": interval(1428.0, 1444.0),
                    "machine_route": "rain/raindrop/rain-on-surface AST",
                    "bounded_frame_finding": (
                        "The camera remains indoors over a saucepan; the route "
                        "is treated as cooking-noise confusion, not rain."
                    ),
                },
                {
                    "source_id": "P28_103",
                    "interval": interval(630.0, 660.0),
                    "machine_route": "quality-passing short speech",
                    "bounded_audio_finding": (
                        "Local Whisper and bounded rerun return only "
                        "'Mm-hmm.', which is not substantive enough to author."
                    ),
                },
            ],
        },
        "candidate_accounting": {
            "proposal_count": len(authored),
            "task166_lead_count": 4,
            "additional_lead_count": 3,
            "keep_count": counts["KEEP"],
            "repair_count": counts["REPAIR"],
            "reject_count": counts["REJECT"],
            "nonempty_question_count": sum(
                bool(item["question"].strip()) for item in authored
            ),
            "nonempty_answer_count": sum(
                bool(item["answer"].strip()) for item in authored
            ),
            "atomic_claim_count": sum(
                len(item["atomic_claims"]) for item in authored
            ),
            "evidence_unit_count": sum(
                len(item["evidence_graph"]["evidence_units"])
                for item in authored
            ),
            "provisional_ses_count": sum(
                len(item["provisional_ses_ledger"]) for item in authored
            ),
            "alternative_route_count": sum(
                len(item["alternative_route_ledger"]) for item in authored
            ),
            "multi_hop_count": sum(
                item["hop_structure"]["hop_stratum"] == "multi_hop"
                for item in authored
            ),
            "substantive_speech_lead_count": 0,
            "counts_are_development_dispositions_not_human_acceptance": True,
        },
        "proposals": authored,
        "human_validation_boundary": {
            "all_proposals_require_human_semantic_prescreen": True,
            "all_kept_proposals_require_full_source_validation": True,
            "all_audio_hypotheses_require_human_listening": True,
            "all_ses_ledgers_are_unaccepted": True,
            "no_h1_h2_necessity_or_minimality_claim": True,
            "development_artifact_may_not_be_promoted_or_copied_into_gate_a": True,
        },
        "global_prohibitions": [
            "Do not treat machine AST, Whisper, CLIP, or OpenCV output as semantic gold.",
            "Do not infer necessity or minimality from this registry.",
            "Do not assign H1 or H2.",
            "Do not execute an intervention from this registry.",
            "Do not use this development-only artifact as future test data.",
            "Do not consult EPIC action, narration, or EPIC-SOUNDS annotations to repair it.",
        ],
    }
    registry["registry_payload_sha256"] = json_hash(registry)
    return registry


def atomic_dump(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    output.resolve(strict=False).relative_to(root)
    registry = build_registry(root)
    if args.execute:
        atomic_dump(output, registry)
        print(
            json.dumps(
                {
                    "decision": registry["decision"],
                    "output": output.relative_to(root).as_posix(),
                    "candidate_accounting": registry["candidate_accounting"],
                    "registry_payload_sha256": registry[
                        "registry_payload_sha256"
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(json.dumps(registry["candidate_accounting"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
