from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/controller_v2_evaluator.py"


def _module():
    spec = importlib.util.spec_from_file_location("controller_v2_evaluator", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pre_key_verification_recomputes_seal_and_raw_results():
    evaluator = _module()
    verified = evaluator.verify_pre_key(ROOT)
    audit = verified["verification"]
    assert audit["pre_key_verification_passed"] is True
    assert audit["sealed_artifact_count"] == 6
    assert audit["case_count"] == 28
    assert audit["order_row_count"] == 56
    assert audit["v1_result_count"] == audit["v2_result_count"] == 28
    assert audit["v1_call_count"] == 44
    assert audit["v2_call_count"] == 60
    assert audit["model_process_count"] == 1
    assert audit["exact_v1_v2_order"] is True
    assert audit["public_only_request_hashes_recomputed"] is True
    assert audit["raw_results_recomputed"] is True
    assert audit["constraint_runtime_failure_count"] == 0
    assert audit["process_failure_count"] == 0


def test_pre_key_verification_does_not_touch_restricted_key(monkeypatch):
    evaluator = _module()
    key_name = evaluator.KEY_REL.name
    original_open = Path.open
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text
    original_stat = Path.stat

    def guard(path: Path) -> None:
        if path.name == key_name:
            raise AssertionError("restricted key touched before release")

    def guarded_open(path: Path, *args, **kwargs):
        guard(path)
        return original_open(path, *args, **kwargs)

    def guarded_read_bytes(path: Path, *args, **kwargs):
        guard(path)
        return original_read_bytes(path, *args, **kwargs)

    def guarded_read_text(path: Path, *args, **kwargs):
        guard(path)
        return original_read_text(path, *args, **kwargs)

    def guarded_stat(path: Path, *args, **kwargs):
        guard(path)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(Path, "stat", guarded_stat)
    assert evaluator.verify_pre_key(ROOT)["verification"]["pre_key_verification_passed"]


def test_restricted_key_is_committed_and_mode_0600():
    evaluator = _module()
    key = ROOT / evaluator.KEY_REL
    contract = json.loads((ROOT / evaluator.CONTRACT_REL).read_text(encoding="utf-8"))
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert (
        evaluator._sha256_file(key)
        == contract["artifact_hashes"]["restricted_evaluator_key"]
    )


def test_real_sealed_evaluation_metrics_and_frozen_decision():
    evaluator = _module()
    evaluation = evaluator.evaluate(ROOT)
    assert evaluation["decision"] == "CONTROLLER_V2_HOLDOUT_NO_GO"
    assert (
        evaluation["next_excluded_r017_controller_v2_competence_gate_permitted"]
        is False
    )
    assert evaluation["scientific_evaluation_families_authorized"] is False

    v1 = evaluation["metrics"]["v1"]
    v2 = evaluation["metrics"]["v2"]
    assert v1["action_syntax_valid_count"] == 18
    assert v2["action_syntax_valid_count"] == 28
    assert v1["state_syntax_valid_count"] == 18
    assert v2["state_syntax_valid_count"] == 28
    assert v1["action_correct_count"] == 5
    assert v2["action_correct_count"] == 15
    assert v1["state_exact_count"] == 0
    assert v2["state_exact_count"] == 0
    assert v1["end_to_end_terminal_correct_count"] == 0
    assert v2["end_to_end_terminal_correct_count"] == 0
    assert v2["supported_answer_count"] == 0
    assert v2["correct_abstention_count"] == 0
    assert v2["unsupported_required_claim_count"] == 0
    assert v2["process_failure_count"] == 0
    assert v2["constraint_runtime_failure_count"] == 0

    assert evaluation["deltas"] == {
        "action_correct_count_delta": 10,
        "state_exact_count_delta": 0,
        "end_to_end_terminal_correct_count_delta": 0,
        "unsupported_required_claim_count_delta": 0,
    }
    assert evaluation["paired_transitions"]["state_exactness_2x2"] == {
        "v1_incorrect_v2_incorrect": 28,
        "v1_incorrect_v2_correct": 0,
        "v1_correct_v2_incorrect": 0,
        "v1_correct_v2_correct": 0,
    }
    assert evaluation["paired_transitions"]["terminal_correctness_2x2"] == {
        "v1_incorrect_v2_incorrect": 8,
        "v1_incorrect_v2_correct": 0,
        "v1_correct_v2_incorrect": 0,
        "v1_correct_v2_correct": 0,
    }
    assert not any(evaluation["gates"]["automatic_no_go_conditions"].values())
    assert evaluation["gates"]["all_frozen_gates_passed"] is False


def test_safe_aggregate_excludes_case_scores_and_raw_or_label_content():
    evaluator = _module()
    safe = evaluator.safe_aggregate(evaluator.evaluate(ROOT))
    serialized = json.dumps(safe, sort_keys=True)
    assert "per_case_scores" not in safe
    assert "raw_output_utf8" not in serialized
    assert "required_terms" not in serialized
    assert "expected_action_index" not in serialized
    assert "case_labels" not in serialized


def test_private_writers_use_restricted_permissions(tmp_path: Path):
    evaluator = _module()
    json_path = tmp_path / "restricted/evaluation.json"
    jsonl_path = tmp_path / "restricted/per_case.jsonl"
    evaluator._write_json_private(json_path, {"ok": True})
    evaluator._write_jsonl_private(jsonl_path, [{"ok": True}])
    assert stat.S_IMODE(json_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(json_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(jsonl_path.stat().st_mode) == 0o600
