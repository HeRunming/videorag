#!/usr/bin/env python3
"""Finalize Task193 machine-expert provisional facts and lead accounting."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "av-trace.semantic-audio-discovery/1.0"
TASK_DATE = "2026-10-10"
OUTPUT_REL = "data/restricted/semantic_audio_discovery_v1"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _self_hashed(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result.pop(field, None)
    result[field] = "sha256:" + _sha256_bytes(_json_bytes(result))
    return result


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(_json_bytes(value))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _concept_map(rankings: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {item["concept_id"]: item for item in rankings["concept_rankings"]}


def _overlap_hits(
    rankings: Mapping[str, Any],
    *,
    source_ref: str,
    start_s: float,
    end_s: float,
    concept_ids: list[str],
) -> list[dict[str, Any]]:
    by_concept = _concept_map(rankings)
    hits: list[dict[str, Any]] = []
    for concept_id in concept_ids:
        concept = by_concept[concept_id]
        for hit in concept["per_source_top"][source_ref]:
            if hit["end_s"] <= start_s or hit["start_s"] >= end_s:
                continue
            hits.append(
                {
                    "concept_id": concept_id,
                    "concept_label": concept["label"],
                    **hit,
                }
            )
    return sorted(hits, key=lambda x: (x["concept_id"], x["rank"]))


def _speech_overlap(
    root: Path, *, source_ref: str, start_s: float, end_s: float
) -> dict[str, Any]:
    if source_ref.startswith("P"):
        path = (
            root
            / "data/restricted/epic_wave1_index_v1/checkpoints"
            / source_ref
            / "speech.json"
        )
    else:
        path = (
            root
            / "data/restricted/captaincook4d_wave0_index_v1/checkpoints"
            / source_ref
            / "speech.json"
        )
    speech = _load(path)
    overlaps = [
        {
            "start_s": item["start_us"] / 1_000_000,
            "end_s": item["end_us"] / 1_000_000,
            "quality_gate_pass": item["quality_gate_pass"],
            "quality_flags": item["quality_flags"],
            "text": item["text"] if item["quality_gate_pass"] else None,
        }
        for item in speech["chunks"]
        if item["end_us"] / 1_000_000 > start_s
        and item["start_us"] / 1_000_000 < end_s
    ]
    return {
        "path": path.relative_to(root).as_posix(),
        "overlapping_chunks": overlaps,
        "passing_substantive_speech_overlap": any(
            item["quality_gate_pass"]
            and len(str(item.get("text", "")).strip().split()) >= 2
            for item in overlaps
        ),
    }


def _fact(
    rankings: Mapping[str, Any],
    root: Path,
    *,
    fact_id: str,
    source_ref: str,
    start_s: float,
    end_s: float,
    sound: str,
    concepts: list[str],
    status: str,
    answer_information: str,
    confidence_basis: list[str],
    recurrence: dict[str, Any],
    visual_substitute: str,
    speech_substitute: str,
    recommended_profile: str | None,
    question_template: str | None,
    answer_template: str | None,
) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "source_ref": source_ref,
        "interval": {"start_s": start_s, "end_s": end_s},
        "sound_event": sound,
        "status": status,
        "artifact_classification": "MACHINE_EXPERT_PROVISIONAL_DEVELOPMENT_ONLY",
        "learned_retrieval_hits": _overlap_hits(
            rankings,
            source_ref=source_ref,
            start_s=start_s,
            end_s=end_s,
            concept_ids=concepts,
        ),
        "answer_information_carried_by_sound": answer_information,
        "confidence_basis": confidence_basis,
        "recurrence_audit": recurrence,
        "cross_modal_substitutes": {
            "vision": visual_substitute,
            "speech": speech_substitute,
            "canonical_speech_overlap": _speech_overlap(
                root, source_ref=source_ref, start_s=start_s, end_s=end_s
            ),
        },
        "recommended_profile": recommended_profile,
        "question_template": question_template,
        "answer_template": answer_template,
        "human_listening_performed": False,
        "human_reviewed": False,
        "h1_assigned": False,
        "h2_assigned": False,
        "necessity_claimed": False,
        "minimality_claimed": False,
        "eligible_to_enter_gate_a": False,
        "future_test_eligible": False,
    }


def finalize(root: Path) -> dict[str, Any]:
    root = root.resolve()
    output = root / OUTPUT_REL
    rankings_path = output / "rankings.json"
    review_path = output / "machine_review_packets.json"
    build_path = output / "build_manifest.json"
    rankings = _load(rankings_path)
    review = _load(review_path)
    build = _load(build_path)

    facts = [
        _fact(
            rankings,
            root,
            fact_id="sad193.fact.p27.wrapper.open",
            source_ref="P27_101",
            start_s=1288.0,
            end_s=1301.0,
            sound="A small flexible package is actively crinkled and torn/opened.",
            concepts=["wrapper_tearing", "plastic_bag_rustling"],
            status="RETAIN_AUDIO_FACT",
            answer_information=(
                "The sound distinguishes active wrapper opening/unwrapping from "
                "merely holding or carrying the small item."
            ),
            confidence_basis=[
                "wrapper_tearing ranks 1-3 at 1288-1300 s with margins 0.358-0.402",
                "plastic_bag_rustling ranks 1-3 in the same cluster",
                "waveform/spectrogram show a dense irregular broadband crinkle cluster",
                "bounded frames show freezer retrieval followed by two-handed package manipulation",
            ],
            recurrence={
                "top15_cluster_count": 5,
                "dominant_cluster": "1284-1324 s contains ranks 1-5,7-9",
                "nearest_secondary_cluster": "960-976 s",
                "assessment": (
                    "The exact late cluster is exceptional, but wrapper-like "
                    "sounds recur; question must bind to the just-retrieved item."
                ),
            },
            visual_substitute=(
                "Vision clearly shows two-handed wrapper manipulation, so audio "
                "is corroborating rather than a clean standalone necessity route."
            ),
            speech_substitute="No canonical quality-passing speech overlaps.",
            recommended_profile="V+A",
            question_template=(
                "After taking the small item from the freezer, what does the "
                "person do to its packaging before walking away?"
            ),
            answer_template="They tear/open and remove the wrapper.",
        ),
        _fact(
            rankings,
            root,
            fact_id="sad193.fact.p28.peel.scrape",
            source_ref="P28_103",
            start_s=196.0,
            end_s=224.0,
            sound="Repeated quiet broadband scraping accompanies use of a handheld peeler.",
            concepts=["peeling_scraping", "grating"],
            status="RETAIN_AUDIO_FACT",
            answer_information=(
                "The repeated scrape pattern corroborates an ongoing abrasive "
                "preparation action rather than static handling of the potato."
            ),
            confidence_basis=[
                "grating ranks 1 and 4 at 216-228 s with margins 0.344-0.413",
                "peeling_scraping ranks 4 and 8 at 220-232 s",
                "spectral median 3.68 kHz and high-band fraction 0.613 fit repeated scraping",
                "bounded frames directly show a handheld peeler and potato",
            ],
            recurrence={
                "top15_cluster_count": 9,
                "dominant_cluster": "220-232 s is the relevant action cluster",
                "assessment": (
                    "Scraping-like detections recur and CLAP confuses peeling "
                    "with grating; object/action binding must come from bounded vision."
                ),
            },
            visual_substitute=(
                "Vision independently identifies the potato and peeler and is a "
                "complete substitute for the action answer."
            ),
            speech_substitute="No canonical quality-passing speech overlaps.",
            recommended_profile="V+A",
            question_template=(
                "What action and accompanying repeated sound occur while the "
                "person works on the potato?"
            ),
            answer_template="They peel it, producing repeated scraping sounds.",
        ),
        _fact(
            rankings,
            root,
            fact_id="sad193.fact.p28.chopping",
            source_ref="P28_103",
            start_s=1116.0,
            end_s=1132.0,
            sound="A regular series of discrete knife-on-board chopping impacts occurs.",
            concepts=["chopping"],
            status="RETAIN_AUDIO_FACT",
            answer_information=(
                "The repeated impacts identify an active chopping phase and its "
                "continuity, not merely the presence of a knife or food."
            ),
            confidence_basis=[
                "chopping ranks 1-3 over 1116-1132 s",
                "waveform has a repeated impulse train aligned with narrow vertical spectrogram strokes",
                "bounded frames show repeated knife motion on the blue board",
            ],
            recurrence={
                "top15_cluster_count": 10,
                "dominant_cluster": "1112-1132 s contains ranks 1-3 and 10",
                "assessment": (
                    "Chopping recurs elsewhere; any pilot question must include "
                    "the local object/state or immediate sequence."
                ),
            },
            visual_substitute=(
                "Vision directly shows knife motion and is a complete substitute "
                "for identifying chopping."
            ),
            speech_substitute="No canonical quality-passing speech overlaps.",
            recommended_profile="V+A",
            question_template=(
                "What repeated preparation action is occurring on the blue "
                "cutting board?"
            ),
            answer_template="The person is chopping with a knife.",
        ),
        _fact(
            rankings,
            root,
            fact_id="sad193.fact.p28.water.start",
            source_ref="P28_103",
            start_s=258.0,
            end_s=271.0,
            sound="Running faucet water starts and continues while items are handled in the sink.",
            concepts=["running_water", "dish_washing"],
            status="RETAIN_AUDIO_FACT",
            answer_information=(
                "The onset and sustained broadband water noise identify the "
                "transition into a rinse/wash phase."
            ),
            confidence_basis=[
                "running_water ranks 3 and 9 at 260-272 s with margins 0.402-0.436",
                "waveform changes from sparse activity to sustained high-frequency noise",
                "bounded frames move from board work to hands under the faucet",
            ],
            recurrence={
                "top15_cluster_count": 11,
                "assessment": (
                    "Running water is highly recurrent in this source and cannot "
                    "answer an object-specific question without visual binding."
                ),
            },
            visual_substitute="The visible sink/faucet is a complete action substitute.",
            speech_substitute="No canonical quality-passing speech overlaps.",
            recommended_profile="V+A",
            question_template=(
                "What audible event marks the transition from board preparation "
                "to work at the sink?"
            ),
            answer_template="The faucet starts running for rinsing/washing.",
        ),
        _fact(
            rankings,
            root,
            fact_id="sad193.fact.cc16.chopping",
            source_ref="16_20",
            start_s=508.0,
            end_s=524.0,
            sound="A sequence of sharp chopping impacts is produced on the cutting board.",
            concepts=["chopping"],
            status="RETAIN_AUDIO_FACT",
            answer_information=(
                "The repeated impacts establish that the visible knife/food "
                "setup is actively chopping rather than paused."
            ),
            confidence_basis=[
                "chopping ranks 2-3 at 508-520 s with margins 0.362-0.416",
                "waveform and spectrogram show a clear train of separated impulses",
                "bounded frames show knife motion through diced tomatoes",
            ],
            recurrence={
                "top15_cluster_count": 5,
                "other_major_clusters": ["888-904 s", "1076-1104 s"],
                "assessment": "Chopping recurs; local food/phase binding is required.",
            },
            visual_substitute="Vision is a complete substitute for chopping identity.",
            speech_substitute="No canonical quality-passing speech overlaps.",
            recommended_profile="V+A",
            question_template=(
                "What preparation action is producing the repeated sharp "
                "impacts on the board?"
            ),
            answer_template="The participant is chopping the tomatoes.",
        ),
        _fact(
            rankings,
            root,
            fact_id="sad193.fact.cc16.stirring",
            source_ref="16_20",
            start_s=584.0,
            end_s=604.0,
            sound="Rapid continuous stirring/whisking with repeated utensil contact occurs in a bowl.",
            concepts=["stirring", "whisking_mixing", "utensil_impacts"],
            status="RETAIN_AUDIO_FACT",
            answer_information=(
                "Audio carries the vigor and continuity of the mixing phase and "
                "the repeated utensil contact."
            ),
            confidence_basis=[
                "stirring ranks 1-4 over 584-604 s with margins 0.270-0.352",
                "whisking ranks 1-4 and utensil impacts ranks 1-3 in the same cluster",
                "spectrogram has sustained repetitive harmonic/impact texture",
                "bounded frames show vigorous stirring in a yellow bowl",
            ],
            recurrence={
                "top15_cluster_count": 7,
                "dominant_cluster": "580-608 s contains stirring ranks 1-6",
                "assessment": (
                    "Other stirring episodes exist, but this is the dominant "
                    "source-local mixing cluster."
                ),
            },
            visual_substitute=(
                "Vision identifies the bowl and stirring; audio adds vigor/rhythm "
                "but is not a nonduplicated standalone route."
            ),
            speech_substitute="No canonical quality-passing speech overlaps.",
            recommended_profile="V+A",
            question_template=(
                "How is the bowl mixture being worked during the sustained "
                "utensil-contact sound?"
            ),
            answer_template="It is being stirred or whisked rapidly.",
        ),
        _fact(
            rankings,
            root,
            fact_id="sad193.fact.cc16.timer.beep.sequence",
            source_ref="16_20",
            start_s=676.0,
            end_s=748.0,
            sound="Three separated clusters of short tonal appliance-like beeps occur.",
            concepts=["appliance_beep"],
            status="RETAIN_AUDIO_FACT",
            answer_information=(
                "The sound itself supplies a count/order signal: multiple alert "
                "clusters occur across the preparation span."
            ),
            confidence_basis=[
                "appliance_beep top clusters at 676-692, 708-720, and 736-752 s",
                "source ranks 1-7 are concentrated in these three separated clusters",
                "spectrogram shows repeated stable horizontal tonal stacks rather than broadband impacts",
                "bounded frames show continuing food preparation without a clearly visible emitting appliance",
            ],
            recurrence={
                "top15_cluster_count": 9,
                "strong_cluster_count_in_bounded_span": 3,
                "assessment": (
                    "Additional weaker beep-like detections exist; the proposed "
                    "lead must explicitly bind to the three strong alert clusters."
                ),
            },
            visual_substitute=(
                "No visible source for the tones is established in bounded frames; "
                "vision shows the concurrent preparation but not the beep count."
            ),
            speech_substitute="No canonical quality-passing speech overlaps.",
            recommended_profile="A",
            question_template=(
                "How many distinct clusters of electronic alert tones occur "
                "during this preparation span?"
            ),
            answer_template="Three clusters.",
        ),
        _fact(
            rankings,
            root,
            fact_id="sad193.fact.cc15.blender.pulses",
            source_ref="15_29",
            start_s=832.0,
            end_s=876.0,
            sound="A countertop blender or food processor runs in three separated motor bursts.",
            concepts=["blender_processor"],
            status="RETAIN_AUDIO_FACT",
            answer_information=(
                "Audio uniquely exposes the number and duration pattern of motor "
                "activations; sparse frames show the appliance but not the full pulse count."
            ),
            confidence_basis=[
                "blender_processor ranks 1-8 across one isolated 828-880 s cluster",
                "top-window margins over generic are 0.353-0.519",
                "waveform/spectrogram show three unmistakable sustained motor blocks",
                "bounded frames show the blender jar being operated between cooking actions",
            ],
            recurrence={
                "top15_cluster_count": 3,
                "dominant_cluster": "828-880 s contains ranks 1-8 and 14",
                "assessment": (
                    "This is the only high-confidence sustained blender cluster; "
                    "minor 676-708 and 1056-1064 detections are weak substitutes."
                ),
            },
            visual_substitute=(
                "Vision identifies the blender and can partially expose operation, "
                "but six sparse frames do not carry the exact three-burst pattern."
            ),
            speech_substitute=(
                "No quality-passing speech overlaps this interval; the source's "
                "only pass is non-substantive 'Mm-hmm.' at 180-210 s."
            ),
            recommended_profile="A",
            question_template=(
                "How many separate motor bursts does the countertop blender make "
                "before the participant returns to the pan?"
            ),
            answer_template="Three bursts.",
        ),
        _fact(
            rankings,
            root,
            fact_id="sad193.fact.cc26.microwave.transition",
            source_ref="26_22",
            start_s=916.0,
            end_s=925.0,
            sound="A steady microwave-like hum stops and is followed by a door/handling transient.",
            concepts=["microwave_operation", "appliance_beep"],
            status="RETAIN_AUDIO_FACT",
            answer_information=(
                "The acoustic transition carries appliance completion/stop timing "
                "immediately before retrieval."
            ),
            confidence_basis=[
                "microwave_operation ranks 1 and 3 at 916-928 s with margins 0.409-0.433",
                "spectrogram changes from steady low-frequency energy to a sharp transient",
                "bounded frames show the microwave opening, mug retrieval, and later stirring",
            ],
            recurrence={
                "top15_cluster_count": 7,
                "other_major_cluster": "820-868 s contains ranks 2 and 4-8",
                "assessment": (
                    "Microwave-like operation is recurrent; the local completion "
                    "transition is useful only when bound to the visible retrieval."
                ),
            },
            visual_substitute=(
                "Vision completely supplies microwave opening, mug retrieval, and "
                "stirring; audio only adds completion timing."
            ),
            speech_substitute="No canonical quality-passing speech overlaps.",
            recommended_profile="V+A",
            question_template=(
                "What appliance-related sound transition occurs just before the "
                "mug is removed?"
            ),
            answer_template="The microwave hum stops before the door is opened.",
        ),
        _fact(
            rankings,
            root,
            fact_id="sad193.fact.cc26.rinse",
            source_ref="26_22",
            start_s=456.0,
            end_s=464.0,
            sound="Running water accompanies rinsing a small utensil at the sink.",
            concepts=["running_water", "dish_washing", "pouring_liquid"],
            status="RETAIN_AUDIO_FACT",
            answer_information=(
                "Audio establishes active rinsing/water flow, while vision "
                "identifies the small red utensil."
            ),
            confidence_basis=[
                "running_water ranks 1-2 at 456-468 s with margins 0.305-0.306",
                "dish_washing ranks 2-3 and pouring_liquid ranks 1-2 in the same cluster",
                "spectrogram shows a bounded sustained noise onset",
                "bounded frames show the red utensil under the faucet",
            ],
            recurrence={
                "top15_cluster_count": 7,
                "assessment": (
                    "Water is highly recurrent; the event cannot be used as a "
                    "standalone object answer and requires the visual utensil route."
                ),
            },
            visual_substitute=(
                "Vision is needed for red-spoon identity and also shows sink use; "
                "audio adds the active water-flow fact."
            ),
            speech_substitute="No canonical quality-passing speech overlaps.",
            recommended_profile="V+A",
            question_template=(
                "What is happening audibly while the small red utensil is held "
                "under the faucet?"
            ),
            answer_template="Running water is rinsing it.",
        ),
    ]

    rejected = [
        {
            "finding_id": "sad193.reject.p27.sizzle.384",
            "source_ref": "P27_101",
            "interval": {"start_s": 384.0, "end_s": 420.0},
            "retrieval_label": "sizzling_frying",
            "disposition": "REJECT_AS_SOURCE_WORLD_LABEL",
            "reason": (
                "The waveform is broadband and high-frequency, but bounded "
                "frames show dish washing/rinsing at the sink rather than frying."
            ),
        },
        {
            "finding_id": "sad193.reject.p28.sizzle.1408",
            "source_ref": "P28_103",
            "interval": {"start_s": 1408.0, "end_s": 1448.0},
            "retrieval_label": "sizzling_frying",
            "disposition": "REJECT_AS_SOURCE_WORLD_LABEL",
            "reason": (
                "A strong rain-like/frying acoustic texture is present, but "
                "bounded frames do not show active frying and this repeats the "
                "Task167 false-positive warning."
            ),
        },
        {
            "finding_id": "sad193.reject.cc15.water.656",
            "source_ref": "15_29",
            "interval": {"start_s": 656.0, "end_s": 676.0},
            "retrieval_label": "running_water",
            "disposition": "REJECT_AS_SOURCE_WORLD_LABEL",
            "reason": (
                "Frames show pan/recipe interaction without faucet use; the "
                "low-frequency audio does not support a running-water fact."
            ),
        },
        {
            "finding_id": "sad193.reject.cc15.microwave.684",
            "source_ref": "15_29",
            "interval": {"start_s": 684.0, "end_s": 712.0},
            "retrieval_label": "microwave_operation",
            "disposition": "REJECT_AS_SOURCE_WORLD_LABEL",
            "reason": (
                "No microwave interaction appears in bounded frames and the "
                "beep similarity is below the generic maximum."
            ),
        },
        {
            "finding_id": "sad193.reject.cc26.wrapper.1216",
            "source_ref": "26_22",
            "interval": {"start_s": 1216.0, "end_s": 1240.0},
            "retrieval_label": "wrapper_tearing",
            "disposition": "REJECT_FOR_ANSWER_BEARING_USE",
            "reason": (
                "Package handling is visible, but the waveform lacks the "
                "distinctive irregular broadband tear/crinkle structure seen in "
                "P27 and does not supply a nonduplicated answer."
            ),
        },
        {
            "finding_id": "sad193.reject.cc16.chopstir.1088",
            "source_ref": "16_20",
            "interval": {"start_s": 1088.0, "end_s": 1108.0},
            "retrieval_label": "chopping",
            "disposition": "REJECT_FOR_NEW_AUDIO_LEAD",
            "reason": (
                "Frames show onion stirring/handling and the audio is mixed; "
                "Task191's visual onion-pan lead remains the cleaner formulation."
            ),
        },
    ]

    exact_counts = {
        "A": 2,
        "V+A": 8,
        "S+A": 0,
        "V+S+A": 0,
        "V+S": 0,
        "S": 0,
        "total_retained_audio_bearing_leads": 10,
    }
    pilot_repairs = {
        "recommended_profile_replacements": [
            {
                "profile": "A",
                "count": 2,
                "leads": [
                    "sad193.fact.cc15.blender.pulses",
                    "sad193.fact.cc16.timer.beep.sequence",
                ],
                "caveat": (
                    "Machine-expert provisional only. Trained-human listening "
                    "must verify event identity and exact count before the A "
                    "quota can be credited."
                ),
            },
            {
                "profile": "V+A",
                "count": 2,
                "recommended_priority": [
                    "sad193.fact.p27.wrapper.open",
                    "sad193.fact.p28.peel.scrape",
                ],
                "alternates": [
                    "sad193.fact.p28.chopping",
                    "sad193.fact.p28.water.start",
                    "sad193.fact.cc16.chopping",
                    "sad193.fact.cc16.stirring",
                    "sad193.fact.cc26.microwave.transition",
                    "sad193.fact.cc26.rinse",
                ],
                "caveat": (
                    "These are complementary audio facts but vision often "
                    "duplicates the action; they are not necessity findings."
                ),
            },
        ],
        "unrepaired_profiles": {
            "S+A": {
                "count": 0,
                "reason": (
                    "No interval combines substantive quality-passing speech "
                    "with a non-speech sound that independently carries part of "
                    "the answer."
                ),
            },
            "V+S+A": {
                "count": 0,
                "reason": (
                    "No inspected interval has nonduplicative dynamic vision, "
                    "substantive speech, and non-speech audio jointly carrying "
                    "the answer."
                ),
            },
        },
        "matrix_effect_if_human_confirmed": {
            "current_task192_profiles": {
                "V": 10,
                "S": 2,
                "A": 0,
                "V+S": 0,
                "V+A_or_S+A": 0,
                "V+S+A": 0,
            },
            "replace_four_visual_slots_not_add_slots": True,
            "prospective_profiles_after_replacement": {
                "V": 6,
                "S": 2,
                "A": 2,
                "V+S": 0,
                "V+A_or_S+A": 2,
                "V+S+A": 0,
            },
            "remaining_profile_shortfalls": {
                "V+S": 2,
                "V+S+A": 2,
            },
            "preferred_slot_actions": [
                (
                    "Regenerate two EPIC/Captain slots as A-only pulse/count "
                    "questions using cc15 blender and cc16 alert tones."
                ),
                (
                    "Regenerate two existing visual slots as V+A using P27 "
                    "wrapper opening and P28 peeling/scraping."
                ),
                (
                    "Do not relabel Task192's existing records; fresh normal-mode "
                    "records and human Task153 listening are required."
                ),
            ],
        },
    }

    full_timeline_audit = {
        "sources": {
            "P27_101": {
                "duration_s": 1360.2,
                "windows": 340,
                "retained_facts": [
                    "sad193.fact.p27.wrapper.open",
                ],
                "important_recurrence_or_substitutes": [
                    (
                        "Wrapper tearing has one dominant late cluster "
                        "(1284-1324 s) but weaker clusters at 960-976 s and "
                        "three isolated earlier hits."
                    ),
                    (
                        "Running-water and cookware-action detections recur "
                        "throughout the source; object-specific answers require vision."
                    ),
                    (
                        "The apparent 384-432 s frying cluster is actually sink "
                        "washing in bounded frames, proving a major acoustic substitute."
                    ),
                ],
            },
            "P28_103": {
                "duration_s": 1825.16,
                "windows": 456,
                "retained_facts": [
                    "sad193.fact.p28.peel.scrape",
                    "sad193.fact.p28.chopping",
                    "sad193.fact.p28.water.start",
                ],
                "important_recurrence_or_substitutes": [
                    (
                        "Running water has at least eleven separated top-15 "
                        "clusters and is unsuitable for an unbound A-only fact."
                    ),
                    (
                        "Peeling/scraping is confused with grating; vision is "
                        "required to bind the potato and handheld peeler."
                    ),
                    (
                        "Sizzle-like spectra recur at seven separated clusters; "
                        "the 1408-1448 s top cluster is not accepted as frying."
                    ),
                ],
            },
            "16_20": {
                "duration_s": 1930.9,
                "windows": 482,
                "retained_facts": [
                    "sad193.fact.cc16.chopping",
                    "sad193.fact.cc16.stirring",
                    "sad193.fact.cc16.timer.beep.sequence",
                ],
                "important_recurrence_or_substitutes": [
                    (
                        "Chopping has five separated top-15 clusters; local food "
                        "binding is required."
                    ),
                    (
                        "Stirring is most concentrated at 580-608 s but recurs in "
                        "six additional clusters."
                    ),
                    (
                        "Three strong tonal alert clusters at 676-752 s have no "
                        "visible emitting appliance in bounded frames; weaker "
                        "beep-like hits recur elsewhere."
                    ),
                    (
                        "The 1372-1396 s blender label is rejected after frames "
                        "show pan/onion handling and no visible blender."
                    ),
                ],
            },
            "15_29": {
                "duration_s": 1292.82,
                "windows": 323,
                "retained_facts": [
                    "sad193.fact.cc15.blender.pulses",
                ],
                "important_recurrence_or_substitutes": [
                    (
                        "The 828-880 s blender cluster contains ranks 1-8 and is "
                        "the only dominant sustained motor event; other hits are weak."
                    ),
                    (
                        "The three motor bursts are answer-bearing in audio, while "
                        "vision identifies the appliance but only partially carries count."
                    ),
                    (
                        "Top running-water at 664 s and microwave at 700 s are "
                        "rejected by bounded frames, which remain on pan/recipe activity."
                    ),
                ],
            },
            "26_22": {
                "duration_s": 1324.22,
                "windows": 331,
                "retained_facts": [
                    "sad193.fact.cc26.microwave.transition",
                    "sad193.fact.cc26.rinse",
                ],
                "important_recurrence_or_substitutes": [
                    (
                        "Microwave-operation similarity has a broad earlier "
                        "820-868 s cluster and a distinct 916-932 s retrieval cluster."
                    ),
                    (
                        "Running water has seven separated top-15 clusters, so "
                        "the red-spoon event must remain V+A rather than A-only."
                    ),
                    (
                        "Wrapper labels at 1212-1244 s are visible package "
                        "handling but not retained as answer-bearing semantic audio."
                    ),
                ],
            },
        },
        "generic_and_distractor_controls": {
            "used_in_every_window": True,
            "generic_margin_reported": True,
            "purpose": (
                "Suppress interpretation of windows whose target score is no "
                "better than speech, room tone, general kitchen activity, "
                "handling noise, hum, or unrelated environmental distractors."
            ),
        },
    }

    facts_document = _self_hashed(
        {
            "schema_version": SCHEMA_VERSION,
            "task": 193,
            "created_date": TASK_DATE,
            "artifact_classification": "MACHINE_EXPERT_PROVISIONAL_DEVELOPMENT_ONLY",
            "input_bindings": {
                "build_manifest": {
                    "path": f"{OUTPUT_REL}/build_manifest.json",
                    "sha256": _sha256_file(build_path),
                    "build_manifest_hash": build["build_manifest_hash"],
                },
                "rankings": {
                    "path": f"{OUTPUT_REL}/rankings.json",
                    "sha256": _sha256_file(rankings_path),
                    "rankings_hash": rankings["rankings_hash"],
                },
                "machine_review_packets": {
                    "path": f"{OUTPUT_REL}/machine_review_packets.json",
                    "sha256": _sha256_file(review_path),
                    "review_packet_hash": review["review_packet_hash"],
                },
            },
            "retained_audio_facts": facts,
            "rejected_or_non_answer_bearing_findings": rejected,
            "full_timeline_recurrence_and_substitute_audit": full_timeline_audit,
            "exact_lead_counts": exact_counts,
            "pilot_matrix_repairs": pilot_repairs,
            "boundary": {
                "semantic_audio_facts_are_provisional": True,
                "human_listening_performed": False,
                "h_tiers_assigned": False,
                "necessity_claimed": False,
                "minimality_claimed": False,
                "gate_a_eligible": False,
                "future_test_eligible": False,
                "no_persisted_media_clips": True,
            },
        },
        "facts_hash",
    )
    output_path = output / "provisional_audio_facts.json"
    _atomic_json(output_path, facts_document)
    return facts_document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    result = finalize(Path(args.repo_root))
    print(
        json.dumps(
            {
                "retained_audio_fact_count": len(result["retained_audio_facts"]),
                "rejected_finding_count": len(
                    result["rejected_or_non_answer_bearing_findings"]
                ),
                "exact_lead_counts": result["exact_lead_counts"],
                "facts_hash": result["facts_hash"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
