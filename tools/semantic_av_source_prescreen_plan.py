#!/usr/bin/env python3
"""Generate deterministic source-uniform sample plans and blank human forms."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

try:
    from .semantic_av_source_prescreen_common import (
        BLIND_ROLE_EXCLUSIONS,
        SemanticPrescreenError,
        load_json,
        plan_hash,
        sha256_file,
        validate_annotation,
        validate_inventory,
        validate_plan,
        write_json,
    )
except ImportError:
    from semantic_av_source_prescreen_common import (
        BLIND_ROLE_EXCLUSIONS,
        SemanticPrescreenError,
        load_json,
        plan_hash,
        sha256_file,
        validate_annotation,
        validate_inventory,
        validate_plan,
        write_json,
    )


def hash_unit(text: str) -> float:
    value = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)
    return value / float(0xFFFFFFFFFFFFFFFF)


def allocation(source_ids: list[str], sample_count: int, seed: str) -> dict[str, int]:
    if sample_count < len(source_ids):
        raise SemanticPrescreenError(
            "sample_count must be at least the number of sources"
        )
    base, remainder = divmod(sample_count, len(source_ids))
    ranked = sorted(
        source_ids,
        key=lambda source_id: (
            hashlib.sha256(f"{seed}|quota|{source_id}".encode()).hexdigest(),
            source_id,
        ),
    )
    return {
        source_id: base + (1 if source_id in set(ranked[:remainder]) else 0)
        for source_id in source_ids
    }


def build_plan(
    inventory: dict[str, Any],
    *,
    inventory_sha256: str,
    plan_id: str,
    created_at: str,
    seed: str,
    sample_count: int,
    interval_duration_s: float,
) -> dict[str, Any]:
    validate_inventory(inventory)
    sources = sorted(inventory["sources"], key=lambda item: item["source_id"])
    quotas = allocation([source["source_id"] for source in sources], sample_count, seed)
    samples = []
    sequence = 1
    for source in sources:
        quota = quotas[source["source_id"]]
        bin_width = source["duration_s"] / quota
        if interval_duration_s > bin_width:
            raise SemanticPrescreenError(
                f"{source['source_id']} is too short for {quota} non-overlapping "
                f"{interval_duration_s:g}s samples"
            )
        for index in range(quota):
            slack = bin_width - interval_duration_s
            jitter = hash_unit(f"{seed}|{source['source_id']}|{index}")
            start = index * bin_width + jitter * slack
            start = round(start, 3)
            end = round(start + interval_duration_s, 3)
            samples.append(
                {
                    "sample_id": f"{plan_id}.sample-{sequence:04d}",
                    "source_id": source["source_id"],
                    "source_group_id": source["source_group_id"],
                    "source_content_sha256": source["source_content_sha256"],
                    "start_s": start,
                    "end_s": end,
                    "adapter_request": {
                        "adapter_reference": source["adapter_reference"],
                        "extract_media": False,
                    },
                }
            )
            sequence += 1
    counts = list(quotas.values())
    plan = {
        "schema_version": "1.0.0",
        "record_type": "semantic_av_source_prescreen_plan",
        "plan_id": plan_id,
        "created_at": created_at,
        "inventory_id": inventory["inventory_id"],
        "inventory_sha256": inventory_sha256,
        "seed": seed,
        "algorithm": "source-uniform-temporal-bin-sha256-jitter-v1",
        "sample_count": len(samples),
        "interval_duration_s": interval_duration_s,
        "source_uniformity": {
            "source_count": len(sources),
            "minimum_per_source": min(counts),
            "maximum_per_source": max(counts),
        },
        "samples": samples,
        "plan_sha256": "",
        "semantic_labels_present": False,
    }
    plan["plan_sha256"] = plan_hash(plan)
    validate_plan(plan)
    return plan


def blank_sample_review(sample_id: str) -> dict[str, Any]:
    blank_risk = {"level": "unknown", "notes": ""}
    return {
        "sample_id": sample_id,
        "review_status": "not_reviewed",
        "dynamic_non_text_visual_events": [],
        "concrete_non_speech_audio_events": [],
        "speech_presence": "unknown",
        "substitution_risk": {
            name: dict(blank_risk)
            for name in ("transcript", "ocr", "caption", "narration")
        },
        "notes": "",
    }


def build_blank_annotation(plan: dict[str, Any], *, form_id: str) -> dict[str, Any]:
    validate_plan(plan)
    grouped: dict[tuple[str, str], list[str]] = {}
    for sample in plan["samples"]:
        key = (sample["source_id"], sample["source_group_id"])
        grouped.setdefault(key, []).append(sample["sample_id"])
    reviews = []
    for (source_id, source_group_id), sample_ids in sorted(grouped.items()):
        reviews.append(
            {
                "source_id": source_id,
                "source_group_id": source_group_id,
                "sample_reviews": [
                    blank_sample_review(sample_id) for sample_id in sample_ids
                ],
                "candidate_facts": [],
                "temporal_recurrence": {
                    "assessment_status": "not_assessed",
                    "groups": [],
                    "notes": "",
                },
                "privacy_review": {
                    "assessment_status": "not_assessed",
                    "concerns": [],
                    "notes": "",
                },
                "safety_review": {
                    "assessment_status": "not_assessed",
                    "concerns": [],
                    "notes": "",
                },
                "authoring_eligibility": "undecided",
                "decision_rationale": "",
                "repair_actions": [],
                "authoring_constraints": [],
            }
        )
    annotation = {
        "schema_version": "1.0.0",
        "record_type": "semantic_av_source_prescreen_annotation",
        "form_id": form_id,
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "completion_status": "not_started",
        "human_semantic_prescreen_only": True,
        "reviewer": {
            "reviewer_id": None,
            "training_attested": False,
            "protocol_version": "semantic-av-source-prescreen-v1",
            "started_at": None,
            "completed_at": None,
        },
        "source_reviews": reviews,
        "prohibited_assignments": {
            "necessity_assigned": False,
            "h1_assigned": False,
            "h2_assigned": False,
            "blind_finder_eligible_for_reviewed_sources": False,
            "saturation_auditor_eligible_for_reviewed_sources": False,
        },
    }
    assert BLIND_ROLE_EXCLUSIONS
    validate_annotation(annotation)
    return annotation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--plan-out", type=Path, required=True)
    parser.add_argument("--form-out", type=Path, required=True)
    parser.add_argument("--plan-id", required=True)
    parser.add_argument("--form-id", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--sample-count", type=int, required=True)
    parser.add_argument("--interval-duration-s", type=float, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        inventory = load_json(args.inventory)
        plan = build_plan(
            inventory,
            inventory_sha256=sha256_file(args.inventory),
            plan_id=args.plan_id,
            created_at=args.created_at,
            seed=args.seed,
            sample_count=args.sample_count,
            interval_duration_s=args.interval_duration_s,
        )
        form = build_blank_annotation(plan, form_id=args.form_id)
        write_json(args.plan_out, plan)
        write_json(args.form_out, form)
    except SemanticPrescreenError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(
        f"WROTE {args.plan_out} and {args.form_out}: "
        f"{plan['sample_count']} unlabeled intervals"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
