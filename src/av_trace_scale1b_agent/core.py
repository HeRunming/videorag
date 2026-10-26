"""Build, execute, and verify the Scale-1B learned G/A pilot."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import stat
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

from .backend import FullTimelineBackend, LearnedFeatureModels
from .checkpoint import read_checkpoint, semantic_hash, write_checkpoint
from .controller import (
    LearnedCallFailure,
    prompt_hashes,
    run_grounded_generator,
    run_learned_agent,
)
from .evaluation import mean_or_none, route_feasibility_certificate, score_final
from .gates import verify_prerequisite_gates
from .process import ProcessConfig, QwenProcess
from .schema import PublicSchemaError, validate_finalization

SCHEMA = "av-trace.scale1b.ga-pilot/1.0"
STAGE = "MACHINE_ADJUDICATED_PROVISIONAL"
WARNING = "LOW_N_MACHINE_PROVISIONAL_GA_PILOT"
RESTRICTED = Path("data/restricted/scale1b/ga_pilot")
RESULTS = Path("mvp/results/scale1b_ga_pilot")
CONTRACT = Path("data/restricted/scale1b/ga_pilot/experiment_contract.json")
FAMILIES = Path("data/restricted/noaa01/scale1a/migrated_families.json")
INTERVENTIONS = Path("data/restricted/noaa01/scale1a/interventions.json")


class GAPilotError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _family_handle(family_id: str) -> str:
    return "fam." + hashlib.sha256(
        f"ga-public-family-v1:{family_id}".encode()
    ).hexdigest()[:20]


def _write(path: Path, value: Any, *, restricted: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if restricted:
        os.chmod(path.parent, 0o700)
    payload = json.dumps(
        value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
    ).encode() + b"\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600 if restricted else 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.chmod(path, 0o644)


def _inputs(root: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    family_doc = _load(root / FAMILIES)
    intervention_doc = _load(root / INTERVENTIONS)
    families = [
        row
        for row in family_doc["families"]
        if row["migration_disposition"] == "retained"
    ]
    interventions = {
        row["family_id"]: row
        for row in intervention_doc["families"]
        if row.get("retained")
    }
    if {row["family_id"] for row in families} != set(interventions):
        raise GAPilotError("FAMILY_INTERVENTION_MISMATCH")
    return families, interventions


def _experiment_matrix(families: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for family in families:
        family_id = family["family_id"]
        # Matched end-to-end core.
        for retrieval in ("F-CTRL", "F-VA"):
            for state in ("CLEAN", "BLOCKED", "RESTORED"):
                rows.extend(
                    {
                        "case_id": semantic_hash(
                            [family_id, system, retrieval, state, "ordinary"]
                        )[7:31],
                        "family_id": family_id,
                        "system": system,
                        "retrieval_variant": retrieval,
                        "state": state,
                        "condition": "ordinary",
                        "restoration_enabled": True,
                    }
                    for system in (
                        "deterministic_react_control",
                        "deterministic_evidence_sufficiency_control",
                        "single_shot_learned_generator",
                        "learned_react",
                        "learned_evidence_sufficiency",
                    )
                )
        # Matched RESTORED no-trigger controls for learned agents.
        for retrieval in ("F-CTRL", "F-VA"):
            for system in ("learned_react", "learned_evidence_sufficiency"):
                rows.append(
                    {
                        "case_id": semantic_hash(
                            [family_id, system, retrieval, "RESTORED", "no_trigger"]
                        )[7:31],
                        "family_id": family_id,
                        "system": system,
                        "retrieval_variant": retrieval,
                        "state": "RESTORED",
                        "condition": "no_trigger",
                        "restoration_enabled": False,
                    }
                )
        # Generator-only evidence utilization diagnostics.
        for condition in ("provisional_evidence", "partial_evidence"):
            rows.append(
                {
                    "case_id": semantic_hash(
                        [family_id, "learned_generator", condition]
                    )[7:31],
                    "family_id": family_id,
                    "system": "learned_generator_diagnostic",
                    "retrieval_variant": "PROVISIONAL_EVIDENCE",
                    "state": "CLEAN",
                    "condition": condition,
                    "restoration_enabled": True,
                }
            )
    # Failure handling probes are real model calls but not benchmark metrics.
    first = families[0]["family_id"]
    for injection in ("timeout", "malformed", "oom", "over_budget", "process_crash"):
        rows.append(
            {
                "case_id": semantic_hash([first, "fault", injection])[7:31],
                "family_id": first,
                "system": "learned_react",
                "retrieval_variant": "F-CTRL",
                "state": "CLEAN",
                "condition": f"fault_{injection}",
                "restoration_enabled": True,
            }
        )
    return rows


def freeze_ga_contract(repo_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repo_root).resolve()
    ledger = _load(root / "data/rehearsal_plan/cvpr_claim_evidence_ledger.json")
    construct = _load(
        root / "data/rehearsal_plan/construct_validity_mini_pilot_plan.json"
    )
    wave = _load(
        root / "data/restricted/scale1b/wave_r/final_post_repair_audit.json"
    )
    scale = _load(root / "data/restricted/noaa01/scale1a/final_audit.json")
    if ledger.get("decision") != "CVPR_THESIS_FROZEN":
        raise GAPilotError("CVPR_THESIS_NOT_FROZEN")
    if construct.get("decision") != "DEFERRED_HUMAN_PROTOCOL_READY":
        raise GAPilotError("CONSTRUCT_VALIDITY_PROTOCOL_NOT_READY")
    if wave.get("decisions", {}).get("retrieval") != "LEARNED_RETRIEVAL_READY":
        raise GAPilotError("LEARNED_RETRIEVAL_NOT_READY")
    if scale.get("decisions", {}).get("engineering") != "SCALE1A_ENGINEERING_GO":
        raise GAPilotError("SCALE1A_ENGINEERING_NOT_READY")
    families, _ = _inputs(root)
    matrix = _experiment_matrix(families)
    contract = {
        "schema_version": SCHEMA,
        "contract_status": "FROZEN_BEFORE_LEARNED_GA_OUTCOMES",
        "stage": STAGE,
        "warning": WARNING,
        "human_reviewed": False,
        "gold_annotation": False,
        "actual_learned_model_required": True,
        "qwen": {
            "repo_id": "Qwen/Qwen2.5-1.5B-Instruct",
            "revision": "989aa7980e4cf806f80c7fef2b1adb7bc71aa306",
        },
        "generation": {
            "do_sample": False,
            "max_new_tokens": 512,
            "repair_attempts": 1,
            "isolated_jsonl_model_subprocess": True,
            "model_process_reused_within_bounded_run": True,
        },
        "readiness_thresholds": {
            "minimum_structured_completion_rate": 0.8,
            "require_each_generator_condition_completed": True,
            "require_each_agent_policy_state_retrieval_completed": True,
            "require_no_trigger_completion": True,
        },
        "retrieval_variants": ["F-CTRL", "F-VA"],
        "states": ["CLEAN", "BLOCKED", "RESTORED"],
        "systems": [
            "deterministic_react_control",
            "deterministic_evidence_sufficiency_control",
            "single_shot_learned_generator",
            "learned_react",
            "learned_evidence_sufficiency",
            "learned_generator_diagnostic",
        ],
        "prompt_hashes": prompt_hashes(),
        "preregistered_inputs": {
            str(path.relative_to(root)): _sha256(path)
            for path in (
                root / "docs/paper/cvpr_thesis_and_evidence_gates.md",
                root / "data/rehearsal_plan/cvpr_claim_evidence_ledger.json",
                root / "data/rehearsal_plan/construct_validity_mini_pilot_plan.json",
                root / "data/restricted/scale1b/wave_r/final_post_repair_audit.json",
                root / "data/restricted/noaa01/scale1a/final_audit.json",
                root / FAMILIES,
                root / INTERVENTIONS,
            )
        },
        "matrix": matrix,
    }
    contract["contract_hash"] = semantic_hash(contract)
    _write(root / CONTRACT, contract, restricted=True)
    return contract


def build_ga_pilot(repo_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repo_root).resolve()
    contract_path = root / CONTRACT
    contract = (
        _load(contract_path) if contract_path.is_file() else freeze_ga_contract(root)
    )
    if contract.get("contract_hash") != semantic_hash(
        {key: value for key, value in contract.items() if key != "contract_hash"}
    ):
        raise GAPilotError("EXPERIMENT_CONTRACT_HASH_MISMATCH")
    gates = verify_prerequisite_gates(root)
    if not gates["ready"]:
        raise GAPilotError("PREREQUISITE_GATES_NOT_READY:" + ",".join(gates["errors"]))
    config = {
        **contract,
        "contract_hash": contract["contract_hash"],
        "qwen": {
            **contract["qwen"],
            "snapshot_path": gates["qwen"]["snapshot_path"],
            "manifest_sha256": gates["qwen"]["manifest_sha256"],
        },
        "gate_inputs": gates["inputs"],
    }
    config["config_hash"] = semantic_hash(config)
    _write(root / RESTRICTED / "experiment_manifest.json", config, restricted=True)
    return config


def _observations_from_fused(backend: FullTimelineBackend, top_k: int = 5) -> list[dict[str, Any]]:
    response = backend.fused_search(top_k)
    observations: list[dict[str, Any]] = []
    seen: set[str] = set()
    per_modality: defaultdict[str, int] = defaultdict(int)
    for result in response.get("results", []):
        for modality, pointer_id in result.get("modality_pointers", {}).items():
            if pointer_id in seen:
                continue
            if per_modality[modality] >= 2:
                continue
            observation_tool = (
                "read_transcript" if modality == "speech" else "inspect_clip"
            )
            if (
                backend.cost_used + backend.costs[observation_tool]
                > backend.budget["cost_limit"] + 1e-9
                or backend.steps_used + 1 >= backend.budget["max_steps"]
            ):
                continue
            seen.add(pointer_id)
            observed = backend.observe(pointer_id)
            if observed.get("status") == "ok":
                observations.append(observed["observation"])
                per_modality[modality] += 1
    return observations


def _infer_public_modalities(question: str) -> list[str]:
    text = question.casefold()
    selected: list[str] = []
    if any(word in text for word in ("speaker", "narration", "stated", "says", "basin")):
        selected.append("speech")
    if any(word in text for word in ("sound", "audio", "heard", "environmental")):
        selected.append("ambient")
    if any(
        word in text
        for word in (
            "visible",
            "shown",
            "view",
            "graphic",
            "carrying",
            "appears",
            "montage",
        )
    ):
        selected.append("vision")
    return selected or ["vision", "speech", "ambient"]


def _deterministic_final(
    backend: FullTimelineBackend,
    observations: Sequence[Mapping[str, Any]],
    *,
    conservative: bool,
) -> dict[str, Any]:
    slots = backend.public_start()["claim_slots"]
    usable = [item for item in observations if item.get("citable")]
    if len(usable) < len(slots):
        return {
            "verdict": "access_failure" if backend.suppressed else "insufficient",
            "answer_text": "",
            "asserted_claims": [],
            "claim_to_citations": {},
            "missing_modalities": _infer_public_modalities(backend.family["question"]),
            "missing_hops": ["other"],
            "missingness_cause": (
                "evidence_in_source_but_inaccessible"
                if backend.suppressed
                else "evidence_accessible_but_not_found"
            ),
            "p_sufficient": 0.05 if conservative else 0.25,
            "recovery_intent": "Continue searching if a legal route remains.",
            "stop_rationale": "Visible evidence does not cover every public claim slot.",
        }
    assertions = []
    for slot, observation in zip(slots, usable):
        assertions.append(
            {
                "claim_handle": slot["claim_handle"],
                "text": str(observation["content"]),
                "citations": [observation["observation_id"]],
            }
        )
    return {
        "verdict": "answer",
        "answer_text": " ".join(row["text"] for row in assertions),
        "asserted_claims": assertions,
        "claim_to_citations": {
            row["claim_handle"]: row["citations"] for row in assertions
        },
        "missing_modalities": [],
        "missing_hops": [],
        "missingness_cause": "not_missing",
        "p_sufficient": 0.9,
        "recovery_intent": "",
        "stop_rationale": "Every public claim slot has one citable observation.",
    }


def _run_deterministic_control(
    backend: FullTimelineBackend, *, sufficiency: bool
) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    for modality in _infer_public_modalities(backend.family["question"]):
        response = backend.search(modality, backend.family["question"], 5)
        pointers = response.get("results", [])
        if pointers:
            observed = backend.observe(pointers[0]["pointer_id"])
            if observed.get("status") == "ok":
                observations.append(observed["observation"])
        if sufficiency and len(observations) < len(backend.public_start()["claim_slots"]):
            backend.status([modality])
            retry = backend.search(
                modality,
                f"{backend.family['question']} additional supporting evidence",
                5,
            )
            if retry.get("results"):
                observed = backend.observe(retry["results"][0]["pointer_id"])
                if observed.get("status") == "ok":
                    observations.append(observed["observation"])
        if backend.steps_used >= backend.budget["max_steps"] - 1:
            break
    return {
        "final": _deterministic_final(
            backend, observations, conservative=sufficiency
        ),
        "public_events": [],
        "model_calls": [],
    }


def _score_case(
    family: Mapping[str, Any],
    backend: FullTimelineBackend,
    final: Mapping[str, Any] | None,
    *,
    state: str,
    process_ok: bool,
) -> dict[str, Any]:
    certificate = route_feasibility_certificate(
        backend, required_modalities=family["provisional_modalities"]
    )
    scored = score_final(
        family=family,
        final=final,
        observations=backend.observation_private,
        evidence_by_observation=backend.evidence_by_observation,
        state=state,
        route_feasibility_certificate=certificate,
        within_budget=(
            process_ok
            and backend.steps_used <= backend.budget["max_steps"]
            and backend.cost_used <= backend.budget["cost_limit"] + 1e-9
        ),
    )
    scored["route_feasibility_certificate"] = certificate
    return scored


def _public_model_calls(
    calls: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    allowed = {
        "attempt",
        "status",
        "request_hash",
        "system_prompt_sha256",
        "prompt_tokens",
        "generated_tokens",
        "latency_seconds",
        "validation_error",
        "error_code",
        "error",
    }
    return [
        {key: value for key, value in call.items() if key in allowed}
        for call in calls
    ]


def _run_case(
    model: QwenProcess,
    *,
    root: Path,
    family: Mapping[str, Any],
    intervention: Mapping[str, Any],
    case: Mapping[str, Any],
    feature_models: LearnedFeatureModels,
) -> dict[str, Any]:
    fault: dict[str, Any] = {}
    if case["condition"] == "fault_timeout":
        fault = {
            "search_visual": "timeout",
            "search_speech": "timeout",
            "search_ambient_audio": "timeout",
        }
    elif case["condition"] == "fault_malformed":
        fault = {
            "search_visual": "malformed",
            "search_speech": "malformed",
            "search_ambient_audio": "malformed",
        }
    elif case["condition"] == "fault_oom":
        fault = {
            "search_visual": "oom",
            "search_speech": "oom",
            "search_ambient_audio": "oom",
        }
    backend = FullTimelineBackend(
        root,
        family=family,
        intervention=intervention,
        retrieval_variant=case["retrieval_variant"],
        state=case["state"],
        restoration_enabled=bool(case["restoration_enabled"]),
        fault_injection=fault,
        feature_models=feature_models,
    )
    deterministic = str(case["system"]).startswith("deterministic_")
    fault_probe = str(case["condition"]).startswith("fault_")
    record: dict[str, Any] = {
        **case,
        "schema_version": SCHEMA,
        "stage": STAGE,
        "warning": WARNING,
        "actual_learned_model": not deterministic and not fault_probe,
        "execution_kind": (
            "fault_injection"
            if fault_probe
            else "deterministic_protocol_control"
            if deterministic
            else "learned_qwen_inference"
        ),
        "human_reviewed": False,
        "gold_annotation": False,
    }
    try:
        if case["condition"] == "fault_process_crash":
            record.update(
                {
                    "status": "typed_failure",
                    "failure": {"code": "PROCESS_CRASH_INJECTION"},
                    "final": None,
                    "model_calls": [],
                    "backend_events": [],
                }
            )
        elif case["condition"] == "fault_over_budget":
            backend.steps_used = backend.budget["max_steps"]
            try:
                backend.search("vision", family["question"], 5)
            except RuntimeError as exc:
                record.update(
                    {
                        "status": "typed_failure",
                        "failure": {"code": str(exc)},
                        "final": None,
                        "model_calls": [],
                        "backend_events": backend.events,
                    }
                )
        elif deterministic:
            outcome = _run_deterministic_control(
                backend,
                sufficiency=case["system"]
                == "deterministic_evidence_sufficiency_control",
            )
            backend.finalize(outcome["final"])
            record.update(
                {
                    "status": "completed",
                    "final": outcome["final"],
                    "model_calls": [],
                    "public_events": outcome["public_events"],
                    "backend_events": backend.events,
                }
            )
        elif case["system"] == "single_shot_learned_generator":
            observations = _observations_from_fused(backend)
            generated = run_grounded_generator(
                model,
                question=family["question"],
                claim_slots=backend.public_start()["claim_slots"],
                observations=observations,
                condition=f"{case['state']}:{case['retrieval_variant']}:single_shot",
            )
            backend.finalize(generated["final"])
            record.update(
                {
                    "status": "completed",
                    "final": generated["final"],
                    "model_calls": generated["model_calls"],
                    "backend_events": backend.events,
                }
            )
        elif case["system"] == "learned_generator_diagnostic":
            observations = backend.provisional_evidence_pack(
                omit_one=case["condition"] == "partial_evidence"
            )
            generated = run_grounded_generator(
                model,
                question=family["question"],
                claim_slots=backend.public_start()["claim_slots"],
                observations=observations,
                condition=case["condition"],
            )
            backend.finalize(generated["final"])
            record.update(
                {
                    "status": "completed",
                    "final": generated["final"],
                    "model_calls": generated["model_calls"],
                    "backend_events": backend.events,
                }
            )
        else:
            policy = (
                "react"
                if case["system"] == "learned_react"
                else "evidence_sufficiency"
            )
            outcome = run_learned_agent(model, backend=backend, policy=policy)
            record.update(
                {
                    "status": (
                        "completed" if outcome["final"] is not None else "typed_failure"
                    ),
                    "final": outcome["final"],
                    "failure": outcome["terminal_error"],
                    "model_calls": outcome["model_calls"],
                    "public_events": outcome["events"],
                    "backend_events": backend.events,
                }
            )
    except LearnedCallFailure as exc:
        record.update(
            {
                "status": "typed_failure",
                "failure": {"code": exc.code},
                "model_calls": exc.details.get("attempts", []),
                "final": None,
                "backend_events": backend.events,
            }
        )
    record["backend_snapshot"] = backend.snapshot()
    record["observations"] = list(backend.observation_private.values())
    record["evidence_by_observation"] = backend.evidence_by_observation
    record["metrics"] = _score_case(
        family,
        backend,
        record.get("final"),
        state=case["state"],
        process_ok=record["status"] == "completed",
    )
    record["record_hash"] = semantic_hash(
        {key: value for key, value in record.items() if key != "record_hash"}
    )
    return record


def _metric_rows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        if record["condition"].startswith("fault_"):
            continue
        diagnostics = _action_diagnostics(record)
        observations = record.get("observations", [])
        inspected_seconds = sum(
            max(
                0.0,
                float(item.get("interval", {}).get("end_s", 0.0))
                - float(item.get("interval", {}).get("start_s", 0.0)),
            )
            for item in observations
        )
        rows.append(
            {
                "case_id": record["case_id"],
                "family_handle": _family_handle(str(record["family_id"])),
                "system": record["system"],
                "retrieval_variant": record["retrieval_variant"],
                "state": record["state"],
                "condition": record["condition"],
                "status": record["status"],
                **record["metrics"],
                "steps_used": (
                    10 - int(record["backend_snapshot"]["remaining_steps"])
                ),
                "cost_remaining": record["backend_snapshot"]["remaining_cost"],
                "cost_used": round(
                    12.0 - float(record["backend_snapshot"]["remaining_cost"]), 6
                ),
                "inspected_seconds": round(inspected_seconds, 6),
                "inspected_fraction": round(
                    inspected_seconds
                    / max(
                        1.0,
                        float(record["backend_snapshot"]["video_duration_s"]),
                    ),
                    8,
                ),
                "triggered": bool(record["backend_snapshot"]["triggered"]),
                "trigger_conditioned_recovery": (
                    float(
                        record["backend_snapshot"]["triggered"]
                        and record["metrics"]["supported_answer_endpoint"] == 1.0
                    )
                    if record["state"] == "RESTORED"
                    and record["condition"] == "ordinary"
                    else None
                ),
                "no_trigger_false_recovery": (
                    float(record["metrics"]["all_evidence_success"] == 1.0)
                    if record["condition"] == "no_trigger"
                    else None
                ),
                **diagnostics,
                "warning": WARNING,
            }
        )
    return rows


def _action_diagnostics(record: Mapping[str, Any]) -> dict[str, Any]:
    events = record.get("public_events") or record.get("backend_events") or []
    search_events = []
    observation_events = []
    status_calls = 0
    for event in events:
        action = event.get("action", {})
        action_type = action.get("type")
        tool = event.get("tool")
        if action_type == "search":
            search_events.append(
                (action.get("modality"), str(action.get("query", "")))
            )
        elif tool in {"search_visual", "search_speech", "search_ambient_audio"}:
            search_events.append((tool.removeprefix("search_").replace("_audio", ""), str(event.get("request", {}).get("query", ""))))
        if action_type == "observe" or tool in {"inspect_clip", "read_transcript"}:
            observation_events.append(event)
        if action_type == "status" or tool == "get_channel_status":
            status_calls += 1
    modalities = [item[0] for item in search_events if item[0]]
    switches = sum(left != right for left, right in pairwise(modalities))
    queries = [item[1].strip().casefold() for item in search_events if item[1].strip()]
    repeat_searches = len(queries) - len(set(queries))
    accepted_ranks: list[int] = []
    evidence_map = record.get("evidence_by_observation", {})
    observations = {
        item.get("observation_id"): item
        for item in record.get("observations", [])
    }
    for observation_id, observation in observations.items():
        if not evidence_map.get(observation_id):
            continue
        pointer_id = observation.get("pointer_id")
        if not pointer_id:
            continue
        for backend_event in record.get("backend_events", []):
            for rank, result in enumerate(
                backend_event.get("response", {}).get("results", []), 1
            ):
                if result.get("pointer_id") == pointer_id:
                    accepted_ranks.append(rank)
    return {
        "search_calls": len(search_events),
        "observation_calls": len(observation_events),
        "status_calls": status_calls,
        "query_reformulation": len(set(queries)) >= 2,
        "modality_switches": switches,
        "redundant_searches": repeat_searches,
        "retrieval_burden": len(search_events) + len(observation_events),
        "first_accepted_evidence_rank": min(accepted_ranks) if accepted_ranks else None,
    }


def _aggregates(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                str(row["system"]),
                str(row["retrieval_variant"]),
                str(row["state"]),
                str(row["condition"]),
            )
        ].append(row)
    output = []
    metric_names = (
        "evidence_recall",
        "all_evidence_success",
        "answer_score",
        "citation_f1",
        "supported_claim_rate",
        "unsupported_claim_rate",
        "success_at_budget",
        "premature_stop",
        "false_sufficient",
        "partial_evidence_hallucination",
        "calibrated_refusal",
        "supported_answer_endpoint",
        "state_target_success",
        "sufficiency_brier",
        "access_failure_diagnosis_accuracy",
        "missing_cause_accuracy",
        "query_reformulation",
        "modality_switches",
        "redundant_searches",
        "retrieval_burden",
        "cost_used",
        "inspected_seconds",
        "inspected_fraction",
        "candidate_modality_routing_coverage",
        "first_accepted_evidence_rank",
        "trigger_conditioned_recovery",
        "no_trigger_false_recovery",
    )
    for key, values in sorted(grouped.items()):
        output.append(
            {
                "system": key[0],
                "retrieval_variant": key[1],
                "state": key[2],
                "condition": key[3],
                "n": len(values),
                **{
                    name: mean_or_none(
                        [
                            float(row[name])
                            if isinstance(row.get(name), (int, float, bool))
                            else None
                            for row in values
                        ]
                    )
                    for name in metric_names
                },
                "warning": WARNING,
            }
        )
    return output


def _paired_diagnostics(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    ordinary = [row for row in rows if row["condition"] == "ordinary"]
    index = {
        (
            row["family_handle"],
            row["system"],
            row["retrieval_variant"],
            row["state"],
        ): row
        for row in ordinary
    }
    output = []
    for family, system, retrieval in sorted(
        {
            (row["family_handle"], row["system"], row["retrieval_variant"])
            for row in ordinary
        }
    ):
        blocked = index.get((family, system, retrieval, "BLOCKED"))
        restored = index.get((family, system, retrieval, "RESTORED"))
        clean = index.get((family, system, retrieval, "CLEAN"))
        if not (clean and blocked and restored):
            continue
        output.append(
            {
                "family_handle": family,
                "system": system,
                "retrieval_variant": retrieval,
                "clean_supported_answer": clean["supported_answer_endpoint"],
                "blocked_supported_answer": blocked["supported_answer_endpoint"],
                "restored_supported_answer": restored["supported_answer_endpoint"],
                "restoration_gain_common_endpoint": (
                    float(restored["supported_answer_endpoint"])
                    - float(blocked["supported_answer_endpoint"])
                ),
                "blocked_state_target_success": blocked["state_target_success"],
                "clean_to_blocked_false_sufficient_delta": (
                    float(blocked["false_sufficient"])
                    - float(clean["false_sufficient"])
                ),
                "blocked_to_restored_premature_stop_delta": (
                    None
                    if blocked["premature_stop"] is None
                    or restored["premature_stop"] is None
                    else float(restored["premature_stop"])
                    - float(blocked["premature_stop"])
                ),
                "warning": WARNING,
            }
        )
    return output


def _decisions(
    records: Sequence[Mapping[str, Any]],
    *,
    construct_validity_go: bool,
    readiness_thresholds: Mapping[str, Any],
) -> dict[str, Any]:
    ordinary = [row for row in records if row["condition"] == "ordinary"]
    generation_rows = [
        row for row in records
        if row["system"] in {
            "single_shot_learned_generator",
            "learned_generator_diagnostic",
        }
    ]
    agent_rows = [
        row for row in ordinary
        if row["system"] in {"learned_react", "learned_evidence_sufficiency"}
    ]
    minimum_rate = float(
        readiness_thresholds["minimum_structured_completion_rate"]
    )
    expected_generator_cases = 5 * (2 * 3 + 2)
    generator_completion_rate = (
        sum(row["status"] == "completed" for row in generation_rows)
        / max(1, len(generation_rows))
    )
    generator_conditions = {
        (
            row["system"],
            row["retrieval_variant"],
            row["state"],
            row["condition"],
        )
        for row in generation_rows
        if row["status"] == "completed"
    }
    expected_generator_conditions = {
        (
            "single_shot_learned_generator",
            retrieval,
            state,
            "ordinary",
        )
        for retrieval in ("F-CTRL", "F-VA")
        for state in ("CLEAN", "BLOCKED", "RESTORED")
    } | {
        (
            "learned_generator_diagnostic",
            "PROVISIONAL_EVIDENCE",
            "CLEAN",
            condition,
        )
        for condition in ("provisional_evidence", "partial_evidence")
    }
    generation_ready = (
        len(generation_rows) == expected_generator_cases
        and all(row["actual_learned_model"] for row in generation_rows)
        and all(
            row["status"] in {"completed", "typed_failure"}
            for row in generation_rows
        )
        and generator_completion_rate >= minimum_rate
        and expected_generator_conditions <= generator_conditions
    )
    no_trigger_agents = [
        row
        for row in records
        if row["condition"] == "no_trigger"
        and row["system"] in {"learned_react", "learned_evidence_sufficiency"}
    ]
    expected_agent_cases = 5 * 2 * 3 * 2
    expected_no_trigger = 5 * 2 * 2
    agent_completion_rate = (
        sum(
            row["status"] == "completed"
            for row in [*agent_rows, *no_trigger_agents]
        )
        / max(1, len([*agent_rows, *no_trigger_agents]))
    )
    completed_agent_groups = {
        (
            row["system"],
            row["retrieval_variant"],
            row["state"],
        )
        for row in agent_rows
        if row["status"] == "completed"
    }
    expected_agent_groups = {
        (system, retrieval, state)
        for system in ("learned_react", "learned_evidence_sufficiency")
        for retrieval in ("F-CTRL", "F-VA")
        for state in ("CLEAN", "BLOCKED", "RESTORED")
    }
    agent_ready = (
        len(agent_rows) == expected_agent_cases
        and len(no_trigger_agents) == expected_no_trigger
        and all(
            row["actual_learned_model"]
            for row in [*agent_rows, *no_trigger_agents]
        )
        and all(
            row["status"] in {"completed", "typed_failure"}
            for row in [*agent_rows, *no_trigger_agents]
        )
        and agent_completion_rate >= minimum_rate
        and expected_agent_groups <= completed_agent_groups
        and any(row["status"] == "completed" for row in no_trigger_agents)
    )
    # A descriptive separation requires at least two families and at least one
    # Ground/Act metric delta between matched learned policies or retrievals.
    by_key = {
        (
            row["family_id"],
            row["state"],
            row["retrieval_variant"],
            row["system"],
        ): row
        for row in ordinary
    }
    separated_families: set[str] = set()
    for family in {row["family_id"] for row in ordinary}:
        for state in ("CLEAN", "BLOCKED", "RESTORED"):
            for retrieval in ("F-CTRL", "F-VA"):
                left = by_key.get((family, state, retrieval, "learned_react"))
                right = by_key.get(
                    (family, state, retrieval, "learned_evidence_sufficiency")
                )
                if left and right and any(
                    left["metrics"].get(metric) != right["metrics"].get(metric)
                    for metric in (
                        "answer_score",
                        "citation_f1",
                        "supported_claim_rate",
                        "false_sufficient",
                        "premature_stop",
                    )
                ):
                    separated_families.add(family)
    machine_provisional_separation = len(separated_families) >= 2
    end_to_end = (
        "END_TO_END_DIAGNOSTIC_GO"
        if (
            construct_validity_go
            and generation_ready
            and agent_ready
            and machine_provisional_separation
        )
        else "END_TO_END_DIAGNOSTIC_INCONCLUSIVE"
    )
    return {
        "generation": (
            "LEARNED_GENERATION_READY"
            if generation_ready
            else "LEARNED_GENERATION_NO_GO"
        ),
        "agent": "LEARNED_AGENT_READY" if agent_ready else "LEARNED_AGENT_INCOMPLETE",
        "diagnostic": end_to_end,
        "data_scale_up": (
            "DATA_SCALE_UP_GO"
            if end_to_end == "END_TO_END_DIAGNOSTIC_GO"
            else "DATA_SCALE_UP_HOLD"
        ),
        "final_benchmark": "FINAL_BENCHMARK_NOT_YET_VALIDATED",
        "separated_family_count": len(separated_families),
        "machine_provisional_separation_observed": machine_provisional_separation,
        "construct_validity_mini_pilot_go": construct_validity_go,
        "generator_structured_completion_rate": generator_completion_rate,
        "agent_structured_completion_rate": agent_completion_rate,
    }


def run_ga_pilot(
    repo_root: str | Path = ".",
    *,
    startup_timeout_s: float = 240.0,
    generation_timeout_s: float = 180.0,
    threads: int = 8,
    max_cases: int | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    manifest_path = root / RESTRICTED / "experiment_manifest.json"
    manifest = (
        _load(manifest_path) if manifest_path.is_file() else build_ga_pilot(root)
    )
    current_gates = verify_prerequisite_gates(root)
    if not current_gates["ready"]:
        raise GAPilotError("PREREQUISITE_GATES_NOT_READY")
    if current_gates["qwen"]["manifest_sha256"] != manifest["qwen"]["manifest_sha256"]:
        raise GAPilotError("STALE_QWEN_GATE_BINDING")
    families, interventions = _inputs(root)
    family_map = {row["family_id"]: row for row in families}
    config_hash = manifest["config_hash"]
    checkpoints = root / RESTRICTED / "checkpoints"
    cases = list(manifest["matrix"])
    if max_cases is not None:
        cases = cases[:max_cases]
    records: list[dict[str, Any]] = []
    feature_models = LearnedFeatureModels(root, threads=threads)
    with QwenProcess(
        Path(manifest["qwen"]["snapshot_path"]),
        config=ProcessConfig(
            startup_timeout_s=startup_timeout_s,
            generation_timeout_s=generation_timeout_s,
            threads=threads,
        ),
    ) as model:
        model_runtime = dict(model.metadata)
        for case in cases:
            checkpoint_path = checkpoints / f"{case['case_id']}.json"
            prior = read_checkpoint(checkpoint_path, config_hash=config_hash)
            if prior is not None:
                records.append(prior["record"])
                continue
            record = _run_case(
                model,
                root=root,
                family=family_map[case["family_id"]],
                intervention=interventions[case["family_id"]],
                case=case,
                feature_models=feature_models,
            )
            write_checkpoint(
                checkpoint_path,
                config_hash=config_hash,
                record=record,
            )
            records.append(record)
    records.sort(key=lambda row: row["case_id"])
    metrics = _metric_rows(records)
    aggregates = _aggregates(metrics)
    paired = _paired_diagnostics(metrics)
    construct_plan = _load(
        root / "data/rehearsal_plan/construct_validity_mini_pilot_plan.json"
    )
    construct_validity_go = (
        construct_plan.get("execution_decision")
        == "CONSTRUCT_VALIDITY_MINI_PILOT_GO"
        and construct_plan.get("human_review_completed") is True
    )
    decisions = _decisions(
        records,
        construct_validity_go=construct_validity_go,
        readiness_thresholds=manifest["readiness_thresholds"],
    )
    restricted_results = {
        "schema_version": SCHEMA,
        "config_hash": config_hash,
        "records": records,
        "records_hash": semantic_hash(records),
        "model_runtime": model_runtime,
    }
    report = {
        "schema_version": SCHEMA,
        "stage": STAGE,
        "warning": WARNING,
        "human_reviewed": False,
        "gold_annotation": False,
        "actual_learned_model_evaluation": True,
        "model_runtime": model_runtime,
        "counts": {
            "families": len(families),
            "cases": len(records),
            "completed": sum(row["status"] == "completed" for row in records),
            "typed_failures": sum(row["status"] == "typed_failure" for row in records),
        },
        "decisions": decisions,
        "aggregates": aggregates,
        "paired_diagnostics": paired,
        "limitations": [
            "Five retained machine-provisional families over three source videos.",
            "Visual observations use declared machine-provisional text perception proxies because Qwen2.5-1.5B is text-only.",
            "No human-validated evidence minimality or modality necessity.",
            "Results are descriptive and not a benchmark leaderboard.",
        ],
    }
    _write(root / RESTRICTED / "trajectories.json", restricted_results, restricted=True)
    _write(root / RESULTS / "report.json", report, restricted=False)
    report_md = root / RESULTS / "report.md"
    report_md.parent.mkdir(parents=True, exist_ok=True)
    report_md.write_text(_report_markdown(report), encoding="utf-8")
    os.chmod(report_md, 0o644)
    _write_csv(root / RESULTS / "metrics.csv", metrics)
    _write_csv(root / RESULTS / "aggregates.csv", aggregates)
    _write_csv(root / RESULTS / "paired_diagnostics.csv", paired)
    _write(
        root / RESULTS / "run_manifest.json",
        {
            "schema_version": SCHEMA,
            "config_hash": config_hash,
            "artifacts": {
                str(path.relative_to(root)): _sha256(path)
                for path in (
                    root / RESTRICTED / "experiment_manifest.json",
                    root / RESTRICTED / "trajectories.json",
                    root / RESULTS / "report.json",
                    root / RESULTS / "report.md",
                    root / RESULTS / "metrics.csv",
                    root / RESULTS / "aggregates.csv",
                    root / RESULTS / "paired_diagnostics.csv",
                )
            },
        },
        restricted=False,
    )
    return report


def _report_markdown(report: Mapping[str, Any]) -> str:
    decisions = report["decisions"]
    lines = [
        "# Scale-1B learned generation/agent pilot",
        "",
        f"Stage: `{report['stage']}`",
        "",
        "## Decisions",
        "",
        f"- `{decisions['generation']}`",
        f"- `{decisions['agent']}`",
        f"- `{decisions['diagnostic']}`",
        f"- `{decisions['data_scale_up']}`",
        f"- `{decisions['final_benchmark']}`",
        "",
        "## Scope",
        "",
        f"- Families: {report['counts']['families']}",
        f"- Cases: {report['counts']['cases']}",
        f"- Completed: {report['counts']['completed']}",
        f"- Typed failures: {report['counts']['typed_failures']}",
        f"- Warning: `{report['warning']}`",
        "",
        (
            "This is a low-N machine-adjudicated provisional pilot. "
            "It is not a human-valid benchmark result."
        ),
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in report["limitations"])
    return "\n".join(lines) + "\n"


def verify_ga_pilot(
    repo_root: str | Path = ".",
    *,
    require_results: bool = True,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    failures: list[str] = []
    gates = verify_prerequisite_gates(root)
    if not gates["ready"]:
        failures.extend(gates["errors"])
    manifest_path = root / RESTRICTED / "experiment_manifest.json"
    if not manifest_path.is_file():
        failures.append("EXPERIMENT_MANIFEST_MISSING")
        return {"passed": False, "failures": failures, "gates": gates}
    manifest = _load(manifest_path)
    if manifest.get("config_hash") != semantic_hash(
        {key: value for key, value in manifest.items() if key != "config_hash"}
    ):
        failures.append("EXPERIMENT_CONFIG_HASH_MISMATCH")
    if not require_results:
        return {"passed": not failures, "failures": failures, "gates": gates}
    trajectory_path = root / RESTRICTED / "trajectories.json"
    report_path = root / RESULTS / "report.json"
    report_md_path = root / RESULTS / "report.md"
    run_path = root / RESULTS / "run_manifest.json"
    for path in (trajectory_path, report_path, report_md_path, run_path):
        if not path.is_file():
            failures.append(f"MISSING:{path.relative_to(root)}")
    if failures:
        return {"passed": False, "failures": failures, "gates": gates}
    trajectories = _load(trajectory_path)
    records = trajectories.get("records", [])
    if trajectories.get("records_hash") != semantic_hash(records):
        failures.append("TRAJECTORY_RECORD_HASH_MISMATCH")
    expected_ids = {row["case_id"] for row in manifest["matrix"]}
    observed_ids = {row.get("case_id") for row in records}
    if expected_ids != observed_ids:
        failures.append("CASE_COVERAGE_MISMATCH")
    families, _interventions = _inputs(root)
    family_map = {row["family_id"]: row for row in families}
    recomputed_metrics_by_case: dict[str, dict[str, Any]] = {}
    for row in records:
        case_id = str(row.get("case_id"))
        is_fault = str(row.get("condition", "")).startswith("fault_")
        is_deterministic = str(row.get("system", "")).startswith(
            "deterministic_"
        )
        if (
            not is_fault
            and not is_deterministic
            and row.get("actual_learned_model") is not True
        ):
            failures.append(f"NOT_ACTUAL_LEARNED_MODEL:{case_id}")
        if (
            not is_fault
            and not is_deterministic
            and not row.get("model_calls")
        ):
            failures.append(f"LEARNED_RECORD_WITHOUT_MODEL_CALL:{case_id}")
        if row.get("record_hash") != semantic_hash(
            {key: value for key, value in row.items() if key != "record_hash"}
        ):
            failures.append(f"RECORD_HASH:{case_id}")
        for call in row.get("model_calls", []):
            raw = str(call.get("raw_text", ""))
            if any(
                marker in raw
                for marker in ("claim.r", "e.r", "noaa01-r", "seg.", "cand-")
            ):
                failures.append(f"PRIVATE_ID_IN_MODEL_OUTPUT:{case_id}")
            if call.get("status") == "valid" and not call.get("request_hash"):
                failures.append(f"MODEL_CALL_WITHOUT_REQUEST_HASH:{case_id}")
        family = family_map.get(str(row.get("family_id")))
        if family is None:
            failures.append(f"UNKNOWN_FAMILY:{case_id}")
            continue
        final = row.get("final")
        if final is not None:
            try:
                validate_finalization(
                    final,
                    claim_handles={
                        f"slot.c{ordinal:02d}"
                        for ordinal, _claim in enumerate(
                            family.get("claims", ()), 1
                        )
                    },
                    observation_ids={
                        str(item["observation_id"])
                        for item in row.get("observations", [])
                    },
                )
            except PublicSchemaError as exc:
                failures.append(f"FINAL_SCHEMA:{case_id}:{exc}")
        certificate = row.get("metrics", {}).get(
            "route_feasibility_certificate"
        )
        if not isinstance(certificate, Mapping):
            failures.append(f"ROUTE_CERTIFICATE_MISSING:{case_id}")
            continue
        certificate_body = {
            key: value
            for key, value in certificate.items()
            if key != "certificate_hash"
        }
        if certificate.get("certificate_hash") != semantic_hash(certificate_body):
            failures.append(f"ROUTE_CERTIFICATE_HASH:{case_id}")
        recomputed = score_final(
            family=family,
            final=final,
            observations={
                str(item["observation_id"]): item
                for item in row.get("observations", [])
            },
            evidence_by_observation=row.get("evidence_by_observation", {}),
            state=str(row["state"]),
            route_feasibility_certificate=certificate,
            within_budget=(
                row.get("status") == "completed"
                and int(row["backend_snapshot"]["remaining_steps"]) >= 0
                and float(row["backend_snapshot"]["remaining_cost"]) >= -1e-9
            ),
        )
        recomputed["route_feasibility_certificate"] = certificate
        if semantic_hash(recomputed) != semantic_hash(row.get("metrics")):
            failures.append(f"METRIC_RECOMPUTE:{case_id}")
        recomputed_metrics_by_case[case_id] = recomputed
        checkpoint_path = (
            root / RESTRICTED / "checkpoints" / f"{case_id}.json"
        )
        checkpoint = read_checkpoint(
            checkpoint_path, config_hash=manifest["config_hash"]
        )
        if checkpoint is None or checkpoint.get("record_hash") != semantic_hash(
            checkpoint.get("record")
        ):
            failures.append(f"CHECKPOINT_INVALID:{case_id}")
    expected_metrics = _metric_rows(records)
    expected_aggregates = _aggregates(expected_metrics)
    expected_paired = _paired_diagnostics(expected_metrics)
    for path, expected, label in (
        (root / RESULTS / "metrics.csv", expected_metrics, "METRICS"),
        (root / RESULTS / "aggregates.csv", expected_aggregates, "AGGREGATES"),
        (
            root / RESULTS / "paired_diagnostics.csv",
            expected_paired,
            "PAIRED",
        ),
    ):
        if not path.is_file():
            failures.append(f"{label}_FILE_MISSING")
            continue
        # CSV scalar rendering is compared by deterministic regeneration.
        temporary = Path(tempfile.mkdtemp(prefix="ga-verify-", dir="/tmp")) / path.name
        try:
            _write_csv(temporary, expected)
            if _sha256(temporary) != _sha256(path):
                failures.append(f"{label}_RECOMPUTE")
        finally:
            temporary.unlink(missing_ok=True)
            temporary.parent.rmdir()
    run_manifest = _load(run_path)
    for relative, expected in run_manifest.get("artifacts", {}).items():
        path = root / relative
        if not path.is_file() or _sha256(path) != expected:
            failures.append(f"ARTIFACT_HASH:{relative}")
    mode = stat.S_IMODE(trajectory_path.stat().st_mode)
    if mode & 0o077:
        failures.append("RESTRICTED_TRAJECTORY_PERMISSIONS")
    prompt_current = prompt_hashes()
    if manifest.get("prompt_hashes") != prompt_current:
        failures.append("PROMPT_HASH_DRIFT")
    report = _load(report_path)
    construct_plan = _load(
        root / "data/rehearsal_plan/construct_validity_mini_pilot_plan.json"
    )
    decisions = _decisions(
        records,
        construct_validity_go=(
            construct_plan.get("execution_decision")
            == "CONSTRUCT_VALIDITY_MINI_PILOT_GO"
            and construct_plan.get("human_review_completed") is True
        ),
        readiness_thresholds=manifest["readiness_thresholds"],
    )
    if report.get("decisions") != decisions:
        failures.append("DECISION_RECOMPUTE")
    if decisions["diagnostic"] == "END_TO_END_DIAGNOSTIC_GO" and not decisions[
        "construct_validity_mini_pilot_go"
    ]:
        failures.append("DIAGNOSTIC_GO_WITHOUT_CONSTRUCT_VALIDITY")
    forbidden_suffixes = {".wav", ".mp3", ".flac", ".mp4", ".avi", ".mov"}
    for path in (root / RESTRICTED).rglob("*"):
        if path.is_file() and path.suffix.casefold() in forbidden_suffixes:
            failures.append(f"PERSISTED_MEDIA_DERIVATIVE:{path.relative_to(root)}")
    return {
        "passed": not failures,
        "failures": failures,
        "gates": gates,
        "record_count": len(records),
    }
