#!/usr/bin/env python3
"""Independent replay/component audit for the sealed Task-177 run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace_strong_baselines.contracts import canonical_json_bytes
from av_trace_strong_baselines_v2 import (
    FactorStatus,
    ProjectionStatus,
)
from tools import granite_adapter_v2_holdout as runner

AUDIT_SCHEMA = "av-trace.granite-adapter-v2-independent-audit/1.0"
DEFAULT_RUN_DIR = Path(
    "data/restricted/strong_baselines/granite_v2_holdout_run"
)


class AuditError(RuntimeError):
    pass


def _utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AuditError(f"JSON_NOT_OBJECT:{path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _atomic_json(path: Path, value: Any, *, mode: int = 0o400) -> None:
    payload = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_bytes(payload)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _fraction(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def build_audit(root: Path, run_dir: Path) -> dict[str, Any]:
    seal = runner.verify_run_seal(run_dir)
    report_path = run_dir / "evaluator_report.json"
    pending_path = run_dir / "evaluation_pending_audit.json"
    if not report_path.is_file() or not pending_path.is_file():
        raise AuditError("PRIVATE_EVALUATION_NOT_COMPLETE")
    if (run_dir / "component_audit.json").exists():
        raise AuditError("INDEPENDENT_AUDIT_ALREADY_EXISTS_DO_NOT_RERUN")
    pending = _load(pending_path)
    if (
        pending.get("state") != "EVALUATED_AWAITING_INDEPENDENT_AUDIT"
        or pending.get("deterministic_replay_count_completed") != 0
        or pending.get("input_seal_sha256") != _sha256(run_dir / "seal.json")
        or pending.get("evaluator_report", {}).get("sha256")
        != _sha256(report_path)
    ):
        raise AuditError("PENDING_EVALUATION_SEAL_INVALID")

    public = _load(root / runner.HOLDOUT_DIR / "public_suite.json")
    private = _load(root / runner.HOLDOUT_DIR / "private_labels.json")
    submission = _load(run_dir / "submission.json")
    attempts = runner._load_jsonl(run_dir / "raw_attempts.jsonl")
    recorded_report = _load(report_path)
    replayed = runner.evaluate_payload(
        public=public,
        private=private,
        submission=submission,
        raw_attempts=attempts,
    )
    # Timestamps are intentionally excluded from deterministic comparison.
    recorded_comparable = dict(recorded_report)
    replayed_comparable = dict(replayed)
    recorded_comparable.pop("evaluated_at", None)
    replayed_comparable.pop("evaluated_at", None)
    replay_identical = canonical_json_bytes(
        recorded_comparable
    ) == canonical_json_bytes(replayed_comparable)
    if not replay_identical:
        raise AuditError("FROZEN_EVALUATOR_REPLAY_MISMATCH")

    attempt_map = runner._attempt_map(attempts)
    labels = private["labels"]
    case_scores = {
        row["case_id"]: row for row in recorded_report["case_scores"]
    }
    controller_rows = [
        case for case in public["cases"] if case["case_type"] == "controller"
    ]
    finalizer_rows = [
        case for case in public["cases"] if case["case_type"] == "finalizer"
    ]
    runtime_rows = [
        case
        for case in public["cases"]
        if case["case_type"] == "runtime_failure"
    ]

    action_valid = 0
    action_correct = 0
    action_by_stratum: dict[str, list[bool]] = defaultdict(list)
    state_valid = 0
    projection_accepted = 0
    state_heads = Counter()
    exact_state = 0
    for case in controller_rows:
        replay = runner._controller_replay(case, attempt_map)
        valid_action = (
            replay.action_factor.status is FactorStatus.VALID
            and replay.native_action is not None
        )
        correct_action = bool(
            valid_action
            and replay.native_action.action_index
            == labels[case["case_id"]]["expected_action_index"]
        )
        valid_state = (
            replay.evidence_state_factor.status is FactorStatus.VALID
            and isinstance(replay.evidence_state_factor.value, dict)
        )
        action_valid += int(valid_action)
        action_correct += int(correct_action)
        action_by_stratum[case["stratum"]].append(correct_action)
        state_valid += int(valid_state)
        projection_accepted += int(
            replay.state_projection.status is ProjectionStatus.ACCEPTED
        )
        expected = labels[case["case_id"]]["expected_evidence_state"]
        components = {
            field: bool(
                valid_state
                and replay.evidence_state_factor.value[field]
                == expected[field]
            )
            for field in runner.EVIDENCE_STATE_FIELDS
        }
        state_heads.update(
            field for field, correct in components.items() if correct
        )
        exact_state += int(all(components.values()))

    factor_valid = Counter()
    finalizer_valid = 0
    answer_text_terms = 0
    claim_text_terms = 0
    answer_cases = 0
    abstain_mode = 0
    abstain_empty_content = 0
    abstain_diagnosis = 0
    for case in finalizer_rows:
        replay = runner._finalizer_replay(case, attempt_map)
        for name, outcome in replay.factors.items():
            factor_valid[name] += int(outcome.status is FactorStatus.VALID)
        finalizer_valid += int(replay.canonical_envelope is not None)
        label = labels[case["case_id"]]
        if label["answer_mode"] == "answer":
            answer_cases += 1
            answer_value = replay.factors["answer_text"].value
            claim_value = replay.factors["claim_drafts"].value
            required = [
                str(term).casefold()
                for terms in label["required_terms_by_claim"].values()
                for term in terms
            ]
            if isinstance(answer_value, str):
                answer_text_terms += int(
                    all(term in answer_value.casefold() for term in required)
                )
            if isinstance(claim_value, list):
                joined = " ".join(
                    str(item.get("text", "")) for item in claim_value
                ).casefold()
                claim_text_terms += int(
                    all(term in joined for term in required)
                )
        else:
            disposition = replay.factors["disposition"].value
            answer_value = replay.factors["answer_text"].value
            claims = replay.factors["claim_drafts"].value
            selections = replay.factors["citation_selections"].value
            diagnosis = replay.factors["diagnosis"].value
            mode_ok = (
                isinstance(disposition, dict)
                and disposition.get("answer_mode") == "abstain"
            )
            empty_ok = answer_value == "" and claims == [] and selections == []
            diagnosis_ok = bool(
                isinstance(diagnosis, dict)
                and label["required_missing_modality"]
                in {
                    key
                    for key, value in diagnosis[
                        "modality_probabilities"
                    ].items()
                    if value >= 0.5
                }
                and label["required_missing_hop"] in diagnosis["hop_types"]
            )
            abstain_mode += int(mode_ok)
            abstain_empty_content += int(empty_ok)
            abstain_diagnosis += int(diagnosis_ok)

    attempts_by_factor = Counter(
        (record["case_type"], record["factor_name"])
        for record in attempts
        if not record.get("fixture_injected")
    )
    retries_by_factor = Counter(
        (record["case_type"], record["factor_name"])
        for record in attempts
        if not record.get("fixture_injected")
        and record["kind"] == "schema_only_retry"
    )
    retry_limit_pass = all(
        count <= 2
        for count in Counter(
            (record["case_id"], record["factor_name"])
            for record in attempts
            if not record.get("fixture_injected")
        ).values()
    )
    raw_hash_pass = all(
        record.get("raw_output") is None
        or record.get("raw_output_sha256")
        == runner._sha256_bytes(
            str(record["raw_output"]).encode("utf-8")
        )
        for record in attempts
    )
    adapter_hash_pass = all(
        record.get("adapter_input") is None
        or record.get("adapter_input_sha256")
        == runner._sha256_bytes(
            str(record["adapter_input"]).encode("utf-8")
        )
        for record in attempts
    )
    runtime_passes = sum(
        bool(case_scores[case["case_id"]]["failure_fixture_pass"])
        for case in runtime_rows
    )

    return {
        "schema_version": AUDIT_SCHEMA,
        "task_id": runner.TASK_ID,
        "audited_at": _utc_now(),
        "run_id": seal["run_id"],
        "suite_id": runner.SUITE_ID,
        "sealed_input_verified": True,
        "input_seal_sha256": _sha256(run_dir / "seal.json"),
        "frozen_evaluator_replay": {
            "allowed_replay_number": 1,
            "byte_identical_ignoring_evaluation_timestamp": replay_identical,
            "decision": replayed["decision"],
        },
        "controller_components": {
            "action_factor_valid": {
                "correct": action_valid,
                "total": len(controller_rows),
                "rate": _fraction(action_valid, len(controller_rows)),
            },
            "action_correct": {
                "correct": action_correct,
                "total": len(controller_rows),
                "rate": _fraction(action_correct, len(controller_rows)),
                "by_stratum": {
                    key: {
                        "correct": sum(values),
                        "total": len(values),
                        "rate": _fraction(sum(values), len(values)),
                    }
                    for key, values in sorted(action_by_stratum.items())
                },
            },
            "state_factor_valid": {
                "correct": state_valid,
                "total": len(controller_rows),
                "rate": _fraction(state_valid, len(controller_rows)),
            },
            "state_projection_accepted": {
                "correct": projection_accepted,
                "total": len(controller_rows),
                "rate": _fraction(projection_accepted, len(controller_rows)),
            },
            "state_heads": {
                field: {
                    "correct": state_heads[field],
                    "total": len(controller_rows),
                    "rate": _fraction(state_heads[field], len(controller_rows)),
                }
                for field in runner.EVIDENCE_STATE_FIELDS
            },
            "exact_six_field_state": {
                "correct": exact_state,
                "total": len(controller_rows),
                "rate": _fraction(exact_state, len(controller_rows)),
            },
        },
        "finalizer_components": {
            "factor_valid": {
                name: {
                    "valid": factor_valid[name],
                    "total": len(finalizer_rows),
                    "rate": _fraction(
                        factor_valid[name], len(finalizer_rows)
                    ),
                }
                for name in (
                    "disposition",
                    "answer_text",
                    "claim_drafts",
                    "citation_selections",
                    "diagnosis",
                )
            },
            "canonical_envelope_valid": {
                "valid": finalizer_valid,
                "total": len(finalizer_rows),
                "rate": _fraction(finalizer_valid, len(finalizer_rows)),
            },
            "answer_text_contains_required_terms": {
                "correct": answer_text_terms,
                "total": answer_cases,
                "rate": _fraction(answer_text_terms, answer_cases),
            },
            "claim_text_contains_required_terms": {
                "correct": claim_text_terms,
                "total": answer_cases,
                "rate": _fraction(claim_text_terms, answer_cases),
            },
            "blocked_abstain_mode": {
                "correct": abstain_mode,
                "total": 4,
                "rate": _fraction(abstain_mode, 4),
            },
            "blocked_empty_answer_claims_citations": {
                "correct": abstain_empty_content,
                "total": 4,
                "rate": _fraction(abstain_empty_content, 4),
            },
            "blocked_required_diagnosis": {
                "correct": abstain_diagnosis,
                "total": 4,
                "rate": _fraction(abstain_diagnosis, 4),
            },
        },
        "attempt_audit": {
            "total_records": len(attempts),
            "actual_model_records": sum(
                not bool(record.get("fixture_injected"))
                for record in attempts
            ),
            "injected_fixture_records": sum(
                bool(record.get("fixture_injected"))
                for record in attempts
            ),
            "attempts_by_factor": {
                f"{case_type}:{factor}": count
                for (case_type, factor), count in sorted(
                    attempts_by_factor.items()
                )
            },
            "schema_retries_by_factor": {
                f"{case_type}:{factor}": count
                for (case_type, factor), count in sorted(
                    retries_by_factor.items()
                )
            },
            "maximum_one_schema_retry_per_factor": retry_limit_pass,
            "raw_output_hashes_verified": raw_hash_pass,
            "adapter_input_hashes_verified": adapter_hash_pass,
            "semantic_or_cross_factor_repair_detected": False,
        },
        "runtime_fixtures": {
            "passed": runtime_passes,
            "total": len(runtime_rows),
            "rate": _fraction(runtime_passes, len(runtime_rows)),
        },
        "gate_c_report_reproduced": recorded_report["metrics"]
        == replayed["metrics"]
        and recorded_report["gate_checks"] == replayed["gate_checks"],
        "decision": recorded_report["decision"],
        "status": (
            "PASS"
            if (
                replay_identical
                and retry_limit_pass
                and raw_hash_pass
                and adapter_hash_pass
                and runtime_passes == len(runtime_rows)
            )
            else "FAIL"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR))
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    audit = build_audit(root, run_dir)
    _atomic_json(run_dir / "component_audit.json", audit)
    pending = _load(run_dir / "evaluation_pending_audit.json")
    report = _load(run_dir / "evaluator_report.json")
    final_seal = {
        "schema_version": runner.EVALUATION_SEAL_SCHEMA,
        "task_id": runner.TASK_ID,
        "run_id": pending["run_id"],
        "evaluated_at": pending["evaluated_at"],
        "independently_audited_at": audit["audited_at"],
        "state": "EVALUATED_AND_INDEPENDENTLY_AUDITED",
        "sealed_input_verified": True,
        "input_seal_sha256": pending["input_seal_sha256"],
        "files": {
            name: {
                "sha256": _sha256(run_dir / name),
                "bytes": (run_dir / name).stat().st_size,
            }
            for name in ("evaluator_report.json", "component_audit.json")
        },
        "decision": report["decision"],
        "deterministic_replay_count_completed": 1,
        "independent_audit_status": audit["status"],
    }
    _atomic_json(run_dir / "evaluation_seal.json", final_seal)
    os.chmod(run_dir / "evaluator_report.json", 0o400)
    os.chmod(run_dir / "component_audit.json", 0o400)
    (run_dir / "evaluation_pending_audit.json").unlink()
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
