from __future__ import annotations

import copy
import importlib.util
import json
import math
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/p23_102_global_distinctiveness_v5.py"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "p23_102_global_distinctiveness_v5", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reseal_bundle(tool, bundle):
    payload = dict(bundle)
    payload.pop("bundle_payload_sha256", None)
    payload["bundle_payload_sha256"] = tool.semantic_hash(payload)
    return payload


def reseal_row(tool, row):
    payload = dict(row)
    payload.pop("row_payload_sha256", None)
    row["row_payload_sha256"] = tool.semantic_hash(payload)


def reseal_plan(tool, plan):
    payload = dict(plan)
    payload.pop("plan_payload_sha256", None)
    payload["plan_payload_sha256"] = tool.semantic_hash(payload)
    return payload


def packet_payload(packet):
    return packet["packet_payload"]


def packet_binding(tool, packet):
    return tool._packet_binding(packet)


def test_synthetic_bundle_passes_and_contains_complete_sealed_inputs() -> None:
    tool = load_tool()
    samples = tool.synthetic_samples()
    bundle = tool.build_authoring_bundle(samples)
    tool.verify_bundle(bundle)

    assert bundle["decision"] == "DESIGN_PREFLIGHT_PASS"
    assert bundle["decision_token"] == "R23_B_V5_DESIGN_READY"
    assert len(bundle["sealed_inputs"]) == len(samples)
    assert [
        tool._audit_decode(row["audit_input"]) for row in bundle["sealed_inputs"]
    ] == samples
    assert all(row["raw_bytes_base64"] for row in bundle["sealed_inputs"])
    assert all(
        row["canonicalization_status"] == "CANONICAL"
        for row in bundle["sealed_inputs"]
    )
    assert len(bundle["sample_results"]) == len(samples)
    assert bundle["global_distinctiveness"]["status"] == "PASS"
    assert bundle["cardinality"]["status"] == "PASS"
    assert bundle["decision_derivation"]["derived_decision"] == bundle["decision"]
    assert bundle["scope"]["model_calls"] == 0
    assert bundle["scope"]["authorization_created_or_consumed"] is False
    assert bundle["public_verifier"] == {
        "integrity_claim": tool.INTEGRITY_CLAIM,
        "execution": False,
        "external_attested": False,
    }


def test_verify_bundle_rejects_resealed_query_tamper_and_resealed_duplicate() -> None:
    tool = load_tool()
    bundle = tool.build_authoring_bundle(tool.synthetic_samples())

    tampered = copy.deepcopy(bundle)
    row = tampered["primary_queries"][0]
    row["query_text"] += " forged"
    row["query_sha256"] = tool.semantic_hash(row["query_text"])
    reseal_row(tool, row)
    tampered = reseal_bundle(tool, tampered)
    with pytest.raises(
        tool.ContractError, match="R23B_BUNDLE_RECOMPUTATION_MISMATCH"
    ):
        tool.verify_bundle(tampered)

    duplicate = copy.deepcopy(bundle)
    second = duplicate["primary_queries"][1]
    first = duplicate["primary_queries"][0]
    second["query_text"] = first["query_text"]
    second["query_sha256"] = tool.semantic_hash(second["query_text"])
    reseal_row(tool, second)
    duplicate = reseal_bundle(tool, duplicate)
    with pytest.raises(
        tool.ContractError, match="R23B_BUNDLE_RECOMPUTATION_MISMATCH"
    ):
        tool.verify_bundle(duplicate)


def test_verify_bundle_is_strict_about_complete_schema_and_runtime_hashes() -> None:
    tool = load_tool()
    bundle = tool.build_authoring_bundle(tool.synthetic_samples())

    missing = copy.deepcopy(bundle)
    missing.pop("sealed_inputs")
    missing = reseal_bundle(tool, missing)
    with pytest.raises(tool.ContractError, match="R23B_BUNDLE_FIELD_SET_INVALID"):
        tool.verify_bundle(missing)

    forged_hash = copy.deepcopy(bundle)
    forged_hash["provenance"]["visual_registry_sha256"] = tool.semantic_hash(
        "forged registry"
    )
    forged_hash = reseal_bundle(tool, forged_hash)
    with pytest.raises(
        tool.ContractError, match="R23B_BUNDLE_RECOMPUTATION_MISMATCH"
    ):
        tool.verify_bundle(forged_hash)


def test_verify_plan_rejects_resealed_threshold_hash_policy_and_schema_tamper() -> None:
    tool = load_tool()
    plan = tool.build_plan()
    tool.verify_plan(plan)

    mutations = [
        lambda value: value["runtime_constants"].__setitem__(
            "jaccard_max_exclusive", 0.99
        ),
        lambda value: value["provenance"].__setitem__(
            "tool_source_sha256", tool.semantic_hash("fake tool")
        ),
        lambda value: value["fixed_gates"].__setitem__(
            "ambient_tuple_global_uniqueness", False
        ),
        lambda value: value["review_policy"].__setitem__(
            "count_rule", "round(rate*candidate_count)"
        ),
        lambda value: value["replacement_policy"].__setitem__(
            "automatic_rewrite_permitted", True
        ),
        lambda value: value["schemas"]["sample"].__setitem__(
            "$id", "forged-schema"
        ),
    ]
    for mutate in mutations:
        tampered = copy.deepcopy(plan)
        mutate(tampered)
        tampered = reseal_plan(tool, tampered)
        with pytest.raises(
            tool.ContractError, match="R23B_PLAN_RUNTIME_CONTRACT_MISMATCH"
        ):
            tool.verify_plan(tampered)


