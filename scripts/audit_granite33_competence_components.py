#!/usr/bin/env python3
"""Independent component audit of the sealed Task-172 Granite run.

This diagnostic never changes the frozen evaluator verdict. It separates
parseable subfields from fully valid public wire envelopes so that failures in
one controller state head do not hide the model's raw action selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace_strong_baselines.competence import (
    evaluate_competence_submission,
    load_submission,
    load_suite,
)
from av_trace_strong_baselines.errors import SchemaViolation
from av_trace_strong_baselines.schemas import (
    EVIDENCE_STATE_FIELDS,
    parse_strict_json,
)

SUITE = Path("data/rehearsal_plan/strong_baseline_competence_suite_v1.json")
RUN_DIR = Path("data/restricted/strong_baselines/granite33_competence_v1")
SEALED_FILES = {
    "submission.json",
    "raw_attempts.jsonl",
    "run_metadata.json",
    "direct_av_eligibility.json",
    "runner_manifest.json",
}
TERMINAL_STRATA = {
    "no_progress_guard",
    "no_trigger",
    "finalize_ready",
}


class AuditError(RuntimeError):
    pass


def _utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _verify_seal(run_dir: Path) -> dict[str, Any]:
    seal = _load(run_dir / "seal.json")
    if (
        seal.get("state") != "SEALED_BEFORE_EVALUATION"
        or set(seal.get("files", {})) != SEALED_FILES
    ):
        raise AuditError("INVALID_INPUT_SEAL")
    for name, expected in seal["files"].items():
        path = run_dir / name
        if (
            not path.is_file()
            or path.stat().st_size != expected["bytes"]
            or _sha256(path) != expected["sha256"]
        ):
            raise AuditError(f"SEALED_INPUT_MISMATCH:{name}")
    return seal


def _fraction(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _count(correct: int, total: int) -> dict[str, int | float | None]:
    return {
        "correct": correct,
        "total": total,
        "rate": _fraction(correct, total),
    }


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _terms_present(text: Any, terms: Sequence[Any]) -> bool:
    if not isinstance(text, str):
        return False
    folded = text.casefold()
    return all(str(term).casefold() in folded for term in terms)


def build_component_audit(
    suite: Mapping[str, Any],
    submission: Mapping[str, Any],
    frozen_report: Mapping[str, Any],
    *,
    seal: Mapping[str, Any],
    direct_eligibility: Mapping[str, Any],
) -> dict[str, Any]:
    cases = suite["cases"]["controller_finalizer"]
    results = {row["case_id"]: row for row in submission["results"]}
    scores = {row["case_id"]: row for row in frozen_report["case_scores"]}

    controller_rows: list[dict[str, Any]] = []
    action_strata: dict[str, list[bool]] = defaultdict(list)
    state_head_counts = {
        field: {"correct": 0, "present": 0, "total": 0}
        for field in EVIDENCE_STATE_FIELDS
    }
    parsed_controller_json = 0
    action_syntax = 0
    action_correct = 0
    joint_state = 0
    full_controller_valid = 0

    for case in cases:
        if case["case_type"] != "controller":
            continue
        result = results[case["case_id"]]
        score = scores[case["case_id"]]
        raw = result.get("raw_output")
        parsed: Mapping[str, Any] = {}
        parse_error = None
        if isinstance(raw, str):
            try:
                value = parse_strict_json(raw, maximum_bytes=8_192)
                if isinstance(value, Mapping):
                    parsed = value
                    parsed_controller_json += 1
            except SchemaViolation as exc:
                parse_error = exc.code
        menu = case["public_input"]["action_menu"]
        action_index = parsed.get("action_index")
        action_well_typed = (
            isinstance(action_index, int)
            and not isinstance(action_index, bool)
            and 0 <= action_index < len(menu)
        )
        selected_tool = menu[action_index]["tool"] if action_well_typed else None
        expected_index = case["scoring_target"]["expected_action_index"]
        raw_action_correct = bool(
            action_well_typed and action_index == expected_index
        )
        action_syntax += action_well_typed
        action_correct += raw_action_correct
        action_strata[case["stratum"]].append(raw_action_correct)
        state = _as_mapping(parsed.get("evidence_state"))
        component_correct: dict[str, bool] = {}
        for field in EVIDENCE_STATE_FIELDS:
            state_head_counts[field]["total"] += 1
            if field in state:
                state_head_counts[field]["present"] += 1
            correct = (
                field in state
                and state[field]
                == case["scoring_target"]["expected_evidence_state"][field]
            )
            component_correct[field] = correct
            state_head_counts[field]["correct"] += correct
        raw_joint = all(component_correct.values())
        joint_state += raw_joint
        full_controller_valid += bool(score.get("structured_valid"))
        controller_rows.append(
            {
                "case_id": case["case_id"],
                "stratum": case["stratum"],
                "parse_error": parse_error,
                "action_index_well_typed_and_in_range": action_well_typed,
                "selected_tool": selected_tool,
                "expected_tool": menu[expected_index]["tool"],
                "raw_action_correct": raw_action_correct,
                "raw_state_component_correct": component_correct,
                "raw_joint_state_correct": raw_joint,
                "frozen_full_controller_valid": bool(
                    score.get("structured_valid")
                ),
                "frozen_error_code": score.get("error_code"),
            }
        )

    state_heads = {
        field: {
            **_count(values["correct"], values["total"]),
            "present": values["present"],
        }
        for field, values in state_head_counts.items()
    }
    terminal_rows = [
        row for row in controller_rows if row["stratum"] in TERMINAL_STRATA
    ]
    terminal_selected_finalize = sum(
        row["selected_tool"] == "finalize" for row in terminal_rows
    )
    terminal_raw_correct = sum(
        row["raw_action_correct"] for row in terminal_rows
    )
    terminal_full_valid_and_correct = sum(
        row["frozen_full_controller_valid"] and row["raw_action_correct"]
        for row in terminal_rows
    )

    finalizer_rows: list[dict[str, Any]] = []
    answer_claim_term_omissions = 0
    answer_natural_term_success = 0
    answer_citation_id_success = 0
    raw_abstain_mode = 0
    raw_abstain_empty_claims = 0
    raw_abstain_modality = 0
    raw_abstain_hop_label = 0
    raw_abstain_hop_array = 0
    finalizer_json_parsed = 0
    for case in cases:
        if case["case_type"] != "finalizer":
            continue
        result = results[case["case_id"]]
        score = scores[case["case_id"]]
        raw = result.get("raw_output")
        parsed: Mapping[str, Any] = {}
        parse_error = None
        if isinstance(raw, str):
            try:
                value = parse_strict_json(raw, maximum_bytes=64_000)
                if isinstance(value, Mapping):
                    parsed = value
                    finalizer_json_parsed += 1
            except SchemaViolation as exc:
                parse_error = exc.code
        final = _as_mapping(parsed.get("final_answer"))
        claims = final.get("claims")
        claims = claims if isinstance(claims, list) else []
        target = case["scoring_target"]
        answer_mode = final.get("answer_mode")
        diagnostic: dict[str, Any] = {}
        if target["answer_mode"] == "answer":
            required_by_claim = target["required_terms_by_claim"]
            natural_success = all(
                _terms_present(
                    final.get("natural_language_answer"),
                    terms,
                )
                for terms in required_by_claim.values()
            )
            claim_success = True
            citation_success = True
            for handle, terms in required_by_claim.items():
                matching = [
                    claim
                    for claim in claims
                    if isinstance(claim, Mapping)
                    and claim.get("registered_claim_id") == handle
                ]
                if not matching or not _terms_present(
                    matching[0].get("text"),
                    terms,
                ):
                    claim_success = False
                accepted = set(target["accepted_support"][handle])
                raw_citations = (
                    matching[0].get("citations", []) if matching else []
                )
                citation_ids = {
                    citation.get("observation_id")
                    for citation in raw_citations
                    if isinstance(citation, Mapping)
                }
                if not citation_ids or not citation_ids <= accepted:
                    citation_success = False
            answer_natural_term_success += natural_success
            answer_claim_term_omissions += not claim_success
            answer_citation_id_success += citation_success
            diagnostic = {
                "raw_natural_answer_has_required_terms": natural_success,
                "raw_registered_claim_text_has_required_terms": claim_success,
                "raw_citation_ids_within_accepted_support": citation_success,
            }
        else:
            modality = target["required_missing_modality"]
            hop = target["required_missing_hop"]
            diagnosis = _as_mapping(final.get("diagnosis"))
            probabilities = _as_mapping(
                diagnosis.get("modality_probabilities")
            )
            hops = diagnosis.get("hop_types")
            mode_ok = answer_mode == "abstain"
            claims_ok = claims == []
            modality_ok = (
                isinstance(probabilities.get(modality), (int, float))
                and not isinstance(probabilities.get(modality), bool)
                and float(probabilities[modality]) >= 0.5
            )
            hop_label_ok = hop in hops if isinstance(hops, list) else hops == hop
            hop_array_ok = isinstance(hops, list) and hop in hops
            raw_abstain_mode += mode_ok
            raw_abstain_empty_claims += claims_ok
            raw_abstain_modality += modality_ok
            raw_abstain_hop_label += hop_label_ok
            raw_abstain_hop_array += hop_array_ok
            diagnostic = {
                "raw_answer_mode_abstain": mode_ok,
                "raw_claims_empty": claims_ok,
                "raw_required_modality_probability_at_least_half": modality_ok,
                "raw_required_hop_label_present_ignoring_container_type": (
                    hop_label_ok
                ),
                "raw_required_hop_in_valid_array_shape": hop_array_ok,
            }
        finalizer_rows.append(
            {
                "case_id": case["case_id"],
                "stratum": case["stratum"],
                "parse_error": parse_error,
                "raw_answer_mode": answer_mode,
                "frozen_full_finalizer_valid": bool(
                    score.get("structured_valid")
                ),
                "frozen_semantic_success": bool(
                    score.get("semantic_success")
                ),
                "frozen_error_code": score.get("error_code"),
                **diagnostic,
            }
        )

    answer_cases = [
        case
        for case in cases
        if case["case_type"] == "finalizer"
        and case["scoring_target"]["answer_mode"] == "answer"
    ]
    abstain_cases = [
        case
        for case in cases
        if case["case_type"] == "finalizer"
        and case["scoring_target"]["answer_mode"] == "abstain"
    ]
    oracle_cases = [
        case
        for case in answer_cases
        if case["scoring_target"].get("oracle_complete")
    ]
    restoration_cases = [
        case
        for case in answer_cases
        if case["stratum"] == "restoration_complete"
    ]
    runtime_cases = [
        case for case in cases if case["case_type"] == "runtime_failure"
    ]
    typed_invalids = Counter(
        str(results[case["case_id"]].get("inference_status"))
        for case in cases
        if case["case_type"] != "runtime_failure"
        and results[case["case_id"]].get("inference_status") != "VALID"
    )
    error_codes = Counter(
        str(scores[case["case_id"]].get("error_code"))
        for case in cases
        if case["case_type"] != "runtime_failure"
        and scores[case["case_id"]].get("error_code")
    )
    runtime_passes = sum(
        bool(scores[case["case_id"]].get("failure_fixture_pass"))
        for case in runtime_cases
    )
    semantic_repairs = sum(
        result.get("repair_kind") not in {None, "none", "schema_only"}
        for result in results.values()
    )
    all_answer_raw_rows = [
        row
        for row in finalizer_rows
        if row["stratum"] in {"oracle_complete", "restoration_complete"}
    ]

    return {
        "schema_version": "av-trace.granite33-component-audit/1.0",
        "task_id": 172,
        "audited_at": _utc_now(),
        "run_id": seal["run_id"],
        "sealed_input_verified": True,
        "frozen_evaluator_report_recomputed_identically": True,
        "frozen_evaluator_decision": frozen_report["decision"],
        "task172_decision": "GRANITE33_COMPETENCE_NO_GO",
        "interpretation": (
            "Raw component diagnostics are descriptive only. They do not "
            "rescue a case rejected by the frozen strict evaluator."
        ),
        "action_syntax": {
            "strict_json_object_parsed": _count(
                parsed_controller_json,
                len(controller_rows),
            ),
            "integer_in_range_action_index": _count(
                action_syntax,
                len(controller_rows),
            ),
            "full_controller_envelope_valid": _count(
                full_controller_valid,
                len(controller_rows),
            ),
        },
        "action_correctness": {
            **_count(action_correct, len(controller_rows)),
            "by_stratum": {
                stratum: _count(sum(values), len(values))
                for stratum, values in sorted(action_strata.items())
            },
        },
        "state_heads_raw_exact_match": state_heads,
        "joint_six_field_state_raw_exact_match": _count(
            joint_state,
            len(controller_rows),
        ),
        "terminal_behavior": {
            "selected_finalize": _count(
                terminal_selected_finalize,
                len(terminal_rows),
            ),
            "raw_action_correct": _count(
                terminal_raw_correct,
                len(terminal_rows),
            ),
            "full_controller_valid_and_action_correct": _count(
                terminal_full_valid_and_correct,
                len(terminal_rows),
            ),
            "rows": terminal_rows,
        },
        "finalizer_syntax": {
            "strict_json_object_parsed": _count(
                finalizer_json_parsed,
                len(finalizer_rows),
            ),
            "full_grounded_envelope_valid": _count(
                sum(row["frozen_full_finalizer_valid"] for row in finalizer_rows),
                len(finalizer_rows),
            ),
        },
        "oracle_supported_answers": {
            "frozen_strict_supported": _count(
                sum(
                    scores[case["case_id"]].get("semantic_success") is True
                    for case in oracle_cases
                ),
                len(oracle_cases),
            ),
            "raw_natural_answer_required_terms": _count(
                sum(
                    row.get("raw_natural_answer_has_required_terms") is True
                    for row in all_answer_raw_rows
                    if row["stratum"] == "oracle_complete"
                ),
                len(oracle_cases),
            ),
            "raw_registered_claim_text_required_terms": _count(
                sum(
                    row.get(
                        "raw_registered_claim_text_has_required_terms"
                    )
                    is True
                    for row in all_answer_raw_rows
                    if row["stratum"] == "oracle_complete"
                ),
                len(oracle_cases),
            ),
        },
        "restoration_complete_answers": {
            "frozen_strict_supported": _count(
                sum(
                    scores[case["case_id"]].get("semantic_success") is True
                    for case in restoration_cases
                ),
                len(restoration_cases),
            ),
            "raw_natural_answer_required_terms": _count(
                sum(
                    row.get("raw_natural_answer_has_required_terms") is True
                    for row in all_answer_raw_rows
                    if row["stratum"] == "restoration_complete"
                ),
                len(restoration_cases),
            ),
            "raw_registered_claim_text_required_terms": _count(
                sum(
                    row.get(
                        "raw_registered_claim_text_has_required_terms"
                    )
                    is True
                    for row in all_answer_raw_rows
                    if row["stratum"] == "restoration_complete"
                ),
                len(restoration_cases),
            ),
        },
        "abstentions": {
            "frozen_strict_correct": _count(
                sum(
                    scores[case["case_id"]].get("semantic_success") is True
                    for case in abstain_cases
                ),
                len(abstain_cases),
            ),
            "raw_answer_mode_abstain": _count(
                raw_abstain_mode,
                len(abstain_cases),
            ),
            "raw_empty_claims": _count(
                raw_abstain_empty_claims,
                len(abstain_cases),
            ),
            "raw_required_modality_probability_at_least_half": _count(
                raw_abstain_modality,
                len(abstain_cases),
            ),
            "raw_required_hop_label_ignoring_container_type": _count(
                raw_abstain_hop_label,
                len(abstain_cases),
            ),
            "raw_required_hop_in_valid_array_shape": _count(
                raw_abstain_hop_array,
                len(abstain_cases),
            ),
        },
        "unsupported_claims": {
            "frozen_metric": frozen_report["metrics"][
                "unsupported_required_claims"
            ],
            "interpretation": (
                "The frozen count is zero because no answer-mode finalizer "
                "output passed structural validation and reached claim "
                "support scoring."
            ),
            "raw_answer_mode_claims_missing_required_terms": {
                "count": answer_claim_term_omissions,
                "total": len(answer_cases),
            },
            "raw_answer_mode_natural_answers_with_required_terms": {
                "count": answer_natural_term_success,
                "total": len(answer_cases),
            },
            "raw_answer_mode_citation_ids_within_accepted_support": {
                "count": answer_citation_id_success,
                "total": len(answer_cases),
            },
        },
        "invalids": {
            "substantive_total": sum(typed_invalids.values()),
            "by_inference_status": dict(sorted(typed_invalids.items())),
            "by_frozen_error_code": dict(sorted(error_codes.items())),
        },
        "runtime_failures": {
            **_count(runtime_passes, len(runtime_cases)),
            "fixture_statuses": {
                case["case_id"]: {
                    "fixture": case["stratum"],
                    "status": results[case["case_id"]].get(
                        "inference_status"
                    ),
                    "model_was_called": results[case["case_id"]].get(
                        "model_was_called"
                    ),
                }
                for case in runtime_cases
            },
        },
        "repairs_and_substitutions": {
            "schema_only_retries_used": sum(
                int(result["schema_repairs_used"])
                for case_id, result in results.items()
                if not case_id.startswith("sbc-runtime-")
            ),
            "semantic_repairs": semantic_repairs,
            "deterministic_answer_substitutions": frozen_report["metrics"][
                "deterministic_answer_substitutions"
            ],
        },
        "direct_av": dict(direct_eligibility),
        "frozen_metrics": frozen_report["metrics"],
        "frozen_gate_checks": frozen_report["gate_checks"],
        "controller_case_diagnostics": controller_rows,
        "finalizer_case_diagnostics": finalizer_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--run-dir", default=str(RUN_DIR))
    parser.add_argument("--output", default="component_audit.json")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    seal = _verify_seal(run_dir)
    suite = load_suite(root / SUITE)
    submission = load_submission(run_dir / "submission.json")
    frozen_report = _load(run_dir / "evaluator_report.json")
    recomputed = evaluate_competence_submission(suite, submission)
    if recomputed != frozen_report:
        raise AuditError("FROZEN_EVALUATOR_REPORT_RECOMPUTE_MISMATCH")
    audit = build_component_audit(
        suite,
        submission,
        frozen_report,
        seal=seal,
        direct_eligibility=_load(run_dir / "direct_av_eligibility.json"),
    )
    output = run_dir / args.output
    _atomic_json(output, audit)
    os.chmod(output, 0o400)
    component_seal = {
        "schema_version": "av-trace.granite33-component-audit-seal/1.0",
        "task_id": 172,
        "run_id": seal["run_id"],
        "sealed_at": _utc_now(),
        "sealed_input_verified": True,
        "input_seal_sha256": "sha256:" + _sha256(run_dir / "seal.json"),
        "frozen_evaluator_report_sha256": "sha256:"
        + _sha256(run_dir / "evaluator_report.json"),
        "component_audit_sha256": "sha256:" + _sha256(output),
        "component_audit_script_sha256": "sha256:"
        + _sha256(Path(__file__)),
        "decision": audit["task172_decision"],
    }
    _atomic_json(run_dir / "component_audit_seal.json", component_seal)
    os.chmod(run_dir / "component_audit_seal.json", 0o400)
    print(json.dumps(audit, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
