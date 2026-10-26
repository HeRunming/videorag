from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "data/rehearsal_plan/controller_v2_holdout_contract.json"
PUBLIC = (
    ROOT
    / "data/rehearsal_plan/controller_v2_holdout/public_execution_packet.json"
)
KEY = (
    ROOT
    / "data/rehearsal_plan/controller_v2_holdout/restricted_evaluator_key.json"
)
ACTION_SCHEMA = ROOT / "docs/spec/controller_v2_action_schema.json"
STATE_SCHEMA = ROOT / "docs/spec/controller_v2_state_schema.json"
TASK111 = ROOT / "data/restricted/scale1b/controller_dev/suite_contract.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash_without(obj: dict, field: str) -> str:
    value = {key: item for key, item in obj.items() if key != field}
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def test_v2_schemas_are_valid_and_closed():
    action = _load(ACTION_SCHEMA)
    state = _load(STATE_SCHEMA)
    Draft202012Validator.check_schema(action)
    Draft202012Validator.check_schema(state)
    assert action["additionalProperties"] is False
    assert action["required"] == ["action_index"]
    assert action["properties"]["action_index"]["enum"] == [0, 1, 2, 3]
    assert state["additionalProperties"] is False
    assert state["required"] == [
        "p_sufficient",
        "covered_claim_handles",
        "missing_modalities",
        "missing_hops",
        "missingness_cause",
        "recovery_intent",
    ]
    assert set(state["properties"]) == set(state["required"])


def test_holdout_is_sealed_balanced_and_label_separated():
    contract = _load(CONTRACT)
    public = _load(PUBLIC)
    key = _load(KEY)
    assert contract["contract_hash"] == _canonical_hash_without(
        contract, "contract_hash"
    )
    assert contract["artifact_hashes"]["public_execution_packet"] == _sha256(PUBLIC)
    assert contract["artifact_hashes"]["restricted_evaluator_key"] == _sha256(KEY)
    assert contract["artifact_hashes"]["action_schema"] == _sha256(ACTION_SCHEMA)
    assert contract["artifact_hashes"]["state_schema"] == _sha256(STATE_SCHEMA)

    cases = public["cases"]
    labels = key["case_labels"]
    assert len(cases) == len(labels) == 28
    assert Counter(key["primary_strata"].values()) == {
        "routing": 4,
        "pointer_read": 4,
        "finalize": 4,
        "abstain": 4,
        "missingness": 4,
        "recovery": 4,
        "adversarial_menu_order": 4,
    }
    assert {case["case_id"] for case in cases} == set(labels)
    forbidden_public_keys = {
        "expected_action_index",
        "expected_action",
        "expected_state",
        "oracle_support",
        "required_terms",
        "answer_key",
        "labels",
    }
    assert forbidden_public_keys.isdisjoint(set(_walk_keys(public)))


def test_case_menus_labels_and_terminal_counts_are_consistent():
    public = _load(PUBLIC)
    key = _load(KEY)
    state_validator = Draft202012Validator(_load(STATE_SCHEMA))
    modality_order = ["vision", "speech", "ambient"]
    hop_order = [
        "entity_identity",
        "event_detection",
        "speech_content",
        "ambient_event",
        "temporal_order",
        "cross_modal_binding",
        "causal_link",
        "state_change",
        "comparison",
        "counting",
        "other",
    ]
    terminal = 0
    answer_terminal = 0
    abstain_terminal = 0
    adversarial_positions = []
    state_fields = set(_load(STATE_SCHEMA)["required"])
    for case in public["cases"]:
        assert "primary_stratum" not in case
        assert "secondary_capabilities" not in case
        label = key["case_labels"][case["case_id"]]
        menu = case["action_menu"]
        assert 1 <= len(menu) <= 4
        assert case["action_output_contract"]["allowed_action_indices"] == list(
            range(len(menu))
        )
        assert case["state_output_contract"]["allowed_claim_handles"] == [
            slot["claim_handle"] for slot in case["public_claim_slots"]
        ]
        expected_index = label["action"]["expected_action_index"]
        assert (
            expected_index
            in case["action_output_contract"]["allowed_action_indices"]
        )
        assert label["action"]["expected_action"] == menu[expected_index]
        assert set(label["state"]) == state_fields
        state_validator.validate(label["state"])
        assert set(label["state"]["covered_claim_handles"]) <= set(
            case["state_output_contract"]["allowed_claim_handles"]
        )
        assert label["state"]["missing_modalities"] == sorted(
            label["state"]["missing_modalities"], key=modality_order.index
        )
        assert label["state"]["missing_hops"] == sorted(
            label["state"]["missing_hops"], key=hop_order.index
        )
        if key["primary_strata"][case["case_id"]] == "adversarial_menu_order":
            adversarial_positions.append(expected_index)
        final = label["finalization"]
        if final["terminal_case"]:
            terminal += 1
            if final["expected_mode"] == "answer":
                answer_terminal += 1
            else:
                abstain_terminal += 1
    assert terminal == 8
    assert answer_terminal == abstain_terminal == 4
    assert sorted(adversarial_positions) == [0, 1, 2, 3]


def test_holdout_content_is_distinct_and_contains_no_evaluation_family_markers():
    public = _load(PUBLIC)
    task111 = _load(TASK111)
    old_questions = {
        _norm(case["question"])
        for group in ("controller_cases", "generator_cases")
        for case in task111[group]
    }
    new_questions = [_norm(case["question"]) for case in public["cases"]]
    assert len(set(new_questions)) == 28
    assert not (set(new_questions) & old_questions)
    serialized_cases = json.dumps(public["cases"], sort_keys=True).casefold()
    forbidden = [
        "noaa",
        "evaluation_family",
        "r004",
        "r007",
        "r011",
        "r016",
        "r017",
        "claim.r",
        "e.r",
        "seg.",
        "cand-",
    ]
    assert all(marker not in serialized_cases for marker in forbidden)


def test_task111_protected_artifacts_remain_byte_identical():
    expected = {
        "data/restricted/scale1b/controller_dev/suite_contract.json": (
            "b4aa831e77e6b8f744387f5a02e1516082bf0b990c010dca2a7d8e83d33f3ef7"
        ),
        "data/restricted/scale1b/controller_dev/results.json": (
            "02f10aa9c781f132e81679d221b696453cbf1d04d146f37eb730f44a6aab1c1d"
        ),
        "data/restricted/scale1b/controller_dev/summary.json": (
            "131643b79fc4addb866c1f07e79f503f00f9e659e3f5618f196f61fc6775af96"
        ),
        "data/restricted/scale1b/controller_dev/calls.jsonl": (
            "1c8e433668d10c242179b7393f67791d0a3127af13210bd4010580d668353654"
        ),
        "docs/review/controller_synthetic_competence.md": (
            "4663c65a633a1fcd0df3c3e6434d3c926e4541c3d9f0335b5db266f24d0fb769"
        ),
        "orchestration/results/111_controller_synthetic_competence.txt": (
            "fa641ddbfd31ed19b315f8c88e73c394e8ebebd3c7452ab52465554779b40698"
        ),
    }
    for relative, digest in expected.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
