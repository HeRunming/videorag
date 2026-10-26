"""Deterministic structural family-diff checks."""

from __future__ import annotations

from typing import Any

from .errors import ValidationIssue, ValidationReport, json_pointer, make_report


def structural_differences(left: Any, right: Any, path: tuple[Any, ...] = ()) -> list[tuple[str, Any, Any]]:
    if type(left) is not type(right):
        return [(json_pointer(path), left, right)]
    if isinstance(left, dict):
        differences: list[tuple[str, Any, Any]] = []
        for key in sorted(set(left) | set(right)):
            if key not in left:
                differences.append((json_pointer(path + (key,)), None, right[key]))
            elif key not in right:
                differences.append((json_pointer(path + (key,)), left[key], None))
            else:
                differences.extend(structural_differences(left[key], right[key], path + (key,)))
        return differences
    if isinstance(left, list):
        differences = []
        if len(left) != len(right):
            differences.append((json_pointer(path + ("length",)), len(left), len(right)))
        for index, (lval, rval) in enumerate(zip(left, right)):
            differences.extend(structural_differences(lval, rval, path + (index,)))
        return differences
    return [] if left == right else [(json_pointer(path), left, right)]


def validate_family_diff(family: dict[str, Any]) -> ValidationReport:
    episodes = family.get("episodes", [])
    if len(episodes) != 3:
        return make_report([ValidationIssue("FAM-001", "/episodes", "Exactly three episodes are required before family diff validation.")])
    clean, blocked, restored = episodes
    issues: list[ValidationIssue] = []
    for field in ("backend", "budget", "intervention_family_id"):
        for name, episode in (("BLOCKED", blocked), ("RESTORED", restored)):
            if episode.get(field) != clean.get(field):
                issues.append(ValidationIssue("FAM-002", f"/episodes/{1 if name == 'BLOCKED' else 2}/{field}", f"{field} must be identical across CLEAN, BLOCKED, and RESTORED."))
    if restored.get("initial_state") != blocked.get("initial_state"):
        issues.append(ValidationIssue("REST-001", "/episodes/2/initial_state", "RESTORED must start with the exact BLOCKED initial state."))
    if restored.get("interventions", [])[:1] != blocked.get("interventions", []):
        issues.append(ValidationIssue("REST-001", "/episodes/2/interventions", "RESTORED must begin with the exact BLOCKED intervention."))
    return make_report(issues)
