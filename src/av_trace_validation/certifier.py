"""Fail-closed certification of generated validator proof bundles."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from av_trace.schemas import SchemaRegistry
from av_trace.semantic import validate_family
from av_trace.trajectory import validate_trajectory
from av_trace.util import load_json, sha256_json, trajectory_content_hash
from av_trace_mvp.backend import AVAILABLE_TOOLS

from .graph import minimality_cases, reachable_ses_ids, ses_satisfied
from .io import DEFAULT_VALIDATOR_ROOT, write_json
from .schemas import require_valid
from .trajectory import evidence_ids_from_trajectory


CERTIFIER_VERSION = "av-trace-validator-certifier-1.0.0"
FIXED_CREATED_AT = "2026-09-06T00:00:00Z"


class CertificationError(ValueError):
    """Raised when strict certification encounters any missing or invalid proof."""

    def __init__(self, certificate: Mapping[str, Any]) -> None:
        issues = certificate.get("issues", ())
        detail = issues[0]["message"] if issues else "unknown certification failure"
        super().__init__(detail)
        self.certificate = dict(certificate)


def _issue(
    issues: list[dict[str, Any]],
    code: str,
    message: str,
    *,
    family_id: str | None = None,
    path: str = "",
) -> None:
    issues.append(
        {
            "code": code,
            "family_id": family_id,
            "path": path,
            "message": message,
        }
    )


def _load_required(
    root: Path,
    relative: str,
    issues: list[dict[str, Any]],
    *,
    family_id: str | None = None,
) -> Any | None:
    path = root / relative
    if not path.is_file():
        _issue(
            issues,
            "CERT-MISSING",
            f"Required validator artifact is missing: {relative}.",
            family_id=family_id,
            path=relative,
        )
        return None
    try:
        return load_json(path)
    except Exception as exc:
        _issue(
            issues,
            "CERT-JSON",
            f"Could not parse {relative}: {exc}",
            family_id=family_id,
            path=relative,
        )
        return None


def _cert_hash(document: Mapping[str, Any]) -> str:
    value = deepcopy(dict(document))
    value.pop("certificate_hash", None)
    return sha256_json(value)


def _intervention_manifest_hash(
    family: Mapping[str, Any],
    state_role: str,
) -> str:
    episode = next(
        item for item in family["episodes"] if item["state_role"] == state_role
    )
    return sha256_json(
        {
            "family_id": family["family_id"],
            "mechanism": family["intervention_mechanism"],
            "state_role": state_role,
            "initial_state": episode["initial_state"],
            "interventions": episode["interventions"],
        }
    )


def _prior_cost(trajectory: Mapping[str, Any], decision_index: int) -> float:
    values = [
        float(event["response"]["cost_used_total"])
        for event in trajectory["events"][:decision_index]
        if event.get("response") is not None
    ]
    return values[-1] if values else 0.0


def _trajectory_binds_episode_and_backend(
    trajectory: Mapping[str, Any],
    family: Mapping[str, Any],
    state_role: str,
    backend: Mapping[str, Any],
    backend_hash: str,
) -> bool:
    episode = next(
        item for item in family["episodes"] if item["state_role"] == state_role
    )
    start = trajectory["episode_start"]
    return (
        start["protocol_version"] == "0.2.0"
        and start["family_id"] == family["family_id"]
        and start["state_role"] == state_role
        and start["episode_id"] == episode["episode_id"]
        and start["question"] == family["question"]["text"]
        and start["video_duration_s"] == family["source"]["duration_s"]
        and start["available_tools"] == list(AVAILABLE_TOOLS)
        and start["budget"]
        == {
            "cost_limit": episode["budget"]["cost_limit"],
            "max_steps": episode["budget"]["max_steps"],
        }
        and start["tool_costs"] == episode["budget"]["tool_costs"]
        and start["tool_costs"] == backend["tool_costs"]
        and trajectory["replay"]["backend_version"] == backend["backend_version"]
        and trajectory["replay"]["backend_hash"] == backend_hash
        and trajectory["replay"]["intervention_manifest_hash"]
        == _intervention_manifest_hash(family, state_role)
    )


def _route_claims_recomputed(
    route: Mapping[str, Any],
    *,
    family: Mapping[str, Any],
    episode: Mapping[str, Any],
    observed_evidence_ids: set[str],
) -> bool:
    graph = family["claim_evidence_graph"]
    evidence = {
        item["evidence_id"]: item for item in graph["evidence_units"]
    }
    sufficient_sets = {
        item["set_id"]: item for item in graph["accepted_sufficient_sets"]
    }
    ses = sufficient_sets.get(route["set_id"])
    if ses is None:
        return False
    expected_route_id = f"route.{family['family_id']}.{ses['set_id']}"
    missing = set(ses["evidence_ids"]) - observed_evidence_ids
    if (
        route["route_id"] != expected_route_id
        or set(route["missing_evidence_ids"]) != missing
    ):
        return False

    schedule = episode["budget"]["tool_costs"]
    covered: set[str] = set()
    for step in route["steps"]:
        tool = step["tool"]
        if tool not in schedule or abs(float(step["cost"]) - float(schedule[tool])) > 1e-9:
            return False
        expected_ids = set(step["expected_evidence_ids"])
        if not expected_ids <= set(evidence):
            return False
        if tool in {"inspect_clip", "read_transcript"}:
            arguments = step["arguments"]
            interval = arguments.get("interval")
            if not isinstance(interval, dict):
                return False
            for evidence_id in expected_ids:
                item = evidence[evidence_id]
                if interval not in item["intervals"]:
                    return False
                if tool == "read_transcript" and item["modality"] != "speech":
                    return False
                if tool == "inspect_clip":
                    if item["modality"] == "vision" and not arguments.get("include_video"):
                        return False
                    if item["modality"] in {"speech", "ambient"} and not arguments.get(
                        "include_audio"
                    ):
                        return False
            covered.update(expected_ids)
        elif expected_ids:
            return False
    if route["feasible"]:
        return (
            bool(missing)
            and bool(route["steps"])
            and route["steps"][-1]["tool"] == "finalize"
            and missing <= covered
        )
    return True


def certify_dataset(
    *,
    validator_root: str | Path = DEFAULT_VALIDATOR_ROOT,
    certificate_path: str | Path | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    """Validate every linkage and proof, emitting PASS only with zero issues."""

    root = Path(validator_root).resolve()
    issues: list[dict[str, Any]] = []
    family_results: list[dict[str, Any]] = []
    index = _load_required(root, "artifact_index.json", issues)
    backend = _load_required(root, "backend_manifest.snapshot.json", issues)
    denominator = _load_required(root, "premature_stop_denominator.json", issues)
    if not isinstance(index, dict) or not isinstance(backend, dict):
        certificate = _final_certificate(index, backend, family_results, issues)
        if certificate_path:
            write_json(certificate_path, certificate)
        if strict:
            raise CertificationError(certificate)
        return certificate

    backend_hash = sha256_json(backend)
    if index.get("backend_manifest_hash") != backend_hash:
        _issue(issues, "CERT-BACKEND-HASH", "Backend manifest snapshot hash mismatch.")
    if index.get("index_hash") != backend.get("index_hash"):
        _issue(issues, "CERT-INDEX-HASH", "Artifact index is not bound to backend index_hash.")

    identities: dict[str, dict[str, Any]] = {}
    for validator_id in index.get("validator_ids", ()):
        relative = f"identities/{validator_id}.json"
        identity = _load_required(root, relative, issues)
        if not isinstance(identity, dict):
            continue
        try:
            require_valid("identity", identity)
        except Exception as exc:
            _issue(issues, "CERT-IDENTITY-SCHEMA", str(exc), path=relative)
            continue
        identities[validator_id] = identity
    if len(identities) < 2:
        _issue(issues, "CERT-INDEPENDENCE", "At least two valid validator identities are required.")

    all_links: dict[str, dict[str, Any]] = {}
    all_trajectories: dict[str, dict[str, Any]] = {}
    certified_route_records: dict[str, dict[str, Any]] = {}
    registry = SchemaRegistry()
    for entry in index.get("families", ()):
        family_id = entry.get("family_id")
        family_issues_before = len(issues)
        rules = {
            "role_independence": False,
            "trajectory_linkage": False,
            "ses_satisfiability": False,
            "ses_minimality": False,
            "blocked_insufficiency": False,
            "restoration_exactness": False,
            "feasible_routes": False,
        }
        family = _load_required(root, entry.get("family_path", ""), issues, family_id=family_id)
        if not isinstance(family, dict):
            family_results.append({"family_id": family_id or "unknown", "status": "FAIL", "rule_results": rules})
            continue
        if sha256_json(family) != entry.get("family_hash"):
            _issue(issues, "CERT-FAMILY-HASH", "Family snapshot hash mismatch.", family_id=family_id)
        source_manifest = _load_required(
            root,
            entry.get("source_manifest_path", ""),
            issues,
            family_id=family_id,
        )
        if (
            not isinstance(source_manifest, dict)
            or sha256_json(source_manifest) != entry.get("source_manifest_hash")
        ):
            _issue(
                issues,
                "CERT-SOURCE-MANIFEST-HASH",
                "Source manifest snapshot hash mismatch.",
                family_id=family_id,
            )
        semantic = validate_family(
            family,
            source_manifest if isinstance(source_manifest, dict) else None,
            registry,
        )
        semantic_errors = list(semantic.issues)
        if semantic_errors:
            _issue(
                issues,
                "CERT-FAMILY-SEMANTIC",
                f"{semantic_errors[0].code}: {semantic_errors[0].message}",
                family_id=family_id,
            )
        authors = set(family["annotation"]["authors"])
        validators = set(family["annotation"]["validators"])
        roles_ok = (
            len(validators) >= 2
            and validators <= set(identities)
            and not authors.intersection(validators)
            and family["annotation"]["adjudicator"] not in validators
            and family["annotation"]["alternative_evidence_finder"] not in validators
            and len({identities[item]["independence_group"] for item in validators}) == len(validators)
            and all(identities[item]["role"] == "validator" for item in validators)
            and all(
                validators - {item}
                <= set(
                    identities[item]["conflict_attestation"][
                        "independent_of_validator_ids"
                    ]
                )
                for item in validators
            )
        )
        if not roles_ok:
            _issue(issues, "CERT-INDEPENDENCE", "Validator role independence failed.", family_id=family_id)
        rules["role_independence"] = roles_ok

        family_links = []
        for validator_id in sorted(validators):
            for state in ("clean", "blocked", "restored"):
                relative = f"families/{family_id}/links/{validator_id}.{state}.json"
                link = _load_required(root, relative, issues, family_id=family_id)
                if not isinstance(link, dict):
                    continue
                try:
                    require_valid("trajectory_link", link)
                except Exception as exc:
                    _issue(issues, "CERT-LINK-SCHEMA", str(exc), family_id=family_id, path=relative)
                    continue
                trajectory = _load_required(root, link["trajectory_path"], issues, family_id=family_id)
                if not isinstance(trajectory, dict):
                    continue
                report = validate_trajectory(trajectory, registry)
                link_ok = (
                    report.ok
                    and trajectory_content_hash(trajectory) == link["trajectory_hash"]
                    and trajectory["replay"]["trajectory_hash"] == link["trajectory_hash"]
                    and link["family_hash"] == entry["family_hash"]
                    and link["backend_manifest_hash"] == backend_hash
                    and link["index_hash"] == backend["index_hash"]
                    and link["family_annotation_version"] == family["annotation"]["version"]
                    and link["source_manifest_hash"] == entry["source_manifest_hash"]
                    and link["intervention_manifest_hash"]
                    == _intervention_manifest_hash(family, link["state_role"])
                    and trajectory["episode_start"]["family_id"] == family_id
                    and trajectory["episode_start"]["state_role"] == link["state_role"]
                    and trajectory["episode_start"]["episode_id"] == link["episode_id"]
                    and _trajectory_binds_episode_and_backend(
                        trajectory,
                        family,
                        link["state_role"],
                        backend,
                        backend_hash,
                    )
                )
                if not link_ok:
                    _issue(issues, "CERT-LINK", "Trajectory linkage or normative validation failed.", family_id=family_id, path=relative)
                    continue
                family_links.append(link)
                all_links[link["link_id"]] = link
                all_trajectories[link["trajectory_id"]] = trajectory
        expected_pairs = {
            (validator_id, state)
            for validator_id in validators
            for state in ("CLEAN", "BLOCKED", "RESTORED")
        }
        actual_pairs = {(item["validator_id"], item["state_role"]) for item in family_links}
        plans = {item["validator_id"]: item["search_plan_id"] for item in family_links if item["state_role"] == "CLEAN"}
        links_ok = expected_pairs == actual_pairs and len(set(plans.values())) == len(validators)
        if not links_ok:
            _issue(issues, "CERT-LINK-COVERAGE", "Expected two independent plans across all three states.", family_id=family_id)
        rules["trajectory_linkage"] = links_ok

        graph = family["claim_evidence_graph"]
        ses_ok = True
        minimality_ok = True
        for ses in graph["accepted_sufficient_sets"]:
            ses_path = f"families/{family_id}/proofs/ses-demo.{family_id}.{ses['set_id']}.json"
            demo = _load_required(root, ses_path, issues, family_id=family_id)
            if not isinstance(demo, dict):
                ses_ok = False
            else:
                try:
                    require_valid("ses_demonstration", demo)
                except Exception as exc:
                    _issue(issues, "CERT-SES-SCHEMA", str(exc), family_id=family_id, path=ses_path)
                    ses_ok = False
                demonstrated = {item["validator_id"] for item in demo.get("validator_demonstrations", ())}
                if (
                    demo.get("evidence_ids") != ses["evidence_ids"]
                    or demo.get("hop_ids") != ses["hop_ids"]
                    or demonstrated != validators
                    or not ses_satisfied(graph, ses, ses["evidence_ids"])
                ):
                    _issue(issues, "CERT-SES", f"SES {ses['set_id']} demonstration failed.", family_id=family_id)
                    ses_ok = False
                for item in demo.get("validator_demonstrations", ()):
                    for trajectory_key in ("clean_trajectory_id", "restored_trajectory_id"):
                        trajectory = all_trajectories.get(item.get(trajectory_key))
                        if trajectory is None or not set(ses["evidence_ids"]) <= evidence_ids_from_trajectory(family, trajectory):
                            _issue(issues, "CERT-SES-TRAJECTORY", f"{trajectory_key} does not acquire {ses['set_id']}.", family_id=family_id)
                            ses_ok = False
            min_path = f"families/{family_id}/proofs/minimality.{family_id}.{ses['set_id']}.json"
            minimality = _load_required(root, min_path, issues, family_id=family_id)
            if not isinstance(minimality, dict):
                minimality_ok = False
            else:
                try:
                    require_valid("minimality_result", minimality)
                except Exception as exc:
                    _issue(issues, "CERT-MIN-SCHEMA", str(exc), family_id=family_id, path=min_path)
                    minimality_ok = False
                expected_cases = minimality_cases(graph, ses)
                if minimality.get("leave_one_out_cases") != expected_cases:
                    _issue(issues, "CERT-MINIMALITY", f"Leave-one-out proof mismatch for {ses['set_id']}.", family_id=family_id)
                    minimality_ok = False
        rules["ses_satisfiability"] = ses_ok
        rules["ses_minimality"] = minimality_ok

        blocked_path = f"families/{family_id}/proofs/blocked.json"
        blocked = _load_required(root, blocked_path, issues, family_id=family_id)
        blocked_ok = isinstance(blocked, dict)
        if blocked_ok:
            try:
                require_valid("blocked_proof", blocked)
            except Exception as exc:
                _issue(issues, "CERT-BLOCKED-SCHEMA", str(exc), family_id=family_id, path=blocked_path)
                blocked_ok = False
        if blocked_ok:
            episode = family["episodes"][1]
            blocked_ok = (
                not reachable_ses_ids(graph, episode["initial_state"]["accessible_evidence_ids"])
                and {item["validator_id"] for item in blocked["validator_results"]} == validators
                and all(
                    item["trajectory_id"] in all_trajectories
                    and not reachable_ses_ids(
                        graph,
                        evidence_ids_from_trajectory(
                            family, all_trajectories[item["trajectory_id"]]
                        ),
                    )
                    for item in blocked["validator_results"]
                )
            )
        if not blocked_ok:
            _issue(issues, "CERT-BLOCKED", "BLOCKED insufficiency proof failed.", family_id=family_id)
        rules["blocked_insufficiency"] = blocked_ok

        restored_path = f"families/{family_id}/proofs/restored.json"
        restored = _load_required(root, restored_path, issues, family_id=family_id)
        restored_ok = isinstance(restored, dict)
        if restored_ok:
            try:
                require_valid("restored_proof", restored)
            except Exception as exc:
                _issue(issues, "CERT-RESTORED-SCHEMA", str(exc), family_id=family_id, path=restored_path)
                restored_ok = False
        if restored_ok:
            clean_episode, blocked_episode, restored_episode = family["episodes"]
            block = blocked_episode["interventions"][0]
            restore = restored_episode["interventions"][1]
            restored_ok = (
                restored["pretrigger_state_equal"]
                and restored["exact_inverse"]
                and {item["validator_id"] for item in restored["validator_results"]} == validators
                and all(item["supported_final_answer"] for item in restored["validator_results"])
                and blocked_episode["initial_state"]
                == restored_episode["initial_state"]
                and restored_episode["interventions"][0]
                == blocked_episode["interventions"][0]
                and restore["restoration"]["restores_intervention_id"]
                == block["intervention_id"]
                and all(
                    restore[field] == block[field]
                    for field in (
                        "mechanism",
                        "affected_necessity_group_id",
                        "affected_evidence_ids",
                        "affected_channel",
                    )
                )
                and set(blocked_episode["initial_state"]["accessible_evidence_ids"])
                == set(clean_episode["initial_state"]["accessible_evidence_ids"])
                - set(block["affected_evidence_ids"])
                and bool(
                    reachable_ses_ids(
                        graph,
                        set(restored_episode["initial_state"]["accessible_evidence_ids"])
                        | set(restore["affected_evidence_ids"]),
                    )
                )
            )
        if not restored_ok:
            _issue(issues, "CERT-RESTORED", "RESTORED recovery proof failed.", family_id=family_id)
        rules["restoration_exactness"] = restored_ok

        route_path = f"families/{family_id}/feasible_routes.json"
        route_records = _load_required(root, route_path, issues, family_id=family_id)
        routes_ok = isinstance(route_records, list) and bool(route_records)
        if routes_ok:
            route_keys: set[tuple[str, str, int]] = set()
            for record in route_records:
                try:
                    require_valid("feasible_route", record)
                except Exception as exc:
                    _issue(issues, "CERT-ROUTE-SCHEMA", str(exc), family_id=family_id, path=route_path)
                    routes_ok = False
                    break
                link = next(
                    (
                        item
                        for item in family_links
                        if item["validator_id"] == record["validator_id"]
                        and item["state_role"] == record["state_role"]
                    ),
                    None,
                )
                trajectory = (
                    all_trajectories.get(link["trajectory_id"])
                    if link is not None
                    else None
                )
                feasible_ids = sorted(
                    item["route_id"]
                    for item in record["route_alternatives"]
                    if item["feasible"]
                )
                decision_index = record["decision_index"]
                episode = next(
                    item
                    for item in family["episodes"]
                    if item["state_role"] == record["state_role"]
                )
                expected_observed = (
                    evidence_ids_from_trajectory(
                        family,
                        {"events": trajectory["events"][:decision_index]},
                    )
                    if trajectory is not None
                    and decision_index < len(trajectory["events"])
                    else None
                )
                key = (
                    record["validator_id"],
                    record["state_role"],
                    decision_index,
                )
                if (
                    key in route_keys
                    or trajectory is None
                    or decision_index >= len(trajectory["events"])
                    or record["source_trajectory_id"] != trajectory["trajectory_id"]
                    or record["source_trajectory_hash"]
                    != trajectory["replay"]["trajectory_hash"]
                    or record["remaining_steps"]
                    != episode["budget"]["max_steps"] - decision_index
                    or abs(
                        record["remaining_cost"]
                        - (
                            episode["budget"]["cost_limit"]
                            - _prior_cost(trajectory, decision_index)
                        )
                    )
                    > 1e-9
                    or set(record["observed_evidence_ids"])
                    != expected_observed
                    or
                    record["feasible_route_ids"] != feasible_ids
                    or record["eligible"] != bool(feasible_ids)
                    or any(
                        item["required_steps"] != len(item["steps"])
                        or abs(
                            item["required_cost"]
                            - sum(float(step["cost"]) for step in item["steps"])
                        )
                        > 1e-9
                        or not _route_claims_recomputed(
                            item,
                            family=family,
                            episode=episode,
                            observed_evidence_ids=set(expected_observed or ()),
                        )
                        for item in record["route_alternatives"]
                    )
                ):
                    routes_ok = False
                    _issue(issues, "CERT-ROUTE", "Feasible-route arithmetic failed.", family_id=family_id)
                    break
                route_keys.add(key)
                certified_route_records[record["record_id"]] = record
            expected_route_keys = {
                (link["validator_id"], link["state_role"], decision_index)
                for link in family_links
                for decision_index in range(
                    len(all_trajectories[link["trajectory_id"]]["events"])
                )
            }
            if routes_ok and route_keys != expected_route_keys:
                routes_ok = False
                _issue(
                    issues,
                    "CERT-ROUTE-COVERAGE",
                    "A route-feasibility record is required at every validator decision point.",
                    family_id=family_id,
                )
        if not routes_ok:
            _issue(issues, "CERT-ROUTE", "Final-decision feasible-route records failed.", family_id=family_id)
        rules["feasible_routes"] = routes_ok
        family_results.append(
            {
                "family_id": family_id,
                "status": "PASS" if len(issues) == family_issues_before else "FAIL",
                "rule_results": rules,
            }
        )

    if isinstance(denominator, dict):
        try:
            require_valid("denominator", denominator)
        except Exception as exc:
            _issue(issues, "CERT-DENOMINATOR-SCHEMA", str(exc))
        if denominator.get("system_independent") is not True:
            _issue(issues, "CERT-DENOMINATOR", "Denominator must declare system_independent=true.")
        if sha256_json(denominator) != index.get("denominator_hash"):
            _issue(
                issues,
                "CERT-DENOMINATOR-HASH",
                "Artifact index denominator hash does not match the denominator document.",
            )
        provenance = denominator.get("provenance", {})
        if (
            provenance.get("backend_manifest_hash") != backend_hash
            or provenance.get("index_hash") != backend.get("index_hash")
            or set(provenance.get("validator_ids", ())) != set(identities)
            or provenance.get("family_hashes")
            != {
                item["family_id"]: item["family_hash"]
                for item in index.get("families", ())
            }
        ):
            _issue(
                issues,
                "CERT-DENOMINATOR-PROVENANCE",
                "Denominator provenance is not bound to the certified dataset.",
            )
        denominator_records: dict[str, dict[str, Any]] = {}
        for record in denominator.get("records", ()):
            try:
                require_valid("feasible_route", record)
            except Exception as exc:
                _issue(issues, "CERT-DENOMINATOR-RECORD", str(exc), family_id=record.get("family_id"))
                break
            if record["record_id"] in denominator_records:
                _issue(
                    issues,
                    "CERT-DENOMINATOR-DUPLICATE",
                    f"Duplicate denominator record {record['record_id']}.",
                    family_id=record.get("family_id"),
                )
                break
            denominator_records[record["record_id"]] = record
        if denominator_records != certified_route_records:
            _issue(
                issues,
                "CERT-DENOMINATOR-COVERAGE",
                "Denominator records must exactly equal certified family route records.",
            )
    else:
        _issue(issues, "CERT-DENOMINATOR", "Premature-stop denominator is missing.")

    for case in index.get("validator_cases", ()):
        if case.get("case_id") != "fixed-call-restoration":
            continue
        case_family = _load_required(root, case["family_path"], issues)
        if not isinstance(case_family, dict) or sha256_json(case_family) != case["family_hash"]:
            _issue(issues, "CERT-FIXED-CALL", "Fixed-call family snapshot is invalid.")
            continue
        for linked in case.get("trajectories", ()):
            trajectory = _load_required(root, linked["trajectory_path"], issues)
            if not isinstance(trajectory, dict):
                continue
            report = validate_trajectory(trajectory, registry)
            restore = next(
                item
                for item in case_family["episodes"][2]["interventions"]
                if item["phase"] == "restoration"
            )
            observed = evidence_ids_from_trajectory(case_family, trajectory)
            if (
                not report.ok
                or trajectory["replay"]["trajectory_hash"] != linked["trajectory_hash"]
                or linked["trigger_event_index"] != case["trigger_value"]
                or trajectory["events"][linked["trigger_event_index"]].get(
                    "active_hook_ids"
                )
                != [restore["intervention_id"]]
                or not reachable_ses_ids(
                    case_family["claim_evidence_graph"], observed
                )
                or trajectory["final_output"]["verdict"] != "sufficient"
            ):
                _issue(issues, "CERT-FIXED-CALL", "Fixed-call validator trajectory failed.")

    certificate = _final_certificate(index, backend, family_results, issues)
    try:
        require_valid("dataset_certificate", certificate)
    except Exception as exc:
        _issue(issues, "CERT-CERTIFICATE-SCHEMA", str(exc))
        certificate = _final_certificate(index, backend, family_results, issues)
    if certificate_path:
        write_json(certificate_path, certificate)
    if strict and certificate["status"] != "PASS":
        raise CertificationError(certificate)
    return certificate


def _final_certificate(
    index: Mapping[str, Any] | None,
    backend: Mapping[str, Any] | None,
    families: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    document = {
        "schema_version": "1.0.0",
        "certificate_id": "certificate.synthetic-full.validator-v1",
        "created_at": FIXED_CREATED_AT,
        "status": "PASS" if not issues else "FAIL",
        "validator_version": CERTIFIER_VERSION,
        "artifact_index_hash": sha256_json(index) if isinstance(index, dict) else "sha256:" + "0" * 64,
        "backend_manifest_hash": sha256_json(backend) if isinstance(backend, dict) else "sha256:" + "0" * 64,
        "index_hash": backend.get("index_hash", "sha256:" + "0" * 64) if isinstance(backend, dict) else "sha256:" + "0" * 64,
        "counts": {
            "families": len(families),
            "families_passed": sum(item["status"] == "PASS" for item in families),
            "issues": len(issues),
        },
        "families": families,
        "issues": issues,
        "certificate_hash": "sha256:" + "0" * 64,
    }
    document["certificate_hash"] = _cert_hash(document)
    return document
