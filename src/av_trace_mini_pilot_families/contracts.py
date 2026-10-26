"""Contracts and validation for machine-provisional family mining."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = "av-trace.mini-pilot-family-mining/1.0"
P_TIERS = (
    "P0_MACHINE_CANDIDATE",
    "P1_MACHINE_CROSS_VALIDATED",
    "P2_MACHINE_COUNTERFACTUAL_VALIDATED",
)
HUMAN_TIERS = ("H1_HUMAN_VALIDATED", "H2_HUMAN_ADJUDICATED_GOLD")
MODALITY_PROFILES = ("V", "S", "A", "V+S", "V+A/S+A", "V+S+A")
INTERVENTIONS = ("necessity_group_withholding", "modality_channel_outage")
HOP_STRATA = ("one_hop", "multi_hop")
TEMPORAL_STRATA = ("near_local", "far_separated")


def canonical_bytes(value: Any) -> bytes:
    """Return the repository's stable JSON representation."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def json_hash(value: Any) -> str:
    """Hash a JSON-compatible value using the stable representation."""
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class SlotSpec:
    """One preregistered reported or calibration slot."""

    slot_id: str
    source_id: str
    source_kind: str
    included_in_reported_denominator: bool
    target_modality_profile: str
    target_modalities: tuple[str, ...]
    target_intervention: str
    target_hop_stratum: str
    target_temporal_stratum: str
    queries: Mapping[str, str]
    seed_family_id: str | None = None
    calibration_purpose: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> SlotSpec:
        return cls(
            slot_id=str(value["slot_id"]),
            source_id=str(value["source_id"]),
            source_kind=str(value["source_kind"]),
            included_in_reported_denominator=bool(
                value["included_in_reported_denominator"]
            ),
            target_modality_profile=str(value["target_modality_profile"]),
            target_modalities=tuple(str(x) for x in value["target_modalities"]),
            target_intervention=str(value["target_intervention"]),
            target_hop_stratum=str(value["target_hop_stratum"]),
            target_temporal_stratum=str(value["target_temporal_stratum"]),
            queries={
                str(key): str(item)
                for key, item in dict(value.get("queries", {})).items()
            },
            seed_family_id=(
                str(value["seed_family_id"])
                if value.get("seed_family_id") is not None
                else None
            ),
            calibration_purpose=(
                str(value["calibration_purpose"])
                if value.get("calibration_purpose") is not None
                else None
            ),
        )


