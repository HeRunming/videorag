#!/usr/bin/env python3
"""Deterministic risk-stratified sampling of provisional AV-TRACE families."""

from __future__ import annotations

import argparse
import hashlib
import math
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from .construct_validity_common import (
        ConstructValidityError,
        load_json,
        now_utc,
        validate_registry,
        write_json,
    )
except ImportError:
    from construct_validity_common import (
        ConstructValidityError,
        load_json,
        now_utc,
        validate_registry,
        write_json,
    )


SIGNAL_WEIGHTS = {
    "ambient_candidate": 8,
    "triple_modal_candidate": 9,
    "machine_validator_disagreement": 7,
    "learned_control_ranking_disagreement": 6,
    "correct_answer_wrong_citation": 8,
    "uncertain_minimality": 7,
    "multiple_alternative_supports": 6,
    "pair_isolation_risk": 8,
    "rights_privacy_risk": 5,
    "low_risk_control": 2,
}
TIER_WEIGHTS = {
    "P0_MACHINE_CANDIDATE": 3,
    "P1_MACHINE_CROSS_VALIDATED": 2,
    "P2_MACHINE_COUNTERFACTUAL_VALIDATED": 1,
}


def stable_tiebreak(seed: str, family_id: str) -> str:
    return hashlib.sha256(f"{seed}\\0{family_id}".encode()).hexdigest()


def base_score(record: dict[str, Any]) -> int:
    return TIER_WEIGHTS[record["current_tier"]] + sum(
        weight
        for signal, weight in SIGNAL_WEIGHTS.items()
        if record["signals"][signal]
    )


