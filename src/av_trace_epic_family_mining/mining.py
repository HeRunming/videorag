"""EPIC-specific event-centric P-tier mining from canonical observations."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import numpy as np

from .adapters import EpicIndexInputs

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "for",
    "from",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "we",
    "with",
    "you",
}
_GENERIC_AUDIO = {
    "speech",
    "male speech, man speaking",
    "female speech, woman speaking",
    "conversation",
    "narration, monologue",
    "music",
    "background music",
    "silence",
    "inside, small room",
    "inside, large room or hall",
    "inside, public space",
    "outside, urban or manmade",
    "outside, rural or natural",
}
DYNAMIC_VISUAL_PROMPTS = (
    "hands manipulating an object",
    "an object visibly changing state",
    "a tool contacting or operating on an object",
    "a container being opened closed filled or emptied",
    "a sequence of physical actions in a kitchen",
)
STATIC_TEXT_VISUAL_PROMPTS = (
    "readable text or captions overlaid on video",
    "a static sign label package or screen",
    "a whiteboard diagram or printed instruction",
    "a mostly static title card or graphic overlay",
)


class VisualQueryEncoder(Protocol):
    """Encode a text prompt into the canonical CLIP vector space."""

    def encode(self, query: str, dimension: int) -> np.ndarray:
        """Return one finite vector of ``dimension``."""


def _documents(
    index: Mapping[str, Any], modality: str, source_id: str
) -> list[Mapping[str, Any]]:
    return [
        item
        for item in index["modalities"][modality].get("documents", ())
        if item.get("source_ref") == source_id
    ]


def _decode_vector(document: Mapping[str, Any]) -> np.ndarray:
    payload = document.get("search_payload", {})
    encoded = payload.get("vector_f16_hex")
    if not isinstance(encoded, str):
        raise TypeError("EPIC_VISUAL_VECTOR_MISSING")
    vector = np.frombuffer(bytes.fromhex(encoded), dtype="<f2").astype(np.float32)
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("EPIC_VISUAL_VECTOR_INVALID")
    return vector / norm


def _prompt_vectors(
    encoder: VisualQueryEncoder, dimension: int
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    def encode(prompt: str) -> np.ndarray:
        vector = np.asarray(encoder.encode(prompt, dimension), dtype=np.float32)
        norm = float(np.linalg.norm(vector))
        if vector.shape != (dimension,) or not math.isfinite(norm) or norm <= 0:
            raise ValueError("EPIC_VISUAL_QUERY_VECTOR_INVALID")
        return vector / norm

    return (
        [encode(prompt) for prompt in DYNAMIC_VISUAL_PROMPTS],
        [encode(prompt) for prompt in STATIC_TEXT_VISUAL_PROMPTS],
    )


def _routing_map(
    records: Sequence[Mapping[str, Any]], source_id: str
) -> dict[str, Mapping[str, Any]]:
    return {
        str(item["cell_id"]): item
        for item in records
        if item.get("source_ref") == source_id
    }


def _overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return max(int(left["start_us"]), int(right["start_us"])) < min(
        int(left["end_us"]), int(right["end_us"])
    )


def _iou(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    intersection = max(
        0,
        min(int(left["end_us"]), int(right["end_us"]))
        - max(int(left["start_us"]), int(right["start_us"])),
    )
    union = max(int(left["end_us"]), int(right["end_us"])) - min(
        int(left["start_us"]), int(right["start_us"])
    )
    return intersection / union if union else 0.0


def _center(item: Mapping[str, Any]) -> float:
    return (int(item["start_us"]) + int(item["end_us"])) / 2


def _salient_speech(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = document.get("search_payload", {})
    tokens = [str(item) for item in payload.get("tokens", ())]
    salient = [
        token
        for token, _ in Counter(tokens).most_common()
        if token not in _STOP and len(token) > 1
    ][:8]
    lexical_score = min(1.0, len(set(salient)) / 8.0)
    return {
        "present": bool(tokens),
        "searchable": bool(document.get("searchable")),
        "score": round(lexical_score, 8),
        "salient_asr_terms": salient,
        "asr_text_copied_to_output": False,
        "record_id": str(document["segment_id"]),
        "start_us": int(document["start_us"]),
        "end_us": int(document["end_us"]),
    }


def _ambient_hypothesis(document: Mapping[str, Any]) -> dict[str, Any]:
    features = list(document.get("search_payload", {}).get("features", ()))
    non_generic: list[dict[str, Any]] = []
    generic: list[str] = []
    speech_weight = 0.0
    for feature in features:
        name = str(feature.get("class_name", feature.get("label", "")))
        weight = float(
            feature.get(
                "weight",
                feature.get(
                    "ranking_probability", feature.get("max_probability", 0.0)
                ),
            )
        )
        if name.casefold() in _GENERIC_AUDIO or feature.get("generic"):
            generic.append(name)
            if "speech" in name.casefold() or "narration" in name.casefold():
                speech_weight = max(speech_weight, weight)
            continue
        non_generic.append({"class_name": name, "weight": round(weight, 8)})
    non_generic.sort(key=lambda item: (-item["weight"], item["class_name"]))
    event_score = min(1.0, sum(item["weight"] for item in non_generic[:3]))
    return {
        "present": bool(non_generic),
        "score": round(event_score, 8),
        "top_machine_ast_observations": non_generic[:5],
        "generic_audio_observations": generic[:5],
        "speech_contamination_score": round(speech_weight, 8),
        "ast_is_semantic_gold": False,
    }


def _visual_hypothesis(
    document: Mapping[str, Any],
    *,
    routing: Mapping[str, Mapping[str, Any]],
    dynamic_vectors: Sequence[np.ndarray],
    static_vectors: Sequence[np.ndarray],
) -> dict[str, Any]:
    vector = _decode_vector(document)
    dynamic_scores = [float(np.dot(vector, item)) for item in dynamic_vectors]
    static_scores = [float(np.dot(vector, item)) for item in static_vectors]
    dynamic_clip = max(dynamic_scores)
    static_clip = max(static_scores)
    routing_items = [
        routing[cell_id]
        for cell_id in document.get("binding_cell_ids", ())
        if cell_id in routing
    ]
    motion_values = [
        float(item.get("features", {}).get("motion_or_change", 0.0))
        for item in routing_items
    ]
    edge_values = [
        float(item.get("features", {}).get("edge_density", 0.0))
        for item in routing_items
    ]
    blank = bool(routing_items) and all(
        item.get("features", {}).get("blank_frame") is True
        for item in routing_items
    )
    motion = max(motion_values, default=0.0)
    motion_score = min(1.0, motion / 0.35)
    dynamic_score = 0.6 * motion_score + 0.4 * ((dynamic_clip + 1.0) / 2.0)
    static_score = 0.55 * ((static_clip + 1.0) / 2.0) + 0.45 * (
        1.0 - motion_score
    )
    if blank:
        visual_class = "visual_unusable_or_blank"
    elif motion >= 0.08 and dynamic_score >= static_score - 0.05:
        visual_class = "dynamic_nontext_visual"
    elif static_score > dynamic_score:
        visual_class = "board_ocr_static_overlay"
    else:
        visual_class = "visual_uncertain_requires_human_classification"
    return {
        "classification": visual_class,
        "dynamic_nontext_visual_score": round(dynamic_score, 8),
        "board_ocr_static_overlay_score": round(static_score, 8),
        "maximum_motion_or_change": round(motion, 8),
        "mean_edge_density": round(
            sum(edge_values) / len(edge_values) if edge_values else 0.0, 8
        ),
        "best_dynamic_prompt": DYNAMIC_VISUAL_PROMPTS[
            int(np.argmax(dynamic_scores))
        ],
        "best_static_text_prompt": STATIC_TEXT_VISUAL_PROMPTS[
            int(np.argmax(static_scores))
        ],
        "clip_and_routing_are_machine_observations_only": True,
        "ocr_executed": False,
        "semantic_claim_allowed": False,
    }


def _event_windows(
    inputs: EpicIndexInputs,
    source_id: str,
    *,
    encoder: VisualQueryEncoder,
) -> list[dict[str, Any]]:
    vision = [
        item
        for item in _documents(inputs.index, "vision", source_id)
        if item.get("scale") == "fine" and item.get("searchable")
    ]
    if not vision:
        raise ValueError(f"EPIC_SOURCE_HAS_NO_FINE_VISUAL_RECORDS:{source_id}")
    dimension = len(_decode_vector(vision[0]))
    dynamic_vectors, static_vectors = _prompt_vectors(encoder, dimension)
    routing = _routing_map(inputs.routing_records, source_id)
    ambient = [
        item
        for item in _documents(inputs.index, "ambient", source_id)
        if item.get("scale") == "fine" and item.get("searchable")
    ]
    speech = [
        item
        for item in _documents(inputs.index, "speech", source_id)
        if item.get("searchable")
    ]
    ambient_by_segment = {str(item["segment_id"]): item for item in ambient}
    output = []
    for document in vision:
        visual = _visual_hypothesis(
            document,
            routing=routing,
            dynamic_vectors=dynamic_vectors,
            static_vectors=static_vectors,
        )
        ambient_document = ambient_by_segment.get(str(document["segment_id"]))
        ambient_summary = (
            _ambient_hypothesis(ambient_document)
            if ambient_document is not None
            else {
                "present": False,
                "score": 0.0,
                "top_machine_ast_observations": [],
                "generic_audio_observations": [],
                "speech_contamination_score": 0.0,
                "ast_is_semantic_gold": False,
            }
        )
        overlapping_speech = [
            _salient_speech(item) for item in speech if _overlap(document, item)
        ]
        best_speech = max(
            overlapping_speech,
            key=lambda item: (item["score"], -item["start_us"]),
            default={
                "present": False,
                "searchable": False,
                "score": 0.0,
                "salient_asr_terms": [],
                "asr_text_copied_to_output": False,
                "record_id": None,
                "start_us": None,
                "end_us": None,
            },
        )
        score = (
            0.48 * float(visual["dynamic_nontext_visual_score"])
            + 0.27 * float(ambient_summary["score"])
            + 0.17 * float(best_speech["score"])
            + 0.08
            * (
                1.0
                - float(visual["board_ocr_static_overlay_score"])
            )
        )
        output.append(
            {
                "segment_id": str(document["segment_id"]),
                "source_id": source_id,
                "start_us": int(document["start_us"]),
                "end_us": int(document["end_us"]),
                "binding_cell_ids": [
                    str(item) for item in document.get("binding_cell_ids", ())
                ],
                "event_score": round(score, 8),
                "visual": visual,
                "ambient": ambient_summary,
                "speech": best_speech,
            }
        )
    output.sort(
        key=lambda item: (
            -item["event_score"],
            item["start_us"],
            item["segment_id"],
        )
    )
    return output


def _compatible_composition(
    anchor: Mapping[str, Any], other: Mapping[str, Any]
) -> tuple[str, str] | None:
    if int(other["start_us"]) <= int(anchor["start_us"]):
        return None
    gap_s = (int(other["start_us"]) - int(anchor["end_us"])) / 1_000_000
    if gap_s < 4.0 or gap_s > 120.0:
        return None
    anchor_visual = anchor["visual"]["classification"]
    other_visual = other["visual"]["classification"]
    if (
        anchor["speech"]["present"]
        and anchor_visual != "dynamic_nontext_visual"
        and other_visual == "dynamic_nontext_visual"
    ):
        return (
            "instruction_or_intent_then_visible_execution",
            "non-dynamic speech-bearing interval precedes a machine-dynamic interval",
        )
    if (
        anchor["ambient"]["present"]
        and anchor_visual != "dynamic_nontext_visual"
        and other_visual == "dynamic_nontext_visual"
    ):
        return (
            "audible_event_then_visible_state_change",
            "non-dynamic AST-bearing interval precedes a machine-dynamic interval",
        )
    if (
        anchor_visual == "dynamic_nontext_visual"
        and other_visual == "visual_uncertain_requires_human_classification"
        and float(other["visual"]["maximum_motion_or_change"])
        <= 0.5 * float(anchor["visual"]["maximum_motion_or_change"])
    ):
        return (
            "visible_action_then_resulting_state",
            "machine-dynamic interval precedes a lower-motion visual-state check",
        )
    return None


def _select_two(windows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not windows:
        raise ValueError("EPIC_NO_EVENT_WINDOWS")
    first = dict(windows[0])
    second: dict[str, Any] | None = None
    composition: tuple[str, str] | None = None
    for anchor in windows[1:40]:
        if _overlap(first, anchor):
            continue
        for other in sorted(
            windows,
            key=lambda item: (
                abs(_center(item) - _center(anchor)),
                item["start_us"],
            ),
        ):
            if other["segment_id"] == anchor["segment_id"] or _overlap(anchor, other):
                continue
            compatible = _compatible_composition(anchor, other)
            if compatible is not None:
                second = {
                    **dict(anchor),
                    "composition_partner": dict(other),
                }
                composition = compatible
                break
        if second is not None:
            break
    if second is None:
        fallback = next(
            (item for item in windows[1:] if _iou(first, item) == 0.0),
            None,
        )
        if fallback is None:
            raise ValueError("EPIC_FEWER_THAN_TWO_DISTINCT_EVENT_WINDOWS")
        second = dict(fallback)
    first["selected_structure"] = "one_hop"
    second["selected_structure"] = (
        "multi_hop" if composition is not None else "one_hop"
    )
    if composition is not None:
        second["composition_operator"] = composition[0]
        second["composition_selection_basis"] = composition[1]
    return [first, second]


def _interval(item: Mapping[str, Any]) -> dict[str, float]:
    return {
        "start_s": round(int(item["start_us"]) / 1_000_000, 6),
        "end_s": round(int(item["end_us"]) / 1_000_000, 6),
    }


def _observation_hypotheses(window: Mapping[str, Any]) -> dict[str, Any]:
    visual = window["visual"]
    ambient = window["ambient"]
    speech = window["speech"]
    return {
        "dynamic_nontext_visual": {
            "status": (
                "MACHINE_HYPOTHESIS"
                if visual["classification"] == "dynamic_nontext_visual"
                else "NOT_PRIMARY_OR_UNCERTAIN"
            ),
            "score": visual["dynamic_nontext_visual_score"],
            "human_prescreen_required_before_authoring": True,
        },
        "board_ocr_static_overlay": {
            "status": (
                "MACHINE_SUBSTITUTE_RISK"
                if visual["classification"] == "board_ocr_static_overlay"
                else "ROUTE_CHALLENGE_REQUIRED"
            ),
            "score": visual["board_ocr_static_overlay_score"],
            "ocr_executed": False,
            "may_not_be_relabelled_as_dynamic_visual": True,
        },
        "speech": {
            "status": (
                "MACHINE_ASR_HYPOTHESIS"
                if speech["present"]
                else "NO_SPEECH_HYPOTHESIS"
            ),
            "score": speech["score"],
            "salient_asr_terms": speech["salient_asr_terms"],
            "verbatim_transcript_in_output": False,
        },
        "non_speech": {
            "status": (
                "MACHINE_AST_HYPOTHESIS"
                if ambient["present"]
                else "NO_CONCRETE_NON_SPEECH_HYPOTHESIS"
            ),
            "score": ambient["score"],
            "top_machine_ast_observations": ambient[
                "top_machine_ast_observations"
            ],
            "human_prescreen_required_before_authoring": True,
            "ast_is_semantic_gold": False,
        },
    }


def _repeat_risks(
    selected: Mapping[str, Any], windows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    selected_labels = {
        item["class_name"]
        for item in selected["ambient"]["top_machine_ast_observations"][:3]
    }
    selected_terms = set(selected["speech"]["salient_asr_terms"])
    repeated = []
    for other in windows:
        if other["segment_id"] == selected["segment_id"]:
            continue
        separated_s = abs(_center(other) - _center(selected)) / 1_000_000
        if separated_s < 16:
            continue
        other_labels = {
            item["class_name"]
            for item in other["ambient"]["top_machine_ast_observations"][:3]
        }
        other_terms = set(other["speech"]["salient_asr_terms"])
        reasons = []
        if selected_labels and selected_labels == other_labels:
            reasons.append("same_top_ast_hypotheses")
        if len(selected_terms.intersection(other_terms)) >= 3:
            reasons.append("repeated_salient_asr_terms")
        if (
            selected["visual"]["best_dynamic_prompt"]
            == other["visual"]["best_dynamic_prompt"]
            and abs(
                float(selected["visual"]["dynamic_nontext_visual_score"])
                - float(other["visual"]["dynamic_nontext_visual_score"])
            )
            <= 0.03
        ):
            reasons.append("near_duplicate_visual_prompt_profile")
        if reasons:
            repeated.append(
                {
                    "segment_id": other["segment_id"],
                    "interval": _interval(other),
                    "reasons": reasons,
                }
            )
    return {
        "repeated_event_risk": bool(repeated),
        "possible_repetitions": repeated[:12],
        "whole_source_repeat_search_required": True,
    }


def _hop_structure(window: Mapping[str, Any]) -> dict[str, Any]:
    if window.get("selected_structure") != "multi_hop":
        return {
            "hop_stratum": "one_hop",
            "temporal_stratum": "near_local",
            "composition": None,
            "one_hop_implies_near": True,
        }
    partner = window["composition_partner"]
    separation_s = abs(_center(partner) - _center(window)) / 1_000_000
    return {
        "hop_stratum": "multi_hop",
        "temporal_stratum": (
            "far_separated" if separation_s >= 120.0 else "near_local"
        ),
        "one_hop_implies_near": True,
        "composition": {
            "status": "MACHINE_COMPOSITION_PLACEHOLDER_NOT_VALIDATED",
            "operator": window["composition_operator"],
            "selection_basis": window["composition_selection_basis"],
            "component_claim_placeholders": [
                {
                    "component_id": "component_1",
                    "interval": _interval(window),
                    "placeholder": (
                        "[Human author: state the first event-grounded premise "
                        "without using transcript/OCR/narration substitutes.]"
                    ),
                },
                {
                    "component_id": "component_2",
                    "interval": _interval(partner),
                    "placeholder": (
                        "[Human author: state the second event-grounded premise "
                        "and verify that it composes with component_1.]"
                    ),
                },
            ],
            "composed_claim_placeholder": (
                "[Human author: write the conclusion that requires both "
                "premises; reject if either interval answers independently.]"
            ),
            "arbitrary_distinct_interval_counting_forbidden": True,
            "semantic_relation_human_validated": False,
        },
    }


def _counterfactuals(hypotheses: Mapping[str, Any]) -> list[dict[str, Any]]:
    present = {
        "vision": hypotheses["dynamic_nontext_visual"]["status"]
        == "MACHINE_HYPOTHESIS",
        "speech": hypotheses["speech"]["status"] == "MACHINE_ASR_HYPOTHESIS",
        "ambient": hypotheses["non_speech"]["status"]
        == "MACHINE_AST_HYPOTHESIS",
    }
    return [
        {
            "drop": modality,
            "remaining_machine_observation_classes": sorted(
                key for key, value in present.items() if value and key != modality
            ),
            "semantic_sufficiency_determined": False,
        }
        for modality in ("vision", "speech", "ambient")
    ] + [
        {
            "drop": "question_only",
            "remaining_machine_observation_classes": [],
            "semantic_sufficiency_determined": False,
        },
        {
            "drop": "metadata_only",
            "remaining_machine_observation_classes": [],
            "semantic_sufficiency_determined": False,
        },
    ]


def _tier(hypotheses: Mapping[str, Any], hop: Mapping[str, Any]) -> str:
    method_count = sum(
        (
            hypotheses["dynamic_nontext_visual"]["status"]
            == "MACHINE_HYPOTHESIS",
            hypotheses["speech"]["status"] == "MACHINE_ASR_HYPOTHESIS",
            hypotheses["non_speech"]["status"] == "MACHINE_AST_HYPOTHESIS",
        )
    )
    if method_count >= 2 and (
        hop["hop_stratum"] == "one_hop" or hop.get("composition")
    ):
        return "P2_MACHINE_COUNTERFACTUAL_VALIDATED"
    if method_count >= 1:
        return "P1_MACHINE_CROSS_VALIDATED"
    return "P0_MACHINE_CANDIDATE"


def mine_initial_machine_leads(
    inputs: EpicIndexInputs,
    *,
    visual_encoder: VisualQueryEncoder,
) -> dict[str, list[dict[str, Any]]]:
    """Mine exactly two machine P-tier leads per source.

    This function accepts no prescreen or official EPIC annotation input. Human
    semantic information can only be joined later by the authoring layer.
    """
    output: dict[str, list[dict[str, Any]]] = {}
    for source_id in sorted(inputs.source_hashes):
        windows = _event_windows(inputs, source_id, encoder=visual_encoder)
        selected = _select_two(windows)
        leads = []
        for ordinal, window in enumerate(selected, 1):
            hypotheses = _observation_hypotheses(window)
            hop = _hop_structure(window)
            candidate_id = "epic.lead." + hashlib.sha256(
                (
                    source_id
                    + ":"
                    + str(ordinal)
                    + ":"
                    + str(window["segment_id"])
                    + ":"
                    + (
                        str(window.get("composition_partner", {}).get("segment_id"))
                        if window.get("composition_partner")
                        else ""
                    )
                ).encode()
            ).hexdigest()[:16]
            lead = {
                "candidate_lead_id": candidate_id,
                "lead_ordinal": ordinal,
                "record_kind": "machine_provisional_epic_event_lead",
                "current_tier": _tier(hypotheses, hop),
                "source_id": source_id,
                "source_group_id": inputs.source_groups[source_id],
                "primary_interval": _interval(window),
                "primary_segment_id": window["segment_id"],
                "event_score": window["event_score"],
                "observation_hypotheses": hypotheses,
                "hop_structure": hop,
                "machine_counterfactual_diagnostics": _counterfactuals(
                    hypotheses
                ),
                "risk_flags": {
                    **_repeat_risks(window, windows),
                    "participant_lineage_leakage": (
                        "REQUIRES_PARTICIPANT_BLOCKED_SPLIT"
                    ),
                    "kitchen_identity_leakage": (
                        "UNKNOWN_REQUIRES_HUMAN_AND_METADATA_CHECK"
                    ),
                    "transcript_substitute": (
                        "PRESENT_REQUIRES_CLOSURE"
                        if hypotheses["speech"]["status"]
                        == "MACHINE_ASR_HYPOTHESIS"
                        else "NOT_OBSERVED_IN_OVERLAPPING_ASR"
                    ),
                    "ocr_or_static_overlay_substitute": (
                        "PRESENT_OR_PLAUSIBLE_REQUIRES_CLOSURE"
                        if hypotheses["board_ocr_static_overlay"]["status"]
                        != "ROUTE_CHALLENGE_REQUIRED"
                        else "UNKNOWN_REQUIRES_OCR_CHALLENGE"
                    ),
                    "narration_substitute": (
                        "UNKNOWN_REQUIRES_HUMAN_LISTENING_AND_CLOSURE"
                    ),
                    "existing_annotation_vault": {
                        "access_prohibited": True,
                        "accessed": False,
                        "prohibited_material": [
                            "EPIC action segments and verb/noun labels",
                            "EPIC narrations and narration timestamps",
                            "EPIC-SOUNDS classes descriptions and timestamps",
                            "benchmark splits prior questions features and outcomes",
                        ],
                    },
                },
                "machine_observation_provenance": {
                    "visual": "OpenCV change plus frozen CLIP embeddings",
                    "speech": "frozen Whisper ASR observations",
                    "ambient": "frozen AST AudioSet observations",
                    "semantic_epic_annotations_accessed": False,
                    "prescreen_used_during_initial_mining": False,
                },
                "human_reviewed": False,
                "human_gold": False,
                "final_accepted": False,
                "human_minimality_asserted": False,
                "human_necessity_asserted": False,
            }
            leads.append(lead)
        output[source_id] = leads
    return output


__all__ = [
    "DYNAMIC_VISUAL_PROMPTS",
    "STATIC_TEXT_VISUAL_PROMPTS",
    "VisualQueryEncoder",
    "mine_initial_machine_leads",
]
