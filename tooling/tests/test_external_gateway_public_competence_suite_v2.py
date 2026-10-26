from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from tools import external_gateway_public_competence_suite_v2 as suite


def committed_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        suite.load_json(ROOT / suite.PUBLIC_PATH),
        suite.load_json(ROOT / suite.PRIVATE_PATH),
    )


def _perfect_submission(
    public: dict[str, Any],
    private: dict[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    for packet in public["packets"]:
        case_id = packet["case_id"]
        label = private["labels"][case_id]
        factor_names = suite._required_factors(packet)
        factor_summary = {
            name: {"status": "RECORDED", "attempt_count": 1}
            for name in factor_names
        }
        if packet["case_type"] == "controller":
            values = {
                "action_choice": {
                    "function_name": (
                        f"select_action_{label['expected_action_index']:02d}"
                    ),
                    "arguments": {},
                },
                "evidence_state": label["expected_evidence_state"],
            }
        else:
            required = label["required_claims"]
            claims = []
            selections = []
            for index, (handle, rule) in enumerate(required.items(), 1):
                claims.append(
                    {
                        "claim_id": f"claim.{case_id}.{index}",
                        "registered_claim_id": handle,
                        "text": rule["accepted_semantic_forms"][0],
                        "confidence": 1.0,
                    }
                )
                selections.append(
                    {
                        "registered_claim_id": handle,
                        "observation_ids": rule["expected_citations"],
                    }
                )
            disposition = label["expected_disposition"]
            diagnosis = {
                **label["expected_diagnosis"],
                "description": "Exclusive closed-world diagnosis.",
            }
            values = {
                "disposition": disposition,
                "answer_text": {
                    "text": " ".join(claim["text"] for claim in claims)
                },
                "claim_drafts": {"claims": claims},
                "citation_selections": {"selections": selections},
                "diagnosis": diagnosis,
            }
        for factor_name, value in values.items():
            attempts.append(
                suite._raw_attempt(packet, factor_name, value)
            )
        rows.append(
            {
                "case_id": case_id,
                "public_packet_sha256": public["freeze_manifest"][
                    "packet_hashes"
                ][case_id],
                "factors": factor_summary,
            }
        )
    return suite._runner_shell(
        public,
        rows,
        attempts,
        run_id="test-perfect-v2",
    )


def _replace_raw(
    submission: dict[str, Any],
    *,
    case_id: str,
    factor_name: str,
    value: Any,
) -> None:
    record = next(
        item
        for item in submission["raw_attempts"]
        if item["case_id"] == case_id
        and item["factor_name"] == factor_name
    )
    raw = (
        value
        if isinstance(value, str)
        else json.dumps(value, sort_keys=True, separators=(",", ":"))
    )
    record["raw_output"] = raw
    record["raw_output_sha256"] = suite.sha256_bytes(raw.encode())


def test_committed_pair_is_deterministic_separate_and_not_authorized() -> None:
    public, private = committed_pair()
    suite.validate_frozen_pair(
        public,
        private,
        private_path=ROOT / suite.PRIVATE_PATH,
    )
    rebuilt = suite.build_frozen_artifacts()
    assert rebuilt == (public, private)
    assert len(public["packets"]) == 48
    assert public["status"] == "REPAIR_NOT_AUTHORIZED"
    assert public["execution_authorized"] is False
    assert public["gateway_or_model_calls"] == 0
    assert public["h2_supported"] is False
    assert private["private_access"]["execution_authorized"] is False
    assert (ROOT / suite.PRIVATE_PATH).stat().st_mode & 0o077 == 0


def test_public_file_has_no_evaluator_labels_strata_or_target_signals() -> None:
    public, private = committed_pair()
    serialized = json.dumps(public, sort_keys=True)
    assert private["private_canary"] not in serialized
    for path, key, _ in suite._walk(public):
        assert key.casefold() not in suite.PROHIBITED_PUBLIC_KEYS, path
    assert '"labels"' not in serialized
    assert '"case_stratum"' not in serialized
    assert '"expected_action_index"' not in serialized
    assert '"accepted_semantic_forms"' not in serialized


def test_opaque_randomized_ids_positions_and_no_within_stratum_clones() -> None:
    public, private = committed_pair()
    case_ids = [packet["case_id"] for packet in public["packets"]]
    assert len(case_ids) == len(set(case_ids)) == 48
    assert all(re.fullmatch(r"[cf]_[0-9a-f]{14}", item) for item in case_ids)

    positions: dict[str, set[int]] = {}
    fingerprints: dict[str, set[str]] = {}
    packet_by_id = {
        packet["case_id"]: packet for packet in public["packets"]
    }
    for case_id, label in private["labels"].items():
        stratum = label["case_stratum"]
        packet = packet_by_id[case_id]
        fingerprints.setdefault(stratum, set()).add(
            suite.sha256_json(packet["public_input"])
        )
        if packet["case_type"] == "controller":
            positions.setdefault(stratum, set()).add(
                label["expected_action_index"]
            )
    assert all(
        len(fingerprints[stratum]) == count
        for stratum, count in private["case_balance"].items()
    )
    assert len({index for values in positions.values() for index in values}) >= 3


def test_public_only_heuristic_and_adversarial_baselines_must_fail() -> None:
    public, private = committed_pair()
    result = suite.run_public_baseline_suite(public, private)
    assert result["all_failed"] is True
    assert {
        row["decision_token"] for row in result["reports"].values()
    } == {suite.NO_GO_TOKEN}
    assert result["reports"]["all_ones_diagnosis"]["metrics"][
        "diagnosis_exact"
    ] == 0.0


def test_perfect_replay_is_technical_go_but_not_h2_or_scientific() -> None:
    public, private = committed_pair()
    report = suite.score_submission(
        public, private, _perfect_submission(public, private)
    )
    assert report["decision_token"] == suite.GO_TOKEN
    assert report["scientific_competence_supported"] is False
    assert report["h2_supported"] is False
    assert all(report["gate_checks"].values())


def test_contradictory_target_substring_is_not_accepted() -> None:
    public, private = committed_pair()
    submission = _perfect_submission(public, private)
    packet = next(
        packet
        for packet in public["packets"]
        if packet["case_type"] == "finalizer"
        and len(private["labels"][packet["case_id"]]["required_claims"]) == 1
    )
    label = private["labels"][packet["case_id"]]
    handle, rule = next(iter(label["required_claims"].items()))
    contradictory = {
        "claims": [
            {
                "claim_id": f"claim.{packet['case_id']}.1",
                "registered_claim_id": handle,
                "text": (
                    rule["accepted_semantic_forms"][0]
                    + " "
                    + rule["forbidden_semantic_forms"][0]
                ),
                "confidence": 1.0,
            }
        ]
    }
    _replace_raw(
        submission,
        case_id=packet["case_id"],
        factor_name="claim_drafts",
        value=contradictory,
    )
    report = suite.score_submission(public, private, submission)
    assert report["metrics"]["contradictory_claims"] >= 1
    assert report["decision_token"] == suite.NO_GO_TOKEN


def test_missing_claim_accounting_is_conservative_on_malformed_claims() -> None:
    public, private = committed_pair()
    submission = _perfect_submission(public, private)
    packet = next(
        packet
        for packet in public["packets"]
        if packet["case_type"] == "finalizer"
        and len(private["labels"][packet["case_id"]]["required_claims"]) == 2
    )
    _replace_raw(
        submission,
        case_id=packet["case_id"],
        factor_name="claim_drafts",
        value={"claims": "forged"},
    )
    report = suite.score_submission(public, private, submission)
    assert report["metrics"]["unsupported_or_missing_claims"] >= 2
    assert report["decision_token"] == suite.NO_GO_TOKEN


def test_forged_declarations_and_provenance_are_rejected() -> None:
    public, private = committed_pair()
    submission = _perfect_submission(public, private)
    submission["runner_report"]["execution"][
        "model_fallback_or_substitution"
    ] = True
    with pytest.raises(
        suite.CompetenceSuiteV2Error,
        match="RUNNER_NO_SUBSTITUTION_MISMATCH",
    ):
        suite.score_submission(public, private, submission)

    submission = _perfect_submission(public, private)
    submission["raw_attempts"][0]["model_slug"] = "forged-model"
    with pytest.raises(
        suite.CompetenceSuiteV2Error,
        match="ATTEMPT_MODEL_SUBSTITUTION",
    ):
        suite.score_submission(public, private, submission)


def test_runner_schema_mismatch_fails_closed() -> None:
    public, private = committed_pair()
    submission = _perfect_submission(public, private)
    submission["runner_report"]["schema_version"] = "forged/9.9"
    with pytest.raises(
        suite.CompetenceSuiteV2Error,
        match="RUNNER_SCHEMA_MISMATCH",
    ):
        suite.score_submission(public, private, submission)


def test_cross_state_isolation_rejects_attempt_reuse_between_cases() -> None:
    public, private = committed_pair()
    submission = _perfect_submission(public, private)
    first, second = [
        packet
        for packet in public["packets"]
        if packet["case_type"] == "controller"
    ][:2]
    record = next(
        item
        for item in submission["raw_attempts"]
        if item["case_id"] == first["case_id"]
        and item["factor_name"] == "action_choice"
    )
    record["case_id"] = second["case_id"]
    with pytest.raises(suite.CompetenceSuiteV2Error):
        suite.score_submission(public, private, submission)


def test_leakage_guard_rejects_private_and_stratum_fields() -> None:
    public, _ = committed_pair()
    leaked = copy.deepcopy(public)
    leaked["packets"][0]["case_stratum"] = "controller_ready"
    with pytest.raises(
        suite.CompetenceSuiteV2Error,
        match="PUBLIC_PRIVATE_KEY_LEAK",
    ):
        suite.validate_public_artifact(leaked)


def test_repeated_evaluation_is_blocked_by_exclusive_atomic_receipt(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(
        json.dumps(
            {
                "schema_version": suite.LEDGER_SCHEMA,
                "state": "ARMED",
                "full_suite_runs": 0,
            }
        ),
        encoding="utf-8",
    )
    suite.consume_one_shot_ledger(
        ledger,
        run_id="run-1",
        submission_sha256="sha256:first",
    )
    with pytest.raises(
        suite.CompetenceSuiteV2Error,
        match="REPEATED_EVALUATION_FORBIDDEN",
    ):
        suite.consume_one_shot_ledger(
            ledger,
            run_id="run-2",
            submission_sha256="sha256:second",
        )
    assert (tmp_path / "ledger.json.consumed").is_file()


def test_parser_failure_fixtures_and_injected_failures_are_present() -> None:
    public, _ = committed_pair()
    fixtures = public["parser_failure_fixtures"]
    assert len(fixtures) >= 4
    assert {row["factor"] for row in fixtures} >= {
        "action_choice",
        "diagnosis",
        "claim_drafts",
        "citation_selections",
    }
    assert all(row["expected"] == "INVALID_OUTPUT" for row in fixtures)


def test_overlap_audit_covers_all_available_public_development_material() -> None:
    public, _ = committed_pair()
    audit = public["overlap_audit"]
    assert audit["status"] == "PASS"
    assert audit["reference_file_count"] >= len(suite.REFERENCE_PATHS)
    assert audit["candidate_rendered_prompt_count"] == 24 * 2 + 24 * 5
    assert all(audit["checks"].values())
    assert set(audit["reference_file_hashes"]) >= {
        str(path) for path in suite.REFERENCE_PATHS
    }
