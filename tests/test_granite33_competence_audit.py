from __future__ import annotations

import json
from pathlib import Path

from av_trace_strong_baselines.competence import (
    evaluate_competence_submission,
    load_submission,
    load_suite,
)
from scripts import audit_granite33_competence_components as audit

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / audit.RUN_DIR


def test_component_audit_preserves_frozen_verdict_and_ineligibility() -> None:
    suite = load_suite(ROOT / audit.SUITE)
    submission = load_submission(RUN_DIR / "submission.json")
    report = evaluate_competence_submission(suite, submission)
    value = audit.build_component_audit(
        suite,
        submission,
        report,
        seal=json.loads((RUN_DIR / "seal.json").read_text()),
        direct_eligibility=json.loads(
            (RUN_DIR / "direct_av_eligibility.json").read_text()
        ),
    )
    assert value["frozen_evaluator_decision"] == (
        "STRONG_BASELINE_COMPETENCE_REPAIR"
    )
    assert value["task172_decision"] == "GRANITE33_COMPETENCE_NO_GO"
    assert value["direct_av"]["eligibility"] == "STRUCTURALLY_INELIGIBLE"
    assert value["direct_av"]["scored_as_zero"] is False


def test_component_audit_separates_raw_action_from_full_envelope() -> None:
    suite = load_suite(ROOT / audit.SUITE)
    submission = load_submission(RUN_DIR / "submission.json")
    report = evaluate_competence_submission(suite, submission)
    value = audit.build_component_audit(
        suite,
        submission,
        report,
        seal=json.loads((RUN_DIR / "seal.json").read_text()),
        direct_eligibility=json.loads(
            (RUN_DIR / "direct_av_eligibility.json").read_text()
        ),
    )
    syntax = value["action_syntax"]
    assert syntax["integer_in_range_action_index"]["correct"] == 24
    assert syntax["full_controller_envelope_valid"]["correct"] == 3
    assert value["action_correctness"]["correct"] == 11
    assert value["joint_six_field_state_raw_exact_match"]["correct"] == 0
