from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/p23_102_global_distinctiveness_v8.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("r23b_v8_tested", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PairMapping(Mapping):
    def __init__(self, pairs):
        self.pairs = list(pairs)

    def __iter__(self):
        return (key for key, _ in self.pairs)

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, key):
        raise KeyError(key)

    def items(self):
        return iter(self.pairs)


class DictState:
    def __init__(self, value):
        self.value = value


class SlotsState:
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value


def assert_contract_error_only(tool, action) -> None:
    try:
        action()
    except Exception as exc:  # noqa: BLE001 - assertion checks public boundary
        assert isinstance(exc, tool.ContractError)
        assert not isinstance(exc, UnicodeEncodeError)
    else:
        raise AssertionError("expected fail-closed ContractError")


def find_surrogate_envelopes(value):
    found = []
    if type(value) is dict:
        if value.get("tag") == "INVALID_UNICODE_SURROGATE":
            found.append(value)
        for item in value.values():
            found.extend(find_surrogate_envelopes(item))
    elif type(value) is list:
        for item in value:
            found.extend(find_surrogate_envelopes(item))
    return found


def review_fixture(tool):
    samples = tool.synthetic_samples()
    manifest = tool.build_slot_manifest(len(samples), manifest_id="v8-review")
    bundle = tool.build_authoring_bundle(samples, manifest)
    record = bundle["successful_component_records"][0]
    packet = tool.build_review_packet(
        record,
        record["component_record"]["source_binding"],
        tool._expected_stratum(record["component_record"]["family_role"]),
    )
    registry = tool.build_synthetic_principal_registry()
    binding = tool._packet_binding(packet)
    left = {
        **binding,
        "principal_id": "opaque-reviewer-a",
        "action_correct": True,
        "object_tokens_correct": True,
        "decision": "PASS",
        "reasons": [],
    }
    right = {
        **binding,
        "principal_id": "opaque-reviewer-b",
        "action_correct": True,
        "object_tokens_correct": True,
        "decision": "PASS",
        "reasons": [],
    }
    adjudication = {
        **binding,
        "principal_id": "opaque-adjudicator-c",
        "decision": "PASS",
        "reasons": [],
    }
    return manifest, bundle, record, packet, registry, left, right, adjudication


def test_v8_plan_commitment_preflight_and_inherited_counts() -> None:
    tool = load_tool()
    samples = tool.synthetic_samples()
    manifest = tool.build_slot_manifest(len(samples), manifest_id="v8-main")
    bundle = tool.build_authoring_bundle(samples, manifest)

    assert bundle["decision_token"] == "R23_B_V8_DESIGN_READY"
    assert bundle["decision"] == "DESIGN_PREFLIGHT_PASS"
    assert len(bundle["successful_component_records"]) == 6
    assert len(bundle["primary_queries"]) == 15
    assert tool.verify_bundle(bundle, manifest)["status"] == "PASS"
    assert tool.verify_plan(tool.build_plan())["status"] == "PASS"
    request = tool.build_external_commitment_request()
    verified = tool.verify_external_commitment_request(request)
    assert verified["status"] == "PASS"
    assert verified["dependency_count"] >= 15
    preflight = tool.run_preflight()
    assert preflight["model_calls"] == 0
    assert preflight["authorization_calls"] == 0


