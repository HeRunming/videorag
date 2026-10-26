"""Generation of linked validator trajectories and proof artifacts."""

from __future__ import annotations

import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from av_trace.util import load_json, sha256_json
from av_trace_mvp.index import load_generated

from .graph import derive_claims, minimality_cases, powerset, reachable_ses_ids, ses_satisfied
from .io import (
    DEFAULT_GENERATED_ROOT,
    DEFAULT_VALIDATOR_ROOT,
    PACKAGE_ROOT,
    relative_path,
    write_json,
)
from .schemas import require_valid
from .trajectory import (
    direct_route_cost,
    evidence_ids_from_trajectory,
    generate_validator_trajectory,
    observation_call,
    observation_ids_by_evidence,
)


VALIDATOR_SCHEMA_VERSION = "1.0.0"
GENERATOR_VERSION = "av-trace-validator-generator-1.0.0"
FIXED_CREATED_AT = "2026-09-06T00:00:00Z"


def _episode(family: Mapping[str, Any], state_role: str) -> Mapping[str, Any]:
    return next(item for item in family["episodes"] if item["state_role"] == state_role)


def _family_file(generated_root: Path, family_id: str) -> Path:
    native = generated_root / "families" / f"{family_id}.json"
    return native if native.is_file() else generated_root / "backend_families.json"


def _source_manifest_path(generated_root: Path, family: Mapping[str, Any]) -> Path:
    return generated_root / "manifests" / f"{family['source']['asset_id']}.json"


def _identity_document(
    validator_id: str,
    *,
    order: int,
) -> dict[str, Any]:
    return {
        "schema_version": VALIDATOR_SCHEMA_VERSION,
        "validator_id": validator_id,
        "display_name": f"Synthetic validator {order}",
        "role": "validator",
        "organization": "av-trace-synthetic-independent-validator",
        "independence_group": validator_id,
        "permitted_private_oracle_access": True,
        "conflict_attestation": {
            "not_family_author": True,
            "not_adjudicator": True,
            "not_alternative_evidence_finder": True,
            "independent_of_validator_ids": [
                "synthetic_validator_b" if order == 1 else "synthetic_validator_a"
            ],
        },
        "identity_version": "synthetic-validator-v1",
    }


def _link_document(
    family: Mapping[str, Any],
    state_role: str,
    validator_id: str,
    trajectory_path: Path,
    trajectory: Mapping[str, Any],
    *,
    root: Path,
    family_path: Path,
    family_hash: str,
    manifest_hash: str,
    backend_manifest_hash: str,
    index_version: str,
    index_hash: str,
    trigger_type: str,
) -> dict[str, Any]:
    episode = _episode(family, state_role)
    return {
        "schema_version": VALIDATOR_SCHEMA_VERSION,
        "link_id": f"link.{validator_id}.{family['family_id']}.{state_role.lower()}",
        "validator_id": validator_id,
        "family_id": family["family_id"],
        "family_annotation_version": family["annotation"]["version"],
        "episode_id": episode["episode_id"],
        "state_role": state_role,
        "trajectory_path": relative_path(trajectory_path, root),
        "trajectory_id": trajectory["trajectory_id"],
        "trajectory_hash": trajectory["replay"]["trajectory_hash"],
        "family_path": relative_path(family_path, root),
        "family_hash": family_hash,
        "backend_version": episode["backend"]["backend_version"],
        "backend_manifest_hash": backend_manifest_hash,
        "index_version": index_version,
        "index_hash": index_hash,
        "source_manifest_hash": manifest_hash,
        "intervention_manifest_hash": trajectory["replay"]["intervention_manifest_hash"],
        "search_plan_id": (
            "search_then_observe_chronological"
            if validator_id.endswith("_a")
            else "direct_observe_reverse_chronological"
        ),
        "trigger_type": trigger_type,
        "generated_at": FIXED_CREATED_AT,
    }