def test_current_integrity_verifiers_do_not_claim_external_authorization() -> None:
    tool = load_tool()
    bundle = tool.build_authoring_bundle(tool.synthetic_samples())
    plan = tool.build_plan()
    request = tool.build_external_commitment_request(plan)

    for result in (
        tool.verify_bundle(bundle),
        tool.verify_plan(plan),
        tool.verify_external_commitment_request(request),
    ):
        assert result["integrity_claim"] == tool.INTEGRITY_CLAIM
        assert result["execution"] is False
        assert result["external_attested"] is False

    assert request["bindings"]["tool_source_sha256"] == tool.file_sha256(
        TOOL_PATH
    )
    assert request["bindings"]["tests_source_sha256"] == tool.file_sha256(
        ROOT / tool.TEST_FILE
    )
    assert request["bindings"]["design_doc_sha256"] == tool.file_sha256(
        ROOT / tool.DESIGN_DOC
    )
    assert request["bindings"]["plan_payload_sha256"] == plan[
        "plan_payload_sha256"
    ]
    assert request["bindings"]["gate_manifest_sha256"] == tool.semantic_hash(
        tool.GATE_MANIFEST
    )
    assert request["bindings"]["schema_manifest_sha256"] == tool.semantic_hash(
        tool.schema_manifest()
    )
    assert request["bindings"]["commitment_request_schema_sha256"] == (
        tool.semantic_hash(tool.COMMITMENT_REQUEST_SCHEMA)
    )
    assert request["bindings"]["runtime_constants"] == tool.runtime_constants()


def test_coordinated_code_change_simulation_never_becomes_external_attestation(
    tmp_path: Path,
) -> None:
    source = TOOL_PATH.read_text(encoding="utf-8")
    temp_tools = tmp_path / "tools"
    temp_tools.mkdir()
    mutated_path = temp_tools / TOOL_PATH.name
    mutated_path.write_text(
        source.replace(
            "JACCARD_MAX_EXCLUSIVE = 0.92",
            "JACCARD_MAX_EXCLUSIVE = 0.91",
            1,
        ),
        encoding="utf-8",
    )
    (temp_tools / "p23_102_query_authoring_v2.py").write_bytes(
        (ROOT / "tools/p23_102_query_authoring_v2.py").read_bytes()
    )
    temp_tests = tmp_path / "tooling/tests"
    temp_tests.mkdir(parents=True)
    (temp_tests / "test_p23_102_global_distinctiveness_v5.py").write_bytes(
        (
            ROOT
            / "tooling/tests/test_p23_102_global_distinctiveness_v5.py"
        ).read_bytes()
    )
    temp_design = tmp_path / "docs/design"
    temp_design.mkdir(parents=True)
    (temp_design / "p23_102_global_distinctiveness_v5.md").write_bytes(
        (ROOT / "docs/design/p23_102_global_distinctiveness_v5.md").read_bytes()
    )
    probe = f"""
import importlib.util, json, pathlib
path = pathlib.Path({str(mutated_path)!r})
spec = importlib.util.spec_from_file_location("mutated_r23b_v5", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
plan = module.build_plan()
request = module.build_external_commitment_request(plan)
print(json.dumps({{
    "plan": module.verify_plan(plan),
    "request": module.verify_external_commitment_request(request),
}}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    result = __import__("json").loads(completed.stdout)
    assert result["plan"]["external_attested"] is False
    assert result["request"]["external_attested"] is False
    assert result["plan"]["integrity_claim"].endswith(
        "NOT_EXTERNAL_AUTHORIZATION"
    )


def test_family_role_closed_far_count_ordering_and_component_requirements() -> None:
    tool = load_tool()

    unknown = tool.synthetic_samples()[0]
    unknown["family_role"] = "far_unknown_role"
    result = tool.author_sample_or_abstain(unknown)
    assert result["reasons"] == ["R23B_FAMILY_ROLE_UNREGISTERED"]

    single_far = tool.synthetic_samples()[0]
    single_far["components"] = single_far["components"][:1]
    single_far["composition_atoms"] = {"relation": "single"}
    result = tool.author_sample_or_abstain(single_far)
    assert result["reasons"] == ["R23B_FAR_ROLE_REQUIRES_AT_LEAST_TWO_COMPONENTS"]

    unordered = tool.synthetic_samples()[0]
    unordered["composition_atoms"] = {"relation": "single"}
    result = tool.author_sample_or_abstain(unordered)
    assert result["reasons"] == ["R23B_MULTI_COMPONENT_ORDERED_RELATION_REQUIRED"]

    missing_property = tool.synthetic_samples()[0]
    missing_property["components"][0]["ambient_tuple"]["acoustic_properties"] = {
        "timbre": None,
        "loudness": None,
        "temporal_pattern": None,
    }
    result = tool.author_sample_or_abstain(missing_property)
    assert result["reasons"] == [
        "R23B_COMPONENT_AMBIENT_EVENT_PLUS_PROPERTY_REQUIRED"
    ]


def test_atom_specificity_rejects_generic_holding_container() -> None:
    tool = load_tool()
    atoms = {
        "kind": "event",
        "action": "holding",
        "objects": ["container"],
        "attributes": [],
        "location": None,
        "state": None,
    }
    with pytest.raises(
        tool.ContractError,
        match="R23B_VISUAL_DISCRIMINATIVE_DIMENSIONS_INSUFFICIENT",
    ):
        tool.validate_visual_atoms(atoms)

    atoms["attributes"] = ["red"]
    atoms["location"] = "counter"
    accepted = tool.validate_visual_atoms(atoms)
    assert tool.discriminative_dimensions(accepted) == ("attribute", "location")


def test_visual_kind_is_in_atoms_signatures_and_mechanical_query_text() -> None:
    tool = load_tool()
    event = copy.deepcopy(tool.synthetic_samples()[0]["components"][0]["visual_atoms"])
    state = copy.deepcopy(event)
    state["kind"] = "state"

    event_texts = tool.derive_visual_texts(event)
    state_texts = tool.derive_visual_texts(state)
    assert event_texts["content_atoms"][0] == "kind:event"
    assert state_texts["content_atoms"][0] == "kind:state"
    assert event_texts["visual_query"] != state_texts["visual_query"]
    assert tool.semantic_hash(event_texts["content_atoms"]) != tool.semantic_hash(
        state_texts["content_atoms"]
    )

    sample = tool.synthetic_samples()[0]
    authored = tool.author_sample(sample)
    visual_row = authored["primary_queries"][0]
    assert tool.query_to_content_atoms(visual_row) == visual_row["content_atoms"]
    tampered = copy.deepcopy(visual_row)
    tampered["query_text"] = tampered["query_text"].replace(
        "kind event", "kind state"
    )
    with pytest.raises(
        tool.ContractError, match="R23B_QUERY_TO_ATOMS_TEXT_MISMATCH"
    ):
        tool.query_to_content_atoms(tampered)

    family = tool.derive_family_texts(sample)
    assert "kind event" in family["family_query"]
    assert "visual:kind:event" in family["content_atoms"]


@pytest.mark.parametrize(
    ("action", "objects", "attributes", "location", "state"),
    [
        ("cutting", ["carrot"], [], None, None),
        ("holding", ["knife"], [], "counter", None),
        ("standing", ["person"], ["red"], "table", None),
    ],
)
def test_visual_requires_two_independent_discriminative_dimensions(
    action, objects, attributes, location, state
) -> None:
    tool = load_tool()
    atoms = {
        "kind": "event",
        "action": action,
        "objects": objects,
        "attributes": attributes,
        "location": location,
        "state": state,
    }
    dimensions = tool.discriminative_dimensions(atoms)
    if len(dimensions) < 2:
        with pytest.raises(tool.ContractError):
            tool.validate_visual_atoms(atoms)
    else:
        assert tool.validate_visual_atoms(atoms)


def test_mixed_abstain_retains_every_input_and_successful_sample_result() -> None:
    tool = load_tool()
    samples = tool.synthetic_samples()
    samples[1]["family_role"] = "unknown"
    bundle = tool.build_authoring_bundle(samples)
    tool.verify_bundle(bundle)

    assert bundle["decision"] == "ABSTAIN"
    assert len(bundle["sealed_inputs"]) == 3
    assert len(bundle["sample_results"]) == 3
    assert len(bundle["primary_queries"]) == 10
    assert [row["disposition"] for row in bundle["sample_results"]] == [
        "STRUCTURED_CANDIDATE",
        "ABSTAIN",
        "STRUCTURED_CANDIDATE",
    ]
    assert bundle["sample_results"][1]["failure_stage"] == (
        "STRUCTURED_INPUT_VALIDATION"
    )
    assert bundle["replacement_governance"]["replacement_pointer"] is None
    assert bundle["replacement_governance"]["replacement_exhaustion"] == (
        "NOT_EVALUATED"
    )
    assert bundle["budgets"]["input_slot_count"] == 3


def test_prevalidation_canonicalization_failure_and_unhashable_atoms_are_audited() -> None:
    tool = load_tool()
    samples = tool.synthetic_samples()
    samples[0]["components"][0]["visual_atoms"]["location"] = math.nan
    samples[1]["components"][0]["visual_atoms"]["objects"] = [["knife"]]
    bundle = tool.build_authoring_bundle(samples)
    tool.verify_bundle(bundle)

    assert bundle["decision"] == "ABSTAIN"
    nan_slot = bundle["sealed_inputs"][0]
    assert nan_slot["canonicalization_status"] == "CANONICALIZATION_FAILED"
    assert nan_slot["capture_reasons"] == ["CANONICALIZATION_FAILED"]
    assert bundle["sample_results"][0]["failure_stage"] == (
        "INPUT_CAPTURE_CANONICALIZATION"
    )
    assert bundle["sample_results"][0]["reasons"] == ["CANONICALIZATION_FAILED"]
    assert bundle["sample_results"][1]["failure_stage"] == (
        "STRUCTURED_INPUT_VALIDATION"
    )
    assert bundle["sample_results"][1]["reasons"][0].startswith(
        "R23B_PREVALIDATION_EXCEPTION:"
    )
    assert bundle["sample_results"][2]["disposition"] == "STRUCTURED_CANDIDATE"
    assert bundle["budgets"]["input_slot_count"] == 3
    assert bundle["human_review"]["candidate_count"] == 2
    assert bundle["replacement_governance"]["replacement_pointer"] is None


def test_nan_json_roundtrip_verifies_in_fresh_process(tmp_path: Path) -> None:
    tool = load_tool()
    samples = tool.synthetic_samples()
    samples[0]["components"][0]["visual_atoms"]["location"] = math.nan
    bundle = tool.build_authoring_bundle(samples)
    path = tmp_path / "nan-bundle.json"
    path.write_text(
        json.dumps(bundle, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    probe = f"""