def test_duplicate_typed_sample_key_preserves_values_positions_and_rejects() -> None:
    tool = load_tool()
    normal = {"sample_key": "same-id", "family_role": "bad", "components": []}
    duplicate = PairMapping(
        [
            ("sample_key", "same-id"),
            ("sample_key", "same-id"),
            ("family_role", "bad"),
            ("components", []),
        ]
    )
    manifest = tool.build_slot_manifest(2, manifest_id="v8-duplicate-sample")
    bundle = tool.build_authoring_bundle([normal, duplicate], manifest)
    tool.verify_bundle(bundle, manifest)

    assert bundle["decision"] == "REJECT_SAMPLE_SET"
    extraction = bundle["sealed_inputs"][1]["sample_key_extraction"]
    assert extraction["status"] == "DUPLICATE_OR_INVALID"
    assert [row["audit_pair_position"] for row in extraction["matches"]] == [2, 3]
    assert [row["string_value"] for row in extraction["matches"]] == [
        "same-id",
        "same-id",
    ]
    failures = {
        row["identity_class"]: row
        for row in bundle["global_distinctiveness"][
            "hard_global_identity_failures"
        ]
    }
    invalid = failures["invalid_or_duplicate_public_keys"]["failures"]
    assert invalid[0]["extraction"]["matches"] == extraction["matches"]
    assert bundle["sealed_inputs"][0]["sample_key"] == "same-id"
    assert bundle["sealed_inputs"][1]["sample_key"] == "unknown"


def test_duplicate_and_invalid_component_public_keys_are_hard_failures() -> None:
    tool = load_tool()
    component = PairMapping(
        [
            ("component_key", "component-x"),
            ("component_key", 7),
        ]
    )
    malformed = PairMapping(
        [
            ("sample_key", "sample-x"),
            ("family_role", "bad"),
            ("components", [component]),
        ]
    )
    manifest = tool.build_slot_manifest(1, manifest_id="v8-duplicate-component")
    bundle = tool.build_authoring_bundle([malformed], manifest)
    tool.verify_bundle(bundle, manifest)
    assert bundle["decision"] == "REJECT_SAMPLE_SET"
    extraction = bundle["sealed_inputs"][0]["component_identities"][0][
        "component_key_extraction"
    ]
    assert extraction["status"] == "DUPLICATE_OR_INVALID"
    assert len(extraction["matches"]) == 2


@pytest.mark.parametrize(
    "tree",
    [
        {"tag": "null", "value": None},
        {"tag": "bool", "value": 1},
        {"tag": "bool", "value": "false"},
        {"tag": "str", "value": 1},
        {"tag": "int", "value": 1},
        {"tag": "int", "value": ""},
        {"tag": "int", "value": "00"},
        {"tag": "int", "value": "-0"},
        {"tag": "int", "value": "+1"},
        {"tag": "float", "value": 1.0},
        {"tag": "float", "value": "1.0"},
        {"tag": "float", "value": "0X1.0P+0"},
        {"tag": "float", "value": "nan"},
        {"tag": "bytes", "base64": 7},
        {"tag": "bytes", "base64": "==="},
        {"tag": "list", "items": "not-a-list"},
        {"tag": "tuple", "items": []},
        {"tag": "set", "items": [{"tag": "int", "value": "1"}]},
        {"tag": "frozenset", "items": [{"tag": "str", "value": "x"}]},
        {"tag": "unknown"},
    ],
)
def test_every_malformed_scalar_or_non_json_tag_is_contract_error(tree) -> None:
    tool = load_tool()
    with pytest.raises(tool.ContractError):
        tool._canonical_json_bytes_from_audit(tree)


def test_valid_scalar_tags_are_exact() -> None:
    tool = load_tool()
    assert tool._canonical_json_bytes_from_audit({"tag": "null"}) == b"null"
    assert tool._canonical_json_bytes_from_audit(
        {"tag": "bool", "value": False}
    ) == b"false"
    assert tool._canonical_json_bytes_from_audit(
        {"tag": "str", "value": "x"}
    ) == b'"x"'
    assert tool._canonical_json_bytes_from_audit(
        {"tag": "int", "value": "-12"}
    ) == b"-12"
    assert tool._canonical_json_bytes_from_audit(
        {"tag": "float", "value": (1.5).hex()}
    ) == b"1.5"
    tool._validate_audit_tree({"tag": "bytes", "base64": "eA=="})
    with pytest.raises(tool.ContractError, match="R23B_CANONICAL_AUDIT_NON_JSON"):
        tool._canonical_json_bytes_from_audit(
            {"tag": "bytes", "base64": "eA=="}
        )


