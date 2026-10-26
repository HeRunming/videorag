from __future__ import annotations

import base64
import copy
import importlib.util
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/p23_102_global_distinctiveness_v6.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("r23b_v6_tested", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reseal_bundle(tool, bundle):
    payload = copy.deepcopy(bundle)
    payload.pop("bundle_payload_sha256", None)
    payload["bundle_payload_sha256"] = tool.semantic_hash(payload)
    return payload


def packet_binding(tool, packet):
    return tool._packet_binding(packet)


def review_fixture(tool):
    samples = tool.synthetic_samples()
    manifest = tool.build_slot_manifest(len(samples))
    bundle = tool.build_authoring_bundle(samples, manifest)
    record = bundle["successful_component_records"][0]
    packet = tool.build_review_packet(
        record,
        record["component_record"]["source_binding"],
        tool._expected_stratum(record["component_record"]["family_role"]),
    )
    registry = tool.build_synthetic_principal_registry()
    binding = packet_binding(tool, packet)
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
    return manifest, bundle, record, packet, registry, left, right


def test_synthetic_bundle_plan_commitment_and_preflight0() -> None:
    tool = load_tool()
    samples = tool.synthetic_samples()
    manifest = tool.build_slot_manifest(len(samples))
    bundle = tool.build_authoring_bundle(samples, manifest)

    assert bundle["decision_token"] == "R23_B_V6_DESIGN_READY"
    assert bundle["decision"] == "DESIGN_PREFLIGHT_PASS"
    assert len(bundle["sealed_inputs"]) == 3
    assert len(bundle["successful_component_records"]) == 6
    assert len(bundle["primary_queries"]) == 15
    assert tool.verify_bundle(bundle, manifest)["status"] == "PASS"
    assert tool.verify_plan(tool.build_plan())["status"] == "PASS"
    request = tool.build_external_commitment_request()
    assert tool.verify_external_commitment_request(request)["status"] == "PASS"
    assert tool.run_preflight()["model_calls"] == 0
    assert tool.run_preflight()["authorization_calls"] == 0


def test_verify_requires_external_slot_manifest_and_exact_slot_order() -> None:
    tool = load_tool()
    samples = tool.synthetic_samples()
    manifest = tool.build_slot_manifest(len(samples))
    bundle = tool.build_authoring_bundle(samples, manifest)

    with pytest.raises(
        tool.ContractError, match="R23B_TRUSTED_SLOT_MANIFEST_REQUIRED"
    ):
        tool.verify_bundle(bundle, None)

    other = tool.build_slot_manifest(
        len(samples), manifest_id="different-external-manifest"
    )
    with pytest.raises(
        tool.ContractError, match="R23B_SLOT_MANIFEST_BINDING_MISMATCH"
    ):
        tool.verify_bundle(bundle, other)


def test_canonicalization_failed_identity_cannot_self_report() -> None:
    tool = load_tool()

    class Unknown:
        def __init__(self, value: str) -> None:
            self.value = value

    manifest = tool.build_slot_manifest(1)
    bundle = tool.build_authoring_bundle([Unknown("left")], manifest)
    sealed = bundle["sealed_inputs"][0]
    assert sealed["canonicalization_status"] == "CANONICALIZATION_FAILED"
    assert sealed["exact_input_sha256"] == sealed["raw_bytes_sha256"]
    tool.verify_bundle(bundle, manifest)

    for field in (
        "sample_identity_sha256",
        "content_input_sha256",
        "sample_key",
        "slot_identity_sha256",
    ):
        tampered = copy.deepcopy(bundle)
        tampered["sealed_inputs"][0][field] = (
            "forged"
            if field == "sample_key"
            else "sha256:" + "f" * 64
        )
        tampered = reseal_bundle(tool, tampered)
        with pytest.raises(
            tool.ContractError, match="R23B_SEALED_INPUT_IDENTITY_MISMATCH"
        ):
            tool.verify_bundle(tampered, manifest)

    component_tampered = copy.deepcopy(bundle)
    component_tampered["sealed_inputs"][0]["component_identities"] = [
        {
            "component_ordinal": 1,
            "component_key": "forged-component",
            "exact_component_input_sha256": "sha256:" + "1" * 64,
            "component_content_sha256": "sha256:" + "2" * 64,
            "component_identity_sha256": "sha256:" + "3" * 64,
        }
    ]
    component_tampered = reseal_bundle(tool, component_tampered)
    with pytest.raises(
        tool.ContractError, match="R23B_SEALED_INPUT_IDENTITY_MISMATCH"
    ):
        tool.verify_bundle(component_tampered, manifest)


def test_raw_bytes_and_exact_input_mismatch_reject() -> None:
    tool = load_tool()

    class Unknown:
        pass

    manifest = tool.build_slot_manifest(1)
    bundle = tool.build_authoring_bundle([Unknown()], manifest)

    exact = copy.deepcopy(bundle)
    exact["sealed_inputs"][0]["exact_input_sha256"] = "sha256:" + "a" * 64
    exact = reseal_bundle(tool, exact)
    with pytest.raises(
        tool.ContractError, match="R23B_EXACT_INPUT_RAW_BYTES_MISMATCH"
    ):
        tool.verify_bundle(exact, manifest)

    raw = copy.deepcopy(bundle)
    raw["sealed_inputs"][0]["raw_bytes_base64"] = base64.b64encode(
        b"forged"
    ).decode("ascii")
    raw = reseal_bundle(tool, raw)
    with pytest.raises(tool.ContractError, match="R23B_RAW_BYTES_HASH_MISMATCH"):
        tool.verify_bundle(raw, manifest)


def test_same_audit_envelope_different_slots_records_duplicate_and_rejects() -> None:
    tool = load_tool()

    class Stateless:
        __slots__ = ()

    manifest = tool.build_slot_manifest(2, manifest_id="duplicate-content")
    bundle = tool.build_authoring_bundle([Stateless(), Stateless()], manifest)
    tool.verify_bundle(bundle, manifest)
    left, right = bundle["sealed_inputs"]

    assert left["audit_input"] == right["audit_input"]
    assert left["slot_identity_sha256"] != right["slot_identity_sha256"]
    assert left["sample_identity_sha256"] != right["sample_identity_sha256"]
    assert left["content_input_sha256"] == right["content_input_sha256"]
    assert bundle["decision"] == "REJECT_SAMPLE_SET"
    classes = {
        row["identity_class"]
        for row in bundle["global_distinctiveness"][
            "hard_global_identity_failures"
        ]
    }
    assert "content_input_sha256_duplicates" in classes
    assert "component_content_sha256_duplicates" not in classes
    assert bundle["global_distinctiveness"]["content_duplicates"]


def test_malformed_duplicate_public_ids_still_reject_globally() -> None:
    tool = load_tool()
    malformed = [
        {
            "sample_key": "duplicate",
            "family_role": "bad",
            "components": [{"component_key": "component-duplicate"}],
        },
        {
            "sample_key": "duplicate",
            "family_role": "also-bad",
            "components": [{"component_key": "component-duplicate"}],
        },
    ]
    manifest = tool.build_slot_manifest(2)
    bundle = tool.build_authoring_bundle(malformed, manifest)
    tool.verify_bundle(bundle, manifest)

    assert bundle["decision"] == "REJECT_SAMPLE_SET"
    assert bundle["primary_queries"] == []
    classes = {
        row["identity_class"]
        for row in bundle["global_distinctiveness"][
            "hard_global_identity_failures"
        ]
    }
    assert {"sample_key_duplicates", "component_key_duplicates"} <= classes


def test_review_packet_is_mechanically_derived_from_trusted_record() -> None:
    tool = load_tool()
    _, _, record, packet, _, _, _ = review_fixture(tool)
    assert tool.verify_review_packet(packet, record)["review_packet_key"]

    for field, forged in (
        ("blind_atoms", {"action_claim": "forged", "object_claims": []}),
        ("questions", ["forged"]),
        ("component_identity_sha256", "sha256:" + "a" * 64),
        ("content_sha256", "sha256:" + "b" * 64),
        ("stratum", "local:forged"),
    ):
        tampered = copy.deepcopy(packet)
        tampered["packet_payload"][field] = forged
        tampered["packet_payload_sha256"] = tool.semantic_hash(
            tampered["packet_payload"]
        )
        tampered["review_packet_key"] = tool.semantic_hash(
            {
                "schema": tool.REVIEW_PACKET_SCHEMA_VERSION,
                "version": 6,
                "trusted_component_record_sha256": record[
                    "component_record_sha256"
                ],
                "packet_payload_sha256": tampered["packet_payload_sha256"],
            }
        )
        with pytest.raises(tool.ContractError):
            tool.verify_review_packet(tampered, record)


def test_coordinated_packet_and_receipt_reseal_rejects_vs_trusted_record() -> None:
    tool = load_tool()
    _, _, record, packet, registry, left, right = review_fixture(tool)
    receipt = tool.build_review_receipt(
        packet, record, left, right, None, registry
    )
    assert tool.verify_review_receipt(receipt, record, registry)["status"] == "PASS"

    forged = copy.deepcopy(receipt)
    forged["review_packet"]["packet_payload"]["blind_atoms"][
        "action_claim"
    ] = "forged-action"
    forged["review_packet"]["packet_payload_sha256"] = tool.semantic_hash(
        forged["review_packet"]["packet_payload"]
    )
    forged["review_packet"]["review_packet_key"] = tool.semantic_hash(
        {
            "schema": tool.REVIEW_PACKET_SCHEMA_VERSION,
            "version": 6,
            "trusted_component_record_sha256": record[
                "component_record_sha256"
            ],
            "packet_payload_sha256": forged["review_packet"][
                "packet_payload_sha256"
            ],
        }
    )
    new_binding = packet_binding(tool, forged["review_packet"])
    for reviewer in ("reviewer_1", "reviewer_2"):
        forged[reviewer].update(new_binding)
    payload = copy.deepcopy(forged)
    payload.pop("receipt_payload_sha256")
    forged["receipt_payload_sha256"] = tool.semantic_hash(payload)

    with pytest.raises(
        tool.ContractError,
        match="R23B_REVIEW_PACKET_TRUSTED_RECORD_MISMATCH",
    ):
        tool.verify_review_receipt(forged, record, registry)


class HostileMeta(type):
    def __getattribute__(cls, name):
        if name in {"__module__", "__qualname__", "__mro__", "__dict__"}:
            raise RuntimeError(f"hostile type {name}")
        return super().__getattribute__(name)


class HostileType(metaclass=HostileMeta):
    pass


class HostileMapping(Mapping):
    def __iter__(self):
        raise RuntimeError("hostile iteration")

    def __len__(self):
        raise RuntimeError("hostile length")

    def __getitem__(self, key):
        raise RuntimeError("hostile getitem")

    def items(self):
        raise RuntimeError("hostile items")


class StatefulMapping(Mapping):
    def __init__(self, state: str) -> None:
        self.state = state

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def __getitem__(self, key):
        raise KeyError(key)

    def items(self):
        return iter(())


def test_hostile_metaclass_mapping_and_state_never_leak_native_exception() -> None:
    tool = load_tool()
    for value in (HostileType(), HostileMapping()):
        capture = tool._capture_raw(value)
        assert capture["canonicalization_status"] == "CANONICALIZATION_FAILED"
        assert capture["audit_input"]["tag"] == "UNSUPPORTED_TYPE"
        assert capture["audit_input"]["type_label"]

        manifest = tool.build_slot_manifest(1)
        bundle = tool.build_authoring_bundle([value], manifest)
        assert bundle["decision"] == "ABSTAIN"
        tool.verify_bundle(bundle, manifest)

    left = tool._capture_raw(StatefulMapping("left"))
    right = tool._capture_raw(StatefulMapping("right"))
    assert left["audit_input"]["tag"] == "mapping"
    assert left["audit_input"]["state_status"] == "SAFE_TYPED_STATE"
    assert left["raw_bytes_sha256"] != right["raw_bytes_sha256"]


def test_pair_list_safe_public_key_extraction_and_no_dict_rebuild() -> None:
    tool = load_tool()

    class PairMapping(Mapping):
        def __init__(self):
            self._pairs = [
                (["unhashable"], "ignored"),
                ("sample_key", "safe-public-key"),
            ]

        def __iter__(self):
            return (key for key, _ in self._pairs)

        def __len__(self):
            return len(self._pairs)

        def __getitem__(self, key):
            raise KeyError(key)

        def items(self):
            return iter(self._pairs)

    manifest = tool.build_slot_manifest(1)
    bundle = tool.build_authoring_bundle([PairMapping()], manifest)
    tool.verify_bundle(bundle, manifest)
    assert bundle["sealed_inputs"][0]["sample_key"] == "safe-public-key"

    path = ROOT / ".pytest_cache" / "r23b-v6-pair-list.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle), encoding="utf-8")
    manifest_path = ROOT / ".pytest_cache" / "r23b-v6-slot-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    probe = f"""
import importlib.util, json, pathlib
spec = importlib.util.spec_from_file_location("v6", pathlib.Path({str(TOOL_PATH)!r}))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
bundle = json.loads(pathlib.Path({str(path)!r}).read_text())
manifest = json.loads(pathlib.Path({str(manifest_path)!r}).read_text())
print(json.dumps(m.verify_bundle(bundle, manifest), sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout)["status"] == "PASS"


def test_principal_registry_rejects_alias_case_space_and_role_reuse() -> None:
    tool = load_tool()
    _, _, record, packet, registry, left, right = review_fixture(tool)

    for alias in (
        "Opaque-Reviewer-A",
        " opaque-reviewer-a",
        "opaque-reviewer-a ",
        "opaque- reviewer-a",
        "opaque-reviewer-a  ",
    ):
        forged = copy.deepcopy(left)
        forged["principal_id"] = alias
        with pytest.raises(tool.ContractError):
            tool.evaluate_review_result(
                packet, record, forged, right, None, registry
            )

    role_reuse = copy.deepcopy(left)
    role_reuse["principal_id"] = "opaque-adjudicator-c"
    with pytest.raises(tool.ContractError, match="R23B_PRINCIPAL_ROLE_MISMATCH"):
        tool.evaluate_review_result(
            packet, record, role_reuse, right, None, registry
        )

    duplicate_subject = copy.deepcopy(registry)
    duplicate_subject["principals"][1]["subject_commitment"] = duplicate_subject[
        "principals"
    ][0]["subject_commitment"]
    payload = copy.deepcopy(duplicate_subject)
    payload.pop("registry_payload_sha256")
    duplicate_subject["registry_payload_sha256"] = tool.semantic_hash(payload)
    with pytest.raises(
        tool.ContractError,
        match="R23B_PRINCIPAL_SUBJECT_COMMITMENT_DUPLICATE",
    ):
        tool.verify_principal_registry(duplicate_subject)


def test_registry_binding_and_current_integrity_disclaimer() -> None:
    tool = load_tool()
    plan = tool.build_plan()
    request = tool.build_external_commitment_request(plan)

    schema = request["bindings"]["principal_registry_schema"]
    assert schema["role_exclusivity"] is True
    assert schema["unique_subject_commitment"] is True
    assert request["bindings"]["principal_registry_schema_sha256"] == (
        tool.semantic_hash(schema)
    )
    registry = request["bindings"]["principal_registry_manifest"]
    assert request["bindings"][
        "principal_registry_manifest_payload_sha256"
    ] == registry["registry_payload_sha256"]
    assert tool.verify_principal_registry(registry)["registry_id"]
    assert "does not prove" in request["identity_disclaimer"]
    assert request["external_attested"] is False
    assert plan["review_contract"]["external_signature_absent_claim"] == (
        tool.INTEGRITY_CLAIM
    )


def test_self_test_is_model_and_authorization_free() -> None:
    tool = load_tool()
    result = tool.run_self_test()
    assert result["status"] == "PASS"
    assert result["model_calls"] == 0
    assert result["authorization_calls"] == 0