def _ses_demonstrations(
    family: Mapping[str, Any],
    trajectories: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    graph = family["claim_evidence_graph"]
    results = []
    for ses in graph["accepted_sufficient_sets"]:
        validator_records = []
        for validator_id in sorted({key[0] for key in trajectories}):
            clean = trajectories[(validator_id, "CLEAN")]
            restored = trajectories[(validator_id, "RESTORED")]
            clean_evidence = evidence_ids_from_trajectory(family, clean)
            restored_evidence = evidence_ids_from_trajectory(family, restored)
            if not set(ses["evidence_ids"]) <= clean_evidence:
                continue
            # The alternate-route family has two accepted SESs. Validator B uses
            # the second route as its first completed route; both still observe
            # all routes so every accepted SES is independently demonstrated.
            if not set(ses["evidence_ids"]) <= restored_evidence:
                continue
            validator_records.append(
                {
                    "validator_id": validator_id,
                    "clean_trajectory_id": clean["trajectory_id"],
                    "clean_trajectory_hash": clean["replay"]["trajectory_hash"],
                    "clean_observation_ids_by_evidence": observation_ids_by_evidence(
                        family, clean
                    ),
                    "restored_trajectory_id": restored["trajectory_id"],
                    "restored_trajectory_hash": restored["replay"]["trajectory_hash"],
                    "restored_observation_ids_by_evidence": observation_ids_by_evidence(
                        family, restored
                    ),
                }
            )
        results.append(
            {
                "schema_version": VALIDATOR_SCHEMA_VERSION,
                "demonstration_id": f"ses-demo.{family['family_id']}.{ses['set_id']}",
                "family_id": family["family_id"],
                "family_annotation_version": family["annotation"]["version"],
                "set_id": ses["set_id"],
                "claim_ids": list(ses["claim_ids"]),
                "evidence_ids": list(ses["evidence_ids"]),
                "hop_ids": list(ses["hop_ids"]),
                "satisfiable": ses_satisfied(graph, ses, ses["evidence_ids"]),
                "validator_demonstrations": validator_records,
            }
        )
    return results


def _minimality_documents(family: Mapping[str, Any]) -> list[dict[str, Any]]:
    graph = family["claim_evidence_graph"]
    documents = []
    for ses in graph["accepted_sufficient_sets"]:
        cases = minimality_cases(graph, ses)
        documents.append(
            {
                "schema_version": VALIDATOR_SCHEMA_VERSION,
                "minimality_result_id": f"minimality.{family['family_id']}.{ses['set_id']}",
                "family_id": family["family_id"],
                "family_annotation_version": family["annotation"]["version"],
                "set_id": ses["set_id"],
                "full_set_satisfiable": ses_satisfied(graph, ses, ses["evidence_ids"]),
                "leave_one_out_cases": cases,
                "minimal": all(
                    not item["still_sufficient"] and item["unsupported_claim_ids"]
                    for item in cases
                ),
                "strict_superset_of_accepted_set_ids": sorted(
                    other["set_id"]
                    for other in graph["accepted_sufficient_sets"]
                    if other["set_id"] != ses["set_id"]
                    and set(other["claim_ids"]) == set(ses["claim_ids"])
                    and set(other["evidence_ids"]) < set(ses["evidence_ids"])
                ),
            }
        )
    return documents


def _blocked_proof(
    family: Mapping[str, Any],
    trajectories: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    graph = family["claim_evidence_graph"]
    clean_access = set(_episode(family, "CLEAN")["initial_state"]["accessible_evidence_ids"])
    blocked = _episode(family, "BLOCKED")
    blocked_access = set(blocked["initial_state"]["accessible_evidence_ids"])
    block = next(item for item in blocked["interventions"] if item["phase"] == "blocked")
    reachable = reachable_ses_ids(graph, blocked_access)
    validator_results = []
    for validator_id in sorted({key[0] for key in trajectories}):
        trajectory = trajectories[(validator_id, "BLOCKED")]
        observed = evidence_ids_from_trajectory(family, trajectory)
        cause = trajectory["final_output"]["diagnosis"]["cause_probabilities"]
        validator_results.append(
            {
                "validator_id": validator_id,
                "trajectory_id": trajectory["trajectory_id"],
                "trajectory_hash": trajectory["replay"]["trajectory_hash"],
                "observed_evidence_ids": sorted(observed),
                "reachable_ses_ids": reachable_ses_ids(graph, observed),
                "final_verdict": trajectory["final_output"]["verdict"],
                "diagnosed_missingness_cause": max(
                    cause, key=lambda key: (cause[key], key)
                ),
                "diagnosed_missing_modalities": sorted(
                    key
                    for key, value in trajectory["final_output"]["diagnosis"][
                        "modality_probabilities"
                    ].items()
                    if value >= 0.5
                ),
            }
        )
    all_subsets_closed = all(
        not reachable_ses_ids(graph, subset)
        for subset in powerset(blocked_access)
    )
    return {
        "schema_version": VALIDATOR_SCHEMA_VERSION,
        "blocked_proof_id": f"blocked-proof.{family['family_id']}",
        "family_id": family["family_id"],
        "family_annotation_version": family["annotation"]["version"],
        "mechanism": family["intervention_mechanism"],
        "blocking_intervention_id": block["intervention_id"],
        "affected_evidence_ids": list(block["affected_evidence_ids"]),
        "affected_channel": block["affected_channel"],
        "clean_accessible_evidence_ids": sorted(clean_access),
        "blocked_accessible_evidence_ids": sorted(blocked_access),
        "removed_evidence_ids": sorted(clean_access - blocked_access),
        "reachable_ses_ids": reachable,
        "all_blocked_subsets_insufficient": all_subsets_closed,
        "missing_route": {
            "necessity_group_id": block["affected_necessity_group_id"],
            "evidence_ids": list(block["affected_evidence_ids"]),
            "channel": block["affected_channel"],
        },
        "validator_results": validator_results,
        "blocked_insufficient": not reachable and all_subsets_closed,
    }


def _restored_proof(
    family: Mapping[str, Any],
    trajectories: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    graph = family["claim_evidence_graph"]
    blocked = _episode(family, "BLOCKED")
    restored = _episode(family, "RESTORED")
    block = next(item for item in blocked["interventions"] if item["phase"] == "blocked")
    restore = next(
        item for item in restored["interventions"] if item["phase"] == "restoration"
    )
    terminal_access = set(restored["initial_state"]["accessible_evidence_ids"]) | set(
        restore["affected_evidence_ids"]
    )
    validator_results = []
    for validator_id in sorted({key[0] for key in trajectories}):
        trajectory = trajectories[(validator_id, "RESTORED")]
        hook_id = restore["intervention_id"]
        trigger_events = [
            index
            for index, event in enumerate(trajectory["events"])
            if hook_id in event.get("active_hook_ids", ())
        ]
        observed = evidence_ids_from_trajectory(family, trajectory)
        validator_results.append(
            {
                "validator_id": validator_id,
                "trajectory_id": trajectory["trajectory_id"],
                "trajectory_hash": trajectory["replay"]["trajectory_hash"],
                "trigger_event_index": trigger_events[0] if len(trigger_events) == 1 else None,
                "trigger_hook_ids": [hook_id] if len(trigger_events) == 1 else [],
                "observed_evidence_ids": sorted(observed),
                "acquired_ses_ids": reachable_ses_ids(graph, observed),
                "supported_final_answer": (
                    trajectory["final_output"]["verdict"] == "sufficient"
                    and bool(reachable_ses_ids(graph, observed))
                ),
                "total_steps": trajectory["completion"]["total_steps"],
                "total_cost": trajectory["completion"]["total_cost"],
            }
        )
    return {
        "schema_version": VALIDATOR_SCHEMA_VERSION,
        "restored_proof_id": f"restored-proof.{family['family_id']}",
        "family_id": family["family_id"],
        "family_annotation_version": family["annotation"]["version"],
        "blocking_intervention_id": block["intervention_id"],
        "restoration_intervention_id": restore["intervention_id"],
        "trigger_type": restore["restoration"]["trigger_type"],
        "trigger_value": restore["restoration"]["trigger_value"],
        "pretrigger_state_equal": (
            blocked["initial_state"] == restored["initial_state"]
            and restored["interventions"][0] == blocked["interventions"][0]
        ),
        "exact_inverse": (
            restore["restoration"]["restores_intervention_id"]
            == block["intervention_id"]
            and restore["mechanism"] == block["mechanism"]
            and restore["affected_evidence_ids"] == block["affected_evidence_ids"]
            and restore["affected_channel"] == block["affected_channel"]
        ),
        "terminal_accessible_evidence_ids": sorted(terminal_access),
        "terminal_reachable_ses_ids": reachable_ses_ids(graph, terminal_access),
        "validator_results": validator_results,
        "restoration_successful": (
            bool(reachable_ses_ids(graph, terminal_access))
            and all(item["supported_final_answer"] for item in validator_results)
        ),
    }


def _direct_route_steps(
    family: Mapping[str, Any],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    evidence = {
        item["evidence_id"]: item
        for item in family["claim_evidence_graph"]["evidence_units"]
    }
    steps = []
    for evidence_id in evidence_ids:
        tool, arguments = observation_call(evidence[evidence_id])
        steps.append(
            {
                "tool": tool,
                "arguments": arguments,
                "cost": _episode(family, "CLEAN")["budget"]["tool_costs"][tool],
                "expected_evidence_ids": [evidence_id],
            }
        )
    steps.append(
        {
            "tool": "finalize",
            "arguments": {"target": "supported_answer"},
            "cost": 0.0,
            "expected_evidence_ids": [],
        }
    )
    return steps


def _feasible_route_records(
    family: Mapping[str, Any],
    trajectories: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Enumerate feasibility at every action boundary, independent of agent runs."""

    graph = family["claim_evidence_graph"]
    evidence = {
        item["evidence_id"]: item
        for item in graph["evidence_units"]
    }
    records = []
    for validator_id in sorted({key[0] for key in trajectories}):
        for state_role in ("CLEAN", "BLOCKED", "RESTORED"):
            trajectory = trajectories[(validator_id, state_role)]
            episode = _episode(family, state_role)
            restore = next(
                (
                    item
                    for item in episode["interventions"]
                    if item["phase"] == "restoration"
                ),
                None,
            )
            observed: set[str] = set()
            cost_used = 0.0
            restored_now = state_role != "RESTORED"
            for decision_index, event in enumerate(trajectory["events"]):
                remaining_steps = episode["budget"]["max_steps"] - decision_index
                remaining_cost = episode["budget"]["cost_limit"] - cost_used
                alternatives = []
                for ses in graph["accepted_sufficient_sets"]:
                    missing = sorted(set(ses["evidence_ids"]) - observed)
                    route_steps: list[dict[str, Any]] = []
                    if not missing:
                        feasible = False
                        reason = "evidence_already_sufficient"
                    elif state_role == "BLOCKED":
                        feasible = False
                        reason = "blocked_state_has_no_restoration_operation"
                    else:
                        trigger_steps: list[dict[str, Any]] = []
                        if state_role == "RESTORED" and not restored_now:
                            if restore is None:
                                feasible = False
                                reason = "missing_restoration_operation"
                            else:
                                spec = restore["restoration"]
                                if spec["trigger_type"] == "get_channel_status":
                                    trigger_steps = [
                                        {
                                            "tool": "get_channel_status",
                                            "arguments": {
                                                "channels": [
                                                    restore["affected_channel"] or "clip"
                                                ]
                                            },
                                            "cost": episode["budget"]["tool_costs"][
                                                "get_channel_status"
                                            ],
                                            "expected_evidence_ids": [],
                                        }
                                    ]
                                    feasible = True
                                    reason = "status_trigger_then_direct_route"
                                elif decision_index <= spec["trigger_value"]:
                                    wait = spec["trigger_value"] - decision_index
                                    trigger_steps = [
                                        {
                                            "tool": "get_channel_status",
                                            "arguments": {"channels": ["clip"]},
                                            "cost": episode["budget"]["tool_costs"][
                                                "get_channel_status"
                                            ],
                                            "expected_evidence_ids": [],
                                        }
                                        for _ in range(wait + 1)
                                    ]
                                    feasible = True
                                    reason = "fixed_call_trigger_then_direct_route"
                                else:
                                    feasible = False
                                    reason = "fixed_call_trigger_missed"
                        else:
                            feasible = True
                            reason = "direct_route"
                        route_steps = trigger_steps + _direct_route_steps(family, missing)
                        route_cost = sum(item["cost"] for item in route_steps)
                        feasible = feasible and len(route_steps) <= remaining_steps and route_cost <= remaining_cost + 1e-9
                        if not feasible and reason in {
                            "direct_route",
                            "status_trigger_then_direct_route",
                            "fixed_call_trigger_then_direct_route",
                        }:
                            reason = "insufficient_remaining_budget_or_steps"
                    route_cost = sum(item["cost"] for item in route_steps)
                    alternatives.append(
                        {
                            "route_id": f"route.{family['family_id']}.{ses['set_id']}",
                            "set_id": ses["set_id"],
                            "missing_evidence_ids": missing,
                            "steps": route_steps,
                            "required_steps": len(route_steps),
                            "required_cost": route_cost,
                            "feasible": feasible,
                            "reason": reason,
                        }
                    )
                feasible_routes = [item for item in alternatives if item["feasible"]]
                records.append(
                    {
                        "schema_version": VALIDATOR_SCHEMA_VERSION,
                        "record_id": (
                            f"feasible.{validator_id}.{family['family_id']}."
                            f"{state_role.lower()}.{decision_index}"
                        ),
                        "family_id": family["family_id"],
                        "family_annotation_version": family["annotation"]["version"],
                        "episode_id": episode["episode_id"],
                        "state_role": state_role,
                        "validator_id": validator_id,
                        "source_trajectory_id": trajectory["trajectory_id"],
                        "source_trajectory_hash": trajectory["replay"]["trajectory_hash"],
                        "decision_index": decision_index,
                        "observed_evidence_ids": sorted(observed),
                        "remaining_steps": remaining_steps,
                        "remaining_cost": round(remaining_cost, 6),
                        "restoration_available": (
                            state_role == "RESTORED" and not restored_now
                        ),
                        "route_alternatives": alternatives,
                        "feasible_route_ids": [
                            item["route_id"] for item in feasible_routes
                        ],
                        "eligible": bool(feasible_routes),
                    }
                )
                if event.get("active_hook_ids"):
                    restored_now = True
                for result in event.get("response", {}).get("results", ()):
                    if result.get("result_type") != "observation":
                        continue
                    observed.update(
                        item
                        for item in evidence
                        if result["interval"] in evidence[item]["intervals"]
                        and evidence[item]["modality"] in result["modalities"]
                    )
                if event.get("response"):
                    cost_used = float(event["response"]["cost_used_total"])
    return records


def generate_validator_artifacts(
    *,
    generated_root: str | Path = DEFAULT_GENERATED_ROOT,
    output_root: str | Path = DEFAULT_VALIDATOR_ROOT,
    clean: bool = True,
    fixed_call_family_id: str = "syn_f08_count_status",
    fixed_call_index: int = 0,
) -> dict[str, Any]:
    """Generate all validator trajectories, links, proofs, and denominator rows."""

    generated_root = Path(generated_root).resolve()
    output_root = Path(output_root).resolve()
    if clean and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    corpus = load_generated(generated_root)
    backend_snapshot = deepcopy(corpus.manifest.document)
    write_json(output_root / "backend_manifest.snapshot.json", backend_snapshot)
    backend_manifest_hash = sha256_json(backend_snapshot)

    identities = [
        _identity_document("synthetic_validator_a", order=1),
        _identity_document("synthetic_validator_b", order=2),
    ]
    for identity in identities:
        require_valid("identity", identity)
        write_json(
            output_root / "identities" / f"{identity['validator_id']}.json",
            identity,
        )

    all_links: list[dict[str, Any]] = []
    all_ses: list[dict[str, Any]] = []
    all_minimality: list[dict[str, Any]] = []
    all_blocked: list[dict[str, Any]] = []
    all_restored: list[dict[str, Any]] = []
    all_feasibility: list[dict[str, Any]] = []
    family_entries: list[dict[str, Any]] = []
    for original in sorted(corpus.families, key=lambda item: item["family_id"]):
        family = deepcopy(original)
        family_id = family["family_id"]
        family_dir = output_root / "families" / family_id
        family_path = write_json(family_dir / "family.snapshot.json", family)
        family_hash = sha256_json(family)
        source_manifest = load_json(_source_manifest_path(generated_root, family))
        source_manifest_hash = sha256_json(source_manifest)
        write_json(family_dir / "source_manifest.snapshot.json", source_manifest)
        trajectories: dict[tuple[str, str], dict[str, Any]] = {}
        links = []
        for identity in identities:
            validator_id = identity["validator_id"]
            for state_role in ("CLEAN", "BLOCKED", "RESTORED"):
                trajectory = generate_validator_trajectory(
                    corpus,
                    family,
                    state_role,
                    validator_id,
                )
                trajectory_path = write_json(
                    family_dir
                    / "trajectories"
                    / f"{validator_id}.{state_role.lower()}.json",
                    trajectory,
                )
                trajectories[(validator_id, state_role)] = trajectory
                restore = next(
                    (
                        item
                        for item in _episode(family, "RESTORED")["interventions"]
                        if item["phase"] == "restoration"
                    ),
                    None,
                )
                link = _link_document(
                    family,
                    state_role,
                    validator_id,
                    trajectory_path,
                    trajectory,
                    root=output_root,
                    family_path=family_path,
                    family_hash=family_hash,
                    manifest_hash=source_manifest_hash,
                    backend_manifest_hash=backend_manifest_hash,
                    index_version=corpus.manifest.index_version,
                    index_hash=corpus.index.index_hash,
                    trigger_type=(
                        restore["restoration"]["trigger_type"]
                        if restore is not None and state_role == "RESTORED"
                        else "none"
                    ),
                )
                require_valid("trajectory_link", link)
                write_json(
                    family_dir
                    / "links"
                    / f"{validator_id}.{state_role.lower()}.json",
                    link,
                )
                links.append(link)
                all_links.append(link)

        ses_docs = _ses_demonstrations(family, trajectories)
        minimality_docs = _minimality_documents(family)
        blocked_doc = _blocked_proof(family, trajectories)
        restored_doc = _restored_proof(family, trajectories)
        feasibility_docs = _feasible_route_records(family, trajectories)
        for document in ses_docs:
            require_valid("ses_demonstration", document)
            write_json(
                family_dir / "proofs" / f"{document['demonstration_id']}.json",
                document,
            )
        for document in minimality_docs:
            require_valid("minimality_result", document)
            write_json(
                family_dir / "proofs" / f"{document['minimality_result_id']}.json",
                document,
            )
        require_valid("blocked_proof", blocked_doc)
        require_valid("restored_proof", restored_doc)
        write_json(family_dir / "proofs" / "blocked.json", blocked_doc)
        write_json(family_dir / "proofs" / "restored.json", restored_doc)
        for document in feasibility_docs:
            require_valid("feasible_route", document)
        write_json(family_dir / "feasible_routes.json", feasibility_docs)
        all_ses.extend(ses_docs)
        all_minimality.extend(minimality_docs)
        all_blocked.append(blocked_doc)
        all_restored.append(restored_doc)
        all_feasibility.extend(feasibility_docs)
        family_entries.append(
            {
                "family_id": family_id,
                "family_path": relative_path(family_path, output_root),
                "family_hash": family_hash,
                "source_manifest_path": relative_path(
                    family_dir / "source_manifest.snapshot.json", output_root
                ),
                "source_manifest_hash": source_manifest_hash,
                "link_ids": sorted(item["link_id"] for item in links),
                "ses_demonstration_ids": sorted(
                    item["demonstration_id"] for item in ses_docs
                ),
                "minimality_result_ids": sorted(
                    item["minimality_result_id"] for item in minimality_docs
                ),
                "blocked_proof_id": blocked_doc["blocked_proof_id"],
                "restored_proof_id": restored_doc["restored_proof_id"],
                "feasible_route_record_ids": sorted(
                    item["record_id"] for item in feasibility_docs
                ),
            }
        )

    fixed_source = next(
        deepcopy(item)
        for item in corpus.families
        if item["family_id"] == fixed_call_family_id
    )
    fixed_restore = next(
        item
        for item in fixed_source["episodes"][2]["interventions"]
        if item["phase"] == "restoration"
    )
    fixed_restore["restoration"]["trigger_type"] = "fixed_call_index"
    fixed_restore["restoration"]["trigger_value"] = fixed_call_index
    fixed_case_dir = output_root / "cases" / "fixed_call"
    fixed_family_path = write_json(fixed_case_dir / "family.snapshot.json", fixed_source)
    fixed_trajectories = []
    for identity in identities:
        trajectory = generate_validator_trajectory(
            corpus,
            fixed_source,
            "RESTORED",
            identity["validator_id"],
        )
        path = write_json(
            fixed_case_dir / f"{identity['validator_id']}.restored.json",
            trajectory,
        )
        fixed_trajectories.append(
            {
                "validator_id": identity["validator_id"],
                "trajectory_path": relative_path(path, output_root),
                "trajectory_hash": trajectory["replay"]["trajectory_hash"],
                "trigger_event_index": next(
                    index
                    for index, event in enumerate(trajectory["events"])
                    if fixed_restore["intervention_id"] in event.get("active_hook_ids", ())
                ),
            }
        )
    validator_cases = [
        {
            "case_id": "fixed-call-restoration",
            "family_id": fixed_call_family_id,
            "family_path": relative_path(fixed_family_path, output_root),
            "family_hash": sha256_json(fixed_source),
            "trigger_type": "fixed_call_index",
            "trigger_value": fixed_call_index,
            "trajectories": fixed_trajectories,
        },
        {
            "case_id": "status-trigger-restoration",
            "family_id": next(
                item["family_id"]
                for item in family_entries
                if item["family_id"] != fixed_call_family_id
            ),
            "trigger_type": "get_channel_status",
            "trigger_value": None,
        },
    ]

    denominator = {
        "schema_version": VALIDATOR_SCHEMA_VERSION,
        "artifact_id": "premature-stop-denominator.synthetic-full.v1",
        "dataset_id": "synthetic-full",
        "generated_at": FIXED_CREATED_AT,
        "generator_version": GENERATOR_VERSION,
        "system_independent": True,
        "provenance": {
            "backend_manifest_hash": backend_manifest_hash,
            "index_hash": corpus.index.index_hash,
            "family_hashes": {
                item["family_id"]: item["family_hash"] for item in family_entries
            },
            "validator_ids": [item["validator_id"] for item in identities],
        },
        "records": all_feasibility,
    }
    require_valid("denominator", denominator)
    denominator_path = write_json(output_root / "premature_stop_denominator.json", denominator)

    artifact_index = {
        "schema_version": VALIDATOR_SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "created_at": FIXED_CREATED_AT,
        "source_generated_root": relative_path(generated_root, PACKAGE_ROOT),
        "backend_manifest_hash": backend_manifest_hash,
        "index_hash": corpus.index.index_hash,
        "validator_ids": [item["validator_id"] for item in identities],
        "fixed_call_family_id": fixed_call_family_id,
        "validator_cases": validator_cases,
        "families": family_entries,
        "counts": {
            "families": len(family_entries),
            "validators": len(identities),
            "trajectories": len(all_links),
            "ses_demonstrations": len(all_ses),
            "minimality_results": len(all_minimality),
            "blocked_proofs": len(all_blocked),
            "restored_proofs": len(all_restored),
            "feasible_route_records": len(all_feasibility),
        },
        "denominator_path": relative_path(denominator_path, output_root),
        "denominator_hash": sha256_json(denominator),
    }
    write_json(output_root / "artifact_index.json", artifact_index)
    return artifact_index
