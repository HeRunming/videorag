#!/usr/bin/env python3
"""Integrate retained NOAA v5 leads with the frozen pilot-v4 planning matrix.

This tool creates a deterministic planning overlay.  It does not alter the
pilot-v4 roster, promote development records, make human decisions, or grant
Gate-A/test eligibility.  Coverage scenarios are inventory views only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
V4_PATH = ROOT / "data/rehearsal_plan/pilot_v4_candidate_matrix.json"
V5_REGISTRY_PATH = (
    ROOT
    / "data/restricted/noaa_targeted_family_candidates_v5_dev/"
    "candidate_registry.json"
)
DEFAULT_OUTPUT = ROOT / "data/rehearsal_plan/pilot_v5_candidate_matrix.json"

CREATED_DATE = "2026-10-12"
MATRIX_ID = "av-trace-pilot-v5-provisional-candidate-integration"
READY = "PILOT_V5_CANDIDATE_MATRIX_READY"
REPAIR = "PILOT_V5_CANDIDATE_MATRIX_REPAIR"

TARGETS = {
    "profiles": {
        "V": 2,
        "S": 2,
        "A": 2,
        "V+S": 2,
        "V+A_or_S+A": 2,
        "V+S+A": 2,
    },
    "hop": {"one": 6, "multi": 6},
    "temporal": {"near_local": 6, "far_separated": 6},
}

RETAINED_LEADS = (
    {
        "candidate_id": "NOAA-V5-047-OCEAN-MODEL-TWILIGHT",
        "source_id": "cand-047",
        "integration_slot_id": "PV5-DEV-NOAA47-01",
        "expected_status": "KEEP",
    },
    {
        "candidate_id": "NOAA-V5-051-TRASH-TRIP-DATA",
        "source_id": "cand-051",
        "integration_slot_id": "PV5-DEV-NOAA51-01",
        "expected_status": "KEEP",
    },
    {
        "candidate_id": "NOAA-V5-049-WAVE-ENTRY-RESCUE",
        "source_id": "cand-049",
        "integration_slot_id": "PV5-DEV-NOAA49-01",
        "expected_status": "REPAIR",
    },
)

FORBIDDEN_TRUE_FIELDS = (
    "human_review_performed",
    "human_decisions_created",
    "accepted_ses_created",
    "h_tiers_created",
    "gate_a_credit_created",
    "gate_a_go_asserted",
    "test_eligibility_created",
    "scientific_execution_authorized",
)


class IntegrationError(ValueError):
    """Raised when inputs or the generated planning matrix fail closed."""


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
    """Return a canonical SHA-256 identifier for a JSON-compatible value."""
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    """Hash a local file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def read_json(path: Path) -> Any:
    """Read one local JSON artifact."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrationError(f"cannot read JSON {path}: {exc}") from exc


def _relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _profile_bucket(label: str) -> str:
    if label in {"V+A", "S+A"}:
        return "V+A_or_S+A"
    return label


def _count_slots(slots: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    profiles: Counter[str] = Counter()
    hop: Counter[str] = Counter()
    temporal: Counter[str] = Counter()
    source_slots: Counter[str] = Counter()
    for slot in slots:
        label = slot["profile"]["label"]
        profiles[label] += 1
        if label in {"V+A", "S+A"}:
            profiles["V+A_or_S+A"] += 1
        hop[slot["hop_temporal"]["hop"]] += 1
        temporal[slot["hop_temporal"]["temporal"]] += 1
        source_slots[slot["source_group_id"]] += 1
    return {
        "profiles": dict(sorted(profiles.items())),
        "hop": dict(sorted(hop.items())),
        "temporal": dict(sorted(temporal.items())),
        "source_slots": dict(sorted(source_slots.items())),
    }


def _baseline_slot_summary(slot: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot_id": slot["slot_id"],
        "source_id": slot["source_id"],
        "source_group_id": slot["source_group_id"],
        "profile": slot["profile"]["label"],
        "profile_status": slot["profile"]["status"],
        "hop": slot["hop_temporal"]["hop"],
        "temporal": slot["hop_temporal"]["temporal"],
        "matrix_disposition": slot["matrix_disposition"],
        "unchanged_from_v4": True,
    }


def _retained_lead_summary(
    lead_spec: dict[str, str], candidate: dict[str, Any]
) -> dict[str, Any]:
    temporal = candidate["temporal_structure"]
    return {
        "integration_slot_id": lead_spec["integration_slot_id"],
        "candidate_id": candidate["candidate_id"],
        "source_id": candidate["source_id"],
        "source_group_id": candidate["source_id"],
        "provisional_status": candidate["provisional_status"],
        "profile": candidate["hypothesized_profile"]["label"],
        "profile_status": candidate["hypothesized_profile"]["status"],
        "hop": (
            "multi"
            if temporal["hop_hypothesis"] == "multi_hop"
            else temporal["hop_hypothesis"]
        ),
        "source_hop_hypothesis": temporal["hop_hypothesis"],
        "temporal": temporal["temporal_hypothesis"],
        "evidence_center_separation_s": temporal[
            "evidence_center_separation_s"
        ],
        "question_hypothesis": candidate["question_hypothesis"],
        "answer_hypothesis": candidate["answer_hypothesis"],
        "candidate_payload_sha256": candidate["candidate_payload_sha256"],
        "human_reviewed": candidate["human_reviewed"],
        "accepted_ses_count": candidate["accepted_ses_count"],
        "h_tier": candidate["h_tier"],
        "gate_a_credit": candidate["gate_a_credit"],
        "future_test_eligible": candidate["future_test_eligible"],
        "integration_treatment": (
            "ADDITIVE_DEVELOPMENT_LEAD_OVERLAY_NOT_A_PILOT_V4_SLOT_REPLACEMENT"
        ),
        "counts_in_baseline_v4": False,
        "counts_in_gate_a": False,
        "requires_human_prescreen": True,
    }


def _added_counts(leads: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    profiles: Counter[str] = Counter()
    hop: Counter[str] = Counter()
    temporal: Counter[str] = Counter()
    for lead in leads:
        profiles[lead["profile"]] += 1
        if lead["profile"] in {"V+A", "S+A"}:
            profiles["V+A_or_S+A"] += 1
        hop[lead["hop"]] += 1
        temporal[lead["temporal"]] += 1
    return {
        "profiles": dict(sorted(profiles.items())),
        "hop": dict(sorted(hop.items())),
        "temporal": dict(sorted(temporal.items())),
    }


def _combine_counts(
    baseline: dict[str, dict[str, int]],
    added: dict[str, dict[str, int]],
) -> dict[str, dict[str, int]]:
    combined: dict[str, dict[str, int]] = {}
    for dimension in ("profiles", "hop", "temporal"):
        keys = set(baseline[dimension]) | set(added[dimension])
        combined[dimension] = {
            key: baseline[dimension].get(key, 0)
            + added[dimension].get(key, 0)
            for key in sorted(keys)
        }
    return combined


def _comparison(
    *,
    target: int,
    baseline: int,
    combined: int,
    caveat: str,
) -> dict[str, Any]:
    return {
        "target": target,
        "baseline_v4": baseline,
        "retained_lead_delta": combined - baseline,
        "provisional_inventory_total": combined,
        "provisional_shortage": max(0, target - combined),
        "provisionally_closed_by_retained_leads": combined >= target,
        "accepted_or_gate_a_credit": 0,
        "caveat": caveat,
    }


def _scenario(
    name: str,
    included_statuses: set[str],
    baseline_counts: dict[str, dict[str, int]],
    baseline_source_groups: list[str],
    retained: list[dict[str, Any]],
) -> dict[str, Any]:
    included = [
        lead for lead in retained if lead["provisional_status"] in included_statuses
    ]
    added = _added_counts(included)
    combined = _combine_counts(baseline_counts, added)
    source_groups = baseline_source_groups + [
        lead["source_group_id"] for lead in included
    ]
    common_caveat = (
        "Inventory coverage only. The leads are not human-confirmed, are not "
        "inserted into the frozen 12-slot roster, and earn no Gate-A credit."
    )
    return {
        "scenario": name,
        "included_statuses": sorted(included_statuses),
        "included_candidate_ids": [lead["candidate_id"] for lead in included],
        "excluded_candidate_ids": [
            lead["candidate_id"] for lead in retained if lead not in included
        ],
        "inventory_view": {
            "baseline_v4_candidate_slots": 12,
            "retained_development_leads": len(included),
            "raw_candidate_inventory": 12 + len(included),
            "baseline_source_groups": len(baseline_source_groups),
            "added_source_groups": len(included),
            "raw_source_group_inventory": len(source_groups),
            "source_group_ids": source_groups,
            "counts_are_additive_without_replacement_or_double_counting": True,
            "constraint_valid_exact_pilot_roster": False,
        },
        "delta_from_baseline_v4": added,
        "provisional_inventory_counts": combined,
        "shortage_closure": {
            "V+S": _comparison(
                target=TARGETS["profiles"]["V+S"],
                baseline=baseline_counts["profiles"].get("V+S", 0),
                combined=combined["profiles"].get("V+S", 0),
                caveat=common_caveat,
            ),
            "multi_hop": _comparison(
                target=TARGETS["hop"]["multi"],
                baseline=baseline_counts["hop"].get("multi", 0),
                combined=combined["hop"].get("multi", 0),
                caveat=common_caveat,
            ),
            "far_separated": _comparison(
                target=TARGETS["temporal"]["far_separated"],
                baseline=baseline_counts["temporal"].get("far_separated", 0),
                combined=combined["temporal"].get("far_separated", 0),
                caveat=common_caveat,
            ),
            "V+S+A": _comparison(
                target=TARGETS["profiles"]["V+S+A"],
                baseline=baseline_counts["profiles"].get("V+S+A", 0),
                combined=combined["profiles"].get("V+S+A", 0),
                caveat=(
                    "Unsupported in both the v4 baseline and retained v5 "
                    "leads. No ambient label, music, surf, handling sound, or "
                    "co-occurrence may be used to force triple-modal credit."
                ),
            ),
        },
        "structural_constraint_result": {
            "exact_six_source_groups": False,
            "exact_two_candidates_per_source_group": False,
            "exact_twelve_candidates": False,
            "presentation_wrapped_group_cap_satisfied": False,
            "reason": (
                "Each retained NOAA lead is one development candidate from a "
                "new presentation-wrapped source group. Adding it would exceed "
                "the frozen 12-slot/six-group roster, leave that new group with "
                "only one candidate, and exceed the two-presentation-group cap "
                "when cand-052 remains. A future roster change must be explicit."
            ),
        },
    }


def _build_next_wave() -> dict[str, Any]:
    return {
        "ordering_rule": (
            "Prescreen retained exact-source leads first; acquire missing "
            "audio-rich independent groups next; narrow targets only after a "
            "documented acquisition no-go and before candidate selection."
        ),
        "wave_0_human_prescreen": [
            {
                "action_id": "PV5-HP-047",
                "integration_slot_id": "PV5-DEV-NOAA47-01",
                "candidate_id": "NOAA-V5-047-OCEAN-MODEL-TWILIGHT",
                "current_status": "KEEP",
                "priority": 1,
                "required_before_review": (
                    "Affirmative source/component annotation authority and "
                    "embedded-clip lineage closure."
                ),
                "review_goal": (
                    "Blind source-uniform visual/speech prescreen and complete "
                    "poll, label, caption, spoken-construction, and recurrence "
                    "route closure."
                ),
                "automatic_roster_replacement": False,
            },
            {
                "action_id": "PV5-HP-051",
                "integration_slot_id": "PV5-DEV-NOAA51-01",
                "candidate_id": "NOAA-V5-051-TRASH-TRIP-DATA",
                "current_status": "KEEP",
                "priority": 1,
                "required_before_review": (
                    "Affirmative source/component annotation authority and "
                    "embedded field-clip lineage closure."
                ),
                "review_goal": (
                    "Blind source-uniform visual/speech prescreen and complete "
                    "narration, app-screen, map, caption, and recurrence route "
                    "closure."
                ),
                "automatic_roster_replacement": False,
            },
            {
                "action_id": "PV5-HP-049-REPAIR",
                "integration_slot_id": "PV5-DEV-NOAA49-01",
                "candidate_id": "NOAA-V5-049-WAVE-ENTRY-RESCUE",
                "current_status": "REPAIR",
                "priority": 2,
                "required_before_review": (
                    "Affirmative annotation authority; preserve the rejected "
                    "surf exclusions and group repeated rescue sequences."
                ),
                "review_goal": (
                    "Determine whether dynamic posture plus later rescue speech "
                    "survives narration, OCR/911, repeat-animation, repeat-speech, "
                    "and coherence challenges."
                ),
                "automatic_roster_replacement": False,
            },
        ],
        "wave_1_new_audio_rich_source_acquisition": [
            {
                "target_slot": "B08",
                "required_profile": "V+S+A",
                "required_hop": "multi",
                "required_temporal": "far_separated",
                "source_requirement": (
                    "New non-presentation, rights-ready, audio-rich source group "
                    "with dynamic non-text vision, substantive speech, and a "
                    "concrete localizable non-speech event."
                ),
                "second_candidate_requirement": (
                    "The same source group needs a second defensible candidate "
                    "before it can satisfy the exact two-per-group pilot rule."
                ),
            },
            {
                "target_slot": "B12",
                "required_profile": "V+S+A",
                "required_hop": "multi",
                "required_temporal": "far_separated",
                "source_requirement": (
                    "A source-disjoint non-presentation lineage meeting the "
                    "same three-modality and far-composition requirements."
                ),
                "second_candidate_requirement": (
                    "The same source group needs a second defensible candidate "
                    "before it can satisfy the exact two-per-group pilot rule."
                ),
            },
            {
                "target_slot": "FAR-KEEP-ONLY-01",
                "required_profile": "OPEN_PROSPECTIVE_NON_FORCED",
                "required_hop": "multi",
                "required_temporal": "far_separated",
                "activation_condition": (
                    "Required if cand-049 remains REPAIR/NO_GO and only the two "
                    "KEEP leads survive. B08 and B12 would raise far inventory "
                    "from three to five, leaving one far cell open."
                ),
                "source_requirement": (
                    "Prefer a source group already admitted by an explicit "
                    "roster redesign; otherwise acquire another rights-ready "
                    "independent source with two-candidate potential."
                ),
            },
        ],
        "wave_2_prospective_target_narrowing": [
            {
                "target_slots": ["B08", "B12"],
                "trigger": (
                    "Both targeted audio-rich acquisition routes are documented "
                    "NO_GO or infeasible under unchanged rights and semantic rules."
                ),
                "required_action": (
                    "Freeze a prospective addendum that reduces/removes the two "
                    "V+S+A targets and names replacement profiles before roster "
                    "construction; never relabel retained leads as V+S+A."
                ),
            },
            {
                "target_slots": ["far_separated_quota"],
                "trigger": (
                    "After human prescreen and acquisition, fewer than six "
                    "coherent far/multi prospects remain."
                ),
                "required_action": (
                    "Freeze the revised far target and corresponding near/far "
                    "balance prospectively. The known retained-lead ceiling is "
                    "four far inventory cells in the optimistic scenario and "
                    "three in the KEEP-only scenario before new acquisition."
                ),
            },
            {
                "target_slots": ["B02", "B11"],
                "trigger": (
                    "Retained NOAA V+S leads pass semantics but cannot be placed "
                    "under six-source, two-candidates-per-source, or presentation "
                    "caps."
                ),
                "required_action": (
                    "Either explicitly redesign the full six-group roster with "
                    "a second candidate for every admitted NOAA group, or acquire "
                    "non-presentation V+S sources. Do not silently replace v4 slots."
                ),
            },
        ],
    }


def build_matrix() -> dict[str, Any]:
    """Build the deterministic provisional integration matrix."""
    v4 = read_json(V4_PATH)
    v5 = read_json(V5_REGISTRY_PATH)

    slots = v4.get("candidate_slots", [])
    if len(slots) != 12:
        raise IntegrationError("pilot-v4 baseline must contain exactly 12 slots")
    if v4.get("decision_token") != "PILOT_V4_CANDIDATE_MATRIX_REPAIR":
        raise IntegrationError("unexpected pilot-v4 decision token")

    candidates_by_id = {
        candidate["candidate_id"]: candidate for candidate in v5["candidates"]
    }
    retained: list[dict[str, Any]] = []
    for spec in RETAINED_LEADS:
        candidate = candidates_by_id.get(spec["candidate_id"])
        if candidate is None:
            raise IntegrationError(f"missing retained lead {spec['candidate_id']}")
        if candidate["source_id"] != spec["source_id"]:
            raise IntegrationError(f"source changed for {spec['candidate_id']}")
        if candidate["provisional_status"] != spec["expected_status"]:
            raise IntegrationError(f"status changed for {spec['candidate_id']}")
        retained.append(_retained_lead_summary(spec, candidate))

    baseline_counts = _count_slots(slots)
    baseline_groups = sorted(baseline_counts["source_slots"])
    conservative = _scenario(
        "CONSERVATIVE_KEEP_ONLY",
        {"KEEP"},
        baseline_counts,
        baseline_groups,
        retained,
    )
    optimistic = _scenario(
        "OPTIMISTIC_ALL_RETAINED_KEEP_PLUS_REPAIR",
        {"KEEP", "REPAIR"},
        baseline_counts,
        baseline_groups,
        retained,
    )

    matrix: dict[str, Any] = {
        "schema_version": "av-trace.pilot-v5-candidate-integration/1.0",
        "matrix_id": MATRIX_ID,
        "created_date": CREATED_DATE,
        "decision_token": REPAIR,
        "artifact_classification": (
            "PROVISIONAL_DEVELOPMENT_LEAD_INTEGRATION_PLANNING_ONLY"
        ),
        "scope": {
            "objective": (
                "Overlay retained NOAA v5 development-only leads on the frozen "
                "pilot-v4 baseline without replacement or double counting."
            ),
            "baseline_v4_slots_modified": 0,
            "retained_leads_integrated": 3,
            "human_review_performed": False,
            "human_decisions_created": False,
            "accepted_ses_created": 0,
            "h_tiers_created": 0,
            "gate_a_credit_created": 0,
            "gate_a_go_asserted": False,
            "test_eligibility_created": False,
            "scientific_execution_authorized": False,
        },
        "input_bindings": [
            {
                "path": _relative(V4_PATH),
                "sha256": file_hash(V4_PATH),
                "role": "Frozen pilot-v4 baseline matrix",
            },
            {
                "path": _relative(V5_REGISTRY_PATH),
                "sha256": file_hash(V5_REGISTRY_PATH),
                "role": "NOAA v5 development-only retained lead registry",
            },
        ],
        "integration_rules": {
            "baseline_is_immutable": True,
            "lead_overlay_is_additive_inventory_only": True,
            "no_silent_replacement": True,
            "no_candidate_double_counting": True,
            "existing_statuses_preserved": True,
            "source_group_is_complete_source_plus_correlated_derivatives": True,
            "one_hop_far_prohibited": True,
            "vsa_requires_independent_v_s_and_a": True,
            "coverage_is_not_acceptance_or_gate_a_credit": True,
        },
        "pivot_v2_targets": TARGETS,
        "baseline_v4": {
            "matrix_id": v4["matrix_id"],
            "decision_token": v4["decision_token"],
            "candidate_slot_count": len(slots),
            "source_group_count": len(baseline_groups),
            "source_group_ids": baseline_groups,
            "counts": baseline_counts,
            "slots": [_baseline_slot_summary(slot) for slot in slots],
            "all_slots_and_statuses_preserved": True,
        },
        "retained_v5_development_leads": retained,
        "coverage_scenarios": {
            "conservative_keep_only": conservative,
            "optimistic_all_retained": optimistic,
        },
        "cross_scenario_conclusion": {
            "V+S_shortage_can_be_provisionally_closed": True,
            "multi_hop_shortage_can_be_provisionally_closed": True,
            "far_shortage_can_be_provisionally_closed": False,
            "V+S+A_supported": False,
            "conservative_far_remaining": conservative["shortage_closure"][
                "far_separated"
            ]["provisional_shortage"],
            "optimistic_far_remaining": optimistic["shortage_closure"][
                "far_separated"
            ]["provisional_shortage"],
            "exact_roster_can_be_closed_by_direct_addition": False,
            "reason": (
                "The leads cover V+S and multi-hop inventory gaps, but only add "
                "two or three far leads to the single v4 far hypothesis. They "
                "supply no V+S+A lead and cannot be directly inserted without "
                "violating frozen source-group, slot-count, two-per-source, and "
                "presentation-cap constraints."
            ),
        },
        "exact_next_wave": _build_next_wave(),
        "final_boundary_statement": (
            "This artifact is a deterministic planning overlay. It preserves "
            "all pilot-v4 records and NOAA v5 KEEP/REPAIR statuses, creates no "
            "human decision or accepted SES, assigns no H tier, grants no Gate-A "
            "credit, and creates no test eligibility."
        ),
    }
    matrix["matrix_payload_sha256"] = object_hash(matrix)
    validate_matrix(matrix, v4=v4, v5=v5)
    return matrix


def validate_matrix(
    matrix: dict[str, Any],
    *,
    v4: dict[str, Any] | None = None,
    v5: dict[str, Any] | None = None,
) -> None:
    """Fail closed on status, accounting, source, and governance drift."""
    if matrix.get("decision_token") != REPAIR:
        raise IntegrationError("decision must remain REPAIR")
    scope = matrix.get("scope", {})
    for field in FORBIDDEN_TRUE_FIELDS:
        expected = 0 if field.endswith("_created") else False
        if scope.get(field) != expected:
            raise IntegrationError(f"scope creates prohibited credit: {field}")
    if scope.get("baseline_v4_slots_modified") != 0:
        raise IntegrationError("pilot-v4 slots were modified")

    v4 = v4 or read_json(V4_PATH)
    v5 = v5 or read_json(V5_REGISTRY_PATH)
    source_slots = v4["candidate_slots"]
    summaries = matrix.get("baseline_v4", {}).get("slots", [])
    if len(summaries) != len(source_slots) or len(summaries) != 12:
        raise IntegrationError("baseline slot summary is incomplete")
    expected_summaries = [_baseline_slot_summary(slot) for slot in source_slots]
    if summaries != expected_summaries:
        raise IntegrationError("baseline slot/status preservation failed")

    retained = matrix.get("retained_v5_development_leads", [])
    if [item.get("candidate_id") for item in retained] != [
        item["candidate_id"] for item in RETAINED_LEADS
    ]:
        raise IntegrationError("retained lead order or identity changed")
    if [item.get("provisional_status") for item in retained] != [
        "KEEP",
        "KEEP",
        "REPAIR",
    ]:
        raise IntegrationError("retained KEEP/REPAIR statuses changed")
    ids = [slot["slot_id"] for slot in summaries] + [
        item["integration_slot_id"] for item in retained
    ]
    if len(ids) != len(set(ids)):
        raise IntegrationError("candidate/slot double counting detected")
    if {item["source_group_id"] for item in retained} & {
        item["source_group_id"] for item in summaries
    }:
        raise IntegrationError("retained source was silently merged with baseline")

    current_candidates = {
        item["candidate_id"]: item for item in v5.get("candidates", [])
    }
    for lead in retained:
        source = current_candidates.get(lead["candidate_id"])
        if source is None:
            raise IntegrationError("retained lead missing from v5 registry")
        if lead["provisional_status"] != source["provisional_status"]:
            raise IntegrationError("retained status differs from v5 registry")
        if lead["candidate_payload_sha256"] != source["candidate_payload_sha256"]:
            raise IntegrationError("retained payload binding differs from registry")
        if (
            lead["human_reviewed"] is not False
            or lead["accepted_ses_count"] != 0
            or lead["h_tier"] is not None
            or lead["gate_a_credit"] is not False
            or lead["future_test_eligible"] is not False
        ):
            raise IntegrationError("retained lead was improperly promoted")

    scenarios = matrix.get("coverage_scenarios", {})
    expected_scenario_ids = {
        "conservative_keep_only": [
            "NOAA-V5-047-OCEAN-MODEL-TWILIGHT",
            "NOAA-V5-051-TRASH-TRIP-DATA",
        ],
        "optimistic_all_retained": [
            "NOAA-V5-047-OCEAN-MODEL-TWILIGHT",
            "NOAA-V5-051-TRASH-TRIP-DATA",
            "NOAA-V5-049-WAVE-ENTRY-RESCUE",
        ],
    }
    for name, expected_ids in expected_scenario_ids.items():
        scenario = scenarios.get(name, {})
        if scenario.get("included_candidate_ids") != expected_ids:
            raise IntegrationError(f"{name} retained lead set changed")
        if scenario.get("inventory_view", {}).get(
            "constraint_valid_exact_pilot_roster"
        ):
            raise IntegrationError(f"{name} falsely claims exact roster validity")
        closure = scenario.get("shortage_closure", {})
        if closure.get("V+S", {}).get("accepted_or_gate_a_credit") != 0:
            raise IntegrationError("scenario claims accepted V+S credit")
        if closure.get("V+S+A", {}).get(
            "provisionally_closed_by_retained_leads"
        ):
            raise IntegrationError("scenario invents V+S+A support")

    expected_closure = {
        "conservative_keep_only": {
            "V+S": (True, 0),
            "multi_hop": (True, 0),
            "far_separated": (False, 3),
            "V+S+A": (False, 2),
        },
        "optimistic_all_retained": {
            "V+S": (True, 0),
            "multi_hop": (True, 0),
            "far_separated": (False, 2),
            "V+S+A": (False, 2),
        },
    }
    for scenario_name, dimensions in expected_closure.items():
        closure = scenarios[scenario_name]["shortage_closure"]
        for dimension, (closed, shortage) in dimensions.items():
            if (
                closure[dimension]["provisionally_closed_by_retained_leads"]
                is not closed
                or closure[dimension]["provisional_shortage"] != shortage
            ):
                raise IntegrationError(
                    f"{scenario_name} {dimension} closure accounting changed"
                )

    conclusion = matrix.get("cross_scenario_conclusion", {})
    if (
        conclusion.get("V+S_shortage_can_be_provisionally_closed") is not True
        or conclusion.get("multi_hop_shortage_can_be_provisionally_closed")
        is not True
        or conclusion.get("far_shortage_can_be_provisionally_closed") is not False
        or conclusion.get("V+S+A_supported") is not False
        or conclusion.get("exact_roster_can_be_closed_by_direct_addition")
        is not False
    ):
        raise IntegrationError("cross-scenario conclusion is not fail-closed")

    acquisitions = matrix.get("exact_next_wave", {}).get(
        "wave_1_new_audio_rich_source_acquisition", []
    )
    if [item.get("target_slot") for item in acquisitions] != [
        "B08",
        "B12",
        "FAR-KEEP-ONLY-01",
    ]:
        raise IntegrationError("exact acquisition wave changed")

    expected_hash = object_hash(
        {
            key: value
            for key, value in matrix.items()
            if key != "matrix_payload_sha256"
        }
    )
    if matrix.get("matrix_payload_sha256") != expected_hash:
        raise IntegrationError("matrix payload hash mismatch")


def write_matrix(path: Path, matrix: dict[str, Any]) -> None:
    """Write the canonical matrix."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(matrix))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output matrix path.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate that the checked-in output matches a fresh build.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        matrix = build_matrix()
        output = args.output.resolve()
        if args.check:
            existing = read_json(output)
            validate_matrix(existing)
            if canonical_bytes(existing) != canonical_bytes(matrix):
                raise IntegrationError(
                    "existing matrix differs from deterministic build"
                )
        else:
            write_matrix(output, matrix)
        print(REPAIR)
        return 0
    except IntegrationError as exc:
        print(f"{REPAIR}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