def choose_sample(
    registry: dict[str, Any],
    *,
    target_size: int,
    source_target: int,
    source_max: int | None,
    seed: str,
    low_risk_minimum: int,
) -> list[dict[str, Any]]:
    validate_registry(registry)
    eligible = [
        record for record in registry["records"] if record["candidate_status"] == "eligible"
    ]
    if not 1 <= target_size <= len(eligible):
        raise ConstructValidityError(
            f"target_size={target_size} but eligible pool has {len(eligible)} records"
        )
    distinct_sources = sorted({record["source_id"] for record in eligible})
    if source_target > min(target_size, len(distinct_sources)):
        raise ConstructValidityError(
            f"source_target={source_target} cannot be met by "
            f"{len(distinct_sources)} eligible sources and target_size={target_size}"
        )
    if source_max is not None and source_max < source_target:
        raise ConstructValidityError("source_max must be >= source_target")

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    source_capacities = Counter(record["source_id"] for record in eligible)
    modality_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    signal_counts: Counter[str] = Counter()

    def marginal(record: dict[str, Any]) -> tuple[int, str]:
        novelty = 0
        if source_counts[record["source_id"]] == 0:
            novelty += 15
        if domain_counts[record["domain"]] == 0:
            novelty += 7
        if modality_counts[record["modality_profile_candidate"]] == 0:
            novelty += 6
        for signal, enabled in record["signals"].items():
            if enabled and signal_counts[signal] == 0:
                novelty += 3
        if record["signals"]["low_risk_control"] and signal_counts["low_risk_control"] == 0:
            novelty += 5
        return base_score(record) + novelty, stable_tiebreak(seed, record["family_id"])

    def take(record: dict[str, Any]) -> None:
        selected.append(record)
        selected_ids.add(record["family_id"])
        source_counts[record["source_id"]] += 1
        domain_counts[record["domain"]] += 1
        modality_counts[record["modality_profile_candidate"]] += 1
        for signal, enabled in record["signals"].items():
            if enabled:
                signal_counts[signal] += 1

    def allowed(record: dict[str, Any]) -> bool:
        if record["family_id"] in selected_ids:
            return False
        prospective_sources = set(source_counts)
        prospective_sources.add(record["source_id"])
        if source_max is not None and len(prospective_sources) > source_max:
            return False
        # Do not greedily consume the source budget with singleton sources when
        # that would make the requested family count impossible.
        available_capacity = sum(
            source_capacities[source_id] for source_id in prospective_sources
        )
        remaining_source_slots = (
            len(source_capacities)
            if source_max is None
            else source_max - len(prospective_sources)
        )
        outside_capacities = sorted(
            (
                capacity
                for source_id, capacity in source_capacities.items()
                if source_id not in prospective_sources
            ),
            reverse=True,
        )
        available_capacity += sum(outside_capacities[:remaining_source_slots])
        return available_capacity >= target_size

    # Include high-value ambient/triple-modal cases first, up to the smaller of
    # twelve and half the sample. This keeps room for source and control strata.
    high_value = [
        record
        for record in eligible
        if record["signals"]["ambient_candidate"]
        or record["signals"]["triple_modal_candidate"]
    ]
    high_value_cap = min(12, max(1, target_size // 2))
    for record in sorted(high_value, key=marginal, reverse=True)[:high_value_cap]:
        if len(selected) < target_size and allowed(record):
            take(record)

    # Guarantee source-disjoint coverage.
    while len(source_counts) < source_target:
        choices = [
            record
            for record in eligible
            if allowed(record)
            and source_counts[record["source_id"]] == 0
        ]
        if not choices:
            raise ConstructValidityError("cannot satisfy source coverage under source cap")
        take(max(choices, key=marginal))

    # Reserve deterministic low-risk controls.
    while signal_counts["low_risk_control"] < low_risk_minimum:
        choices = [
            record
            for record in eligible
            if allowed(record) and record["signals"]["low_risk_control"]
        ]
        if not choices:
            raise ConstructValidityError(
                f"cannot satisfy low_risk_minimum={low_risk_minimum}"
            )
        take(max(choices, key=marginal))

    # Then maximize predeclared risk and stratum coverage.
    while len(selected) < target_size:
        choices = [record for record in eligible if allowed(record)]
        if not choices:
            raise ConstructValidityError(
                "target cannot be filled under source cap; add more families per source"
            )
        take(max(choices, key=marginal))
    return selected


def build_sample(
    registry: dict[str, Any],
    *,
    target_size: int,
    source_target: int,
    source_max: int | None,
    seed: str,
    low_risk_minimum: int,
    mode: str,
) -> dict[str, Any]:
    records = choose_sample(
        registry,
        target_size=target_size,
        source_target=source_target,
        source_max=source_max,
        seed=seed,
        low_risk_minimum=low_risk_minimum,
    )
    return {
        "schema_version": "1.0.0",
        "record_type": "construct_validity_stratified_sample",
        "sample_id": f"cv-sample-{hashlib.sha256(seed.encode()).hexdigest()[:12]}",
        "generated_at": now_utc(),
        "registry_id": registry["registry_id"],
        "registry_status": registry["registry_status"],
        "human_review_completed": False,
        "human_gold": False,
        "seed": seed,
        "target_size": target_size,
        "source_target": source_target,
        "source_max": source_max,
        "mode": mode,
        "low_risk_minimum": low_risk_minimum,
        "selection_contract": {
            "priority_order": list(SIGNAL_WEIGHTS),
            "signal_weights": SIGNAL_WEIGHTS,
            "tier_weights": TIER_WEIGHTS,
            "algorithm": (
                "greedy deterministic maximum marginal predeclared risk and "
                "coverage; SHA-256 seeded tie break"
            ),
            "no_outcome_or_gold_labels_used": True,
        },
        "selected_family_ids": [record["family_id"] for record in records],
        "selected_records": records,
        "coverage": {
            "families": len(records),
            "sources": len({record["source_id"] for record in records}),
            "domains": sorted({record["domain"] for record in records}),
            "modality_profiles": dict(
                sorted(Counter(r["modality_profile_candidate"] for r in records).items())
            ),
            "signals": {
                signal: sum(record["signals"][signal] for record in records)
                for signal in SIGNAL_WEIGHTS
            },
        },
        "warnings": [
            "Selection is a future review assignment, not evidence of human review.",
            "Machine modality and risk labels are sampling strata, not validated constructs.",
            "Low-N mini-pilot statistics are descriptive and require confidence intervals.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-size", type=int, default=10)
    parser.add_argument("--source-target", type=int, default=5)
    parser.add_argument("--source-max", type=int)
    parser.add_argument("--mode", choices=("immediate", "scale"), default="immediate")
    parser.add_argument("--low-risk-minimum", type=int)
    parser.add_argument("--seed", default="av-trace-construct-validity-v1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        registry = load_json(args.registry)
        source_max = args.source_max
        low_risk_minimum = args.low_risk_minimum
        if args.mode == "immediate":
            if not 8 <= args.target_size <= 12:
                raise ConstructValidityError("immediate target_size must be 8-12")
            if not 5 <= args.source_target <= 6:
                raise ConstructValidityError("immediate source_target must be 5-6")
            source_max = 6 if source_max is None else source_max
            low_risk_minimum = 1 if low_risk_minimum is None else low_risk_minimum
        else:
            if not 30 <= args.target_size <= 50:
                raise ConstructValidityError("scale human sample target_size must be 30-50")
            eligible_count = sum(
                record["candidate_status"] == "eligible"
                for record in registry["records"]
            )
            if not 100 <= eligible_count <= 200:
                raise ConstructValidityError(
                    "scale mode requires a 100-200 eligible-family pool"
                )
            low_risk_minimum = (
                math.ceil(0.20 * args.target_size)
                if low_risk_minimum is None
                else low_risk_minimum
            )
        sample = build_sample(
            registry,
            target_size=args.target_size,
            source_target=args.source_target,
            source_max=source_max,
            seed=args.seed,
            low_risk_minimum=low_risk_minimum,
            mode=args.mode,
        )
        write_json(args.output, sample)
    except ConstructValidityError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(
        f"WROTE {args.output}: {sample['coverage']['families']} families, "
        f"{sample['coverage']['sources']} sources, human_review_completed=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
