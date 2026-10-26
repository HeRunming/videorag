"""Deterministic machine-provisional family candidate mining helpers."""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from .adapters import MiningInputs, sidecar_query
from .contracts import (
    P_TIERS,
    SCHEMA_VERSION,
    SlotSpec,
    assert_machine_provisional_only,
    json_hash,
    validate_candidate_registry,
    validate_slot_matrix,
)

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
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
    "with",
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


class VisualQueryEncoder(Protocol):
    """Map query text to the frozen visual-vector space."""

    def encode(self, query: str, dimension: int) -> np.ndarray:
        """Return one finite nonzero vector of the requested dimension."""


@dataclass
class FrozenClipQueryEncoder:
    """Lazy local-only CLIP text encoder for executable mining."""

    repo_root: Any
    model_path: str = (
        "data/restricted/noaa01/models/clip-vit-base-patch32-3d74acf"
    )
    _processor: Any = None
    _model: Any = None
    _torch: Any = None

    def encode(self, query: str, dimension: int) -> np.ndarray:
        if self._model is None:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
            with np.errstate(all="ignore"):
                if "long" not in np.__dict__:
                    np.long = np.int64  # type: ignore[attr-defined]
                if "ulong" not in np.__dict__:
                    np.ulong = np.uint64  # type: ignore[attr-defined]
            from pathlib import Path

            import torch
            from transformers import CLIPModel, CLIPProcessor

            root = Path(self.repo_root).resolve()
            path = (root / self.model_path).resolve()
            path.relative_to(root)
            self._processor = CLIPProcessor.from_pretrained(
                path, local_files_only=True, use_fast=False
            )
            self._model = CLIPModel.from_pretrained(
                path, local_files_only=True
            ).to("cpu").eval()
            for parameter in self._model.parameters():
                parameter.requires_grad_(False)
            self._torch = torch
        inputs = self._processor(
            text=[query],
            return_tensors="pt",
            padding=True,
            truncation=True,
        )
        with self._torch.inference_mode():
            outputs = self._model.text_model(
                input_ids=inputs.input_ids,
                attention_mask=inputs.attention_mask,
                return_dict=True,
            )
            values = self._model.text_projection(outputs.pooler_output)
        values = values.float()
        values = values / values.norm(dim=-1, keepdim=True).clamp_min(1e-12)
        vector = values[0].cpu().numpy().astype(np.float32)
        if vector.shape != (dimension,):
            raise ValueError(
                f"VISUAL_QUERY_DIMENSION_MISMATCH:{vector.shape}:{dimension}"
            )
        return vector


class HashFixtureEncoder:
    """Deterministic test/fixture encoder; forbidden for real execution."""

    fixture_only = True

    def encode(self, query: str, dimension: int) -> np.ndarray:
        values = []
        counter = 0
        while len(values) < dimension:
            block = hashlib.sha256(f"{query}:{counter}".encode()).digest()
            values.extend((byte - 127.5) / 127.5 for byte in block)
            counter += 1
        vector = np.asarray(values[:dimension], dtype=np.float32)
        return vector / np.linalg.norm(vector)


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.casefold())


def _payload(document: Mapping[str, Any]) -> Mapping[str, Any]:
    value = document.get("search_payload")
    return value if isinstance(value, Mapping) else document


def _documents(
    index: Mapping[str, Any], modality: str, source_ref: str
) -> list[Mapping[str, Any]]:
    return [
        item
        for item in index["modalities"][modality].get("documents", ())
        if item.get("searchable") and item.get("source_ref") == source_ref
    ]


