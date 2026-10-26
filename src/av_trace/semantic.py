"""Semantic family validation for the executable Pilot-0 contract."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from .diffing import validate_family_diff
from .errors import ValidationIssue, ValidationReport, make_report
from .manifest import GateProfile, validate_manifest_gate
from .schemas import SchemaRegistry
from .util import is_finite_number, safe_sha256_json

VALIDATOR_VERSION = "0.1.0"


def _issue(code: str, pointer: str, message: str, *ids: str) -> ValidationIssue:
    return ValidationIssue(code, pointer, message, tuple(ids))


def _index(items: Iterable[dict[str, Any]], key: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    found: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for item in items:
        value = item.get(key)
        if value in found:
            duplicates.append(value)
        else:
            found[value] = item
    return found, duplicates


def _supportable_claims(graph: dict[str, Any], evidence_ids: set[str], allowed_hop_ids: set[str] | None = None) -> set[str]:
    hops = {hop["hop_id"]: hop for hop in graph["hops"]}
    support_sources: dict[str, set[str]] = defaultdict(set)
    for edge in graph["support_edges"]:
        if edge["relation"] == "supports_hop":
            support_sources[edge["to_id"]].update(edge["from_ids"])
    available_hops: set[str] = set()
    changed = True
    while changed:
        changed = False
        for hop_id, hop in hops.items():
            if hop_id in available_hops or (allowed_hop_ids is not None and hop_id not in allowed_hop_ids):
                continue
            declared_inputs = set(hop["input_evidence_ids"]) | set(hop["input_hop_ids"])
            connected = declared_inputs <= support_sources[hop_id]
            if connected and set(hop["input_evidence_ids"]) <= evidence_ids and set(hop["input_hop_ids"]) <= available_hops:
                available_hops.add(hop_id)
                changed = True
    claims: set[str] = set()
    for edge in graph["support_edges"]:
        relation = edge["relation"]
        sources = set(edge["from_ids"])
        if relation == "direct_support" and sources <= evidence_ids:
            claims.add(edge["to_id"])
        elif relation == "hop_supports_claim" and sources <= available_hops:
            claims.add(edge["to_id"])
    return claims


def _available_hops(graph: dict[str, Any], evidence_ids: set[str]) -> set[str]:
    hops = {hop["hop_id"]: hop for hop in graph["hops"]}
    support_sources: dict[str, set[str]] = defaultdict(set)
    for edge in graph["support_edges"]:
        if edge["relation"] == "supports_hop":
            support_sources[edge["to_id"]].update(edge["from_ids"])
    available: set[str] = set()
    changed = True
    while changed:
        changed = False
        for hop_id, hop in hops.items():
            if hop_id in available:
                continue
            declared = set(hop["input_evidence_ids"]) | set(hop["input_hop_ids"])
            if (
                declared <= support_sources[hop_id]
                and set(hop["input_evidence_ids"]) <= evidence_ids
                and set(hop["input_hop_ids"]) <= available
            ):
                available.add(hop_id)
                changed = True
    return available


def _ses_reachable(ses: dict[str, Any], accessible: set[str]) -> bool:
    return set(ses["evidence_ids"]) <= accessible


def _channel_modalities(channel: str | None) -> set[str]:
    return {
        "visual": {"vision"},
        "speech": {"speech"},
        "transcript": {"speech"},
        "ambient": {"ambient"},
        "clip": {"vision", "speech", "ambient"},
    }.get(channel, set())


def _explicit_synthetic_testing_fixture(
    family: dict[str, Any],
    manifest: dict[str, Any] | None,
) -> bool:
    """Recognize only fixtures that explicitly declare project-owned synthetic media."""

    if not isinstance(manifest, dict):
        return False
    source = manifest.get("source")
    rights = manifest.get("rights")
    if not isinstance(source, dict) or not isinstance(rights, dict):
        return False
    grant = rights.get("license_or_grant")
    review = rights.get("review")
    if not isinstance(grant, dict) or not isinstance(review, dict):
        return False
    synthetic_grants = {"synthetic_project_owned", "Synthetic fixture grant"}
    return (
        manifest.get("dataset_id") in {
            "synthetic_project_owned",
            "synthetic_direct_grant",
        }
        and grant.get("name") in synthetic_grants
        and review.get("jurisdiction")
        in {"synthetic", "project-owned synthetic fixture"}
        and isinstance(family.get("family_id"), str)
        and (
            family["family_id"].startswith("syn_")
            or family["family_id"].startswith("synthetic")
        )
    )


def validate_family(
    family: dict[str, Any],
    manifest: dict[str, Any] | None = None,
    registry: SchemaRegistry | None = None,
    verified_asset: dict[str, Any] | None = None,
    *,
    media_mode: str | None = None,
) -> ValidationReport:
    if media_mode is None:
        media_mode = (
            "synthetic_testing"
            if _explicit_synthetic_testing_fixture(family, manifest)
            else "real"
        )
    elif media_mode not in {"real", "synthetic_testing"}:
        raise ValueError("media_mode must be 'real' or 'synthetic_testing'")
    registry = registry or SchemaRegistry()
    structural = registry.validate("episode-family", family)
    issues = list(structural.issues)
    if not structural.ok or not isinstance(family, dict):
        return make_report(issues, validator_version=VALIDATOR_VERSION, family_hash=safe_sha256_json(family))

    graph = family["claim_evidence_graph"]
    claims, dup_claims = _index(graph["claims"], "claim_id")
    evidence, dup_evidence = _index(graph["evidence_units"], "evidence_id")
    hops, dup_hops = _index(graph["hops"], "hop_id")
    edges, dup_edges = _index(graph["support_edges"], "edge_id")
    sets, dup_sets = _index(graph["accepted_sufficient_sets"], "set_id")
    groups, dup_groups = _index(graph["necessity_groups"], "group_id")
    episodes, dup_episodes = _index(family["episodes"], "episode_id")
    interventions = [item for episode in family["episodes"] for item in episode["interventions"]]
    _, dup_interventions = _index(interventions, "intervention_id")

    for namespace, duplicates in (
        ("claim", dup_claims), ("evidence", dup_evidence), ("hop", dup_hops),
        ("edge", dup_edges), ("SES", dup_sets), ("necessity group", dup_groups),
        ("episode", dup_episodes),
    ):
        for duplicate in sorted(set(duplicates)):
            issues.append(_issue("ID-001", "/claim_evidence_graph", f"Duplicate {namespace} ID: {duplicate}.", duplicate))
    # The same block ID intentionally appears in BLOCKED and RESTORED. Duplicates within one episode are invalid.
    for episode_index, episode in enumerate(family["episodes"]):
        _, local_duplicates = _index(episode["interventions"], "intervention_id")
        for duplicate in sorted(set(local_duplicates)):
            issues.append(_issue("ID-001", f"/episodes/{episode_index}/interventions", f"Duplicate intervention ID within episode: {duplicate}.", duplicate))

    requirement_lists = {
        "required": family["answer_spec"]["required_claim_ids"],
        "optional": family["answer_spec"]["optional_claim_ids"],
        "forbidden": family["answer_spec"]["forbidden_claim_ids"],
    }
    for requirement, listed_claim_ids in requirement_lists.items():
        for claim_id in listed_claim_ids:
            if claim_id not in claims or claims[claim_id]["requirement"] != requirement:
                issues.append(_issue("ID-002", f"/answer_spec/{requirement}_claim_ids", f"Claim {claim_id} must resolve to exactly one {requirement} graph claim.", claim_id))
    for claim_id, claim in claims.items():
        if claim_id not in requirement_lists[claim["requirement"]]:
            issues.append(_issue("ID-002", "/claim_evidence_graph/claims", f"Graph claim {claim_id} is not listed in the matching answer-spec class.", claim_id))
        for contradiction_id in claim.get("contradiction_claim_ids", []):
            if contradiction_id not in claims:
                issues.append(_issue("ID-003", "/claim_evidence_graph/claims", f"Unknown contradiction claim ID {contradiction_id}.", claim_id, contradiction_id))

    annotation = family["annotation"]
    authors = set(annotation["authors"])
    validators = set(annotation["validators"])
    role_conflicts = authors & (
        validators | {annotation["alternative_evidence_finder"], annotation["adjudicator"]}
    )
    if role_conflicts or annotation["adjudicator"] in validators:
        issues.append(_issue("SES-006", "/annotation", "Authors, validators, alternative-evidence finder, and adjudicator must satisfy the frozen independence requirements.", *sorted(role_conflicts)))
    if annotation["status"] in {"accepted", "frozen"} and not annotation["alternative_search_completed"]:
        issues.append(_issue("SES-003", "/annotation/alternative_search_completed", "Accepted or frozen families require completed exhaustive alternative-evidence search."))
    if annotation["status"] in {"accepted", "frozen"}:
        incomplete_audits = [
            audit["audit_type"]
            for audit in annotation["shortcut_audits"]
            if audit["status"] in {"fail", "pending"}
        ]
        if incomplete_audits:
            issues.append(_issue("INT-005", "/annotation/shortcut_audits", f"Accepted or frozen families cannot contain failed or pending shortcut audits: {sorted(incomplete_audits)}."))

    stream_by_id, duplicate_streams = _index(family["source"]["streams"], "stream_id")
    for duplicate in sorted(set(duplicate_streams)):
        issues.append(_issue("ID-001", "/source/streams", f"Duplicate stream ID: {duplicate}.", duplicate))
    duration = family["source"]["duration_s"]
    for index, unit in enumerate(graph["evidence_units"]):
        stream = stream_by_id.get(unit["stream_id"])
        if stream is None:
            issues.append(_issue("ID-003", f"/claim_evidence_graph/evidence_units/{index}/stream_id", f"Unknown stream ID {unit['stream_id']}.", unit["stream_id"]))
        elif stream["hash"] != unit["provenance"]["stream_hash"]:
            issues.append(_issue("TIME-003", f"/claim_evidence_graph/evidence_units/{index}/provenance/stream_hash", "Evidence provenance stream hash does not match the source stream.", unit["evidence_id"], unit["stream_id"]))
        if unit["provenance"]["asset_id"] != family["source"]["asset_id"]:
            issues.append(_issue("PROV-002", f"/claim_evidence_graph/evidence_units/{index}/provenance/asset_id", "Evidence provenance asset ID does not match the family source.", unit["evidence_id"]))
        for interval_index, interval in enumerate(unit["intervals"]):
            start, end = interval["start_s"], interval["end_s"]
            pointer = f"/claim_evidence_graph/evidence_units/{index}/intervals/{interval_index}"
            if not is_finite_number(start) or not is_finite_number(end) or end <= start:
                issues.append(_issue("TIME-001", pointer, "Interval values must be finite and end_s must be greater than start_s.", unit["evidence_id"]))
            elif start < 0 or end > duration:
                issues.append(_issue("TIME-002", pointer, f"Interval must lie within source duration [0, {duration}].", unit["evidence_id"]))

    claim_ids, evidence_ids, hop_ids = set(claims), set(evidence), set(hops)
    for index, hop in enumerate(graph["hops"]):
        for evidence_id in hop["input_evidence_ids"]:
            if evidence_id not in evidence_ids:
                issues.append(_issue("ID-003", f"/claim_evidence_graph/hops/{index}/input_evidence_ids", f"Unknown evidence ID {evidence_id}.", hop["hop_id"], evidence_id))
        for dependency in hop["input_hop_ids"]:
            if dependency not in hop_ids:
                issues.append(_issue("ID-003", f"/claim_evidence_graph/hops/{index}/input_hop_ids", f"Unknown hop ID {dependency}.", hop["hop_id"], dependency))

    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(hop_id: str) -> bool:
        if hop_id in visiting:
            return False
        if hop_id in visited:
            return True
        visiting.add(hop_id)
        for dependency in hops[hop_id]["input_hop_ids"]:
            if dependency in hops and not visit(dependency):
                return False
        visiting.remove(hop_id)
        visited.add(hop_id)
        return True
    for hop_id in sorted(hops):
        if not visit(hop_id):
            issues.append(_issue("GRAPH-001", "/claim_evidence_graph/hops", "Hop-dependency graph must be acyclic.", hop_id))
            break

    for index, edge in enumerate(graph["support_edges"]):
        relation, sources, target = edge["relation"], edge["from_ids"], edge["to_id"]
        valid = False
        if relation == "direct_support":
            valid = bool(sources) and set(sources) <= evidence_ids and target in claim_ids
        elif relation == "supports_hop":
            valid = bool(sources) and set(sources) <= (evidence_ids | hop_ids) and target in hop_ids
        elif relation == "hop_supports_claim":
            valid = bool(sources) and set(sources) <= hop_ids and target in claim_ids
        elif relation == "contradicts":
            valid = bool(sources) and set(sources) <= (evidence_ids | hop_ids | claim_ids) and target in claim_ids
        if not valid:
            issues.append(_issue("GRAPH-002", f"/claim_evidence_graph/support_edges/{index}", f"Edge {edge['edge_id']} has type-incompatible or unresolved endpoints.", edge["edge_id"]))
    support_sources: dict[str, set[str]] = defaultdict(set)
    for edge in graph["support_edges"]:
        if edge["relation"] == "supports_hop":
            support_sources[edge["to_id"]].update(edge["from_ids"])
    for index, hop in enumerate(graph["hops"]):
        declared_inputs = set(hop["input_evidence_ids"]) | set(hop["input_hop_ids"])
        if not declared_inputs <= support_sources[hop["hop_id"]]:
            issues.append(_issue("GRAPH-002", f"/claim_evidence_graph/hops/{index}", f"Hop {hop['hop_id']} inputs must be connected by supports_hop edges.", hop["hop_id"]))

    required_claims = set(family["answer_spec"]["required_claim_ids"])
    covered: set[str] = set()
    for index, ses in enumerate(graph["accepted_sufficient_sets"]):
        pointer = f"/claim_evidence_graph/accepted_sufficient_sets/{index}"
        if set(ses["claim_ids"]) != required_claims or not set(ses["evidence_ids"]) <= evidence_ids or not set(ses["hop_ids"]) <= hop_ids:
            issues.append(_issue("SES-001", pointer, f"SES {ses['set_id']} must cover all required claims and contain only resolved evidence and hops.", ses["set_id"]))
            continue
        covered.update(ses["claim_ids"])
        supported = _supportable_claims(graph, set(ses["evidence_ids"]), set(ses["hop_ids"]))
        if not set(ses["claim_ids"]) <= supported:
            issues.append(_issue("SES-002", pointer, f"SES {ses['set_id']} does not induce a complete derivation for all listed claims.", ses["set_id"]))
        for member in ses["evidence_ids"]:
            reduced = set(ses["evidence_ids"]) - {member}
            if set(ses["claim_ids"]) <= _supportable_claims(graph, reduced, set(ses["hop_ids"])):
                issues.append(_issue("SES-004", pointer, f"SES {ses['set_id']} remains sufficient after removing {member}.", ses["set_id"], member))
        if len(set(ses["validator_ids"])) < 2:
            issues.append(_issue("SES-006", pointer + "/validator_ids", f"SES {ses['set_id']} requires at least two independent validators.", ses["set_id"]))
        if not set(ses["validator_ids"]) <= validators:
            issues.append(_issue("SES-006", pointer + "/validator_ids", f"SES {ses['set_id']} validator IDs must be registered family validators.", ses["set_id"]))
    if not required_claims <= covered:
        issues.append(_issue("SES-003", "/claim_evidence_graph/accepted_sufficient_sets", f"Required claims lack accepted SES coverage: {sorted(required_claims - covered)}."))
    for left_index, left in enumerate(graph["accepted_sufficient_sets"]):
        for right_index, right in enumerate(graph["accepted_sufficient_sets"]):
            if left_index == right_index or set(left["claim_ids"]) != set(right["claim_ids"]):
                continue
            if set(left["evidence_ids"]) > set(right["evidence_ids"]):
                issues.append(_issue("SES-005", f"/claim_evidence_graph/accepted_sufficient_sets/{left_index}", f"SES {left['set_id']} is a strict evidence superset of {right['set_id']} for the same claims.", left["set_id"], right["set_id"]))

    for index, group in enumerate(graph["necessity_groups"]):
        pointer = f"/claim_evidence_graph/necessity_groups/{index}"
        members = set(group["member_evidence_ids"])
        targets = set(group["claim_ids"])
        if not members <= evidence_ids or not targets or not targets <= required_claims:
            issues.append(_issue("NEC-001", pointer, f"Necessity group {group['group_id']} must reference evidence and at least one required claim.", group["group_id"]))
            continue
        relevant = [ses for ses in graph["accepted_sufficient_sets"] if targets <= set(ses["claim_ids"])]
        if not relevant or any(not members.intersection(ses["evidence_ids"]) for ses in relevant):
            issues.append(_issue("NEC-002", pointer, f"Necessity group {group['group_id']} does not intersect every accepted SES covering its target claims.", group["group_id"]))
        remaining = evidence_ids - members
        surviving_targets = targets & _supportable_claims(graph, remaining)
        if surviving_targets:
            issues.append(_issue("NEC-003", pointer, f"Removing all members of necessity group {group['group_id']} leaves targeted claims supported: {sorted(surviving_targets)}.", group["group_id"]))
        modalities = {evidence[item]["modality"] for item in members if item in evidence}
        if set(group["required_modalities"]) != modalities:
            issues.append(_issue("NEC-004", pointer + "/required_modalities", f"required_modalities must equal modalities induced by all group members: {sorted(modalities)}.", group["group_id"]))
        if not set(group["required_hop_ids"]) <= hop_ids:
            issues.append(_issue("NEC-005", pointer + "/required_hop_ids", "Every required_hop_id must resolve.", group["group_id"]))
        else:
            relevant_hops = {
                hop_id
                for ses in relevant
                for hop_id in ses["hop_ids"]
            }
            available_after_removal = _available_hops(graph, remaining)
            broken_relevant_hops = relevant_hops - available_after_removal
            if set(group["required_hop_ids"]) != broken_relevant_hops:
                issues.append(_issue("NEC-005", pointer + "/required_hop_ids", f"required_hop_ids must exactly enumerate intervention-broken hops in relevant accepted SESs: {sorted(broken_relevant_hops)}.", group["group_id"]))

    issues.extend(validate_family_diff(family).issues)
    clean, blocked, restored = family["episodes"]
    expected_roles = ["CLEAN", "BLOCKED", "RESTORED"]
    if [episode["state_role"] for episode in family["episodes"]] != expected_roles:
        issues.append(_issue("FAM-001", "/episodes", "Episodes must be exactly CLEAN, BLOCKED, RESTORED in that order."))
    if clean["anchor_episode_id"] is not None or blocked["anchor_episode_id"] != clean["episode_id"] or restored["anchor_episode_id"] != clean["episode_id"]:
        issues.append(_issue("ID-005", "/episodes", "BLOCKED and RESTORED must anchor to CLEAN; CLEAN anchor must be null."))
    for index, episode in enumerate(family["episodes"]):
        if episode["intervention_family_id"] != family["intervention_family_id"]:
            issues.append(_issue("ID-004", f"/episodes/{index}/intervention_family_id", "Episode intervention_family_id must match the family value.", episode["episode_id"]))
        for intervention in episode["interventions"]:
            if intervention["mechanism"] != family["intervention_mechanism"]:
                issues.append(_issue("FAM-003", f"/episodes/{index}/interventions", "Every intervention must use the one declared family mechanism.", intervention["intervention_id"]))
            for evidence_id in intervention["affected_evidence_ids"]:
                if evidence_id not in evidence_ids:
                    issues.append(_issue("ID-003", f"/episodes/{index}/interventions", f"Intervention references unknown evidence ID {evidence_id}.", intervention["intervention_id"], evidence_id))
            group_id = intervention["affected_necessity_group_id"]
            if group_id is not None and group_id not in groups:
                issues.append(_issue("ID-003", f"/episodes/{index}/interventions", f"Intervention references unknown necessity group ID {group_id}.", intervention["intervention_id"], group_id))
        for evidence_id in episode["initial_state"]["accessible_evidence_ids"]:
            if evidence_id not in evidence_ids:
                issues.append(_issue("ID-003", f"/episodes/{index}/initial_state/accessible_evidence_ids", f"Unknown accessible evidence ID {evidence_id}.", episode["episode_id"], evidence_id))
        oracle = episode["oracle"]
        for group_id in oracle["gold_missing_necessity_group_ids"]:
            if group_id not in groups:
                issues.append(_issue("ID-003", f"/episodes/{index}/oracle/gold_missing_necessity_group_ids", f"Unknown necessity group ID {group_id}.", episode["episode_id"], group_id))
        for hop_id in oracle["gold_missing_hop_ids"]:
            if hop_id not in hops:
                issues.append(_issue("ID-003", f"/episodes/{index}/oracle/gold_missing_hop_ids", f"Unknown hop ID {hop_id}.", episode["episode_id"], hop_id))
        for set_id in oracle["accepted_final_set_ids"]:
            if set_id not in sets:
                issues.append(_issue("ID-003", f"/episodes/{index}/oracle/accepted_final_set_ids", f"Unknown accepted SES ID {set_id}.", episode["episode_id"], set_id))
        listed_sets = [sets[set_id] for set_id in oracle["accepted_final_set_ids"] if set_id in sets]
        reachable_listed = [ses for ses in listed_sets if _ses_reachable(ses, set(episode["initial_state"]["accessible_evidence_ids"]))]
        if episode["state_role"] == "CLEAN" and len(reachable_listed) != len(listed_sets):
            issues.append(_issue("FAM-004", f"/episodes/{index}/oracle/accepted_final_set_ids", "Every CLEAN accepted final SES must be initially reachable."))
        if episode["state_role"] == "BLOCKED" and listed_sets:
            issues.append(_issue("FAM-005", f"/episodes/{index}/oracle/accepted_final_set_ids", "BLOCKED may not declare an accepted final SES."))
    clean_access = set(clean["initial_state"]["accessible_evidence_ids"])
    blocked_access = set(blocked["initial_state"]["accessible_evidence_ids"])
    restored_access = set(restored["initial_state"]["accessible_evidence_ids"])
    ses_values = list(sets.values())
    clean_reachable_ids = {ses["set_id"] for ses in ses_values if _ses_reachable(ses, clean_access)}
    if set(clean["oracle"]["accepted_final_set_ids"]) != clean_reachable_ids:
        issues.append(_issue("FAM-004", "/episodes/0/oracle/accepted_final_set_ids", "CLEAN accepted_final_set_ids must exactly enumerate initially reachable accepted SESs."))
    if clean["interventions"] or not clean["oracle"]["initial_accessible_sufficient"] or not any(_ses_reachable(s, clean_access) for s in ses_values):
        issues.append(_issue("FAM-004", "/episodes/0", "CLEAN must have no intervention and must initially expose an accepted SES."))
    if blocked["oracle"]["initial_accessible_sufficient"] or blocked["oracle"]["expected_final_sufficiency"] != "insufficient":
        issues.append(_issue("FAM-005", "/episodes/1/oracle", "BLOCKED must be initially and finally insufficient."))
    if any(_ses_reachable(s, blocked_access) for s in ses_values):
        issues.append(_issue("INT-004", "/episodes/1/initial_state/accessible_evidence_ids", "An accepted SES remains reachable in BLOCKED."))
    if restored_access != blocked_access or restored["initial_state"]["enabled_channels"] != blocked["initial_state"]["enabled_channels"] or restored["oracle"]["expected_final_sufficiency"] != "sufficient":
        issues.append(_issue("FAM-006", "/episodes/2", "RESTORED must begin exactly as BLOCKED and end sufficient."))
    if not any(_ses_reachable(s, clean_access) for s in ses_values) or not restored["oracle"]["accepted_final_set_ids"]:
        issues.append(_issue("FAM-007", "/episodes", "CLEAN and restored terminal state must expose at least one accepted SES."))
    if family["source"]["access_class"] == "public_core_redistributable" and any(e["backend"]["track"] != "PUBLIC_CORE_FIXED_BACKEND_TRIPLETS" for e in family["episodes"]):
        issues.append(_issue("FAM-008", "/episodes", "Public-core families must use PUBLIC_CORE_FIXED_BACKEND_TRIPLETS."))
    if family["source"]["access_class"] == "public_core_redistributable" and not 1200.0 <= duration <= 5400.0:
        issues.append(_issue("FAM-008", "/source/duration_s", "Pilot-0 public-core source duration must be between 20 and 90 minutes."))
    if family["source"]["access_class"] == "restricted_compatibility" and any(e["backend"]["track"] != "EXTERNAL_COMPATIBILITY_UNPOOLED" for e in family["episodes"]):
        issues.append(_issue("FAM-008", "/episodes", "Restricted families must use EXTERNAL_COMPATIBILITY_UNPOOLED."))

    if not blocked_access <= clean_access:
        issues.append(_issue("INT-001", "/episodes/1/initial_state/accessible_evidence_ids", "BLOCKED may not add evidence that was inaccessible in CLEAN."))
    if not set(blocked["initial_state"]["enabled_channels"]) <= set(clean["initial_state"]["enabled_channels"]):
        issues.append(_issue("INT-001", "/episodes/1/initial_state/enabled_channels", "BLOCKED may not enable a channel that was disabled in CLEAN."))
    if blocked["replay"]["seed"] != clean["replay"]["seed"] or restored["replay"]["seed"] != clean["replay"]["seed"]:
        issues.append(_issue("FAM-002", "/episodes", "Replay seed must be identical across CLEAN, BLOCKED, and RESTORED."))

    blocked_ops = [item for item in blocked["interventions"] if item["phase"] == "blocked"]
    restore_ops = [item for item in restored["interventions"] if item["phase"] == "restoration"]
    if len(blocked_ops) != 1:
        issues.append(_issue("FAM-003", "/episodes/1/interventions", "BLOCKED must contain exactly one blocking intervention."))
    if len(restore_ops) != 1:
        issues.append(_issue("REST-003", "/episodes/2/interventions", "RESTORED must contain exactly one restoration intervention."))
    if blocked_ops:
        block = blocked_ops[0]
        declared = set(block["affected_evidence_ids"])
        removed = clean_access - blocked_access
        if block["activation"] != {"hook": "episode_start", "call_index": None}:
            issues.append(_issue("INT-001", "/episodes/1/interventions/0/activation", "The blocking intervention must activate at episode_start with no call index."))
        if block["restoration"] != {
            "enabled": False,
            "trigger_type": "none",
            "trigger_value": None,
            "restores_intervention_id": None,
        }:
            issues.append(_issue("INT-001", "/episodes/1/interventions/0/restoration", "The BLOCKED intervention may not carry an active restoration trigger."))
        if family["intervention_mechanism"] == "necessity_group_withholding":
            group = groups.get(block["affected_necessity_group_id"])
            if group is None:
                issues.append(_issue("ID-003", "/episodes/1/interventions/0/affected_necessity_group_id", "Blocking intervention references an unknown necessity group."))
            else:
                members = set(group["member_evidence_ids"])
                if declared != members or removed != members:
                    issues.append(_issue("INT-002", "/episodes/1/interventions/0", "Withholding must declare and remove every necessity-group member.", group["group_id"]))
                expected_access = [item for item in clean["initial_state"]["accessible_evidence_ids"] if item not in members]
                if blocked["initial_state"]["accessible_evidence_ids"] != expected_access:
                    issues.append(_issue("INT-001", "/episodes/1/initial_state/accessible_evidence_ids", "Withholding must preserve CLEAN evidence order and change only the declared necessity-group members."))
                if set(blocked["oracle"]["gold_missing_necessity_group_ids"]) != {group["group_id"]}:
                    issues.append(_issue("INT-002", "/episodes/1/oracle/gold_missing_necessity_group_ids", "BLOCKED oracle must name exactly the withheld necessity group."))
            if block["affected_channel"] is not None:
                issues.append(_issue("INT-001", "/episodes/1/interventions/0/affected_channel", "Necessity-group withholding must not declare a channel outage."))
            if clean["initial_state"]["enabled_channels"] != blocked["initial_state"]["enabled_channels"]:
                issues.append(_issue("INT-001", "/episodes/1/initial_state/enabled_channels", "Necessity-group withholding may not change enabled channels."))
        else:
            channel = block["affected_channel"]
            if channel is None or block["affected_necessity_group_id"] is not None:
                issues.append(_issue("INT-003", "/episodes/1/interventions/0", "Channel outage must declare exactly one affected channel and no necessity-group ID."))
            expected_removed = {item for item in clean_access if evidence[item]["modality"] in _channel_modalities(channel)}
            if declared != expected_removed or removed != expected_removed:
                issues.append(_issue("INT-003", "/episodes/1", f"Channel outage must disable exactly evidence routed through {channel}."))
            enabled_delta = set(clean["initial_state"]["enabled_channels"]) - set(blocked["initial_state"]["enabled_channels"])
            if enabled_delta != {channel}:
                issues.append(_issue("INT-003", "/episodes/1/initial_state/enabled_channels", f"Channel outage must disable exactly {channel}."))
            expected_access = [item for item in clean["initial_state"]["accessible_evidence_ids"] if item not in expected_removed]
            expected_channels = [item for item in clean["initial_state"]["enabled_channels"] if item != channel]
            if blocked["initial_state"]["accessible_evidence_ids"] != expected_access or blocked["initial_state"]["enabled_channels"] != expected_channels:
                issues.append(_issue("INT-003", "/episodes/1/initial_state", "Channel outage must preserve ordering and change only the declared channel route."))
        unavailable_hops = _available_hops(graph, clean_access) - _available_hops(graph, blocked_access)
        unavailable_hop_types = {hops[hop_id]["hop_type"] for hop_id in unavailable_hops}
        expected_modalities = sorted({evidence[item]["modality"] for item in removed})
        for episode_index, episode in ((1, blocked), (2, restored)):
            oracle = episode["oracle"]
            if set(oracle["gold_missing_hop_ids"]) != unavailable_hops:
                issues.append(_issue("NEC-005", f"/episodes/{episode_index}/oracle/gold_missing_hop_ids", f"Oracle missing hops must exactly match intervention-broken hops: {sorted(unavailable_hops)}."))
            if set(oracle["gold_missing_hop_types"]) != unavailable_hop_types:
                issues.append(_issue("NEC-005", f"/episodes/{episode_index}/oracle/gold_missing_hop_types", f"Oracle missing hop types must match the broken hops: {sorted(unavailable_hop_types)}."))
            if {tuple(sorted(item)) for item in oracle["gold_missing_modality_sets"]} != {tuple(expected_modalities)}:
                issues.append(_issue("NEC-004", f"/episodes/{episode_index}/oracle/gold_missing_modality_sets", f"Oracle missing modality sets must match the blocked evidence modalities: {expected_modalities}."))
            if oracle["missingness_cause"] != "evidence_in_source_but_inaccessible":
                issues.append(_issue("FAM-005", f"/episodes/{episode_index}/oracle/missingness_cause", "BLOCKED and pre-trigger RESTORED missingness cause must be evidence_in_source_but_inaccessible."))
    if restore_ops:
        restore = restore_ops[0]
        if restore["activation"] != {"hook": "on_restore", "call_index": None}:
            issues.append(_issue("REST-002", "/episodes/2/interventions/1/activation", "Restoration must use the on_restore hook with no activation call index."))
        if restore["restoration"]["trigger_type"] not in {"fixed_call_index", "get_channel_status"}:
            issues.append(_issue("REST-002", "/episodes/2/interventions/1/restoration/trigger_type", "Restoration trigger must be fixed_call_index or get_channel_status."))
        trigger_type = restore["restoration"]["trigger_type"]
        trigger_value = restore["restoration"]["trigger_value"]
        if (trigger_type == "fixed_call_index" and not isinstance(trigger_value, int)) or (
            trigger_type == "get_channel_status" and trigger_value is not None
        ):
            issues.append(_issue("REST-002", "/episodes/2/interventions/1/restoration/trigger_value", "Fixed-call restoration requires an integer trigger value; get_channel_status requires null."))
        if trigger_type == "fixed_call_index" and isinstance(trigger_value, int) and trigger_value >= restored["budget"]["max_steps"]:
            issues.append(_issue("REST-004", "/episodes/2/interventions/1/restoration/trigger_value", "Fixed-call restoration must be reachable before max_steps is exhausted."))
        if not restore["restoration"]["enabled"]:
            issues.append(_issue("REST-003", "/episodes/2/interventions/1/restoration/enabled", "Restoration intervention must be enabled."))
        if blocked_ops:
            block = blocked_ops[0]
            if restore["restoration"]["restores_intervention_id"] != block["intervention_id"]:
                issues.append(_issue("REST-003", "/episodes/2/interventions/1/restoration/restores_intervention_id", "Restoration must reverse the registered blocking intervention."))
            for field in ("mechanism", "affected_necessity_group_id", "affected_evidence_ids", "affected_channel"):
                if restore[field] != block[field]:
                    issues.append(_issue("REST-003", "/episodes/2/interventions/1", f"Restoration field {field} must exactly match the block."))
        restored_terminal_access = restored_access | set(restore["affected_evidence_ids"])
        accepted_terminal_sets = [
            sets[set_id]
            for set_id in restored["oracle"]["accepted_final_set_ids"]
            if set_id in sets
        ]
        if not accepted_terminal_sets or not any(_ses_reachable(ses, restored_terminal_access) for ses in accepted_terminal_sets):
            issues.append(_issue("REST-003", "/episodes/2/oracle/accepted_final_set_ids", "Restoration must make at least one declared accepted SES reachable without adding undeclared evidence."))
        restored_reachable_ids = {
            ses["set_id"] for ses in ses_values if _ses_reachable(ses, restored_terminal_access)
        }
        if set(restored["oracle"]["accepted_final_set_ids"]) != restored_reachable_ids:
            issues.append(_issue("REST-003", "/episodes/2/oracle/accepted_final_set_ids", "RESTORED accepted_final_set_ids must exactly enumerate terminally reachable accepted SESs."))

    if annotation["status"] == "frozen":
        issues.append(_issue("CERT-001", "/annotation/status", "Dataset-freeze certification requires the external backend/intervention manifest and linked validator trajectories, which are not accepted by this reference API."))

    if manifest is None:
        issues.append(_issue("PROV-000", "/source", "A matching acquisition manifest is required; semantic validation fails closed without it."))
    else:
        gate = GateProfile.ANNOTATION
        manifest_report = validate_manifest_gate(manifest, gate, registry)
        issues.extend(manifest_report.issues)
        source = family["source"]
        manifest_rights = manifest.get("rights", {}) if isinstance(manifest, dict) else {}
        if not isinstance(manifest_rights, dict):
            manifest_rights = {}
        manifest_integrity = manifest.get("integrity", {}) if isinstance(manifest, dict) else {}
        if not isinstance(manifest_integrity, dict):
            manifest_integrity = {}
        manifest_media = manifest.get("media", {}) if isinstance(manifest, dict) else {}
        if not isinstance(manifest_media, dict):
            manifest_media = {}
        if source["manifest_asset_id"] != (manifest.get("asset_id") if isinstance(manifest, dict) else None) or source["manifest_revision"] != (manifest.get("manifest_revision") if isinstance(manifest, dict) else None) or source["rights_decision_id"] != manifest_rights.get("rights_decision_id"):
            issues.append(_issue("PROV-001", "/source", "Family source asset, revision, and rights decision must match the acquisition manifest."))
        if (
            media_mode == "synthetic_testing"
            and verified_asset is None
            and (
            source["content_hash"] != manifest_integrity.get("content_sha256")
            or source["duration_s"] != manifest_media.get("duration_s")
            )
        ):
            issues.append(_issue("PROV-002", "/source", "Family source content hash and duration must match the acquisition manifest."))
        if manifest_report.ok and any(e["backend"]["track"] == "PUBLIC_CORE_FIXED_BACKEND_TRIPLETS" for e in family["episodes"]):
            decision_names = ("acquisition", "processing", "derivative_release", "annotation_release", "transcript_release", "raw_media_release")
            bad = [name for name in decision_names if manifest["rights"]["decisions"][name] != "allowed"]
            if bad:
                issues.append(_issue("PROV-003", "/rights/decisions", f"Public-core family requires all six decisions allowed; non-allowed: {bad}."))
        if media_mode == "real" and verified_asset is None:
            issues.append(
                _issue(
                    "PROV-005",
                    "/source",
                    "Real-media family validation requires a verified-asset bridge record.",
                )
            )
        elif verified_asset is not None:
            # Local import avoids making the core schema/semantic package depend
            # on data-adapter initialization.  The bridge is still normative
            # whenever a verified-asset record is supplied.
            from av_trace_data.provenance import validate_episode_provenance

            bridge_report = validate_episode_provenance(
                family,
                manifest,
                verified_asset,
                registry=registry,
            )
            issues.extend(bridge_report.issues)

    return make_report(
        issues,
        validator_version=VALIDATOR_VERSION,
        family_hash=safe_sha256_json(family),
        manifest_hash=safe_sha256_json(manifest) if manifest is not None else None,
        verified_asset_hash=safe_sha256_json(verified_asset)
        if verified_asset is not None
        else None,
    )
