"""Small, deterministic claim/evidence graph proof routines."""

from __future__ import annotations

from itertools import combinations
from typing import Any, Iterable, Mapping


def powerset(values: Iterable[str]) -> list[tuple[str, ...]]:
    ordered = tuple(sorted(set(values)))
    return [
        item
        for size in range(len(ordered) + 1)
        for item in combinations(ordered, size)
    ]


def derive_claims(
    graph: Mapping[str, Any],
    evidence_ids: Iterable[str],
) -> tuple[set[str], set[str]]:
    """Return derived hop and claim IDs under conjunctive support edges."""

    available: set[str] = set(evidence_ids)
    derived_hops: set[str] = set()
    derived_claims: set[str] = set()
    changed = True
    edges = graph["support_edges"]
    while changed:
        changed = False
        known = available | derived_hops | derived_claims
        for edge in edges:
            if not set(edge["from_ids"]) <= known:
                continue
            if edge["relation"] == "supports_hop":
                if edge["to_id"] not in derived_hops:
                    derived_hops.add(edge["to_id"])
                    changed = True
            elif edge["relation"] in {"direct_support", "hop_supports_claim"}:
                if edge["to_id"] not in derived_claims:
                    derived_claims.add(edge["to_id"])
                    changed = True
    return derived_hops, derived_claims


def ses_satisfied(graph: Mapping[str, Any], ses: Mapping[str, Any], evidence_ids: Iterable[str]) -> bool:
    supplied = set(evidence_ids)
    if not set(ses["evidence_ids"]) <= supplied:
        return False
    hops, claims = derive_claims(graph, set(ses["evidence_ids"]))
    return set(ses["hop_ids"]) <= hops and set(ses["claim_ids"]) <= claims


def reachable_ses_ids(graph: Mapping[str, Any], evidence_ids: Iterable[str]) -> list[str]:
    supplied = set(evidence_ids)
    return sorted(
        ses["set_id"]
        for ses in graph["accepted_sufficient_sets"]
        if ses_satisfied(graph, ses, supplied)
    )


def minimality_cases(graph: Mapping[str, Any], ses: Mapping[str, Any]) -> list[dict[str, Any]]:
    cases = []
    full = set(ses["evidence_ids"])
    for removed in ses["evidence_ids"]:
        retained = full - {removed}
        _hops, claims = derive_claims(graph, retained)
        unsupported = sorted(set(ses["claim_ids"]) - claims)
        cases.append(
            {
                "removed_evidence_id": removed,
                "retained_evidence_ids": sorted(retained),
                "unsupported_claim_ids": unsupported,
                "still_sufficient": not bool(unsupported),
            }
        )
    return cases