def validate_slot_matrix(slots: Sequence[SlotSpec]) -> dict[str, Any]:
    """Validate the frozen 12+2 design without forcing mined outcomes."""
    if len(slots) != 14:
        raise ValueError(f"SLOT_COUNT_MUST_BE_14:{len(slots)}")
    if len({slot.slot_id for slot in slots}) != len(slots):
        raise ValueError("DUPLICATE_SLOT_ID")

    reported = [slot for slot in slots if slot.included_in_reported_denominator]
    calibration = [
        slot for slot in slots if not slot.included_in_reported_denominator
    ]
    if len(reported) != 12 or len(calibration) != 2:
        raise ValueError(
            "REPORTED_CALIBRATION_COUNTS_MUST_BE_12_AND_2:"
            f"{len(reported)}:{len(calibration)}"
        )

    source_kind_counts = Counter(slot.source_kind for slot in reported)
    if source_kind_counts != Counter({"new_source": 8, "noaa_development": 4}):
        raise ValueError(
            "SOURCE_KIND_COUNTS_MUST_BE_8_NEW_4_NOAA:"
            f"{dict(source_kind_counts)}"
        )
    per_source = Counter(slot.source_id for slot in reported)
    if sorted(per_source.values()) != [2, 2, 2, 2, 2, 2]:
        raise ValueError(f"REPORTED_SLOTS_MUST_BE_TWO_PER_SOURCE:{dict(per_source)}")
    new_sources = {
        slot.source_id for slot in reported if slot.source_kind == "new_source"
    }
    noaa_sources = {
        slot.source_id
        for slot in reported
        if slot.source_kind == "noaa_development"
    }
    if len(new_sources) != 4 or len(noaa_sources) != 2:
        raise ValueError(
            "SOURCE_GROUP_COUNTS_MUST_BE_4_NEW_2_NOAA:"
            f"{len(new_sources)}:{len(noaa_sources)}"
        )

    modality_counts = Counter(slot.target_modality_profile for slot in reported)
    if modality_counts != Counter({profile: 2 for profile in MODALITY_PROFILES}):
        raise ValueError(f"MODALITY_TARGETS_MUST_BE_TWO_EACH:{dict(modality_counts)}")
    for field, expected in (
        ("target_intervention", Counter({item: 6 for item in INTERVENTIONS})),
        ("target_hop_stratum", Counter({item: 6 for item in HOP_STRATA})),
        ("target_temporal_stratum", Counter({item: 6 for item in TEMPORAL_STRATA})),
    ):
        observed = Counter(getattr(slot, field) for slot in reported)
        if observed != expected:
            raise ValueError(f"UNBALANCED_{field.upper()}:{dict(observed)}")

    for slot in slots:
        if slot.target_intervention not in INTERVENTIONS:
            raise ValueError(f"INVALID_INTERVENTION:{slot.slot_id}")
        if slot.target_hop_stratum not in HOP_STRATA:
            raise ValueError(f"INVALID_HOP_STRATUM:{slot.slot_id}")
        if slot.target_temporal_stratum not in TEMPORAL_STRATA:
            raise ValueError(f"INVALID_TEMPORAL_STRATUM:{slot.slot_id}")
        if not slot.target_modalities:
            raise ValueError(f"EMPTY_MODALITY_TARGET:{slot.slot_id}")
        if not set(slot.target_modalities) <= {"vision", "speech", "ambient"}:
            raise ValueError(f"INVALID_MODALITY:{slot.slot_id}")
    return {
        "slot_count": 14,
        "reported_slot_count": 12,
        "excluded_calibration_slot_count": 2,
        "new_source_reported_slots": 8,
        "noaa_development_reported_slots": 4,
        "reported_source_count": 6,
        "two_reported_slots_per_source": True,
        "target_modality_profile_counts": dict(sorted(modality_counts.items())),
        "target_intervention_counts": dict(
            sorted(Counter(x.target_intervention for x in reported).items())
        ),
        "target_hop_counts": dict(
            sorted(Counter(x.target_hop_stratum for x in reported).items())
        ),
        "target_temporal_counts": dict(
            sorted(Counter(x.target_temporal_stratum for x in reported).items())
        ),
    }


def assert_machine_provisional_only(value: Any) -> None:
    """Reject human tiers or affirmative human-validation assertions."""
    protected_true_keys = {
        "human_reviewed",
        "human_validated",
        "human_gold",
        "human_minimality",
        "human_necessity",
        "minimality_human_validated",
        "modality_necessity_human_validated",
        "accepted_family",
        "final_accepted",
    }

    def walk(item: Any, location: str) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                child_location = f"{location}.{key}"
                if key in protected_true_keys and child is not False:
                    raise ValueError(
                        f"HUMAN_OR_FINAL_ASSERTION_FORBIDDEN:{child_location}"
                    )
                walk(child, child_location)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, f"{location}[{index}]")
        elif isinstance(item, str) and item in HUMAN_TIERS:
            raise ValueError(f"HUMAN_TIER_FORBIDDEN:{location}:{item}")

    walk(value, "root")


def validate_candidate_registry(registry: Mapping[str, Any]) -> None:
    """Validate output-stage invariants shared by dry and executable runs."""
    if registry.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("REGISTRY_SCHEMA_VERSION_INVALID")
    if registry.get("registry_kind") not in {
        "DETERMINISTIC_DRY_RUN_FIXTURE",
        "MACHINE_PROVISIONAL_CANDIDATE_PROPOSALS",
    }:
        raise ValueError("REGISTRY_KIND_INVALID")
    slots = list(registry.get("slots", ()))
    if len(slots) != 14:
        raise ValueError("REGISTRY_MUST_CONTAIN_14_SLOTS")
    if len({str(item.get("slot_id")) for item in slots}) != 14:
        raise ValueError("REGISTRY_SLOT_IDS_NOT_UNIQUE")
    for item in slots:
        candidate = item.get("candidate")
        if candidate is None:
            continue
        tier = candidate.get("current_tier")
        if tier not in P_TIERS:
            raise ValueError(f"NON_PROVISIONAL_TIER:{tier}")
        if candidate.get("human_reviewed") is not False:
            raise ValueError("HUMAN_REVIEW_MUST_BE_FALSE")
        if candidate.get("human_gold") is not False:
            raise ValueError("HUMAN_GOLD_MUST_BE_FALSE")
        if candidate.get("final_accepted") is not False:
            raise ValueError("FINAL_ACCEPTED_MUST_BE_FALSE")
    assert_machine_provisional_only(registry)

