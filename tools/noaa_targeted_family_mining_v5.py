#!/usr/bin/env python3
"""Mine deterministic development-only NOAA family leads for pilot-v4 gaps.

The miner is intentionally conservative. It reads only already-local exact
source/index/metadata artifacts, never decodes or downloads media, and emits
machine-expert hypotheses rather than human validation or Gate-A credit.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT
    / "data/restricted/noaa_targeted_family_candidates_v5_dev/"
    "candidate_registry.json"
)
INDEX_PATH = ROOT / "data/restricted/noaa01/scale1a/full_timeline_index.json"
SEGMENT_PATH = ROOT / "data/restricted/noaa01/scale1a/segment_manifest.json"
OBSERVATION_PATH = (
    ROOT / "data/restricted/noaa01/scale1a/observation_manifest.json"
)
PRIOR_REGISTRY_PATH = (
    ROOT / "data/restricted/mini_pilot_family_candidates_v2_dev/"
    "candidate_registry.json"
)
MACHINE_REVIEW_PATH = (
    ROOT / "data/restricted/noaa01/machine_review/"
    "noaa01_machine_review_records.json"
)
PROSPECTING_PATH = (
    ROOT / "data/rehearsal_plan/pilot_v5_targeted_source_prospecting.json"
)
MEDIA_AUDIT_PATH = ROOT / "data/restricted/noaa01/manifests/noaa01_media_audit.json"
CHECKPOINT_ROOT = ROOT / "data/restricted/noaa01/scale1a/checkpoints"
RAW_ROOT = ROOT / "data/restricted/noaa01/raw"

CREATED_DATE = "2026-10-12"
REGISTRY_ID = "noaa-targeted-family-candidates-v5-dev"
READY = "NOAA_TARGETED_FAMILY_MINING_V5_READY"
REPAIR = "NOAA_TARGETED_FAMILY_MINING_V5_REPAIR"
FAR_THRESHOLD_S = 120.0
SOURCE_ORDER = ("cand-049", "cand-047", "cand-051", "cand-045", "cand-052")
PROVISIONAL_STATUSES = {"KEEP", "REPAIR", "REJECT"}
ALLOWED_PROFILE_HYPOTHESES = {"V+S", "V+S+A", "NONE"}

FORBIDDEN_TEXT = (
    "human validated",
    "human-validated",
    "h1 assigned",
    "h2 assigned",
    "gate a go",
    "gate-a go",
)
FORBIDDEN_CAND049_ROUTES = (
    "dev-f09-surf-audio-property",
    "noaa01-r004-surf-av",
)
CHECKPOINT_NAMES = (
    "ambient.json",
    "speech.json",
    "vision_clip.json",
    "vision_routing.json",
)
METADATA_BY_SOURCE = {
    "cand-045": "oceantodaywebinar_040720-lg.mp4.metadata.json",
    "cand-047": "oceantoday-watchparty-050720b-sm.mp4.metadata.json",
    "cand-049": "05_archive_070620_sm.mp4.metadata.json",
    "cand-051": "07_trashtalk_archive_0902_smc.mp4.metadata.json",
    "cand-052": "08_climatealive_archive_1001_smc.mp4.metadata.json",
}


class MiningError(ValueError):
    """Raised when local inputs or the generated registry fail closed."""


def canonical_bytes(value: Any) -> bytes:
    """Return stable UTF-8 JSON bytes with one terminal newline."""
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def object_hash(value: Any) -> str:
    """Hash one JSON-compatible value canonically."""
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    """Hash one local input without following any network route."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def read_json(path: Path) -> Any:
    """Read local JSON or raise a task-specific error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MiningError(f"cannot read local JSON {path}: {exc}") from exc


def _relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _interval(start_s: float, end_s: float) -> dict[str, float]:
    return {"start_s": start_s, "end_s": end_s}


def _center(interval: dict[str, float]) -> float:
    return (interval["start_s"] + interval["end_s"]) / 2.0


def _source_durations(segment_manifest: dict[str, Any]) -> dict[str, float]:
    return {
        source["source_ref"]: round(source["duration_us"] / 1_000_000, 6)
        for source in segment_manifest["sources"]
    }


def _record_ids(index: dict[str, Any]) -> dict[str, set[str]]:
    return {
        "speech": {
            item["segment_id"]
            for item in index["modalities"]["speech"]["documents"]
        },
        "vision": {
            item["segment_id"]
            for item in index["modalities"]["vision"]["documents"]
        },
        "ambient": {
            item["segment_id"]
            for item in index["modalities"]["ambient"]["documents"]
        },
    }


def _handle(
    modality: str,
    source_id: str,
    start_s: float,
    end_s: float,
    record_references: list[str],
    claim_role: str,
    evidence_basis: str,
) -> dict[str, Any]:
    return {
        "modality": modality,
        "source_id": source_id,
        "interval": _interval(start_s, end_s),
        "record_references": record_references,
        "claim_role": claim_role,
        "evidence_basis": evidence_basis,
        "human_validation_status": "NOT_PERFORMED_MACHINE_EXPERT_PROVISIONAL",
    }


def _candidate_templates() -> list[dict[str, Any]]:
    """Return a small, fixed candidate set grounded in local source artifacts."""
    return [
        {
            "candidate_id": "NOAA-V5-049-WAVE-ENTRY-RESCUE",
            "rank": 1,
            "source_id": "cand-049",
            "source_priority": 1,
            "provisional_status": "REPAIR",
            "status_rationale": (
                "The source contains dynamic wave-entry footage and a much later "
                "rescue-instruction sequence, but narration, repeated rescue "
                "animation, visible 911/instruction text, and repeat clips remain "
                "complete-substitute risks."
            ),
            "target_shortages": ["V+S", "coherent_far_multi_hop"],
            "question_hypothesis": (
                "What body orientation is demonstrated for entering breaking "
                "waves, and what should a shore bystander use to aid a person in "
                "a rip current without entering the water?"
            ),
            "answer_hypothesis": (
                "Turn the hips and shoulders sideways and brace through the "
                "waves; use a flotation device or other floating/reaching aid "
                "while remaining out of the water."
            ),
            "atomic_claims": [
                {
                    "claim_id": "c.049.1",
                    "text": (
                        "The dynamic demonstration shows a sideways, braced "
                        "orientation for moving through breaking waves."
                    ),
                    "status": "HYPOTHESIZED_NOT_ACCEPTED",
                },
                {
                    "claim_id": "c.049.2",
                    "text": (
                        "The later spoken rescue guidance says to use flotation "
                        "or another floating/reaching aid without entering the "
                        "water."
                    ),
                    "status": "HYPOTHESIZED_NOT_ACCEPTED",
                },
            ],
            "evidence_handles": [
                _handle(
                    "vision",
                    "cand-049",
                    988.0,
                    1028.0,
                    [
                        "seg.1934c31cb031.fine.000247",
                        "seg.1934c31cb031.fine.000253",
                        "seg.1934c31cb031.fine.000256",
                        "noaa01-review-004",
                    ],
                    "hypothesized support for claim c.049.1",
                    (
                        "Complete visual timeline plus prior exact-window machine "
                        "review; semantics remain machine-expert provisional."
                    ),
                ),
                _handle(
                    "speech",
                    "cand-049",
                    1170.0,
                    1200.0,
                    [
                        "asr.cd74b5663528c83f0d4e",
                        "speech.1934c31cb031.000039",
                    ],
                    "hypothesized support for claim c.049.2",
                    "Quality-passing local ASR chunk from the complete speech index.",
                ),
            ],
            "hypothesized_profile": {
                "label": "V+S",
                "status": "TARGET_ONLY_NOT_FORCED_NOT_NECESSITY",
                "modality_work": {
                    "V": (
                        "Dynamic non-text body orientation and bracing must be "
                        "read from the demonstration, not from OCR."
                    ),
                    "S": (
                        "The later instruction supplies the type and safety use "
                        "of the rescue aid."
                    ),
                    "A": "No answer-bearing non-speech event is claimed.",
                },
            },
            "temporal_structure": {
                "hop_hypothesis": "multi_hop",
                "temporal_hypothesis": "far_separated",
                "coherence_hypothesis": (
                    "Both components concern distinct stages of water-safety "
                    "response: self-protective entry and shore-based aid."
                ),
            },
            "substitutes_and_shortcut_risks": [
                "Narration near the wave-entry demonstration may verbalize the posture.",
                "The rescue procedure is repeated around 2092-2116 seconds.",
                "Speech alone may answer both authored clauses.",
                "Visible 911 and instruction overlays create OCR/caption routes.",
                "The old cand-049 ambient surf route is rejected and excluded.",
            ],
            "alternative_evidence_routes": [
                {
                    "route": "earlier rescue animation and speech around 1140-1200",
                    "effect": "possible complete duplicate requiring grouped closure",
                },
                {
                    "route": "later rescue animation and speech around 2070-2130",
                    "effect": "known near-duplicate from DEV-F10",
                },
                {
                    "route": "poll or spoken rip-current answer around 270-330",
                    "effect": "may expose rescue concepts without dynamic visual work",
                },
            ],
            "required_repair": [
                "Direct human source-uniform review of both intervals.",
                "Prove the wave-entry posture is not fully spoken or captioned.",
                "Group and challenge both rescue animations and all speech/OCR derivatives.",
                "Reject if the two clauses do not form one coherent authored answer.",
            ],
            "known_route_exclusions": [
                {
                    "route_id": "DEV-F09-SURF-AUDIO-PROPERTY",
                    "reason": "known rejected ambient surf route",
                },
                {
                    "route_id": "noaa01-r004-surf-av",
                    "reason": "machine-provisional surf V+A route cannot be revived",
                },
            ],
            "retrieval_evidence": {
                "speech_query_terms": [
                    "flotation device",
                    "call 911",
                    "without entering water",
                ],
                "visual_query_terms": [
                    "person entering breaking waves sideways bracing",
                ],
                "audio_query_terms": [],
                "learned_retrieval_interpretation": (
                    "Routing support only; no learned score is semantic validation."
                ),
            },
        },
        {
            "candidate_id": "NOAA-V5-047-OCEAN-MODEL-TWILIGHT",
            "rank": 2,
            "source_id": "cand-047",
            "source_priority": 2,
            "provisional_status": "KEEP",
            "status_rationale": (
                "The complete timeline exposes a hands-on layered ocean model "
                "followed more than 120 seconds later by a substantive explanation "
                "that most animals occupy the twilight zone. It is a useful "
                "authoring lead, not a validated V+S family."
            ),
            "target_shortages": ["V+S", "coherent_far_multi_hop"],
            "question_hypothesis": (
                "Which ocean zone is represented by the party-bead layer in the "
                "completed household model, and which zone does the expert later "
                "say contains most ocean animals?"
            ),
            "answer_hypothesis": (
                "The party beads represent the twilight zone, and the expert says "
                "most animals live in the twilight zone."
            ),
            "atomic_claims": [
                {
                    "claim_id": "c.047.1",
                    "text": (
                        "The completed hands-on model uses party beads for the "
                        "twilight-zone layer."
                    ),
                    "status": "HYPOTHESIZED_NOT_ACCEPTED",
                },
                {
                    "claim_id": "c.047.2",
                    "text": (
                        "The later expert explanation identifies the twilight "
                        "zone as the zone containing most animals."
                    ),
                    "status": "HYPOTHESIZED_NOT_ACCEPTED",
                },
            ],
            "evidence_handles": [
                _handle(
                    "vision",
                    "cand-047",
                    900.0,
                    960.0,
                    [
                        "seg.ddfb6c2ffa27.fine.000225",
                        "seg.ddfb6c2ffa27.fine.000235",
                        "seg.ddfb6c2ffa27.fine.000238",
                    ],
                    "hypothesized support for claim c.047.1",
                    (
                        "Complete visual index interval aligned to the locally "
                        "indexed model-construction ASR sequence."
                    ),
                ),
                _handle(
                    "speech",
                    "cand-047",
                    1110.0,
                    1140.0,
                    [
                        "asr.b017d62b88fc3a875ae3",
                        "speech.ddfb6c2ffa27.000037",
                    ],
                    "hypothesized support for claim c.047.2",
                    "Quality-passing local ASR chunk from the complete speech index.",
                ),
            ],
            "hypothesized_profile": {
                "label": "V+S",
                "status": "TARGET_ONLY_NOT_FORCED_NOT_NECESSITY",
                "modality_work": {
                    "V": (
                        "The physical placement and identity of the model layer "
                        "must be verified as dynamic non-text visual evidence."
                    ),
                    "S": (
                        "The later expert supplies the biological distribution "
                        "claim about where most animals live."
                    ),
                    "A": "No underwater or handling ambience is claimed.",
                },
            },
            "temporal_structure": {
                "hop_hypothesis": "multi_hop",
                "temporal_hypothesis": "far_separated",
                "coherence_hypothesis": (
                    "The constructed layer and later explanation refer to the same "
                    "ocean-zone concept."
                ),
            },
            "substitutes_and_shortcut_risks": [
                "The model labels or spoken construction instructions may expose the layer.",
                "The expert explanation alone may answer a simplified question.",
                "Poll text and results around the expert answer may be complete substitutes.",
                "The visible object may be too small or text-dependent to count as dynamic V.",
                "The source repeatedly discusses ocean zones.",
            ],
            "alternative_evidence_routes": [
                {
                    "route": "spoken model-building description around 810-960",
                    "effect": "may duplicate the party-bead/layer mapping",
                },
                {
                    "route": "poll and on-screen text around 1050-1110",
                    "effect": "may reveal the twilight-zone answer",
                },
                {
                    "route": "later repeated animal-zone discussion",
                    "effect": "requires full-source recurrence search",
                },
            ],
            "required_repair": [
                "Inspect the physical model interval for non-text visual work.",
                "Inventory labels, poll text, captions, and spoken construction duplicates.",
                "Verify embedded-clip/component rights before any human packet.",
                "Reject or narrow if speech alone answers both clauses.",
            ],
            "known_route_exclusions": [],
            "retrieval_evidence": {
                "speech_query_terms": [
                    "most animals live twilight zone",
                    "ocean zones",
                ],
                "visual_query_terms": [
                    "hands building layered ocean zone model household materials",
                ],
                "audio_query_terms": [],
                "learned_retrieval_interpretation": (
                    "CLIP/ASR handles localize a prospect; they do not prove the "
                    "visual object, speech accuracy, or modality necessity."
                ),
            },
        },
        {
            "candidate_id": "NOAA-V5-051-TRASH-TRIP-DATA",
            "rank": 3,
            "source_id": "cand-051",
            "source_priority": 3,
            "provisional_status": "KEEP",
            "status_rationale": (
                "The late field sequence shows a person collecting a bag of trash "
                "and is followed by an explanation of where logged data goes. The "
                "lead is coherent and speech-rich but remains vulnerable to "
                "narration, app-screen, caption, and repeated-debris substitutes."
            ),
            "target_shortages": ["V+S", "coherent_far_multi_hop"],
            "question_hypothesis": (
                "What does the field participant visibly finish collecting, and "
                "where does the expert later say the logged observations are made "
                "available?"
            ),
            "answer_hypothesis": (
                "The participant finishes with a bag of collected trash; the "
                "logged observations are uploaded to a publicly accessible online "
                "database."
            ),
            "atomic_claims": [
                {
                    "claim_id": "c.051.1",
                    "text": (
                        "The field sequence ends with the participant carrying a "
                        "bag of collected trash."
                    ),
                    "status": "HYPOTHESIZED_NOT_ACCEPTED",
                },
                {
                    "claim_id": "c.051.2",
                    "text": (
                        "The later explanation says collected observations are "
                        "uploaded to a publicly accessible online database."
                    ),
                    "status": "HYPOTHESIZED_NOT_ACCEPTED",
                },
            ],
            "evidence_handles": [
                _handle(
                    "vision",
                    "cand-051",
                    2848.0,
                    2864.0,
                    [
                        "seg.279f6b384118.fine.000712",
                        "seg.279f6b384118.fine.000713",
                        "seg.279f6b384118.fine.000714",
                    ],
                    "hypothesized support for claim c.051.1",
                    (
                        "Complete visual timeline neighborhood selected from the "
                        "field trash-trip sequence; direct semantics remain "
                        "machine-expert provisional."
                    ),
                ),
                _handle(
                    "speech",
                    "cand-051",
                    3150.0,
                    3210.0,
                    [
                        "asr.ee780b414ea7e18217a0",
                        "asr.1e500ed1bd1e6ba23610",
                        "speech.279f6b384118.000105",
                        "speech.279f6b384118.000106",
                    ],
                    "hypothesized support for claim c.051.2",
                    "Quality-passing local ASR chunks from the complete speech index.",
                ),
            ],
            "hypothesized_profile": {
                "label": "V+S",
                "status": "TARGET_ONLY_NOT_FORCED_NOT_NECESSITY",
                "modality_work": {
                    "V": (
                        "The completed collection result and carried bag must be "
                        "visually established as a field-action outcome."
                    ),
                    "S": (
                        "The later expert explains the destination and access "
                        "status of the logged data."
                    ),
                    "A": (
                        "Zero supported: footsteps, handling, water, animal, and "
                        "other AST labels are predictions only and are not used."
                    ),
                },
            },
            "temporal_structure": {
                "hop_hypothesis": "multi_hop",
                "temporal_hypothesis": "far_separated",
                "coherence_hypothesis": (
                    "The two intervals form one collection-to-data-use chain."
                ),
            },
            "substitutes_and_shortcut_risks": [
                "Narration during the walk may explicitly say a bag was collected.",
                "App screens, captions, or maps may visibly state where data goes.",
                "The expert speech alone may answer a narrower database question.",
                "Marine-debris and collection concepts recur throughout the source.",
                "The exact early field interval needs direct inspection and tightening.",
            ],
            "alternative_evidence_routes": [
                {
                    "route": "spoken trash-trip narration around 2790-3150",
                    "effect": "may duplicate the field-action result",
                },
                {
                    "route": "app interface and map pins around 2940-3030",
                    "effect": "potential OCR/visual-text route",
                },
                {
                    "route": "closing citizen-science instructions around 3630-3719",
                    "effect": "possible repeated speech route for data use",
                },
            ],
            "required_repair": [
                "Directly inspect and tighten the field-action interval.",
                "Search all speech/caption/app-screen routes for both claims.",
                "Verify the first claim is dynamic visual work rather than narration.",
                "Do not promote to V+S+A without a concrete human-listened event.",
            ],
            "known_route_exclusions": [
                {
                    "route_id": "DEV-CAL01-PLASTIC-VISUAL-ROUTE-CLOSURE",
                    "reason": "known duplicate-prone bottle/OCR calibration route",
                }
            ],
            "retrieval_evidence": {
                "speech_query_terms": [
                    "data uploaded public database",
                    "collected trash trip",
                ],
                "visual_query_terms": [
                    "person carrying bag collecting trash beside water",
                ],
                "audio_query_terms": [
                    "water",
                    "footsteps",
                    "handling",
                ],
                "learned_retrieval_interpretation": (
                    "Ambient results were inspected only to reject unsupported A; "
                    "no predicted event becomes an atomic claim."
                ),
            },
        },
        {
            "candidate_id": "NOAA-V5-045-RESOURCE-CORAL",
            "rank": 4,
            "source_id": "cand-045",
            "source_priority": 4,
            "provisional_status": "REJECT",
            "status_rationale": (
                "The apparent visual route is presentation, website, and resource "
                "screen content. Local evidence does not establish necessary "
                "dynamic non-text vision, so this cannot honestly fill V+S."
            ),
            "target_shortages": ["V+S"],
            "question_hypothesis": (
                "Rejected prospect: combine resource navigation with a spoken "
                "coral-learning claim."
            ),
            "answer_hypothesis": (
                "No defensible V+S answer is fixed from the local evidence."
            ),
            "atomic_claims": [
                {
                    "claim_id": "c.045.1",
                    "text": (
                        "A dynamic non-text resource action independently carries "
                        "an answer component."
                    ),
                    "status": "REJECTED_UNSUPPORTED",
                }
            ],
            "evidence_handles": [
                _handle(
                    "vision",
                    "cand-045",
                    584.0,
                    592.0,
                    [
                        "seg.03da99e7a33a.fine.000146",
                    ],
                    "rejected routing lead",
                    "Complete visual index; presentation/OCR substitution dominates.",
                ),
                _handle(
                    "speech",
                    "cand-045",
                    630.0,
                    660.0,
                    [
                        "asr.454655d301121b37cdec",
                        "speech.03da99e7a33a.000021",
                    ],
                    "speech route with no independent V partner",
                    "Quality-passing local ASR from the complete speech index.",
                ),
            ],
            "hypothesized_profile": {
                "label": "NONE",
                "status": "REJECTED_NOT_V+S",
                "modality_work": {
                    "V": "Not established beyond slides, websites, graphics, and OCR.",
                    "S": "Substantive presentation speech is present.",
                    "A": "No answer-bearing non-speech event is claimed.",
                },
            },
            "temporal_structure": {
                "hop_hypothesis": "none_accepted",
                "temporal_hypothesis": "not_credited",
                "coherence_hypothesis": "Presentation proximity is not multi-hop evidence.",
            },
            "substitutes_and_shortcut_risks": [
                "Website text and screen labels expose resource names.",
                "Speech narrates the visible navigation.",
                "Slides and static graphics dominate the visual route.",
                "Resource titles create metadata and OCR shortcuts.",
            ],
            "alternative_evidence_routes": [
                {
                    "route": "speech-only resource description",
                    "effect": "complete route for likely questions",
                },
                {
                    "route": "website/OCR",
                    "effect": "complete duplicate rather than dynamic V",
                },
            ],
            "required_repair": [
                "Acquire or find a genuinely dynamic non-text demonstration.",
                "Otherwise retain only as a presentation-source negative.",
            ],
            "known_route_exclusions": [],
            "retrieval_evidence": {
                "speech_query_terms": ["coral resource", "3d printed coral polyp"],
                "visual_query_terms": ["hands physical science demonstration"],
                "audio_query_terms": ["typing", "click"],
                "learned_retrieval_interpretation": (
                    "Visual/audio predictions do not overcome the presentation/OCR "
                    "substitute problem."
                ),
            },
        },
        {
            "candidate_id": "NOAA-V5-052-HURRICANE-GRAPHIC",
            "rank": 5,
            "source_id": "cand-052",
            "source_priority": 5,
            "provisional_status": "REJECT",
            "status_rationale": (
                "The known three-factor route is narration plus duplicate "
                "text/graphic evidence, while the aircraft footage is separately "
                "described by speech/captions. Neither route supplies necessary "
                "dynamic V for a targeted V+S family."
            ),
            "target_shortages": ["V+S", "coherent_far_multi_hop"],
            "question_hypothesis": (
                "Rejected prospect: combine hurricane footage or graphics with "
                "later hurricane explanation."
            ),
            "answer_hypothesis": (
                "No defensible targeted V+S or coherent far family is fixed."
            ),
            "atomic_claims": [
                {
                    "claim_id": "c.052.1",
                    "text": (
                        "Dynamic non-text vision supplies a claim not already "
                        "available from speech, captions, or OCR."
                    ),
                    "status": "REJECTED_UNSUPPORTED",
                }
            ],
            "evidence_handles": [
                _handle(
                    "vision",
                    "cand-052",
                    420.0,
                    452.0,
                    [
                        "seg.c4f5d8c6e60d.context.000026",
                        "seg.c4f5d8c6e60d.fine.000105",
                        "seg.c4f5d8c6e60d.fine.000111",
                        "noaa01-review-014",
                    ],
                    "rejected aircraft/storm visual route",
                    "Learned visual retrieval plus prior exact-window machine review.",
                ),
                _handle(
                    "speech",
                    "cand-052",
                    1320.0,
                    1350.0,
                    [
                        "asr.11a2eaf6b4520c2f6f19",
                        "speech.c4f5d8c6e60d.000044",
                        "noaa01-review-016",
                    ],
                    "known duplicate speech/graphic route",
                    "Complete speech index and prior machine-reviewed family.",
                ),
            ],
            "hypothesized_profile": {
                "label": "NONE",
                "status": "REJECTED_NOT_V+S",
                "modality_work": {
                    "V": (
                        "Aircraft footage is captioned/described; factor graphics "
                        "are static text/illustration duplicates."
                    ),
                    "S": "Speech is substantive but independently sufficient.",
                    "A": "Music and AST weather labels are not answer-bearing A.",
                },
            },
            "temporal_structure": {
                "hop_hypothesis": "none_accepted",
                "temporal_hypothesis": "distance_only_not_credited",
                "coherence_hypothesis": (
                    "Combining aircraft footage and factor narration would join "
                    "separate hurricane topics without a necessary composed claim."
                ),
            },
            "substitutes_and_shortcut_risks": [
                "Burned-in captions and OCR duplicate the three-factor narration.",
                "Speech alone answers the factor route.",
                "Aircraft footage is paired with explanatory captions/narration.",
                "Generic hurricane priors and repeated source discussion are strong.",
            ],
            "alternative_evidence_routes": [
                {
                    "route": "factor graphic/OCR around 1330-1347",
                    "effect": "known complete duplicate of speech",
                },
                {
                    "route": "North Atlantic speech around 2640-2700",
                    "effect": "speech-only route, not targeted V+S",
                },
            ],
            "required_repair": [
                "Do not revive DEV-F12 as V+S.",
                "A new candidate would need dynamic non-text vision with a distinct claim.",
            ],
            "known_route_exclusions": [
                {
                    "route_id": "DEV-F12-HURRICANE-FORMATION-FACTORS",
                    "reason": "known narration/OCR duplicate route",
                },
                {
                    "route_id": "noaa01-r016-three-factors-vs",
                    "reason": "corroboration is not modality necessity",
                },
            ],
            "retrieval_evidence": {
                "speech_query_terms": [
                    "hurricane formation factors",
                    "North Atlantic Basin",
                ],
                "visual_query_terms": ["aircraft wing dense storm clouds"],
                "audio_query_terms": ["storm wind"],
                "learned_retrieval_interpretation": (
                    "High retrieval rank does not cure known text/speech duplication."
                ),
            },
        },
    ]


def _input_bindings(paths: list[Path]) -> list[dict[str, Any]]:
    bindings = []
    for path in paths:
        if not path.is_file():
            raise MiningError(f"required local input is missing: {_relative(path)}")
        bindings.append(
            {
                "path": _relative(path),
                "sha256": file_hash(path),
                "local_only": True,
            }
        )
    return bindings


def _enrich_candidate(
    candidate: dict[str, Any],
    durations: dict[str, float],
) -> dict[str, Any]:
    output = copy.deepcopy(candidate)
    intervals = [
        item["interval"]
        for item in output["evidence_handles"]
        if item["modality"] in {"vision", "speech", "ambient"}
    ]
    centers = [_center(item) for item in intervals]
    separation = round(max(centers) - min(centers), 6) if centers else 0.0
    output["source_duration_s"] = durations[output["source_id"]]
    output["temporal_structure"]["evidence_center_separation_s"] = separation
    output["temporal_structure"]["far_threshold_s"] = FAR_THRESHOLD_S
    output["temporal_structure"]["threshold_passes"] = (
        output["temporal_structure"]["temporal_hypothesis"] == "far_separated"
        and separation >= FAR_THRESHOLD_S
    )
    output["human_reviewed"] = False
    output["human_semantic_prescreen_complete"] = False
    output["accepted_ses_count"] = 0
    output["h_tier"] = None
    output["gate_a_credit"] = False
    output["future_test_eligible"] = False
    output["candidate_payload_sha256"] = object_hash(
        {key: value for key, value in output.items() if key != "candidate_payload_sha256"}
    )
    return output


def build_registry(root: Path = ROOT) -> dict[str, Any]:
    """Build the registry from fixed hypotheses and verified local handles."""
    if root.resolve() != ROOT.resolve():
        raise MiningError("alternate repository roots are not supported")
    checkpoint_paths = [
        CHECKPOINT_ROOT / source_id / checkpoint_name
        for source_id in SOURCE_ORDER
        for checkpoint_name in CHECKPOINT_NAMES
    ]
    metadata_paths = [
        RAW_ROOT / METADATA_BY_SOURCE[source_id] for source_id in SOURCE_ORDER
    ]
    paths = [
        INDEX_PATH,
        SEGMENT_PATH,
        OBSERVATION_PATH,
        PRIOR_REGISTRY_PATH,
        MACHINE_REVIEW_PATH,
        PROSPECTING_PATH,
        MEDIA_AUDIT_PATH,
        *checkpoint_paths,
        *metadata_paths,
    ]
    index = read_json(INDEX_PATH)
    segment_manifest = read_json(SEGMENT_PATH)
    observation_manifest = read_json(OBSERVATION_PATH)
    prior_registry = read_json(PRIOR_REGISTRY_PATH)
    prospecting = read_json(PROSPECTING_PATH)
    machine_review = read_json(MACHINE_REVIEW_PATH)

    if not observation_manifest.get("all_five_complete"):
        raise MiningError("NOAA full-timeline observation manifest is incomplete")
    if segment_manifest.get("human_reviewed") is not False:
        raise MiningError("unexpected human-reviewed segment manifest")
    if prospecting.get("decision_token") != "PILOT_V5_TARGETED_PROSPECTING_READY":
        raise MiningError("unexpected pilot-v5 prospecting decision")
    if prior_registry.get("human_validation_boundary", {}).get(
        "human_review_performed"
    ):
        raise MiningError("prior registry unexpectedly claims human review")
    if machine_review.get("reviewer_type") != "machine_codex":
        raise MiningError("machine-review input has unexpected reviewer type")

    durations = _source_durations(segment_manifest)
    if tuple(source for source in SOURCE_ORDER if source in durations) != SOURCE_ORDER:
        raise MiningError("NOAA source set does not contain the frozen five-source order")
    candidates = [
        _enrich_candidate(candidate, durations)
        for candidate in _candidate_templates()
    ]
    registry: dict[str, Any] = {
        "schema_version": "av-trace.noaa-targeted-family-mining-v5/1.0",
        "registry_id": REGISTRY_ID,
        "created_date": CREATED_DATE,
        "decision": READY,
        "artifact_classification": (
            "DEVELOPMENT_ONLY_MACHINE_EXPERT_PROVISIONAL_TARGETED_MINING"
        ),
        "scope": {
            "objective": (
                "Mine a small ranked local-only set for V+S, V+S+A, and coherent "
                "far multi-hop pilot-v4 shortages."
            ),
            "prioritized_sources": list(SOURCE_ORDER),
            "candidate_count": len(candidates),
            "media_downloaded": False,
            "network_used": False,
            "media_decoded_by_this_miner": False,
            "human_review_performed": False,
            "human_validation_claimed": False,
            "accepted_ses_created": 0,
            "h_tiers_assigned": 0,
            "gate_a_go_asserted": False,
            "future_test_eligible": False,
        },
        "input_bindings": _input_bindings(paths),
        "index_bindings": {
            "index_hash": index["index_hash"],
            "segment_manifest_hash": segment_manifest["segment_manifest_hash"],
            "observation_manifest_hash": observation_manifest[
                "observation_manifest_hash"
            ],
            "source_hashes": index["source_hashes"],
            "complete_source_refs": observation_manifest["complete_source_refs"],
        },
        "method": {
            "determinism": (
                "Fixed source order, fixed candidate templates, exact local "
                "record-ID existence checks, canonical JSON, and payload hashes."
            ),
            "asr": (
                "Read complete local quality-gated ASR index/checkpoints; transcript "
                "text is used only for machine-expert hypothesis authoring."
            ),
            "visual": (
                "Inspect complete visual index and prior local learned-retrieval "
                "outputs/record handles; no media decoding occurs."
            ),
            "audio": (
                "Inspect complete ambient index and machine labels only to route or "
                "reject leads. Predicted labels never establish a source-world event."
            ),
            "far_rule": (
                "At least 120 seconds between evidence centers plus an explicit "
                "coherence hypothesis; distance alone earns no credit."
            ),
        },
        "profile_accounting": {
            "V+S": {
                "keep": sum(
                    item["provisional_status"] == "KEEP"
                    and item["hypothesized_profile"]["label"] == "V+S"
                    for item in candidates
                ),
                "repair": sum(
                    item["provisional_status"] == "REPAIR"
                    and item["hypothesized_profile"]["label"] == "V+S"
                    for item in candidates
                ),
                "validated_or_accepted": 0,
            },
            "V+S+A": {
                "keep": 0,
                "repair": 0,
                "validated_or_accepted": 0,
                "honest_zero": True,
                "reason": (
                    "No local exact-source evidence establishes a concrete, "
                    "temporally localizable, source-world non-speech event carrying "
                    "a non-duplicative answer component."
                ),
                "recommendation": (
                    "Use separately approved acquisition of audio-rich procedural "
                    "sources, or prospectively narrow/remove V+S+A rather than "
                    "forcing AST labels, music, surf, generic handling, or co-occurrence."
                ),
            },
            "coherent_far_multi_hop": {
                "keep": sum(
                    item["provisional_status"] == "KEEP"
                    and item["temporal_structure"]["threshold_passes"]
                    for item in candidates
                ),
                "repair": sum(
                    item["provisional_status"] == "REPAIR"
                    and item["temporal_structure"]["threshold_passes"]
                    for item in candidates
                ),
                "validated_or_accepted": 0,
            },
        },
        "global_prohibitions": [
            "No human validation claim.",
            "No accepted SES, H tier, or Gate-A credit.",
            "No forced modality label.",
            "No invented or AST-only ambient event.",
            "No cand-049 ambient surf revival.",
            "No duplicate/OCR route revival as independent V.",
            "No media download, network access, or media decoding.",
        ],
        "candidates": candidates,
        "next_action": (
            "Run source-uniform human prescreen only after annotation authority; "
            "if V+S+A remains empty, recommend acquisition or preregistered narrowing."
        ),
    }
    registry["registry_payload_sha256"] = object_hash(
        {
            key: value
            for key, value in registry.items()
            if key != "registry_payload_sha256"
        }
    )
    validate_registry(registry, index=index)
    return registry


def validate_registry(
    registry: dict[str, Any],
    *,
    index: dict[str, Any] | None = None,
) -> None:
    """Fail closed on governance, handle, ordering, and modality violations."""
    if registry.get("decision") != READY:
        raise MiningError("registry decision is not READY")
    scope = registry.get("scope", {})
    false_fields = (
        "media_downloaded",
        "network_used",
        "media_decoded_by_this_miner",
        "human_review_performed",
        "human_validation_claimed",
        "gate_a_go_asserted",
        "future_test_eligible",
    )
    for field in false_fields:
        if scope.get(field) is not False:
            raise MiningError(f"scope must fail closed: {field}")
    if scope.get("accepted_ses_created") != 0 or scope.get("h_tiers_assigned") != 0:
        raise MiningError("registry claims accepted SES or H tiers")

    candidates = registry.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise MiningError("registry has no candidates")
    if [item.get("rank") for item in candidates] != list(
        range(1, len(candidates) + 1)
    ):
        raise MiningError("candidate ranks are not contiguous")
    if [item.get("source_id") for item in candidates] != list(SOURCE_ORDER):
        raise MiningError("candidate source priority order changed")

    ids = _record_ids(index or read_json(INDEX_PATH))
    for candidate in candidates:
        if candidate.get("provisional_status") not in PROVISIONAL_STATUSES:
            raise MiningError("invalid provisional status")
        profile = candidate.get("hypothesized_profile", {})
        if profile.get("label") not in ALLOWED_PROFILE_HYPOTHESES:
            raise MiningError("invalid profile hypothesis")
        if profile.get("status") is None or "NOT" not in profile["status"]:
            raise MiningError("profile is not explicitly provisional/rejected")
        if candidate.get("human_reviewed") is not False:
            raise MiningError("candidate claims human review")
        if candidate.get("accepted_ses_count") != 0:
            raise MiningError("candidate claims accepted SES")
        if candidate.get("h_tier") is not None:
            raise MiningError("candidate claims H tier")
        if candidate.get("gate_a_credit") is not False:
            raise MiningError("candidate claims Gate-A credit")
        if candidate.get("future_test_eligible") is not False:
            raise MiningError("development source claims future-test eligibility")
        expected_candidate_hash = object_hash(
            {
                key: value
                for key, value in candidate.items()
                if key != "candidate_payload_sha256"
            }
        )
        if candidate.get("candidate_payload_sha256") != expected_candidate_hash:
            raise MiningError("candidate payload hash mismatch")

        seen_modalities = set()
        for handle in candidate.get("evidence_handles", []):
            modality = handle.get("modality")
            seen_modalities.add(modality)
            if handle.get("source_id") != candidate.get("source_id"):
                raise MiningError("cross-source evidence handle")
            interval = handle.get("interval", {})
            start = interval.get("start_s")
            end = interval.get("end_s")
            if not isinstance(start, (int, float)) or not isinstance(
                end, (int, float)
            ):
                raise MiningError("non-numeric interval")
            if start < 0 or end <= start or end > candidate["source_duration_s"] + 1e-6:
                raise MiningError("evidence interval is outside source duration")
            if handle.get("human_validation_status") != (
                "NOT_PERFORMED_MACHINE_EXPERT_PROVISIONAL"
            ):
                raise MiningError("evidence handle claims validation")
            for reference in handle.get("record_references", []):
                if reference.startswith("asr.") and reference not in ids["speech"]:
                    raise MiningError(f"unknown ASR handle: {reference}")
                if reference.startswith("seg.") and reference not in ids[modality]:
                    raise MiningError(f"unknown {modality} handle: {reference}")

        label = profile["label"]
        if label == "V+S" and not {"vision", "speech"}.issubset(seen_modalities):
            raise MiningError("V+S lead lacks exact V and S handles")
        if label == "V+S+A" and not {"vision", "speech", "ambient"}.issubset(
            seen_modalities
        ):
            raise MiningError("V+S+A lead lacks exact V, S, and A handles")
        temporal = candidate["temporal_structure"]
        if temporal["temporal_hypothesis"] == "far_separated":
            if temporal["evidence_center_separation_s"] < FAR_THRESHOLD_S:
                raise MiningError("far lead is below threshold")
            if temporal["hop_hypothesis"] != "multi_hop":
                raise MiningError("one-hop/far lead is prohibited")
            if not temporal["coherence_hypothesis"]:
                raise MiningError("far lead lacks coherence hypothesis")

        if candidate["source_id"] == "cand-049":
            exclusions = {
                item["route_id"].casefold()
                for item in candidate.get("known_route_exclusions", [])
            }
            if not set(FORBIDDEN_CAND049_ROUTES).issubset(exclusions):
                raise MiningError("cand-049 forbidden routes are not excluded")

    vsa = registry.get("profile_accounting", {}).get("V+S+A", {})
    if (
        vsa.get("keep") != 0
        or vsa.get("repair") != 0
        or vsa.get("validated_or_accepted") != 0
        or vsa.get("honest_zero") is not True
    ):
        raise MiningError("V+S+A accounting must report honest zero")

    rendered = json.dumps(registry, ensure_ascii=False).casefold()
    for phrase in FORBIDDEN_TEXT:
        if phrase in rendered:
            raise MiningError(f"forbidden governance claim appears: {phrase}")
    expected_hash = object_hash(
        {
            key: value
            for key, value in registry.items()
            if key != "registry_payload_sha256"
        }
    )
    if registry.get("registry_payload_sha256") != expected_hash:
        raise MiningError("registry payload hash mismatch")


def write_registry(path: Path, registry: dict[str, Any]) -> None:
    """Write the deterministic registry with restricted permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(registry))
    os.chmod(path.parent, 0o700)
    os.chmod(path, 0o600)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Development registry path.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate that the existing output exactly matches a fresh build.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        registry = build_registry()
        output = args.output.resolve()
        if args.check:
            existing = read_json(output)
            validate_registry(existing)
            if canonical_bytes(existing) != canonical_bytes(registry):
                raise MiningError("existing registry differs from deterministic build")
        else:
            write_registry(output, registry)
        print(READY)
        return 0
    except MiningError as exc:
        print(f"{REPAIR}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
