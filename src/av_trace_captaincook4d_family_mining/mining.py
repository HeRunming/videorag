"""Event-centric mining from canonical CaptainCook4D observations only."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import numpy as np

from av_trace_mini_pilot_families.mining import (
    FrozenClipQueryEncoder,
    HashFixtureEncoder,
)

from .adapters import CaptainCook4DIndexInputs

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
    "hands performing a changing cooking procedure",
    "a utensil or tool transforms food or material",
    "an ingredient is added mixed spread folded cut or shaped",
    "a container appliance or control is operated during a procedure",
    "a before action after state transition in an egocentric task",
    "multiple ordered physical actions on the same object or vessel",
)
STATIC_TEXT_VISUAL_PROMPTS = (
    "readable text captions or recipe instructions on screen",
    "a static package label sign appliance display or printed page",
    "a mostly static title card graphic overlay or menu",
    "text or numbers that could answer without observing the action",
)


class VisualQueryEncoder(Protocol):
    """Encode text in the canonical CLIP vector space."""

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
    encoded = document.get("search_payload", {}).get("vector_f16_hex")
    if not isinstance(encoded, str):
        raise TypeError("CAPTAINCOOK4D_VISUAL_VECTOR_MISSING")
    vector = np.frombuffer(bytes.fromhex(encoded), dtype="<f2").astype(np.float32)
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("CAPTAINCOOK4D_VISUAL_VECTOR_INVALID")
    return vector / norm


def _prompt_vectors(
    encoder: VisualQueryEncoder, dimension: int
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    def encode(prompt: str) -> np.ndarray:
        vector = np.asarray(encoder.encode(prompt, dimension), dtype=np.float32)
        norm = float(np.linalg.norm(vector))
        if vector.shape != (dimension,) or not math.isfinite(norm) or norm <= 0:
            raise ValueError("CAPTAINCOOK4D_QUERY_VECTOR_INVALID")
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
    tokens = [
        str(item)
        for item in document.get("search_payload", {}).get("tokens", ())
    ]
    salient = [
        token
        for token, _ in Counter(tokens).most_common()
        if token not in _STOP and len(token) > 1
    ][:8]
    return {
        "present": bool(tokens),
        "score": round(min(1.0, len(set(salient)) / 8.0), 8),
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
    concrete_score = min(1.0, sum(item["weight"] for item in non_generic[:3]))
    meaningful_score = concrete_score * max(0.0, 1.0 - speech_weight)
    return {
        "present": bool(non_generic),
        "score": round(meaningful_score, 8),
        "top_machine_ast_observations": non_generic[:5],
        "generic_audio_observations": generic[:5],
        "speech_contamination_score": round(speech_weight, 8),
        "meaningful_non_speech_requires_direct_listening": True,
        "ast_is_semantic_evidence": False,
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
    dynamic_clip = max(dynamic_scores)
    static_clip = max(static_scores)
    dynamic_score = 0.65 * motion_score + 0.35 * ((dynamic_clip + 1.0) / 2.0)
    static_score = 0.58 * ((static_clip + 1.0) / 2.0) + 0.42 * (
        1.0 - motion_score
    )
    if blank:
        classification = "visual_unusable_or_blank"
    elif motion >= 0.08 and dynamic_score >= static_score - 0.04:
        classification = "dynamic_nontext_visual"
    elif static_score > dynamic_score:
        classification = "board_ocr_static_overlay"
    else:
        classification = "visual_uncertain_requires_direct_inspection"
    return {
        "classification": classification,
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
        "clip_and_routing_are_observations_only": True,
        "ocr_executed": False,
        "semantic_claim_allowed": False,
    }


def _event_windows(
    inputs: CaptainCook4DIndexInputs,
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
        raise ValueError(f"CAPTAINCOOK4D_NO_FINE_VISUAL_RECORDS:{source_id}")
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
        audio = (
            _ambient_hypothesis(ambient_document)
            if ambient_document is not None
            else {
                "present": False,
                "score": 0.0,
                "top_machine_ast_observations": [],
                "generic_audio_observations": [],
                "speech_contamination_score": 0.0,
                "meaningful_non_speech_requires_direct_listening": True,
                "ast_is_semantic_evidence": False,
            }
        )
        overlapping_speech = [
            _salient_speech(item) for item in speech if _overlap(document, item)
        ]
        spoken = max(
            overlapping_speech,
            key=lambda item: (item["score"], -item["start_us"]),
            default={
                "present": False,
                "score": 0.0,
                "salient_asr_terms": [],
                "asr_text_copied_to_output": False,
                "record_id": None,
                "start_us": None,
                "end_us": None,
            },
        )
        dynamic = float(visual["dynamic_nontext_visual_score"])
        static = float(visual["board_ocr_static_overlay_score"])
        audio_score = float(audio["score"])
        speech_score = float(spoken["score"])
        score = (
            0.57 * dynamic
            + 0.28 * audio_score
            + 0.07 * speech_score
            + 0.08 * (1.0 - static)
        )
        if visual["classification"] == "dynamic_nontext_visual":
            score += 0.08
        if audio["present"] and audio["speech_contamination_score"] < 0.35:
            score += 0.04
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
                "ambient": audio,
                "speech": spoken,
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


def _coherent_pair(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> tuple[str, str] | None:
    if int(second["start_us"]) <= int(first["start_us"]):
        return None
    gap_s = (int(second["start_us"]) - int(first["end_us"])) / 1_000_000
    if gap_s < 2.0 or gap_s > 900.0:
        return None
    first_dynamic = (
        first["visual"]["classification"] == "dynamic_nontext_visual"
    )
    second_dynamic = (
        second["visual"]["classification"] == "dynamic_nontext_visual"
    )
    first_audio = bool(first["ambient"]["present"])
    second_audio = bool(second["ambient"]["present"])
    first_motion = float(first["visual"]["maximum_motion_or_change"])
    second_motion = float(second["visual"]["maximum_motion_or_change"])
    if first_dynamic and second_dynamic:
        if abs(first_motion - second_motion) <= 0.18:
            return (
                "tool_or_ingredient_selection_then_transformation",
                (
                    "ordered machine-dynamic windows have compatible motion "
                    "profiles; direct inspection must verify one shared object "
                    "or procedure"
                ),
            )
        return (
            "setup_or_preparation_then_execution",
            (
                "ordered machine-dynamic windows suggest preparation followed "
                "by execution; direct inspection must verify procedural coherence"
            ),
        )
    if first_dynamic and second_motion <= 0.55 * max(first_motion, 1e-6):
        return (
            "visible_action_then_resulting_state",
            "machine-dynamic action precedes a lower-motion state window",
        )
    if first_audio and second_dynamic:
        return (
            "audible_process_then_visible_state_change",
            (
                "non-speech AST-bearing process precedes a machine-dynamic "
                "visual window; listening and frame inspection must verify "
                "one event"
            ),
        )
    if first_dynamic and second_audio:
        return (
            "earlier_action_then_later_consequence",
            (
                "machine-dynamic action precedes a non-speech process window; "
                "direct inspection must verify the consequence relation"
            ),
        )
    return None


def _select_two(windows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if len(windows) < 2:
        raise ValueError("CAPTAINCOOK4D_FEWER_THAN_TWO_EVENT_WINDOWS")
    first = dict(windows[0])
    pair_candidates: list[tuple[float, Mapping[str, Any], Mapping[str, Any], tuple[str, str]]] = []
    search = list(windows[:120])
    for anchor in search:
        if _iou(first, anchor) > 0:
            continue
        for other in search:
            if _overlap(anchor, other):
                continue
            relation = _coherent_pair(anchor, other)
            if relation is None:
                continue
            separation_s = (_center(other) - _center(anchor)) / 1_000_000
            far_bonus = 0.12 if separation_s >= 120 else 0.0
            score = (
                float(anchor["event_score"])
                + float(other["event_score"])
                + far_bonus
            )
            pair_candidates.append((score, anchor, other, relation))
    if pair_candidates:
        _, anchor, other, relation = max(
            pair_candidates,
            key=lambda item: (
                item[0],
                -int(item[1]["start_us"]),
                -int(item[2]["start_us"]),
            ),
        )
        second = {
            **dict(anchor),
            "composition_partner": dict(other),
            "composition_operator": relation[0],
            "composition_selection_basis": relation[1],
            "selected_structure": "multi_hop",
        }
    else:
        fallback = next(
            (
                item
                for item in windows[1:]
                if _iou(first, item) == 0.0
                and abs(_center(first) - _center(item)) >= 16_000_000
            ),
            None,
        )
        if fallback is None:
            raise ValueError("CAPTAINCOOK4D_NO_DISTINCT_SECOND_LEAD")
        second = {**dict(fallback), "selected_structure": "one_hop"}
    first["selected_structure"] = "one_hop"
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
            "direct_frame_inspection_required": True,
        },
        "board_ocr_static_overlay": {
            "status": (
                "MACHINE_SUBSTITUTE_RISK"
                if visual["classification"] == "board_ocr_static_overlay"
                else "ROUTE_CHALLENGE_REQUIRED"
            ),
            "score": visual["board_ocr_static_overlay_score"],
            "ocr_executed": False,
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
            "human_listening_required": True,
            "ast_is_semantic_evidence": False,
        },
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
    separation_s = (_center(partner) - _center(window)) / 1_000_000
    coherence_basis = {
        "setup_or_preparation_then_execution": "same_procedure_stage_chain",
        "tool_or_ingredient_selection_then_transformation": (
            "same_object_or_material"
        ),
        "visible_action_then_resulting_state": "same_result_state",
        "audible_process_then_visible_state_change": (
            "audio_visual_process_result"
        ),
        "earlier_action_then_later_consequence": "same_procedure_stage_chain",
    }[str(window["composition_operator"])]
    return {
        "hop_stratum": "multi_hop",
        "temporal_stratum": (
            "far_separated" if separation_s >= 120.0 else "near_local"
        ),
        "one_hop_implies_near": True,
        "composition": {
            "status": "MACHINE_COHERENCE_HYPOTHESIS_REQUIRES_INSPECTION",
            "operator": window["composition_operator"],
            "selection_basis": window["composition_selection_basis"],
            "coherence_basis": coherence_basis,
            "separation_seconds": round(separation_s, 6),
            "components": [
                {
                    "component_id": "component_1",
                    "interval": _interval(window),
                    "claim_hypothesis": (
                        "The first interval contains a procedure stage that "
                        "sets up or causes the later stage."
                    ),
                    "routing_hypothesis": {
                        "visual": window["visual"]["best_dynamic_prompt"],
                        "visual_classification": window["visual"][
                            "classification"
                        ],
                        "non_speech_ast": [
                            item["class_name"]
                            for item in window["ambient"][
                                "top_machine_ast_observations"
                            ][:3]
                        ],
                    },
                },
                {
                    "component_id": "component_2",
                    "interval": _interval(partner),
                    "claim_hypothesis": (
                        "The second interval contains the related execution, "
                        "transformation, process, or result."
                    ),
                    "routing_hypothesis": {
                        "visual": partner["visual"]["best_dynamic_prompt"],
                        "visual_classification": partner["visual"][
                            "classification"
                        ],
                        "non_speech_ast": [
                            item["class_name"]
                            for item in partner["ambient"][
                                "top_machine_ast_observations"
                            ][:3]
                        ],
                    },
                },
            ],
            "composed_claim_hypothesis": (
                "Both intervals are required to answer one source-world "
                "procedure relation; reject if either interval answers alone."
            ),
            "arbitrary_interval_pairing_forbidden": True,
            "each_component_required_human_validated": False,
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
    repetitions = []
    for other in windows:
        if other["segment_id"] == selected["segment_id"]:
            continue
        if abs(_center(other) - _center(selected)) < 20_000_000:
            continue
        reasons = []
        labels = {
            item["class_name"]
            for item in other["ambient"]["top_machine_ast_observations"][:3]
        }
        terms = set(other["speech"]["salient_asr_terms"])
        if selected_labels and selected_labels == labels:
            reasons.append("same_top_ast_hypotheses")
        if len(selected_terms.intersection(terms)) >= 3:
            reasons.append("repeated_salient_asr_terms")
        if (
            selected["visual"]["best_dynamic_prompt"]
            == other["visual"]["best_dynamic_prompt"]
            and abs(
                float(selected["visual"]["dynamic_nontext_visual_score"])
                - float(other["visual"]["dynamic_nontext_visual_score"])
            )
            <= 0.035
        ):
            reasons.append("near_duplicate_visual_prompt_profile")
        if reasons:
            repetitions.append(
                {
                    "segment_id": other["segment_id"],
                    "interval": _interval(other),
                    "reasons": reasons,
                }
            )
    return {
        "status": "POSSIBLE_RECURRENCE_REQUIRES_FULL_SOURCE_REVIEW",
        "machine_flagged": bool(repetitions),
        "possible_repetitions": repetitions[:16],
        "machine_recurrence_is_not_adjudication": True,
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
    ]


def _tier(hypotheses: Mapping[str, Any], hop: Mapping[str, Any]) -> str:
    count = sum(
        (
            hypotheses["dynamic_nontext_visual"]["status"]
            == "MACHINE_HYPOTHESIS",
            hypotheses["speech"]["status"] == "MACHINE_ASR_HYPOTHESIS",
            hypotheses["non_speech"]["status"] == "MACHINE_AST_HYPOTHESIS",
        )
    )
    if count >= 2 and (
        hop["hop_stratum"] == "one_hop" or hop.get("composition")
    ):
        return "P2_MACHINE_COUNTERFACTUAL_VALIDATED"
    if count >= 1:
        return "P1_MACHINE_CROSS_VALIDATED"
    return "P0_MACHINE_CANDIDATE"


def mine_initial_machine_leads(
    inputs: CaptainCook4DIndexInputs,
    *,
    visual_encoder: VisualQueryEncoder,
) -> dict[str, list[dict[str, Any]]]:
    """Mine exactly two label-free machine leads per source."""
    output: dict[str, list[dict[str, Any]]] = {}
    for source_id in sorted(inputs.source_hashes):
        windows = _event_windows(inputs, source_id, encoder=visual_encoder)
        selected = _select_two(windows)
        leads = []
        for ordinal, window in enumerate(selected, 1):
            hypotheses = _observation_hypotheses(window)
            hop = _hop_structure(window)
            candidate_id = "cc4d.lead." + hashlib.sha256(
                (
                    source_id
                    + ":"
                    + str(ordinal)
                    + ":"
                    + str(window["segment_id"])
                    + ":"
                    + str(
                        window.get("composition_partner", {}).get(
                            "segment_id", ""
                        )
                    )
                ).encode()
            ).hexdigest()[:16]
            leads.append(
                {
                    "candidate_lead_id": candidate_id,
                    "lead_ordinal": ordinal,
                    "record_kind": (
                        "machine_expert_provisional_captaincook4d_event_lead"
                    ),
                    "current_tier": _tier(hypotheses, hop),
                    "source_id": source_id,
                    "source_group_id": inputs.source_groups[source_id],
                    "primary_interval": _interval(window),
                    "primary_segment_id": window["segment_id"],
                    "event_score": window["event_score"],
                    "observation_hypotheses": hypotheses,
                    "routing_observation_summary": {
                        "best_dynamic_visual_prompt": window["visual"][
                            "best_dynamic_prompt"
                        ],
                        "visual_classification": window["visual"][
                            "classification"
                        ],
                        "maximum_motion_or_change": window["visual"][
                            "maximum_motion_or_change"
                        ],
                        "top_machine_ast_observations": window["ambient"][
                            "top_machine_ast_observations"
                        ][:3],
                        "salient_asr_terms": window["speech"][
                            "salient_asr_terms"
                        ],
                        "semantic_evidence": False,
                    },
                    "hop_structure": hop,
                    "machine_counterfactual_diagnostics": _counterfactuals(
                        hypotheses
                    ),
                    "risk_flags": {
                        "recurrence": _repeat_risks(window, windows),
                        "people_leakage": (
                            "REQUIRES_PERSON_BLOCKED_SPLIT_AND_VISIBLE_BODY_"
                            "IDENTITY_REVIEW"
                        ),
                        "environment_leakage": (
                            "REQUIRES_ENVIRONMENT_BLOCKED_SPLIT_AND_KITCHEN_"
                            "SCENE_SHORTCUT_REVIEW"
                        ),
                        "speech_asr_substitute": (
                            "PRESENT_REQUIRES_CLOSURE"
                            if hypotheses["speech"]["status"]
                            == "MACHINE_ASR_HYPOTHESIS"
                            else "NOT_OBSERVED_IN_OVERLAPPING_ASR"
                        ),
                        "caption_ocr_text_substitute": (
                            "PRESENT_OR_PLAUSIBLE_REQUIRES_CLOSURE"
                            if hypotheses["board_ocr_static_overlay"]["status"]
                            == "MACHINE_SUBSTITUTE_RISK"
                            else "UNKNOWN_REQUIRES_DIRECT_OCR_CAPTION_CHALLENGE"
                        ),
                        "semantic_annotation_firewall": {
                            "captaincook_action_annotations_accessed": False,
                            "task_graphs_accessed": False,
                            "step_annotations_accessed": False,
                            "error_labels_accessed": False,
                            "recipe_labels_accessed": False,
                        },
                    },
                    "machine_observation_provenance": {
                        "visual": "OpenCV change plus frozen CLIP embeddings",
                        "speech": "frozen Whisper ASR observations",
                        "ambient": "frozen AST AudioSet observations",
                        "raw_local_media_used_during_initial_mining": False,
                        "task153_prescreen_used_during_initial_mining": False,
                        "semantic_captaincook_annotations_used": False,
                    },
                    "human_reviewed": False,
                    "h1_assigned": False,
                    "h2_assigned": False,
                    "human_gold": False,
                    "accepted_family": False,
                    "human_minimality_asserted": False,
                    "human_necessity_asserted": False,
                }
            )
        output[source_id] = leads
    return output


__all__ = [
    "DYNAMIC_VISUAL_PROMPTS",
    "STATIC_TEXT_VISUAL_PROMPTS",
    "FrozenClipQueryEncoder",
    "HashFixtureEncoder",
    "VisualQueryEncoder",
    "mine_initial_machine_leads",
]