def test_malformed_tree_boundary_never_leaks_native_exception() -> None:
    tool = load_tool()
    hostile = [
        None,
        [],
        {"tag": None},
        {"tag": "mapping", "entries": None},
        {"tag": "list", "items": [{"tag": "int", "value": object()}]},
    ]
    for tree in hostile:
        try:
            tool._canonical_json_bytes_from_audit(tree)
        except Exception as exc:  # noqa: BLE001
            assert isinstance(exc, tool.ContractError)
        else:
            raise AssertionError(f"malformed tree accepted: {tree!r}")


@pytest.mark.parametrize(
    ("value", "codepoint"),
    [
        ("\ud800", "U+D800"),
        ({"\ud801": "mapping-key"}, "U+D801"),
        ({"mapping-value": "\ud802"}, "U+D802"),
        (["list-member", "\ud803"], "U+D803"),
        (DictState("\ud804"), "U+D804"),
        (SlotsState("\ud805"), "U+D805"),
    ],
)
def test_unpaired_surrogate_positions_are_utf8_safe_abstain(value, codepoint) -> None:
    tool = load_tool()
    manifest = tool.build_slot_manifest(1, manifest_id=f"v8-{codepoint}")
    bundle = tool.build_authoring_bundle([value], manifest)

    assert bundle["decision"] == "ABSTAIN"
    assert bundle["sample_results"][0]["disposition"] == "ABSTAIN"
    assert bundle["sealed_inputs"][0]["canonicalization_status"] == (
        "CANONICALIZATION_FAILED"
    )
    assert bundle["sample_results"][0]["reasons"] == ["CANONICALIZATION_FAILED"]
    envelopes = find_surrogate_envelopes(
        bundle["sealed_inputs"][0]["audit_input"]
    )
    assert any(
        row["positions"][0]["codepoint_hex"] == codepoint for row in envelopes
    )
    assert all(
        "\\ud" in row["safe_normalized_escaped"].lower() for row in envelopes
    )
    encoded = tool.canonical_bytes(bundle)
    encoded.decode("utf-8", errors="strict")
    assert tool.verify_bundle(bundle, manifest)["status"] == "PASS"


def test_typed_string_validator_rejects_surrogate_and_bad_diagnostics() -> None:
    tool = load_tool()
    malformed = [
        {"tag": "str", "value": "\ud800"},
        {
            "tag": "INVALID_UNICODE_SURROGATE",
            "failure": "INVALID_UNICODE_SURROGATE",
            "positions": [{"position": 0, "codepoint_hex": "U+0041"}],
            "safe_normalized_escaped": "\\ud800",
        },
        {
            "tag": "INVALID_UNICODE_SURROGATE",
            "failure": "INVALID_UNICODE_SURROGATE",
            "positions": [{"position": 0, "codepoint_hex": "U+D800"}],
            "safe_normalized_escaped": "\ud800",
        },
    ]
    for tree in malformed:
        assert_contract_error_only(tool, lambda tree=tree: tool._validate_audit_tree(tree))


def test_capture_and_typed_pipeline_native_failures_are_contained(monkeypatch) -> None:
    tool = load_tool()

    def native_failure(*_args, **_kwargs):
        raise ValueError("synthetic native failure")

    monkeypatch.setattr(tool, "_audit_encode_safely", native_failure)
    assert_contract_error_only(tool, lambda: tool._capture_raw({"x": 1}))

    monkeypatch.undo()
    tool = load_tool()
    original_canonical = tool.canonical_bytes

    def fallback_failure(value):
        if type(value) is dict and value.get("schema") == (
            tool.RAW_AUDIT_ENCODING_SCHEMA_VERSION
        ):
            raise UnicodeEncodeError("utf-8", "\ud800", 0, 1, "synthetic")
        return original_canonical(value)

    monkeypatch.setattr(tool, "canonical_bytes", fallback_failure)
    assert_contract_error_only(tool, lambda: tool._capture_raw(object()))