import importlib.util, json, pathlib
tool_path = pathlib.Path({str(TOOL_PATH)!r})
spec = importlib.util.spec_from_file_location("r23b_v5_fresh", tool_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
bundle = json.loads(pathlib.Path({str(path)!r}).read_text(encoding="utf-8"))
result = module.verify_bundle(bundle)
print(json.dumps({{"result": result, "decision": bundle["decision"]}}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    result = json.loads(completed.stdout)
    assert result["result"]["status"] == "PASS"
    assert result["decision"] == "ABSTAIN"


def test_nan_and_nonhashable_fixture_verifies_in_fresh_process(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    samples = tool.synthetic_samples()
    samples[0]["components"][0]["visual_atoms"]["location"] = math.nan
    samples[1]["components"][0]["visual_atoms"]["objects"] = [["knife"]]
    bundle = tool.build_authoring_bundle(samples)
    path = tmp_path / "nan-nonhashable-bundle.json"
    path.write_text(
        json.dumps(bundle, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    probe = f"""
import importlib.util, json, pathlib
tool_path = pathlib.Path({str(TOOL_PATH)!r})
spec = importlib.util.spec_from_file_location("r23b_v5_fresh_combo", tool_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
bundle = json.loads(pathlib.Path({str(path)!r}).read_text(encoding="utf-8"))
module.verify_bundle(bundle)
print(json.dumps({{
    "decision": bundle["decision"],
    "dispositions": [row["disposition"] for row in bundle["sample_results"]],
}}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    result = json.loads(completed.stdout)
    assert result["decision"] == "ABSTAIN"
    assert result["dispositions"][:2] == ["ABSTAIN", "ABSTAIN"]


def test_canonical_typed_audit_mapping_reorder_bytes_and_unknown_object() -> None:
    tool = load_tool()

    class AddressRepr:
        pass

    left = {"z": b"\x00\xff", "a": math.inf, "opaque": AddressRepr()}
    right = {"opaque": AddressRepr(), "a": math.inf, "z": b"\x00\xff"}
    left_capture = tool._capture_raw_bytes(left)
    right_capture = tool._capture_raw_bytes(right)

    assert left_capture == right_capture
    assert left_capture["raw_encoding"] == "CANONICAL_TYPED_AUDIT_JSON_UTF8"
    assert left_capture["raw_encoding_schema"] == (
        tool.RAW_AUDIT_ENCODING_SCHEMA_VERSION
    )
    encoded_text = json.dumps(left_capture["audit_input"], sort_keys=True)
    assert "base64" in encoded_text
    assert "+Infinity" in encoded_text
    assert "0x" not in encoded_text
    assert "repr" not in encoded_text


def test_canonical_typed_audit_is_stable_across_fresh_processes() -> None:
    probe = f"""
import importlib.util, json, math, pathlib
path = pathlib.Path({str(TOOL_PATH)!r})
spec = importlib.util.spec_from_file_location("r23b_v5_cross_process", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
value = {{"opaque": object(), "bytes": b"\\x00\\xff", "float": math.nan}}
print(json.dumps(module._capture_raw_bytes(value), sort_keys=True))
"""
    outputs = [
        subprocess.run(
            [sys.executable, "-c", probe],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        ).stdout
        for _ in range(2)
    ]
    assert outputs[0] == outputs[1]


def test_opaque_raw_value_still_produces_verifiable_abstain_audit_chain() -> None:
    tool = load_tool()

    class Opaque:
        def __repr__(self) -> str:
            return "<opaque-fixture>"

    bundle = tool.build_authoring_bundle([Opaque()])
    tool.verify_bundle(bundle)

    assert bundle["decision"] == "ABSTAIN"
    audit = bundle["sealed_inputs"][0]["audit_input"]
    assert audit["tag"] == "UNSUPPORTED_TYPE"
    assert audit["type"].endswith("<locals>.Opaque")
    assert audit["state_status"] == "SAFE_TYPED_STATE"
    assert audit["state"]["tag"] == "mapping"
    assert "repr" not in audit
    assert bundle["sample_results"][0]["failure_stage"] == (
        "INPUT_CAPTURE_CANONICALIZATION"
    )
    assert bundle["sample_results"][0]["reasons"] == ["CANONICALIZATION_FAILED"]


def test_empty_input_is_audited_fail_closed_not_vacuous_pass() -> None:
    tool = load_tool()
    bundle = tool.build_authoring_bundle([])
    tool.verify_bundle(bundle)

    assert bundle["decision"] == "ABSTAIN"
    assert bundle["sealed_inputs"] == []
    assert bundle["sample_results"] == []
    assert bundle["primary_queries"] == []
    assert bundle["global_distinctiveness"]["status"] == "FAIL_CLOSED"
    assert bundle["global_distinctiveness"]["gates"][
        "nonempty_primary_query_set"
    ]["status"] == "FAIL_CLOSED"
    assert bundle["cardinality"]["status"] == "FAIL_CLOSED"
    assert set(bundle["cardinality"]["blocking_checks"]) == {
        "minimum_bundle_sample_count",
        "minimum_bundle_component_count",
        "minimum_expected_query_count",
    }


def test_global_reject_retains_successes_all_inputs_review_and_budget() -> None:
    tool = load_tool()
    samples = tool.synthetic_samples()
    samples[1]["components"][0]["ambient_tuple"] = copy.deepcopy(
        samples[0]["components"][0]["ambient_tuple"]
    )
    bundle = tool.build_authoring_bundle(samples)
    tool.verify_bundle(bundle)

    assert bundle["decision"] == "REJECT_SAMPLE_SET"
    assert len(bundle["sealed_inputs"]) == 3
    assert len(bundle["sample_results"]) == 3
    assert len(bundle["primary_queries"]) == 15
    assert all(
        row["disposition"] == "REJECTED_BY_GLOBAL_GATE"
        for row in bundle["sample_results"]
    )
    assert bundle["human_review"]["status"] == "INTERFACE_ONLY_NOT_EXECUTED"
    assert bundle["budgets"]["model_calls_in_this_task"] == 0


def test_query_keys_are_mechanical_and_duplicate_ids_fail_global_gate() -> None:
    tool = load_tool()
    samples = tool.synthetic_samples()
    bundle = tool.build_authoring_bundle(samples)
    for row in bundle["primary_queries"]:
        expected = tool.derive_query_key(
            sample_identity_sha256=row["sample_identity_sha256"],
            component_identity_sha256=row["component_identity_sha256"],
            component_ordinal=row["component_ordinal"],
            query_kind=row["query_kind"],
        )
        assert row["query_key"] == expected

    duplicates = tool.synthetic_samples()
    duplicates[1]["sample_key"] = duplicates[0]["sample_key"]
    duplicates[1]["components"][0]["component_key"] = (
        duplicates[0]["components"][0]["component_key"]
    )
    rejected = tool.build_authoring_bundle(duplicates)
    gate = rejected["global_distinctiveness"]["gates"][
        "global_sample_component_query_key_identity_uniqueness"
    ]
    assert rejected["decision"] == "REJECT_SAMPLE_SET"
    assert gate["status"] == "FAIL_CLOSED"
    assert gate["findings"]["sample_key_duplicates"]
    assert gate["findings"]["component_key_duplicates"]

    duplicate_identity = tool.synthetic_samples()
    clone = copy.deepcopy(duplicate_identity[0])
    clone["sample_key"] = "renamed-clone"
    for index, component in enumerate(clone["components"], 1):
        component["component_key"] = f"renamed-clone-{index}"
    duplicate_identity.append(clone)
    rejected = tool.build_authoring_bundle(duplicate_identity)
    gate = rejected["global_distinctiveness"]["gates"][
        "global_sample_component_query_key_identity_uniqueness"
    ]
    assert gate["status"] == "FAIL_CLOSED"
    assert gate["findings"]["query_key_duplicates"]
    assert gate["findings"]["sample_identity_sha256_duplicates"]
    assert gate["findings"]["component_identity_sha256_duplicates"]


def test_duplicate_component_identity_cross_sample_is_global_reject() -> None:
    tool = load_tool()
    samples = tool.synthetic_samples()
    duplicate_component = copy.deepcopy(samples[0]["components"][0])
    duplicate_component["component_key"] = "renamed-cross-sample-component"
    samples[1]["components"][0] = duplicate_component
    bundle = tool.build_authoring_bundle(samples)
    gate = bundle["global_distinctiveness"]["gates"][
        "global_sample_component_query_key_identity_uniqueness"
    ]

    assert bundle["decision"] == "REJECT_SAMPLE_SET"
    findings = gate["findings"]["component_identity_sha256_duplicates"]
    assert len(findings) == 1
    assert findings[0]["locations"] == [
        "slot:1:component:1",
        "slot:2:component:1",
    ]
    review = bundle["human_review"]
    assert review["raw_candidate_occurrence_count"] == 6
    assert review["candidate_count"] == 5
    assert len(
        {
            packet_payload(row)["component_identity_sha256"]
            for row in review["review_rows"]
        }
    ) == len(review["review_rows"])


def test_duplicate_noncanonical_sample_identity_is_global_reject() -> None:
    tool = load_tool()
    bundle = tool.build_authoring_bundle([{"bad": math.nan}, {"bad": math.nan}])
    findings = bundle["global_distinctiveness"]["gates"][
        "global_sample_component_query_key_identity_uniqueness"
    ]["findings"]

    assert bundle["decision"] == "REJECT_SAMPLE_SET"
    assert findings["sample_identity_sha256_duplicates"][0]["locations"] == [
        "slot:1",
        "slot:2",
    ]
    assert all(
        row["disposition"] == "REJECTED_BY_GLOBAL_IDENTITY_GATE"
        for row in bundle["sample_results"]
    )


def test_duplicate_ids_preserve_exact_values_and_audit_chain() -> None:
    tool = load_tool()
    samples = tool.synthetic_samples()
    samples[1]["sample_key"] = samples[0]["sample_key"]
    samples[2]["components"][0]["component_key"] = samples[0]["components"][0][
        "component_key"
    ]
    bundle = tool.build_authoring_bundle(samples)
    tool.verify_bundle(bundle)
    findings = bundle["global_distinctiveness"]["gates"][
        "global_sample_component_query_key_identity_uniqueness"
    ]["findings"]

    assert findings["sample_key_duplicates"][0]["value"] == "opaque-alpha"
    assert findings["component_key_duplicates"][0]["value"] == "opaque-alpha-a"
    assert len(bundle["sealed_inputs"]) == 3
    assert len(bundle["sample_results"]) == 3
    assert bundle["decision_derivation"]["derived_decision"] == (
        "REJECT_SAMPLE_SET"
    )


def test_review_sampling_uses_content_media_hash_not_renameable_ids() -> None:
    tool = load_tool()
    original = tool.build_authoring_bundle(tool.synthetic_samples())
    renamed_samples = tool.synthetic_samples()
    for sample_index, sample in enumerate(renamed_samples, 1):
        sample["sample_key"] = f"renamed-sample-{sample_index}"
        for component_index, component in enumerate(sample["components"], 1):
            component["component_key"] = (
                f"renamed-component-{sample_index}-{component_index}"
            )
    renamed = tool.build_authoring_bundle(renamed_samples)

    original_packets = [
        (
            packet_payload(row)["component_identity_sha256"],
            packet_payload(row)["content_sha256"],
            packet_payload(row)["media_binding_sha256"],
        )
        for row in original["human_review"]["review_rows"]
    ]
    renamed_packets = [
        (
            packet_payload(row)["component_identity_sha256"],
            packet_payload(row)["content_sha256"],
            packet_payload(row)["media_binding_sha256"],
        )
        for row in renamed["human_review"]["review_rows"]
    ]
    assert original_packets == renamed_packets


def test_review_count_is_ceil_for_six_and_seven_candidates() -> None:
    tool = load_tool()
    base = tool.synthetic_samples()
    six = tool.build_authoring_bundle(base)
    assert six["human_review"]["candidate_count"] == 6
    assert six["human_review"]["planned_review_count"] == math.ceil(0.2 * 6) == 2

    seven_samples = copy.deepcopy(base)
    local = copy.deepcopy(base[0])
    local["sample_key"] = "opaque-local"
    local["family_role"] = "local_v15_structure"
    local["components"] = [local["components"][0]]
    local["components"][0]["component_key"] = "opaque-local-a"
    local["components"][0]["ambient_tuple"] = {
        "event_kind": "beep",
        "acoustic_properties": {
            "timbre": "crisp",
            "loudness": "faint",
            "temporal_pattern": "brief",
        },
    }
    local["components"][0]["media_binding"] = tool._media("local-a", 19000)
    local["composition_atoms"] = {"relation": "single"}
    seven_samples.append(local)
    seven = tool.build_authoring_bundle(seven_samples)
    assert seven["human_review"]["candidate_count"] == 7
    assert seven["human_review"]["planned_review_count"] == math.ceil(0.2 * 7) == 2
    strata = {
        packet_payload(row)["stratum"].split(":", 1)[0]
        for row in seven["human_review"]["review_rows"]
    }
    assert strata == {"far", "local"}


def test_review_three_strata_count_three_has_full_role_coverage_no_duplicate() -> None:
    tool = load_tool()
    samples = tool.synthetic_samples()
    successes = []
    for slot, sample in enumerate(samples, 1):
        identity = tool._capture_input_identity(sample, slot)
        successes.append((tool.author_sample(sample, identity), identity))
    candidates = [
        tool._review_candidate(authored, identity, 1)
        for authored, identity in successes
    ]
    selected = tool._select_review_candidates(candidates, 3)

    assert {row["stratum"] for row in selected} == {
        "far:far_structural",
        "far:far_continuity_anaphora",
        "far:far_vocalization_asr_ambiguity",
    }
    assert (
        len(
            {
                (row["sample_identity_sha256"], row["component_ordinal"])
                for row in selected
            }
        )
        == 3
    )


def test_review_candidate_pools_and_final_are_component_identity_deduplicated() -> None:
    tool = load_tool()
    samples = tool.synthetic_samples()
    successes = []
    for slot, sample in enumerate(samples, 1):
        identity = tool._capture_input_identity(sample, slot)
        successes.append((tool.author_sample(sample, identity), identity))
    candidate = tool._review_candidate(*successes[0], 1)
    duplicate = copy.deepcopy(candidate)
    duplicate["sample_identity_sha256"] = tool.semantic_hash("other-sample")
    duplicate["component_ordinal"] = 2
    duplicate["selection_hash"] = tool.semantic_hash("later-duplicate")
    selected = tool._select_review_candidates([candidate, duplicate], 2)

    assert len(selected) == 1
    assert selected[0]["component_identity_sha256"] == candidate[
        "component_identity_sha256"
    ]


def test_review_packets_are_blind_exactly_bound_and_unfilled() -> None:
    tool = load_tool()
    bundle = tool.build_authoring_bundle(tool.synthetic_samples())
    review = bundle["human_review"]
    assert review["policy"]["reviewer_count"] == 2
    assert "adjudication" in review["policy"]["conflict_rule"]
    assert "FAIL_CLOSED" in review["policy"]["missing_rule"]
    for row in review["review_rows"]:
        payload = packet_payload(row)
        assert set(payload["blind_atoms"]) == {"action_claim", "object_claims"}
        assert "target_answer" not in row
        assert row["reviewer_1"] is None
        assert row["reviewer_2"] is None
        assert row["adjudication"] is None
        assert row["decision"] is None
        assert row["packet_payload_sha256"] == tool.semantic_hash(payload)
        assert payload["media_binding_sha256"] == tool.semantic_hash(
            payload["media_binding"]
        )
        assert payload["evidence_binding_sha256"] == tool.semantic_hash(
            {
                "evidence_sha256": payload["media_binding"]["evidence_sha256"],
                "evidence_start_ms": payload["media_binding"]["evidence_start_ms"],
                "evidence_end_ms": payload["media_binding"]["evidence_end_ms"],
            }
        )


def test_review_missing_conflict_and_adjudication_policy() -> None:
    tool = load_tool()
    packet = tool.build_authoring_bundle(tool.synthetic_samples())["human_review"][
        "review_rows"
    ][0]
    binding = packet_binding(tool, packet)
    passed = {
        **binding,
        "reviewer_id": "reviewer-a",
        "action_correct": True,
        "object_tokens_correct": True,
        "decision": "PASS",
        "reasons": [],
    }
    failed = {
        **binding,
        "reviewer_id": "reviewer-b",
        "action_correct": False,
        "object_tokens_correct": True,
        "decision": "FAIL",
        "reasons": ["action mismatch"],
    }
    assert tool.evaluate_review_result(packet, None, passed, None)["reason"] == (
        "MISSING_REQUIRED_REVIEWER"
    )
    assert tool.evaluate_review_result(packet, passed, failed, None)["reason"] == (
        "CONFLICT_REQUIRES_ADJUDICATION"
    )
    adjudication = {
        **binding,
        "adjudicator_id": "adjudicator-c",
        "decision": "FAIL",
        "reasons": ["action mismatch confirmed"],
    }
    resolved = tool.evaluate_review_result(packet, passed, failed, adjudication)
    assert resolved == {
        "status": "COMPLETE",
        "decision": "REJECT_SAMPLE",
        "reason": "ADJUDICATED_CONFLICT",
    }
    same_as_reviewer = {
        **binding,
        "adjudicator_id": "reviewer-a",
        "decision": "FAIL",
        "reasons": ["not independent"],
    }
    assert tool.evaluate_review_result(
        packet, passed, failed, same_as_reviewer
    ) == {
        "status": "FAIL_CLOSED",
        "decision": "REJECT_SAMPLE",
        "reason": "ADJUDICATOR_NOT_INDEPENDENT",
    }


def test_cross_packet_replay_rejected_and_receipt_tamper_fails() -> None:
    tool = load_tool()
    packets = tool.build_authoring_bundle(tool.synthetic_samples())["human_review"][
        "review_rows"
    ]
    left_packet, right_packet = packets

    def submission(packet, reviewer):
        return {
            **packet_binding(tool, packet),
            "reviewer_id": reviewer,
            "action_correct": True,
            "object_tokens_correct": True,
            "decision": "PASS",
            "reasons": [],
        }

    left = submission(left_packet, "reviewer-a")
    replayed = submission(right_packet, "reviewer-b")
    result = tool.evaluate_review_result(left_packet, left, replayed, None)
    assert result["status"] == "FAIL_CLOSED"
    assert result["reason"] == "REVIEWER_2_PACKET_BINDING_MISMATCH"

    right = submission(left_packet, "reviewer-b")
    receipt = tool.build_review_receipt(left_packet, left, right, None)
    assert tool.verify_review_receipt(receipt)["status"] == "PASS"

    tampered = copy.deepcopy(receipt)
    tampered["decision"]["reason"] = "forged"
    with pytest.raises(
        tool.ContractError, match="R23B_REVIEW_RECEIPT_HASH_MISMATCH"
    ):
        tool.verify_review_receipt(tampered)

    resealed_packet_tamper = copy.deepcopy(receipt)
    resealed_packet_tamper["review_packet"]["packet_payload"]["media_binding"][
        "evidence_end_ms"
    ] += 1
    payload = copy.deepcopy(resealed_packet_tamper)
    payload.pop("receipt_payload_sha256")
    resealed_packet_tamper["receipt_payload_sha256"] = tool.semantic_hash(payload)
    with pytest.raises(
        tool.ContractError,
        match="R23B_REVIEW_PACKET_PAYLOAD_HASH_MISMATCH",
    ):
        tool.verify_review_receipt(resealed_packet_tamper)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["blind_atoms"].__setitem__(
            "action_claim", "forged-action"
        ),
        lambda payload: payload["questions"].__setitem__(
            0, "Forged review question?"
        ),
        lambda payload: payload.__setitem__(
            "component_identity_sha256",
            "sha256:" + "f" * 64,
        ),
        lambda payload: payload.__setitem__(
            "stratum", "far:forged-stratum"
        ),
    ],
)
def test_review_packet_payload_tamper_resealed_receipt_rejects(mutate) -> None:
    tool = load_tool()
    packet = tool.build_authoring_bundle(tool.synthetic_samples())["human_review"][
        "review_rows"
    ][0]
    binding = packet_binding(tool, packet)
    reviewer_1 = {
        **binding,
        "reviewer_id": "reviewer-a",
        "action_correct": True,
        "object_tokens_correct": True,
        "decision": "PASS",
        "reasons": [],
    }
    reviewer_2 = {
        **binding,
        "reviewer_id": "reviewer-b",
        "action_correct": True,
        "object_tokens_correct": True,
        "decision": "PASS",
        "reasons": [],
    }
    receipt = tool.build_review_receipt(
        packet, reviewer_1, reviewer_2, None
    )
    mutate(receipt["review_packet"]["packet_payload"])
    receipt_payload = copy.deepcopy(receipt)
    receipt_payload.pop("receipt_payload_sha256")
    receipt["receipt_payload_sha256"] = tool.semantic_hash(receipt_payload)

    with pytest.raises(
        tool.ContractError,
        match="R23B_REVIEW_PACKET_PAYLOAD_HASH_MISMATCH",
    ):
        tool.verify_review_receipt(receipt)


def test_packet_itself_blind_question_identity_and_stratum_tamper_rejects() -> None:
    tool = load_tool()
    packet = tool.build_authoring_bundle(tool.synthetic_samples())["human_review"][
        "review_rows"
    ][0]
    for field, forged in (
        ("blind_atoms", {"action_claim": "forged", "object_claims": []}),
        ("questions", ["forged"]),
        ("sample_identity_sha256", "sha256:" + "a" * 64),
        ("stratum", "local:forged"),
    ):
        tampered = copy.deepcopy(packet)
        tampered["packet_payload"][field] = forged
        with pytest.raises(
            tool.ContractError,
            match="R23B_REVIEW_PACKET_PAYLOAD_HASH_MISMATCH",
        ):
            tool._validate_review_packet(tampered)


def test_duplicate_public_ids_all_malformed_still_hard_global_reject() -> None:
    tool = load_tool()
    malformed = [
        {
            "sample_key": "duplicate-sample",
            "family_role": "unknown-role",
            "components": [
                {
                    "component_key": "duplicate-component",
                    "visual_atoms": {},
                    "ambient_tuple": {},
                    "media_binding": {},
                }
            ],
            "composition_atoms": {},
        },
        {
            "sample_key": "duplicate-sample",
            "family_role": "also-unknown",
            "components": [
                {
                    "component_key": "duplicate-component",
                    "visual_atoms": {"bad": True},
                    "ambient_tuple": {"bad": True},
                    "media_binding": {"bad": True},
                }
            ],
            "composition_atoms": {"bad": True},
        },
    ]
    bundle = tool.build_authoring_bundle(malformed)
    tool.verify_bundle(bundle)

    assert bundle["decision"] == "REJECT_SAMPLE_SET"
    assert bundle["primary_queries"] == []
    assert all(
        row["disposition"] == "REJECTED_BY_GLOBAL_IDENTITY_GATE"
        for row in bundle["sample_results"]
    )
    failures = bundle["global_distinctiveness"][
        "hard_global_identity_failures"
    ]
    classes = {row["identity_class"] for row in failures}
    assert {"sample_key_duplicates", "component_key_duplicates"} <= classes
    assert bundle["decision_derivation"]["decision_precedence"][1] == (
        "HARD_GLOBAL_IDENTITY_FAILURES"
    )


def test_unknown_same_type_safe_dict_state_hashes_differ() -> None:
    tool = load_tool()

    class StatefulUnknown:
        def __init__(self, state: str) -> None:
            self.state = state

    left = tool._capture_raw_bytes(StatefulUnknown("left"))
    right = tool._capture_raw_bytes(StatefulUnknown("right"))

    assert left["audit_input"]["tag"] == "UNSUPPORTED_TYPE"
    assert left["audit_input"]["state_status"] == "SAFE_TYPED_STATE"
    assert left["raw_bytes_sha256"] != right["raw_bytes_sha256"]
    assert left["audit_input"]["state_sha256"] != right["audit_input"][
        "state_sha256"
    ]


def test_unknown_same_type_safe_slots_state_hashes_differ() -> None:
    tool = load_tool()

    class SlottedUnknown:
        __slots__ = ("state",)

        def __init__(self, state: str) -> None:
            self.state = state

    left = tool._capture_raw_bytes(SlottedUnknown("left"))
    right = tool._capture_raw_bytes(SlottedUnknown("right"))

    assert left["audit_input"]["state_status"] == "SAFE_TYPED_STATE"
    assert left["raw_bytes_sha256"] != right["raw_bytes_sha256"]
    assert left["audit_input"]["state_sha256"] != right["audit_input"][
        "state_sha256"
    ]


def test_unknown_without_safe_state_is_position_bound_not_content_claimed() -> None:
    tool = load_tool()

    class SlotUnknown:
        __slots__ = ()

    bundle = tool.build_authoring_bundle([SlotUnknown(), SlotUnknown()])
    tool.verify_bundle(bundle)

    left, right = bundle["sealed_inputs"]
    assert left["audit_input"]["state_status"] == "UNAVAILABLE"
    assert left["audit_input"] == right["audit_input"]
    assert left["sample_identity_sha256"] != right["sample_identity_sha256"]
    assert bundle["decision"] == "ABSTAIN"
    assert bundle["global_distinctiveness"][
        "hard_global_identity_failures"
    ] == []


class _UnhashableKeyMapping(Mapping):
    def __init__(self) -> None:
        self._entries = [
            (["list-key"], {"value": 1}),
            ({"dict": "key"}, ["value"]),
        ]

    def __iter__(self):
        return (key for key, _ in self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __getitem__(self, key):
        raise KeyError(key)

    def items(self):
        return iter(self._entries)


class _HostileMapping(Mapping):
    def __iter__(self):
        raise RuntimeError("hostile iteration")

    def __len__(self) -> int:
        raise RuntimeError("hostile length")

    def __getitem__(self, key):
        raise RuntimeError("hostile getitem")

    def items(self):
        raise RuntimeError("hostile items")

    def get(self, key, default=None):
        raise RuntimeError("hostile get")


def test_mapping_unhashable_keys_pair_list_cross_process_verify(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    bundle = tool.build_authoring_bundle([_UnhashableKeyMapping()])
    tool.verify_bundle(bundle)
    audit = bundle["sealed_inputs"][0]["audit_input"]
    assert audit["tag"] == "mapping"
    assert {entry["key"]["tag"] for entry in audit["entries"]} == {
        "list",
        "mapping",
    }

    path = tmp_path / "unhashable-mapping-bundle.json"
    path.write_text(json.dumps(bundle, sort_keys=True), encoding="utf-8")
    probe = f"""
import importlib.util, json, pathlib
tool_path = pathlib.Path({str(TOOL_PATH)!r})
spec = importlib.util.spec_from_file_location("r23b_v5_pair_mapping", tool_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
bundle = json.loads(pathlib.Path({str(path)!r}).read_text(encoding="utf-8"))
print(json.dumps(module.verify_bundle(bundle), sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert json.loads(completed.stdout)["status"] == "PASS"


def test_hostile_mapping_never_leaks_native_exception() -> None:
    tool = load_tool()
    bundle = tool.build_authoring_bundle([_HostileMapping()])
    tool.verify_bundle(bundle)

    assert bundle["decision"] == "ABSTAIN"
    audit = bundle["sealed_inputs"][0]["audit_input"]
    assert audit["tag"] == "UNSUPPORTED_TYPE"
    assert audit["capture_error_type"] == "builtins.RuntimeError"

    malformed = copy.deepcopy(bundle)
    malformed["sealed_inputs"][0]["audit_input"] = {
        "tag": "mapping",
        "entries": [{"key": {"tag": "list", "items": []}}],
    }
    typed_payload = {
        "schema": malformed["sealed_inputs"][0]["raw_encoding_schema"],
        "version": malformed["sealed_inputs"][0]["raw_encoding_version"],
        "value": malformed["sealed_inputs"][0]["audit_input"],
    }
    malformed["sealed_inputs"][0]["raw_encoding_payload_sha256"] = (
        tool.semantic_hash(typed_payload)
    )
    raw_bytes = tool.canonical_bytes(typed_payload)
    malformed["sealed_inputs"][0]["raw_bytes_base64"] = (
        __import__("base64").b64encode(raw_bytes).decode("ascii")
    )
    malformed["sealed_inputs"][0]["raw_bytes_sha256"] = tool.bytes_hash(raw_bytes)
    malformed = reseal_bundle(tool, malformed)
    with pytest.raises(tool.ContractError):
        tool.verify_bundle(malformed)


def test_red_team_duplicate_query_and_signature_gates_remain_active() -> None:
    tool = load_tool()
    authored = tool.author_sample(tool.synthetic_samples()[0])
    left = authored["primary_queries"][0]
    right = copy.deepcopy(left)
    right["query_key"] = tool.semantic_hash("different-key")
    right["sample_identity_sha256"] = tool.semantic_hash("different-sample")
    right["component_identity_sha256"] = tool.semantic_hash("different-component")
    right["query_key"] = tool.derive_query_key(
        sample_identity_sha256=right["sample_identity_sha256"],
        component_identity_sha256=right["component_identity_sha256"],
        component_ordinal=right["component_ordinal"],
        query_kind=right["query_kind"],
    )
    reseal_row(tool, right)
    analysis = tool.analyze_global_distinctiveness([left, right], [], [])
    assert analysis["status"] == "FAIL_CLOSED"
    assert (
        analysis["gates"]["normalized_exact_uniqueness_all_primary"]["status"]
        == "FAIL_CLOSED"
    )
    assert (
        analysis["gates"]["content_atom_signature_uniqueness"]["status"]
        == "FAIL_CLOSED"
    )


def test_plan_preflight_and_self_test_are_model_free() -> None:
    tool = load_tool()
    plan = tool.build_plan()
    tool.verify_plan(plan)
    preflight = tool.run_preflight()
    self_test = tool.run_self_test()

    assert plan["decision"] == tool.DECISION_TOKEN
    assert plan["scope"]["model_calls"] == 0
    assert plan["scope"]["authorization_created_or_consumed"] is False
    assert preflight["status"] == "PASS"
    assert preflight["model_calls"] == 0
    assert preflight["authorization_calls"] == 0
    assert self_test["status"] == "PASS"
    assert self_test["model_calls"] == 0
