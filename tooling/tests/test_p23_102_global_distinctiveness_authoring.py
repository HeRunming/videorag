from __future__ import annotations

import copy
import importlib.util
import math
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/p23_102_global_distinctiveness_authoring.py"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "p23_102_global_distinctiveness_authoring", TOOL_PATH
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


def test_synthetic_bundle_passes_and_contains_complete_sealed_inputs() -> None:
    tool = load_tool()
    samples = tool.synthetic_samples()
    bundle = tool.build_authoring_bundle(samples)
    tool.verify_bundle(bundle)

    assert bundle["decision"] == "DESIGN_PREFLIGHT_PASS"
    assert bundle["decision_token"] == "R23_B_V3_DESIGN_READY"
    assert len(bundle["sealed_inputs"]) == len(samples)
    assert [row["audit_input"] for row in bundle["sealed_inputs"]] == samples
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
    probe = f"""
import importlib.util, json, pathlib
path = pathlib.Path({str(mutated_path)!r})
spec = importlib.util.spec_from_file_location("mutated_r23b", path)
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


def test_opaque_raw_value_still_produces_verifiable_abstain_audit_chain() -> None:
    tool = load_tool()

    class Opaque:
        def __repr__(self) -> str:
            return "<opaque-fixture>"

    bundle = tool.build_authoring_bundle([Opaque()])
    tool.verify_bundle(bundle)

    assert bundle["decision"] == "ABSTAIN"
    assert bundle["sealed_inputs"][0]["audit_input"] == {
        "$audit_type": "opaque",
        "type": (
            "test_p23_102_global_distinctiveness_authoring."
            "test_opaque_raw_value_still_produces_verifiable_abstain_audit_chain."
            "<locals>.Opaque"
        ),
        "repr": "<opaque-fixture>",
    }
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
        "global_sample_component_query_key_uniqueness"
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
        "global_sample_component_query_key_uniqueness"
    ]
    assert gate["status"] == "FAIL_CLOSED"
    assert gate["findings"]["query_key_duplicates"]


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
        "global_sample_component_query_key_uniqueness"
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
            row["component_identity_sha256"],
            row["content_sha256"],
            row["media_binding_sha256"],
        )
        for row in original["human_review"]["review_rows"]
    ]
    renamed_packets = [
        (
            row["component_identity_sha256"],
            row["content_sha256"],
            row["media_binding_sha256"],
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
    strata = {row["stratum"].split(":", 1)[0] for row in seven["human_review"]["review_rows"]}
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


def test_review_packets_are_blind_exactly_bound_and_unfilled() -> None:
    tool = load_tool()
    bundle = tool.build_authoring_bundle(tool.synthetic_samples())
    review = bundle["human_review"]
    assert review["policy"]["reviewer_count"] == 2
    assert "adjudication" in review["policy"]["conflict_rule"]
    assert "FAIL_CLOSED" in review["policy"]["missing_rule"]
    for row in review["review_rows"]:
        assert set(row["blind_atoms"]) == {"action_claim", "object_claims"}
        assert "target_answer" not in row
        assert row["reviewer_1"] is None
        assert row["reviewer_2"] is None
        assert row["adjudication"] is None
        assert row["decision"] is None
        assert row["media_binding_sha256"] == tool.semantic_hash(
            row["media_binding"]
        )


def test_review_missing_conflict_and_adjudication_policy() -> None:
    tool = load_tool()
    passed = {
        "reviewer_id": "reviewer-a",
        "action_correct": True,
        "object_tokens_correct": True,
        "decision": "PASS",
        "reasons": [],
    }
    failed = {
        "reviewer_id": "reviewer-b",
        "action_correct": False,
        "object_tokens_correct": True,
        "decision": "FAIL",
        "reasons": ["action mismatch"],
    }
    assert tool.evaluate_review_result(None, passed, None)["reason"] == (
        "MISSING_REQUIRED_REVIEWER"
    )
    assert tool.evaluate_review_result(passed, failed, None)["reason"] == (
        "CONFLICT_REQUIRES_ADJUDICATION"
    )
    adjudication = {
        "adjudicator_id": "adjudicator-c",
        "decision": "FAIL",
        "reasons": ["action mismatch confirmed"],
    }
    resolved = tool.evaluate_review_result(passed, failed, adjudication)
    assert resolved == {
        "status": "COMPLETE",
        "decision": "REJECT_SAMPLE",
        "reason": "ADJUDICATED_CONFLICT",
    }
    same_as_reviewer = {
        "adjudicator_id": "reviewer-a",
        "decision": "FAIL",
        "reasons": ["not independent"],
    }
    assert tool.evaluate_review_result(passed, failed, same_as_reviewer) == {
        "status": "FAIL_CLOSED",
        "decision": "REJECT_SAMPLE",
        "reason": "ADJUDICATOR_NOT_INDEPENDENT",
    }


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