def test_malformed_persisted_audit_tree_is_contract_error_only() -> None:
    tool = load_tool()
    value = ["\ud800"]
    manifest = tool.build_slot_manifest(1, manifest_id="v8-malformed-tree")
    bundle = tool.build_authoring_bundle([value], manifest)
    malformed = copy.deepcopy(bundle)
    malformed["sealed_inputs"][0]["audit_input"] = {
        "tag": "list",
        "items": [{"tag": "str", "value": "\ud800"}],
    }
    assert_contract_error_only(
        tool, lambda: tool.verify_bundle(malformed, manifest)
    )


def test_surrogate_bundle_cross_process_reload_and_resealed_tamper(
    tmp_path,
) -> None:
    tool = load_tool()
    values = [
        "\ud800",
        {"\ud801": "key", "value": "\ud802"},
        ["\ud803"],
        DictState("\ud804"),
        SlotsState("\ud805"),
    ]
    manifest = tool.build_slot_manifest(len(values), manifest_id="v8-reload")
    bundle = tool.build_authoring_bundle(values, manifest)
    assert bundle["decision"] in {"ABSTAIN", "REJECT_SAMPLE_SET"}
    assert all(
        row["canonicalization_status"] == "CANONICALIZATION_FAILED"
        for row in bundle["sealed_inputs"]
    )
    bundle_path = tmp_path / "bundle.json"
    manifest_path = tmp_path / "manifest.json"
    bundle_path.write_text(
        json.dumps(bundle, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
        errors="strict",
    )
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
        errors="strict",
    )
    script = """
import importlib.util
import json
import sys
from pathlib import Path
tool_path, bundle_path, manifest_path = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("r23b_v8_reload", tool_path)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
bundle = json.loads(bundle_path.read_text(encoding="utf-8", errors="strict"))
manifest = json.loads(manifest_path.read_text(encoding="utf-8", errors="strict"))
print(json.dumps(tool.verify_bundle(bundle, manifest), sort_keys=True))
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(TOOL_PATH),
            str(bundle_path),
            str(manifest_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert json.loads(completed.stdout)["status"] == "PASS"

    tampered = copy.deepcopy(bundle)
    envelope = find_surrogate_envelopes(
        tampered["sealed_inputs"][0]["audit_input"]
    )[0]
    envelope["positions"][0]["codepoint_hex"] = "U+D801"
    typed = tool._typed_payload(tampered["sealed_inputs"][0]["audit_input"])
    raw_bytes = tool.canonical_bytes(typed)
    sealed = tampered["sealed_inputs"][0]
    sealed["raw_encoding_payload_sha256"] = tool.semantic_hash(typed)
    sealed["raw_bytes_base64"] = tool.base64.b64encode(raw_bytes).decode("ascii")
    sealed["raw_bytes_sha256"] = tool.bytes_hash(raw_bytes)
    sealed["exact_input_sha256"] = sealed["raw_bytes_sha256"]
    payload = copy.deepcopy(tampered)
    payload.pop("bundle_payload_sha256")
    tampered["bundle_payload_sha256"] = tool.semantic_hash(payload)
    assert_contract_error_only(
        tool, lambda: tool.verify_bundle(tampered, manifest)
    )


def test_agreement_requires_null_adjudication_after_full_validation() -> None:
    tool = load_tool()
    _, _, record, packet, registry, left, right, adjudication = review_fixture(tool)
    receipt = tool.build_review_receipt(
        packet, record, left, right, None, registry
    )
    assert receipt["adjudication"] is None
    assert tool.verify_review_receipt(receipt, record, registry)["status"] == "PASS"

    with pytest.raises(
        tool.ContractError,
        match="R23B_UNEXPECTED_ADJUDICATION_WITHOUT_CONFLICT",
    ):
        tool.build_review_receipt(
            packet, record, left, right, adjudication, registry
        )

    bad_role = copy.deepcopy(adjudication)
    bad_role["principal_id"] = "opaque-reviewer-a"
    with pytest.raises(tool.ContractError, match="R23B_PRINCIPAL_ROLE_MISMATCH"):
        tool.build_review_receipt(packet, record, left, right, bad_role, registry)

    bad_binding = copy.deepcopy(adjudication)
    bad_binding["content_sha256"] = "sha256:" + "f" * 64
    with pytest.raises(
        tool.ContractError, match="R23B_ADJUDICATION_PACKET_BINDING_MISMATCH"
    ):
        tool.build_review_receipt(
            packet, record, left, right, bad_binding, registry
        )


def test_conflict_requires_and_validates_adjudication() -> None:
    tool = load_tool()
    _, _, record, packet, registry, left, right, adjudication = review_fixture(tool)
    right = copy.deepcopy(right)
    right["object_tokens_correct"] = False
    right["decision"] = "FAIL"

    with pytest.raises(tool.ContractError, match="R23B_CONFLICT_REQUIRES_ADJUDICATION"):
        tool.build_review_receipt(packet, record, left, right, None, registry)

    receipt = tool.build_review_receipt(
        packet, record, left, right, adjudication, registry
    )
    assert receipt["decision"]["reason"] == "ADJUDICATED_CONFLICT"
    assert receipt["adjudication"] == adjudication


def test_receipt_builder_does_not_carry_unvalidated_mapping() -> None:
    tool = load_tool()
    _, _, record, packet, registry, left, right, _ = review_fixture(tool)

    class ExtraMapping(dict):
        pass

    hostile = ExtraMapping(left)
    hostile["unvalidated"] = "must-not-be-carried"
    with pytest.raises(
        tool.ContractError, match="R23B_REVIEW_SUBMISSION_FIELD_SET_INVALID"
    ):
        tool.build_review_receipt(packet, record, hostile, right, None, registry)


def test_dependency_manifest_binds_parent_tool_and_fixture(monkeypatch) -> None:
    tool = load_tool()
    request = tool.build_external_commitment_request()
    assert tool.verify_external_commitment_request(request)["status"] == "PASS"

    original_file_hash = tool.file_sha256

    def changed_file_hash(path):
        if Path(path) == tool.ROOT / tool.PARENT_AMBIENT_TOOL:
            return "sha256:" + "f" * 64
        return original_file_hash(path)

    monkeypatch.setattr(tool, "file_sha256", changed_file_hash)
    with pytest.raises(
        tool.ContractError,
        match="R23B_DEPENDENCY_CLOSURE_CURRENT_BINDING_MISMATCH",
    ):
        tool.verify_external_commitment_request(request)

    monkeypatch.setattr(tool, "file_sha256", original_file_hash)
    original_fixture = tool.V6.synthetic_samples
    monkeypatch.setattr(
        tool.V6,
        "synthetic_samples",
        lambda: [*original_fixture(), {"fixture": "changed"}],
    )
    with pytest.raises(
        tool.ContractError,
        match="R23B_DEPENDENCY_CLOSURE_CURRENT_BINDING_MISMATCH",
    ):
        tool.verify_external_commitment_request(request)


def test_dependency_manifest_names_required_transitive_closure() -> None:
    tool = load_tool()
    manifest = tool.build_dependency_manifest()
    ids = {row["dependency_id"] for row in manifest["entries"]}
    assert {
        "v8_tool",
        "v7_inherited_tool",
        "v6_inherited_tool",
        "v5_inherited_tool",
        "parent_ambient_tool",
        "v8_tests",
        "v7_inherited_tests",
        "v6_inherited_tests",
        "v5_inherited_tests",
        "v8_design_doc",
        "v5_schema_manifest",
        "v5_gate_manifest",
        "v5_visual_registry_manifest",
        "v5_family_registry_manifest",
        "v5_generator_manifest",
        "parent_ambient_output_schema",
        "v8_typed_audit_schema",
        "v8_review_receipt_schema",
        "review_principal_registry_schema",
        "review_principal_registry_manifest",
        "synthetic_fixture",
    } <= ids


def test_self_test_is_model_and_authorization_free() -> None:
    tool = load_tool()
    result = tool.run_self_test()
    assert result["status"] == "PASS"
    assert result["model_calls"] == 0
    assert result["authorization_calls"] == 0
