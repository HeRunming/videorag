"""Evaluator-private scoring for learned generation and agent trajectories."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(value: str) -> set[str]:
    return set(TOKEN_RE.findall(value.casefold()))


def claim_slot_map(family: Mapping[str, Any]) -> dict[str, str]:
    return {
        f"slot.c{ordinal:02d}": claim["claim_id"]
        for ordinal, claim in enumerate(family.get("claims", ()), 1)
    }


def _semantic_match(text: str, claim: Mapping[str, Any]) -> bool:
    visible = _tokens(text)
    terms = claim.get("semantic_terms", [])
    return all(_tokens(str(term)) <= visible for term in terms)


def score_final(
    *,
    family: Mapping[str, Any],
    final: Mapping[str, Any] | None,
    observations: Mapping[str, Mapping[str, Any]],
    evidence_by_observation: Mapping[str, Sequence[str]],
    state: str,
    route_feasibility_certificate: Mapping[str, Any],
    within_budget: bool,
) -> dict[str, Any]:
    expected_claims = {row["claim_id"]: row for row in family["claims"]}
    expected_evidence = {
        eid
        for support_set in family["candidate_support_sets"]
        for eid in support_set["evidence_ids"]
    }
    acquired = {
        eid
        for observation_id in observations
        for eid in evidence_by_observation.get(observation_id, ())
    }
    acquired_modalities = {
        str(observation.get("modality"))
        for observation_id, observation in observations.items()
        if evidence_by_observation.get(observation_id, ())
    }
    candidate_modalities = set(family.get("provisional_modalities", ()))
    route_feasible_at_final = route_feasibility_certificate.get("route_feasible")
    if final is None:
        return {
            "output_valid": False,
            "answer_score": 0.0,
            "citation_f1": 0.0,
            "supported_claim_rate": None,
            "unsupported_claim_rate": None,
            "correct_answer_wrong_citation": False,
            "partial_evidence_hallucination": False,
            "calibrated_refusal": False,
            "all_evidence_success": float(expected_evidence <= acquired),
            "evidence_recall": len(expected_evidence & acquired) / max(1, len(expected_evidence)),
            "success_at_budget": 0.0,
            "premature_stop": None,
            "false_sufficient": None,
            "supported_answer_endpoint": 0.0,
            "state_target_success": 0.0,
            "sufficiency_brier": None,
            "access_failure_diagnosis_accuracy": None,
            "missing_modality_accuracy": None,
            "missing_hop_accuracy": None,
            "missing_cause_accuracy": None,
            "candidate_modality_routing_coverage": (
                len(acquired_modalities & candidate_modalities)
                / max(1, len(candidate_modalities))
            ),
            "modality_necessity_recall": None,
        }
    slot_map = claim_slot_map(family)
    valid_links = 0
    total_links = 0
    expected_pairs = {
        (claim["claim_id"], eid)
        for claim in family["claims"]
        for eid in claim["support_evidence_ids"]
    }
    covered_pairs: set[tuple[str, str]] = set()
    assertion_rows = []
    semantically_correct: set[str] = set()
    supported_claims: set[str] = set()
    for assertion in final["asserted_claims"]:
        handle = assertion["claim_handle"]
        claim_id = slot_map.get(handle)
        claim = expected_claims.get(claim_id or "")
        semantic = bool(claim and _semantic_match(assertion["text"], claim))
        if semantic and claim_id:
            semantically_correct.add(claim_id)
        cited_evidence: set[str] = set()
        for observation_id in assertion["citations"]:
            total_links += 1
            support = set(evidence_by_observation.get(observation_id, ()))
            cited_evidence.update(support)
            if claim:
                useful = support & set(claim["support_evidence_ids"])
                if useful:
                    valid_links += 1
                    covered_pairs.update((claim_id, eid) for eid in useful)
        supported = bool(
            claim
            and semantic
            and set(claim["support_evidence_ids"]) <= cited_evidence
        )
        if supported and claim_id:
            supported_claims.add(claim_id)
        assertion_rows.append(
            {
                "claim_handle": handle,
                "evaluator_claim_id": claim_id,
                "semantic_match": semantic,
                "supported": supported,
            }
        )
    answer_score = float(
        final["verdict"] == "answer"
        and set(expected_claims) <= semantically_correct
    )
    support_rate = (
        sum(row["supported"] for row in assertion_rows) / len(assertion_rows)
        if assertion_rows
        else None
    )
    citation_precision = valid_links / total_links if total_links else 0.0
    citation_recall = len(covered_pairs) / len(expected_pairs) if expected_pairs else 0.0
    citation_f1 = (
        2 * citation_precision * citation_recall / (citation_precision + citation_recall)
        if citation_precision + citation_recall
        else 0.0
    )
    all_evidence = expected_evidence <= acquired
    refusal = final["verdict"] in {"insufficient", "access_failure", "abstain"}
    correct_access_diagnosis = bool(
        state == "BLOCKED"
        and final["verdict"] == "access_failure"
        and final["missingness_cause"] == "evidence_in_source_but_inaccessible"
    )
    calibrated_refusal = bool(refusal and state == "BLOCKED" and not assertion_rows)
    false_sufficient = bool(final["verdict"] == "answer" and not all_evidence)
    observed_sufficient = float(all_evidence)
    sufficiency_brier = (float(final["p_sufficient"]) - observed_sufficient) ** 2
    premature = (
        None
        if route_feasible_at_final is None
        else bool(not all_evidence and route_feasible_at_final)
    )
    supported_answer = bool(
        within_budget
        and answer_score == 1.0
        and all_evidence
        and set(expected_claims) <= supported_claims
    )
    blocked_target = bool(
        within_budget
        and state == "BLOCKED"
        and correct_access_diagnosis
        and not assertion_rows
        and float(final["p_sufficient"]) < 0.5
    )
    state_target = supported_answer if state in {"CLEAN", "RESTORED"} else blocked_target
    return {
        "output_valid": True,
        "assertion_rows": assertion_rows,
        "answer_score": answer_score,
        "citation_precision": citation_precision,
        "citation_recall": citation_recall,
        "citation_f1": citation_f1,
        "supported_claim_rate": support_rate,
        "unsupported_claim_rate": None if support_rate is None else 1.0 - support_rate,
        "correct_answer_wrong_citation": bool(answer_score == 1.0 and citation_f1 < 1.0),
        "partial_evidence_hallucination": bool(
            final["verdict"] == "answer" and 0 < len(acquired) < len(expected_evidence)
        ),
        "calibrated_refusal": calibrated_refusal,
        "all_evidence_success": float(all_evidence),
        "evidence_recall": len(expected_evidence & acquired) / max(1, len(expected_evidence)),
        "success_at_budget": float(supported_answer),
        "supported_answer_endpoint": float(supported_answer),
        "state_target_success": float(state_target),
        "premature_stop": premature,
        "false_sufficient": false_sufficient,
        "sufficiency_brier": sufficiency_brier,
        "access_failure_diagnosis_accuracy": (
            float(correct_access_diagnosis) if state == "BLOCKED" else None
        ),
        # Necessity and hop gold remain unavailable at the current machine
        # provisional stage. They are deliberately null rather than scored
        # against the candidate routing labels.
        "missing_modality_accuracy": None,
        "missing_hop_accuracy": None,
        "missing_cause_accuracy": (
            float(
                final["missingness_cause"]
                == (
                    "evidence_in_source_but_inaccessible"
                    if state == "BLOCKED"
                    else "not_missing"
                )
            )
        ),
        "candidate_modality_routing_coverage": (
            len(acquired_modalities & candidate_modalities)
            / max(1, len(candidate_modalities))
        ),
        "modality_necessity_recall": None,
        "expected_evidence_count": len(expected_evidence),
        "acquired_evidence_count": len(expected_evidence & acquired),
    }


def route_feasibility_certificate(
    backend: Any,
    *,
    required_modalities: Sequence[str],
) -> dict[str, Any]:
    snapshot = getattr(backend, "final_decision_snapshot", None)
    if snapshot is None:
        remaining_steps = backend.budget["max_steps"] - backend.steps_used
        remaining_cost = backend.budget["cost_limit"] - backend.cost_used
        suppressed = set(backend.suppressed)
        triggered = bool(backend.triggered)
    else:
        remaining_steps = int(snapshot["remaining_steps"])
        remaining_cost = float(snapshot["remaining_cost"])
        suppressed = set(snapshot.get("suppressed_segment_ids", backend.suppressed))
        triggered = bool(snapshot.get("triggered", backend.triggered))
    missing_modalities = [
        modality
        for modality in required_modalities
        if not any(
            backend.evidence_by_observation.get(observation_id)
            and backend.observation_private[observation_id]["modality"] == modality
            for observation_id in backend.observation_private
        )
    ]
    suffix: list[dict[str, Any]] = []
    if not missing_modalities:
        body = {
            "schema_version": "av-trace.ga-route-certificate/1.0",
            "eligibility_proven": True,
            "route_feasible": True,
            "reason": "accepted_support_already_observed",
            "remaining_steps": remaining_steps,
            "remaining_cost": remaining_cost,
            "missing_modalities": [],
            "triggered": triggered,
            "suppressed_segment_ids": sorted(suppressed),
            "legal_action_suffix": [{"tool": "finalize", "cost": 0.0}],
            "required_steps": 1,
            "required_cost": 0.0,
        }
        body["certificate_hash"] = "sha256:" + hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return body
    need_restore = bool(
        suppressed
        & set().union(
            *(backend.support_by_modality.get(modality, set()) for modality in missing_modalities)
        )
    )
    steps = 1
    cost = 0.0
    if need_restore:
        if (
            backend.state != "RESTORED"
            or not backend.restoration_enabled
        ):
            feasible = False
            reason = "required_route_inaccessible"
            body = {
                "schema_version": "av-trace.ga-route-certificate/1.0",
                "eligibility_proven": True,
                "route_feasible": feasible,
                "reason": reason,
                "remaining_steps": remaining_steps,
                "remaining_cost": remaining_cost,
                "missing_modalities": missing_modalities,
                "triggered": triggered,
                "suppressed_segment_ids": sorted(suppressed),
                "legal_action_suffix": [],
                "required_steps": None,
                "required_cost": None,
            }
            body["certificate_hash"] = "sha256:" + hashlib.sha256(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            return body
        if not triggered:
            trigger = str(backend.intervention.get("trigger", ""))
            if trigger.startswith("get_channel_status"):
                suffix.append(
                    {
                        "tool": "get_channel_status",
                        "modalities": [
                            backend.intervention.get("channel")
                            or missing_modalities[0]
                        ],
                        "cost": backend.costs["get_channel_status"],
                    }
                )
                steps += 1
                cost += backend.costs["get_channel_status"]
            elif trigger.startswith("second distinct visual query"):
                prior = len(backend.search_queries.get("vision", ()))
                if prior == 0:
                    suffix.append(
                        {
                            "tool": "search_visual",
                            "query": "first distinct recovery probe",
                            "cost": backend.costs["search_visual"],
                        }
                    )
                    steps += 1
                    cost += backend.costs["search_visual"]
                # The actual support-search action below can serve as the
                # second distinct query and fire restoration.
            else:
                body = {
                    "schema_version": "av-trace.ga-route-certificate/1.0",
                    "eligibility_proven": False,
                    "route_feasible": None,
                    "reason": "unknown_restoration_trigger",
                    "remaining_steps": remaining_steps,
                    "remaining_cost": remaining_cost,
                    "missing_modalities": missing_modalities,
                    "triggered": triggered,
                    "suppressed_segment_ids": sorted(suppressed),
                    "legal_action_suffix": [],
                    "required_steps": None,
                    "required_cost": None,
                }
                body["certificate_hash"] = "sha256:" + hashlib.sha256(
                    json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                return body
    for modality in missing_modalities:
        search_tool = {
            "vision": "search_visual",
            "speech": "search_speech",
            "ambient": "search_ambient_audio",
        }[modality]
        observe_tool = "read_transcript" if modality == "speech" else "inspect_clip"
        suffix.extend(
            [
                {
                    "tool": search_tool,
                    "query": "registered support route query (evaluator-private)",
                    "cost": backend.costs[search_tool],
                },
                {
                    "tool": observe_tool,
                    "pointer": "result of prior search",
                    "cost": backend.costs[observe_tool],
                },
            ]
        )
        steps += 2
        cost += backend.costs[search_tool] + backend.costs[observe_tool]
    suffix.append({"tool": "finalize", "cost": backend.costs["finalize"]})
    feasible = steps <= remaining_steps and cost <= remaining_cost + 1e-9
    body = {
        "schema_version": "av-trace.ga-route-certificate/1.0",
        "eligibility_proven": True,
        "route_feasible": feasible,
        "reason": "legal_suffix_within_budget" if feasible else "budget_insufficient",
        "remaining_steps": remaining_steps,
        "remaining_cost": remaining_cost,
        "missing_modalities": missing_modalities,
        "triggered": triggered,
        "suppressed_segment_ids": sorted(suppressed),
        "legal_action_suffix": suffix,
        "required_steps": steps,
        "required_cost": cost,
    }
    body["certificate_hash"] = "sha256:" + hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return body


def mean_or_none(values: Sequence[float | None]) -> float | None:
    valid = [float(value) for value in values if value is not None and math.isfinite(value)]
    return sum(valid) / len(valid) if valid else None
