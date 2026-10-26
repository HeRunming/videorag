"""Deterministic planning fixture for the 12 reported plus 2 calibration slots."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from .contracts import (
    SCHEMA_VERSION,
    SlotSpec,
    json_hash,
    validate_candidate_registry,
    validate_slot_matrix,
)


def slot_mappings() -> list[dict[str, Any]]:
    """Return the frozen slot design; targets remain hypotheses."""
    rows = [
        (
            "F01",
            "SG-OXFORD-QM-001",
            "new_source",
            "V",
            ("vision",),
            "necessity_group_withholding",
            "one_hop",
            "near_local",
            {"vision": "lecture apparatus blackboard quantum demonstration"},
            None,
        ),
        (
            "F02",
            "SG-OXFORD-QM-001",
            "new_source",
            "V+A/S+A",
            ("speech", "ambient"),
            "modality_channel_outage",
            "multi_hop",
            "far_separated",
            {
                "speech": "quantum mechanics explanation probability",
                "ambient": "applause writing chalk sound",
            },
            None,
        ),
        (
            "F03",
            "SG-OXFORD-DHL-CONSCIOUSNESS",
            "new_source",
            "S",
            ("speech",),
            "modality_channel_outage",
            "one_hop",
            "near_local",
            {"speech": "lawrence consciousness literature argument"},
            None,
        ),
        (
            "F04",
            "SG-OXFORD-DHL-CONSCIOUSNESS",
            "new_source",
            "V+S",
            ("vision", "speech"),
            "necessity_group_withholding",
            "multi_hop",
            "far_separated",
            {
                "vision": "lecture slide literary quotation",
                "speech": "speaker interpretation lawrence quotation",
            },
            None,
        ),
        (
            "F05",
            "SG-MIT-RES12-003-L01",
            "new_source",
            "A",
            ("ambient",),
            "modality_channel_outage",
            "one_hop",
            "far_separated",
            {"ambient": "writing chalk impact demonstration sound"},
            None,
        ),
        (
            "F06",
            "SG-MIT-RES12-003-L01",
            "new_source",
            "V+S+A",
            ("vision", "speech", "ambient"),
            "necessity_group_withholding",
            "multi_hop",
            "near_local",
            {
                "vision": "fluid dynamics demonstration apparatus",
                "speech": "fluid flow explanation demonstration",
                "ambient": "water writing impact sound",
            },
            None,
        ),
        (
            "F07",
            "SG-YALE-PHYS200-L01",
            "new_source",
            "V",
            ("vision",),
            "necessity_group_withholding",
            "one_hop",
            "near_local",
            {"vision": "physics lecture experiment apparatus blackboard"},
            None,
        ),
        (
            "F08",
            "SG-YALE-PHYS200-L01",
            "new_source",
            "V+A/S+A",
            ("vision", "ambient"),
            "necessity_group_withholding",
            "multi_hop",
            "far_separated",
            {
                "vision": "physics demonstration moving apparatus",
                "ambient": "impact mechanical writing sound",
            },
            None,
        ),
        (
            "F09",
            "cand-049",
            "noaa_development",
            "A",
            ("ambient",),
            "necessity_group_withholding",
            "one_hop",
            "far_separated",
            {"ambient": "ocean waves surf wind"},
            "noaa01-r004-surf-av",
        ),
        (
            "F10",
            "cand-049",
            "noaa_development",
            "V+S+A",
            ("vision", "speech", "ambient"),
            "modality_channel_outage",
            "multi_hop",
            "near_local",
            {
                "vision": "person water safety near shore",
                "speech": "beach bay safety instruction",
                "ambient": "ocean waves surf wind",
            },
            "noaa01-r004-surf-av",
        ),
        (
            "F11",
            "cand-052",
            "noaa_development",
            "S",
            ("speech",),
            "modality_channel_outage",
            "one_hop",
            "near_local",
            {"speech": "main area hurricane activity basin"},
            "noaa01-r017-north-atlantic-basin",
        ),
        (
            "F12",
            "cand-052",
            "noaa_development",
            "V+S",
            ("vision", "speech"),
            "modality_channel_outage",
            "multi_hop",
            "far_separated",
            {
                "vision": "hurricane formation factors educational graphic",
                "speech": "three hurricane formation factors",
            },
            "noaa01-r016-three-factors-vs",
        ),
    ]
    mappings = [
        {
            "slot_id": slot_id,
            "source_id": source_id,
            "source_kind": source_kind,
            "included_in_reported_denominator": True,
            "target_modality_profile": profile,
            "target_modalities": list(modalities),
            "target_intervention": intervention,
            "target_hop_stratum": hop,
            "target_temporal_stratum": temporal,
            "queries": queries,
            "seed_family_id": seed,
            "calibration_purpose": None,
        }
        for (
            slot_id,
            source_id,
            source_kind,
            profile,
            modalities,
            intervention,
            hop,
            temporal,
            queries,
            seed,
        ) in rows
    ]
    mappings.extend(
        [
            {
                "slot_id": "CAL01",
                "source_id": "cand-051",
                "source_kind": "noaa_development",
                "included_in_reported_denominator": False,
                "target_modality_profile": "V",
                "target_modalities": ["vision"],
                "target_intervention": "necessity_group_withholding",
                "target_hop_stratum": "one_hop",
                "target_temporal_stratum": "near_local",
                "queries": {"vision": "discarded plastic introductory montage"},
                "seed_family_id": "noaa01-r007-opening-plastic-waste",
                "calibration_purpose": "excluded_low_risk_visual_anchor",
            },
            {
                "slot_id": "CAL02",
                "source_id": "SG-OXFORD-DHL-CONSCIOUSNESS",
                "source_kind": "new_source",
                "included_in_reported_denominator": False,
                "target_modality_profile": "S",
                "target_modalities": ["speech"],
                "target_intervention": "modality_channel_outage",
                "target_hop_stratum": "one_hop",
                "target_temporal_stratum": "near_local",
                "queries": {"speech": "lecture opening statement"},
                "seed_family_id": None,
                "calibration_purpose": "excluded_wording_and_timing_calibration",
            },
        ]
    )
    return mappings


def slot_specs() -> tuple[SlotSpec, ...]:
    """Return validated immutable slot objects."""
    slots = tuple(SlotSpec.from_mapping(item) for item in slot_mappings())
    validate_slot_matrix(slots)
    return slots


def build_dry_run_fixture_registry() -> dict[str, Any]:
    """Build the committed non-family fixture registry deterministically."""
    slots = slot_specs()
    fixture_slots = []
    for slot in slots:
        fixture_candidate = {
            "candidate_family_id": f"fixture.mpf.{slot.slot_id.casefold()}",
            "record_kind": "dry_run_slot_fixture_not_a_real_family",
            "current_tier": "P0_MACHINE_CANDIDATE",
            "question_hypothesis": "FIXTURE_ONLY_NOT_AUTHORED",
            "answer_hypothesis": "FIXTURE_ONLY_NOT_VERIFIED",
            "atomic_claims": [],
            "evidence_intervals": [],
            "ses_hypotheses": [],
            "machine_leave_one_out_checks": [],
            "machine_modality_drop_checks": [],
            "derived_route_closure_registry": {
                "status": "FIXTURE_ONLY_NOT_EXECUTED",
                "human_route_saturation_asserted": False,
            },
            "cbr_no_trigger_templates": {
                "status": "FIXTURE_ONLY_NOT_EXECUTED",
                "states": ["CLEAN", "BLOCKED", "RESTORED", "NO_TRIGGER"],
                "human_pair_isolation_asserted": False,
            },
            "strata": {
                "target": {
                    "modality_profile": slot.target_modality_profile,
                    "intervention": slot.target_intervention,
                    "hop_stratum": slot.target_hop_stratum,
                    "temporal_stratum": slot.target_temporal_stratum,
                },
                "observed": None,
                "outcome": "NOT_MINED",
                "quota_forcing_forbidden": True,
            },
            "risk_flags": {
                "status": "NOT_MINED",
                "human_minimality_unverified": True,
                "human_necessity_unverified": True,
            },
            "source_split": {
                "source_group_id": slot.source_id,
                "source_kind": slot.source_kind,
                "construction_split": (
                    "NEW_SOURCE_MINI_PILOT_CONSTRUCTION"
                    if slot.source_kind == "new_source"
                    else "NOAA_CONSUMED_DEVELOPMENT_ONLY"
                ),
                "future_primary_test_eligible": (
                    slot.source_kind == "new_source"
                ),
                "source_group_split_required": True,
            },
            "provenance": {
                "record_origin": "deterministic_planning_fixture",
                "real_index_accessed": False,
                "real_family_generated": False,
                "seed_family_id": slot.seed_family_id,
            },
            "human_reviewed": False,
            "human_gold": False,
            "final_accepted": False,
            "human_minimality_asserted": False,
            "human_necessity_asserted": False,
        }
        fixture_slots.append(
            {
                "slot_id": slot.slot_id,
                "included_in_reported_denominator": (
                    slot.included_in_reported_denominator
                ),
                "excluded_calibration": (
                    not slot.included_in_reported_denominator
                ),
                "calibration_purpose": slot.calibration_purpose,
                "source_id": slot.source_id,
                "source_kind": slot.source_kind,
                "slot_status": "DRY_RUN_FIXTURE_ONLY",
                "target_hypothesis": fixture_candidate["strata"]["target"],
                "queries": dict(slot.queries),
                "candidate": fixture_candidate,
            }
        )
    matrix = validate_slot_matrix(slots)
    registry = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": "mini-pilot-family-mining-v1-dry-run",
        "registry_kind": "DETERMINISTIC_DRY_RUN_FIXTURE",
        "status": "DRY_RUN_FIXTURE_NOT_REAL_FAMILIES",
        "created_date": "2026-09-23",
        "authoritative_contracts": [
            "docs/paper/cvpr_pivot_decision_and_6week_plan.md",
            "docs/review/human_mini_pilot_source_pool_plan.md",
            "docs/annotation/construct_validity_protocol.md",
            "docs/design/scale1a_full_timeline_design.md",
            "docs/design/mini_pilot_full_timeline_index_v1.md",
        ],
        "input_contract": {
            "canonical_new_source_index": (
                "data/restricted/mini_pilot_index_v1"
            ),
            "canonical_index_must_be_complete_non_smoke": True,
            "frozen_noaa_index": "data/restricted/noaa01/scale1a",
            "official_sidecars": "derived_route_challenge_only",
            "controller_evaluator_keys_or_labels_accessed": False,
            "human_review_restricted_key_accessed": False,
        },
        "slot_matrix": matrix,
        "slots": fixture_slots,
        "summary": {
            "fixture_slot_count": len(fixture_slots),
            "reported_fixture_count": sum(
                item["included_in_reported_denominator"]
                for item in fixture_slots
            ),
            "excluded_calibration_fixture_count": sum(
                item["excluded_calibration"] for item in fixture_slots
            ),
            "tier_counts": dict(
                Counter(
                    item["candidate"]["current_tier"] for item in fixture_slots
                )
            ),
            "real_index_access_count": 0,
            "real_family_count": 0,
            "human_reviewed_count": 0,
            "human_gold_count": 0,
            "final_accepted_family_count": 0,
        },
        "prohibitions": {
            "H1_or_H2_assignment": True,
            "human_minimality_or_necessity_assertion": True,
            "final_family_acceptance": True,
            "quota_forcing": True,
            "mining_on_incomplete_or_smoke_index": True,
        },
    }
    registry["registry_hash"] = json_hash(registry)
    validate_candidate_registry(registry)
    return registry


def plan_from_registry(value: Mapping[str, Any]) -> tuple[SlotSpec, ...]:
    """Read slots from the committed dry-run registry."""
    slots = []
    for item in value["slots"]:
        candidate = item["candidate"]
        target = candidate["strata"]["target"]
        slots.append(
            SlotSpec.from_mapping(
                {
                    "slot_id": item["slot_id"],
                    "source_id": item["source_id"],
                    "source_kind": item["source_kind"],
                    "included_in_reported_denominator": item[
                        "included_in_reported_denominator"
                    ],
                    "target_modality_profile": target["modality_profile"],
                    "target_modalities": next(
                        mapping["target_modalities"]
                        for mapping in slot_mappings()
                        if mapping["slot_id"] == item["slot_id"]
                    ),
                    "target_intervention": target["intervention"],
                    "target_hop_stratum": target["hop_stratum"],
                    "target_temporal_stratum": target["temporal_stratum"],
                    "queries": item["queries"],
                    "seed_family_id": candidate["provenance"]["seed_family_id"],
                    "calibration_purpose": item.get("calibration_purpose"),
                }
            )
        )
    result = tuple(slots)
    validate_slot_matrix(result)
    return result