def _pointer(
    document: Mapping[str, Any],
    *,
    score: float,
    ranker: str,
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    segment_id = str(document["segment_id"])
    modality = str(document["modality"])
    start_us = int(document["start_us"])
    end_us = int(document["end_us"])
    return {
        "pointer_id": "mine.ptr."
        + hashlib.sha256(f"{segment_id}:{modality}".encode()).hexdigest()[:16],
        "segment_id": segment_id,
        "source_ref": str(document["source_ref"]),
        "modality": modality,
        "scale": str(document.get("scale", "unknown")),
        "start_us": start_us,
        "end_us": end_us,
        "interval": {
            "start_s": round(start_us / 1_000_000, 6),
            "end_s": round(end_us / 1_000_000, 6),
        },
        "binding_cell_ids": sorted(
            str(item) for item in document.get("binding_cell_ids", ())
        ),
        "score": round(float(score), 8),
        "ranker": ranker,
        "machine_observation_summary": dict(summary),
    }


def search_speech_bm25(
    index: Mapping[str, Any],
    query: str,
    *,
    source_ref: str,
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """Search either mini-pilot or Scale-1A speech records."""
    modality = index["modalities"]["speech"]
    documents = _documents(index, "speech", source_ref)
    n_documents = max(1, int(modality.get("document_count", len(documents))))
    average_length = max(
        1e-12,
        float(
            modality.get(
                "average_document_length",
                sum(
                    len(_payload(item).get("tokens", ())) for item in documents
                )
                / max(1, len(documents)),
            )
        ),
    )
    document_frequency = modality.get("document_frequency", {})
    query_tokens = _tokens(query)
    scored = []
    for document in documents:
        payload = _payload(document)
        terms = list(payload.get("tokens", ()))
        frequencies = payload.get("term_frequency") or Counter(terms)
        score = 0.0
        for token in query_tokens:
            frequency = int(frequencies.get(token, 0))
            if not frequency:
                continue
            frequency_docs = int(document_frequency.get(token, 0))
            inverse = math.log(
                1.0
                + (n_documents - frequency_docs + 0.5)
                / (frequency_docs + 0.5)
            )
            score += inverse * (frequency * 2.2) / (
                frequency
                + 1.2
                * (1 - 0.75 + 0.75 * max(1, len(terms)) / average_length)
            )
        if score <= 0:
            continue
        salient = [
            token
            for token, _ in Counter(terms).most_common()
            if token not in _STOP
        ][:8]
        pointer = _pointer(
            document,
            score=score,
            ranker="speech_bm25",
            summary={
                "salient_terms": salient,
                "derived_from_chunk_ids": sorted(
                    str(item)
                    for item in payload.get("derived_from_chunk_ids", ())
                ),
                "text_not_copied_to_candidate_registry": True,
            },
        )
        pointer["derived_from_chunk_ids"] = sorted(
            str(item) for item in payload.get("derived_from_chunk_ids", ())
        )
        scored.append(pointer)
    scored.sort(
        key=lambda item: (
            -item["score"],
            item["start_us"],
            item["end_us"],
            item["segment_id"],
        )
    )
    return scored[:top_k]


def search_ambient_labels(
    index: Mapping[str, Any],
    query: str,
    *,
    source_ref: str,
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """Search sparse ambient-label observations."""
    query_tokens = set(_tokens(query))
    scored = []
    for document in _documents(index, "ambient", source_ref):
        features = list(_payload(document).get("features", ()))
        numerator = 0.0
        norm = 0.0
        labels = []
        non_generic = []
        for feature in features:
            label = str(feature.get("class_name", feature.get("label", "")))
            tokens = set(feature.get("tokens") or _tokens(label))
            weight = float(
                feature.get(
                    "weight",
                    feature.get(
                        "ranking_probability",
                        feature.get("max_probability", 0.0),
                    ),
                )
            )
            norm += weight * weight
            numerator += weight * len(tokens.intersection(query_tokens))
            labels.append(label)
            if not bool(feature.get("generic")) and label.casefold() not in _GENERIC_AUDIO:
                non_generic.append(label)
        score = numerator / (
            math.sqrt(max(1, len(query_tokens))) * math.sqrt(norm)
        ) if numerator and norm else 0.0
        if score <= 0:
            continue
        scored.append(
            _pointer(
                document,
                score=score,
                ranker="ambient_weighted_label_overlap",
                summary={
                    "top_labels": labels[:8],
                    "non_generic_labels": non_generic[:8],
                    "ambient_labels_are_machine_predictions": True,
                },
            )
        )
    scored.sort(
        key=lambda item: (
            -item["score"],
            item["start_us"],
            item["end_us"],
            item["segment_id"],
        )
    )
    return scored[:top_k]


def _decode_vector(document: Mapping[str, Any]) -> np.ndarray:
    value = _payload(document).get("vector_f16_hex")
    if not isinstance(value, str):
        raise TypeError("VISUAL_VECTOR_MISSING")
    return np.frombuffer(bytes.fromhex(value), dtype="<f2").astype(np.float32)


def search_visual_vectors(
    index: Mapping[str, Any],
    query: str,
    *,
    source_ref: str,
    encoder: VisualQueryEncoder,
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """Search normalized visual vectors with an explicit local encoder."""
    documents = _documents(index, "vision", source_ref)
    if not documents:
        return []
    dimension = len(_decode_vector(documents[0]))
    query_vector = np.asarray(encoder.encode(query, dimension), dtype=np.float32)
    norm = float(np.linalg.norm(query_vector))
    if query_vector.shape != (dimension,) or not math.isfinite(norm) or norm <= 0:
        raise ValueError("VISUAL_QUERY_VECTOR_INVALID")
    query_vector /= norm
    scored = []
    for document in documents:
        vector = _decode_vector(document)
        vector_norm = float(np.linalg.norm(vector))
        if vector.shape != query_vector.shape or vector_norm <= 0:
            continue
        score = float(np.dot(query_vector, vector / vector_norm))
        scored.append(
            _pointer(
                document,
                score=score,
                ranker="visual_clip_cosine",
                summary={
                    "query_text": query,
                    "semantic_description_generated": False,
                    "vector_dimension": dimension,
                },
            )
        )
    scored.sort(
        key=lambda item: (
            -item["score"],
            item["start_us"],
            item["end_us"],
            item["segment_id"],
        )
    )
    return scored[:top_k]


def _center(item: Mapping[str, Any]) -> float:
    return (int(item["start_us"]) + int(item["end_us"])) / 2


def _iou(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    intersection = max(
        0,
        min(int(left["end_us"]), int(right["end_us"]))
        - max(int(left["start_us"]), int(right["start_us"])),
    )
    union = max(
        int(left["end_us"]), int(right["end_us"])
    ) - min(int(left["start_us"]), int(right["start_us"]))
    return intersection / union if union else 0.0


def _select_evidence(
    rankings: Mapping[str, Sequence[Mapping[str, Any]]],
    slot: SlotSpec,
) -> tuple[list[dict[str, Any]], list[str]]:
    missing = [
        modality
        for modality in slot.target_modalities
        if not rankings.get(modality)
    ]
    available = [
        modality
        for modality in slot.target_modalities
        if rankings.get(modality)
    ]
    if not available:
        return [], missing
    selected = [dict(rankings[available[0]][0])]
    for modality in available[1:]:
        candidates = rankings[modality]
        if slot.target_temporal_stratum == "near_local":
            choice = min(
                candidates,
                key=lambda item: (
                    min(abs(_center(item) - _center(anchor)) for anchor in selected),
                    -float(item["score"]),
                    int(item["start_us"]),
                ),
            )
        else:
            choice = max(
                candidates[:10],
                key=lambda item: (
                    min(abs(_center(item) - _center(anchor)) for anchor in selected),
                    float(item["score"]),
                    -int(item["start_us"]),
                ),
            )
        selected.append(dict(choice))
    return selected, missing


def _routing_summary(
    inputs: MiningInputs,
    evidence: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    visual_intervals = [
        item for item in evidence if item.get("modality") == "vision"
    ]
    matched = []
    for record in inputs.new_routing_records:
        for item in visual_intervals:
            if (
                record.get("source_ref") == item.get("source_ref")
                and int(record.get("sample_time_us", -1)) >= int(item["start_us"])
                and int(record.get("sample_time_us", -1)) < int(item["end_us"])
            ):
                matched.append(record)
                break
    if not matched:
        return {
            "records_found": 0,
            "semantic_claim_allowed": False,
            "routing_supports_semantic_claim": False,
        }
    features = [dict(item.get("features", {})) for item in matched]
    return {
        "records_found": len(matched),
        "blank_frame_count": sum(bool(item.get("blank_frame")) for item in features),
        "face_presence_count": sum(
            bool(item.get("pinned_haar_face_presence")) for item in features
        ),
        "max_motion_or_change": round(
            max(float(item.get("motion_or_change", 0.0)) for item in features),
            8,
        ),
        "semantic_claim_allowed": False,
        "routing_supports_semantic_claim": False,
    }


def _duplicate_and_alternative_risk(
    rankings: Mapping[str, Sequence[Mapping[str, Any]]],
    selected: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    duplicate_routes = []
    alternative_routes = []
    selected_ids = {str(item["segment_id"]) for item in selected}
    for chosen in selected:
        for item in rankings.get(str(chosen["modality"]), ()):
            if str(item["segment_id"]) in selected_ids:
                continue
            overlap = _iou(chosen, item)
            shared_cells = set(chosen.get("binding_cell_ids", ())).intersection(
                item.get("binding_cell_ids", ())
            )
            record = {
                "selected_segment_id": chosen["segment_id"],
                "candidate_segment_id": item["segment_id"],
                "source_ref": item["source_ref"],
                "modality": chosen["modality"],
                "scale": item["scale"],
                "interval": dict(item["interval"]),
                "retrieval_score": item["score"],
                "retrieval_ranker": item["ranker"],
                "machine_observation_summary": dict(
                    item["machine_observation_summary"]
                ),
                "temporal_iou": round(overlap, 8),
                "shared_binding_cell_count": len(shared_cells),
                "score_ratio": round(
                    float(item["score"]) / max(1e-12, float(chosen["score"])),
                    8,
                ),
            }
            if overlap >= 0.5 or shared_cells:
                duplicate_routes.append(record)
            elif record["score_ratio"] >= 0.8:
                alternative_routes.append(record)
    return {
        "duplicate_routes": duplicate_routes[:20],
        "alternative_routes": alternative_routes[:20],
        "duplicate_route_risk": bool(duplicate_routes),
        "alternative_support_risk": (
            "high" if alternative_routes else "not_detected_by_machine_search"
        ),
    }


def _claims(evidence: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    claims = []
    for index, item in enumerate(evidence, 1):
        modality = str(item["modality"])
        summary = item["machine_observation_summary"]
        if modality == "speech":
            cue = ", ".join(summary.get("salient_terms", ())[:5]) or "speech cues"
            text = f"The machine speech observation contains cues related to: {cue}."
        elif modality == "ambient":
            cue = ", ".join(summary.get("non_generic_labels", ())[:5])
            cue = cue or ", ".join(summary.get("top_labels", ())[:5])
            text = (
                "The ambient-event model provisionally assigns labels related "
                f"to: {cue or 'an unresolved sound event'}."
            )
        else:
            text = (
                "The visual embedding for this interval is provisionally similar "
                f"to the query: {summary.get('query_text', 'unspecified')}."
            )
        claims.append(
            {
                "claim_id": f"claim.machine.{index:02d}",
                "text": text,
                "claim_kind": "machine_observation_hypothesis",
                "support_evidence_ids": [f"e.machine.{index:02d}"],
                "human_correctness_asserted": False,
                "human_support_asserted": False,
            }
        )
    return claims


def _evidence_units(
    selected: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output = []
    for index, item in enumerate(selected, 1):
        output.append(
            {
                "evidence_id": f"e.machine.{index:02d}",
                "source_ref": item["source_ref"],
                "segment_id": item["segment_id"],
                "interval": dict(item["interval"]),
                "modality": item["modality"],
                "scale": item["scale"],
                "retrieval_score": item["score"],
                "retrieval_ranker": item["ranker"],
                "machine_observation_summary": dict(
                    item["machine_observation_summary"]
                ),
                "supports_claim_ids": [f"claim.machine.{index:02d}"],
                "support_status": "machine_hypothesis_not_human_validated",
                "necessity_status": "not_human_validated",
            }
        )
    return output


def _alternative_ses_hypotheses(
    evidence: Sequence[Mapping[str, Any]],
    risk: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    primary_ids = [str(item["evidence_id"]) for item in evidence]
    evidence_by_segment = {
        str(item["segment_id"]): item for item in evidence
    }
    output = [
        {
            "ses_id": "ses.machine.preferred",
            "evidence_ids": primary_ids,
            "claim_ids": [
                claim_id
                for item in evidence
                for claim_id in item["supports_claim_ids"]
            ],
            "status": "machine_sufficiency_hypothesis",
            "human_sufficiency_asserted": False,
            "human_minimality_asserted": False,
        }
    ]
    alternatives = []
    for index, route in enumerate(risk["alternative_routes"][:3], 1):
        replaced = evidence_by_segment[str(route["selected_segment_id"])]
        replacement = (
            "e.alt."
            + hashlib.sha256(
                str(route["candidate_segment_id"]).encode()
            ).hexdigest()[:10]
        )
        alternatives.append(
            {
                "evidence_id": replacement,
                "source_ref": route["source_ref"],
                "segment_id": route["candidate_segment_id"],
                "interval": dict(route["interval"]),
                "modality": route["modality"],
                "scale": route["scale"],
                "retrieval_score": route["retrieval_score"],
                "retrieval_ranker": route["retrieval_ranker"],
                "machine_observation_summary": dict(
                    route["machine_observation_summary"]
                ),
                "supports_claim_ids": list(replaced["supports_claim_ids"]),
                "support_status": (
                    "alternative_machine_hypothesis_not_human_validated"
                ),
                "necessity_status": "not_human_validated",
            }
        )
        alternative_ids = [
            replacement if item == replaced["evidence_id"] else item
            for item in primary_ids
        ]
        output.append(
            {
                "ses_id": f"ses.machine.alternative.{index:02d}",
                "evidence_ids": alternative_ids,
                "claim_ids": [
                    claim_id
                    for item in evidence
                    for claim_id in item["supports_claim_ids"]
                ],
                "status": "alternative_route_hypothesis_requires_review",
                "replacement_segment_id": route["candidate_segment_id"],
                "human_sufficiency_asserted": False,
                "human_minimality_asserted": False,
            }
        )
    return output, alternatives


def machine_leave_one_out(
    evidence: Sequence[Mapping[str, Any]],
    ses_hypotheses: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Record machine support behavior without asserting human minimality."""
    results = []
    preferred = set(ses_hypotheses[0]["evidence_ids"]) if ses_hypotheses else set()
    alternatives = [set(item["evidence_ids"]) for item in ses_hypotheses[1:]]
    for item in evidence:
        evidence_id = str(item["evidence_id"])
        surviving = [
            index + 1
            for index, alternative in enumerate(alternatives)
            if evidence_id not in alternative and alternative
        ]
        results.append(
            {
                "removed_evidence_id": evidence_id,
                "preferred_machine_support_broken": evidence_id in preferred,
                "surviving_alternative_hypothesis_indices": surviving,
                "machine_support_survives": bool(surviving),
                "human_minimality_asserted": False,
            }
        )
    return results


def machine_modality_drops(
    evidence: Sequence[Mapping[str, Any]],
    ses_hypotheses: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Evaluate route hypotheses after each modality drop."""
    modality_by_evidence = {
        str(item["evidence_id"]): str(item["modality"]) for item in evidence
    }
    results = []
    for modality in ("vision", "speech", "ambient"):
        surviving = []
        for ses in ses_hypotheses:
            ids = {str(item) for item in ses["evidence_ids"]}
            known = ids.intersection(modality_by_evidence)
            if known and all(modality_by_evidence[item] != modality for item in known):
                surviving.append(str(ses["ses_id"]))
        results.append(
            {
                "condition": f"drop_{modality}",
                "surviving_machine_ses_hypotheses": surviving,
                "machine_answerability_hypothesis": "yes" if surviving else "no",
                "human_modality_necessity_asserted": False,
            }
        )
    results.extend(
        [
            {
                "condition": "question_only",
                "machine_answerability_hypothesis": "unknown_requires_challenge",
                "human_modality_necessity_asserted": False,
            },
            {
                "condition": "metadata_only",
                "machine_answerability_hypothesis": "unknown_requires_challenge",
                "human_modality_necessity_asserted": False,
            },
        ]
    )
    return results


def derived_route_closure(
    *,
    index: Mapping[str, Any],
    source_ref: str,
    selected: Sequence[Mapping[str, Any]],
    sidecar_matches: Sequence[Mapping[str, Any]],
    alternative_segment_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Enumerate direct, duplicate, bound, and transcript-derived routes."""
    by_modality: dict[str, list[Mapping[str, Any]]] = {
        modality: _documents(index, modality, source_ref)
        for modality in ("vision", "speech", "ambient")
    }
    entries = []
    all_suppressed = set(alternative_segment_ids)
    for item in selected:
        modality = str(item["modality"])
        start_us = int(item["start_us"])
        end_us = int(item["end_us"])
        binding_cells = set(item.get("binding_cell_ids", ()))
        related = set()
        speech_chunks = set(item.get("derived_from_chunk_ids", ()))
        for document in by_modality[modality]:
            payload = _payload(document)
            overlaps = (
                int(document["start_us"]) < end_us
                and int(document["end_us"]) > start_us
            )
            shares_cells = bool(
                binding_cells.intersection(document.get("binding_cell_ids", ()))
            )
            shares_chunk = bool(
                speech_chunks.intersection(
                    payload.get("derived_from_chunk_ids", ())
                )
            )
            if overlaps or shares_cells or shares_chunk:
                related.add(str(document["segment_id"]))
        sidecars = [
            str(route["route_id"])
            for route in sidecar_matches
            if route.get("start_us") is None
            or (
                int(route["start_us"]) < end_us
                and int(route["end_us"]) > start_us
            )
        ]
        all_suppressed.update(related)
        entries.append(
            {
                "evidence_segment_id": item["segment_id"],
                "modality": modality,
                "direct_and_derived_segment_ids": sorted(related),
                "official_sidecar_route_ids": sorted(sidecars),
                "official_sidecars_citable": False,
                "closure_machine_complete": bool(related),
            }
        )
    return {
        "registry_version": "derived-route-closure/1.0",
        "entries": entries,
        "all_direct_derived_segment_ids": sorted(all_suppressed),
        "alternative_segment_ids": sorted(set(alternative_segment_ids)),
        "official_sidecar_route_ids": sorted(
            str(item["route_id"]) for item in sidecar_matches
        ),
        "all_entries_machine_complete": bool(entries)
        and all(item["closure_machine_complete"] for item in entries),
        "human_route_saturation_asserted": False,
    }


def cbr_no_trigger_templates(
    *,
    slot: SlotSpec,
    index: Mapping[str, Any],
    source_ref: str,
    evidence: Sequence[Mapping[str, Any]],
    closure: Mapping[str, Any],
) -> dict[str, Any]:
    """Create inert C/B/R/no-trigger blueprints, not executable outcomes."""
    if slot.target_intervention == "modality_channel_outage":
        affected_modalities = sorted({str(item["modality"]) for item in evidence})
        suppressed = sorted(
            str(document["segment_id"])
            for modality in affected_modalities
            for document in _documents(index, modality, source_ref)
        )
        trigger = {
            "type": "get_channel_status",
            "channels": affected_modalities,
        }
    else:
        affected_modalities = sorted({str(item["modality"]) for item in evidence})
        suppressed = list(closure["all_direct_derived_segment_ids"])
        trigger = {
            "type": "second_distinct_search",
            "minimum_distinct_queries": 2,
        }
    suppressed_sidecars = (
        list(closure["official_sidecar_route_ids"])
        if "speech" in affected_modalities
        else []
    )
    common = {
        "question_claims_source_budget_held_fixed": True,
        "template_only_not_executed": True,
        "human_pair_isolation_asserted": False,
    }
    return {
        "template_version": "machine-provisional-cbr-no-trigger/1.0",
        "intervention_hypothesis": slot.target_intervention,
        "affected_modalities": affected_modalities,
        "CLEAN": {
            **common,
            "suppressed_segment_ids": [],
            "expected_route_state": "machine_candidate_routes_available",
        },
        "BLOCKED": {
            **common,
            "suppressed_segment_ids": suppressed,
            "suppressed_official_sidecar_route_ids": suppressed_sidecars,
            "source_media_remains_available": True,
            "expected_route_state": "registered_routes_inaccessible",
        },
        "RESTORED": {
            **common,
            "pretrigger_byte_equal_to_blocked_required": True,
            "trigger": trigger,
            "restoration_reverses_only_registered_block": True,
            "evidence_reacquisition_required": True,
        },
        "NO_TRIGGER": {
            **common,
            "pretrigger_byte_equal_to_blocked_required": True,
            "trigger_absent": True,
            "restoration_expected": False,
        },
    }


def _observed_strata(
    selected: Sequence[Mapping[str, Any]], slot: SlotSpec
) -> dict[str, Any]:
    modalities = sorted({str(item["modality"]) for item in selected})
    profile_map = {
        ("vision",): "V",
        ("speech",): "S",
        ("ambient",): "A",
        ("speech", "vision"): "V+S",
        ("ambient", "vision"): "V+A/S+A",
        ("ambient", "speech"): "V+A/S+A",
        ("ambient", "speech", "vision"): "V+S+A",
    }
    centers = [_center(item) for item in selected]
    separation_s = (max(centers) - min(centers)) / 1_000_000 if centers else 0.0
    distinct_intervals = {
        (int(item["start_us"]), int(item["end_us"])) for item in selected
    }
    observed = {
        "modality_profile": profile_map.get(tuple(modalities), "UNRESOLVED"),
        "hop_stratum": "multi_hop" if len(distinct_intervals) > 1 else "one_hop",
        "temporal_stratum": (
            "far_separated" if separation_s >= 120.0 else "near_local"
        ),
        "maximum_center_separation_s": round(separation_s, 6),
    }
    mismatches = []
    for key, target in (
        ("modality_profile", slot.target_modality_profile),
        ("hop_stratum", slot.target_hop_stratum),
        ("temporal_stratum", slot.target_temporal_stratum),
    ):
        if observed[key] != target:
            mismatches.append(
                {"stratum": key, "target": target, "observed": observed[key]}
            )
    return {
        "target": {
            "modality_profile": slot.target_modality_profile,
            "hop_stratum": slot.target_hop_stratum,
            "temporal_stratum": slot.target_temporal_stratum,
            "intervention": slot.target_intervention,
        },
        "observed": observed,
        "outcome": "TARGET_MET" if not mismatches else "RELABEL_REQUIRED",
        "mismatches": mismatches,
        "quota_forcing_forbidden": True,
    }


def _tier(
    *,
    evidence: Sequence[Mapping[str, Any]],
    sidecar_matches: Sequence[Mapping[str, Any]],
    closure: Mapping[str, Any],
    leave_one_out: Sequence[Mapping[str, Any]],
    modality_drops: Sequence[Mapping[str, Any]],
    cbr: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    methods = {str(item["retrieval_ranker"]) for item in evidence}
    if sidecar_matches:
        methods.add("official_sidecar_route_challenge")
    p1 = len(methods) >= 2 and bool(evidence)
    p2 = (
        p1
        and closure["all_entries_machine_complete"]
        and len(modality_drops) == 5
        and bool(leave_one_out)
        and cbr["RESTORED"]["pretrigger_byte_equal_to_blocked_required"]
    )
    tier = P_TIERS[2] if p2 else P_TIERS[1] if p1 else P_TIERS[0]
    return tier, {
        "P0": bool(evidence),
        "P1": p1,
        "P2": p2,
        "independent_machine_methods": sorted(methods),
        "entailment_is_machine_hypothesis_only": True,
        "alternative_search_attempted": True,
        "counterfactual_checks_executed_as_machine_checks": p2,
        "human_validation_completed": False,
    }


def mine_slot(
    inputs: MiningInputs,
    slot: SlotSpec,
    *,
    visual_encoder: VisualQueryEncoder,
    top_k: int = 20,
) -> dict[str, Any]:
    """Mine one slot; an unmet target is relabeled or left unfilled."""
    index = inputs.index_for(slot.source_kind)
    queries = dict(slot.queries)
    rankings = {
        "speech": search_speech_bm25(
            index,
            queries.get("speech", queries.get("joint", "")),
            source_ref=slot.source_id,
            top_k=top_k,
        ),
        "ambient": search_ambient_labels(
            index,
            queries.get("ambient", queries.get("joint", "")),
            source_ref=slot.source_id,
            top_k=top_k,
        ),
        "vision": search_visual_vectors(
            index,
            queries.get("vision", queries.get("joint", "")),
            source_ref=slot.source_id,
            encoder=visual_encoder,
            top_k=top_k,
        ),
    }
    selected, missing = _select_evidence(rankings, slot)
    if not selected:
        return {
            "slot_id": slot.slot_id,
            "included_in_reported_denominator": (
                slot.included_in_reported_denominator
            ),
            "source_id": slot.source_id,
            "source_kind": slot.source_kind,
            "slot_status": "UNFILLED_NO_MACHINE_EVIDENCE",
            "target_hypothesis": {
                "modality_profile": slot.target_modality_profile,
                "intervention": slot.target_intervention,
                "hop_stratum": slot.target_hop_stratum,
                "temporal_stratum": slot.target_temporal_stratum,
            },
            "missing_target_modalities": missing,
            "candidate": None,
        }

    joint_query = " ".join(queries.values())
    sidecars = (
        sidecar_query(
            inputs.official_transcript_routes,
            source_ref=slot.source_id,
            query=joint_query,
            top_k=20,
        )
        if slot.source_kind == "new_source"
        else []
    )
    risk = _duplicate_and_alternative_risk(rankings, selected)
    evidence = _evidence_units(selected)
    claims = _claims(selected)
    ses, alternative_evidence = _alternative_ses_hypotheses(evidence, risk)
    all_evidence = evidence + alternative_evidence
    leave_one_out = machine_leave_one_out(evidence, ses)
    modality_drops = machine_modality_drops(all_evidence, ses)
    closure = derived_route_closure(
        index=index,
        source_ref=slot.source_id,
        selected=selected,
        sidecar_matches=sidecars,
        alternative_segment_ids=[
            str(item["segment_id"]) for item in alternative_evidence
        ],
    )
    cbr = cbr_no_trigger_templates(
        slot=slot,
        index=index,
        source_ref=slot.source_id,
        evidence=selected,
        closure=closure,
    )
    tier, tier_checks = _tier(
        evidence=evidence,
        sidecar_matches=sidecars,
        closure=closure,
        leave_one_out=leave_one_out,
        modality_drops=modality_drops,
        cbr=cbr,
    )
    strata = _observed_strata(selected, slot)
    source_hash = inputs.source_hash(
        slot.source_kind,
        slot.source_id,
    )
    candidate_id = (
        "mpf."
        + slot.slot_id.casefold()
        + "."
        + hashlib.sha256(
            (
                slot.source_id
                + ":"
                + ":".join(str(item["segment_id"]) for item in selected)
            ).encode()
        ).hexdigest()[:12]
    )
    candidate = {
        "candidate_family_id": candidate_id,
        "record_kind": "machine_provisional_family_candidate",
        "current_tier": tier,
        "tier_checks": tier_checks,
        "question_hypothesis": (
            "Which source observations support the provisional machine cues "
            f"registered for slot {slot.slot_id}?"
        ),
        "answer_hypothesis": (
            "A machine-generated observation summary; a human author must "
            "replace or reject this hypothesis."
        ),
        "atomic_claims": claims,
        "evidence_intervals": all_evidence,
        "ses_hypotheses": ses,
        "machine_leave_one_out_checks": leave_one_out,
        "machine_modality_drop_checks": modality_drops,
        "derived_route_closure_registry": closure,
        "cbr_no_trigger_templates": cbr,
        "strata": strata,
        "risk_flags": {
            **risk,
            "official_transcript_route_count": len(sidecars),
            "official_transcript_shortcut_risk": bool(sidecars),
            "routing": _routing_summary(inputs, selected),
            "missing_target_modalities": missing,
            "question_only_shortcut": "UNKNOWN_REQUIRES_HUMAN_CHALLENGE",
            "metadata_only_shortcut": "UNKNOWN_REQUIRES_HUMAN_CHALLENGE",
            "rights_privacy_safety": "INHERIT_SOURCE_DOSSIER_REVIEW_REQUIRED",
            "human_minimality_unverified": True,
            "human_necessity_unverified": True,
        },
        "official_transcript_sidecar_challenge": {
            "use": "alternative_or_derived_route_risk_only",
            "searchable_as_primary_family_evidence": False,
            "citable": False,
            "matches": sidecars,
        },
        "source_split": {
            "source_group_id": slot.source_id,
            "source_kind": slot.source_kind,
            "construction_split": (
                "NEW_SOURCE_MINI_PILOT_CONSTRUCTION"
                if slot.source_kind == "new_source"
                else "NOAA_CONSUMED_DEVELOPMENT_ONLY"
            ),
            "future_primary_test_eligible": slot.source_kind == "new_source",
            "source_group_split_required": True,
        },
        "provenance": {
            "source_sha256": source_hash,
            "input_adapter": inputs.provenance[slot.source_kind],
            "slot_id": slot.slot_id,
            "seed_family_id": slot.seed_family_id,
            "queries": queries,
            "candidate_hash_inputs": [
                str(item["segment_id"]) for item in selected
            ],
        },
        "human_reviewed": False,
        "human_gold": False,
        "final_accepted": False,
        "human_minimality_asserted": False,
        "human_necessity_asserted": False,
    }
    candidate["candidate_hash"] = json_hash(candidate)
    return {
        "slot_id": slot.slot_id,
        "included_in_reported_denominator": (
            slot.included_in_reported_denominator
        ),
        "source_id": slot.source_id,
        "source_kind": slot.source_kind,
        "slot_status": (
            "PROPOSED_TARGET_MET"
            if strata["outcome"] == "TARGET_MET" and not missing
            else "PROPOSED_RELABEL_REQUIRED"
        ),
        "target_hypothesis": strata["target"],
        "missing_target_modalities": missing,
        "candidate": candidate,
    }


def build_candidate_registry(
    inputs: MiningInputs,
    slots: Sequence[SlotSpec],
    *,
    visual_encoder: VisualQueryEncoder,
    top_k: int = 20,
) -> dict[str, Any]:
    """Build a deterministic P-tier proposal registry over all 14 slots."""
    matrix = validate_slot_matrix(slots)
    slot_records = [
        mine_slot(inputs, slot, visual_encoder=visual_encoder, top_k=top_k)
        for slot in slots
    ]
    candidates = [
        item["candidate"] for item in slot_records if item["candidate"] is not None
    ]
    tier_counts = Counter(str(item["current_tier"]) for item in candidates)
    registry = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": "mini-pilot-family-candidate-proposals-v1",
        "registry_kind": "MACHINE_PROVISIONAL_CANDIDATE_PROPOSALS",
        "status": "PROPOSALS_ONLY_NOT_HUMAN_REVIEWED_NOT_ACCEPTED",
        "created_date": "2026-09-23",
        "slot_matrix": matrix,
        "slots": slot_records,
        "summary": {
            "proposed_candidate_count": len(candidates),
            "unfilled_slot_count": len(slot_records) - len(candidates),
            "tier_counts": dict(sorted(tier_counts.items())),
            "human_reviewed_count": 0,
            "human_gold_count": 0,
            "final_accepted_family_count": 0,
            "strata_may_fail_or_relabel": True,
        },
        "prohibitions": {
            "H1_or_H2_assignment": True,
            "human_minimality_or_necessity_assertion": True,
            "final_family_acceptance": True,
            "quota_forcing": True,
        },
    }
    registry["registry_hash"] = json_hash(registry)
    validate_candidate_registry(registry)
    assert_machine_provisional_only(registry)
    return registry
