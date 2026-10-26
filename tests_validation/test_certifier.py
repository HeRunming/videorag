from __future__ import annotations

from copy import deepcopy

import pytest

from av_trace.util import load_json, sha256_json
from av_trace_validation.certifier import CertificationError, certify_dataset
from av_trace_validation.generator import generate_validator_artifacts
from av_trace_validation.io import write_json


def test_certifier_fails_closed_on_missing_proof(tmp_path):
    root = tmp_path / "bundle"
    index = generate_validator_artifacts(output_root=root)
    family_id = index["families"][0]["family_id"]
    (root / "families" / family_id / "proofs" / "blocked.json").unlink()
    with pytest.raises(CertificationError) as exc:
        certify_dataset(validator_root=root, strict=True)
    assert exc.value.certificate["status"] == "FAIL"
    assert any(item["code"] == "CERT-MISSING" for item in exc.value.certificate["issues"])


def test_certifier_detects_author_validator_overlap(tmp_path):
    root = tmp_path / "bundle"
    index = generate_validator_artifacts(output_root=root)
    entry = index["families"][0]
    family_path = root / entry["family_path"]
    family = load_json(family_path)
    family["annotation"]["authors"] = [family["annotation"]["validators"][0]]
    write_json(family_path, family)
    index_doc = load_json(root / "artifact_index.json")
    index_doc["families"][0]["family_hash"] = "sha256:" + "0" * 64
    write_json(root / "artifact_index.json", index_doc)
    certificate = certify_dataset(validator_root=root)
    assert certificate["status"] == "FAIL"
    assert any(item["code"] == "CERT-INDEPENDENCE" for item in certificate["issues"])


def test_certifier_detects_trajectory_hash_tampering(tmp_path):
    root = tmp_path / "bundle"
    index = generate_validator_artifacts(output_root=root)
    family_id = index["families"][0]["family_id"]
    path = root / "families" / family_id / "trajectories" / "synthetic_validator_a.clean.json"
    trajectory = load_json(path)
    trajectory["final_output"]["natural_language_answer"] += " tampered"
    write_json(path, trajectory)
    certificate = certify_dataset(validator_root=root)
    assert certificate["status"] == "FAIL"
    assert any(item["code"] == "CERT-LINK" for item in certificate["issues"])


def test_certifier_recomputes_route_step_costs_from_backend_schedule(tmp_path):
    root = tmp_path / "bundle"
    index = generate_validator_artifacts(output_root=root)
    family_id = index["families"][0]["family_id"]
    routes_path = root / "families" / family_id / "feasible_routes.json"
    routes = load_json(routes_path)
    record = next(
        item
        for item in routes
        if any(route["feasible"] for route in item["route_alternatives"])
    )
    route = next(item for item in record["route_alternatives"] if item["feasible"])
    route["steps"][0]["cost"] += 0.5
    route["required_cost"] += 0.5
    write_json(routes_path, routes)

    denominator_path = root / "premature_stop_denominator.json"
    denominator = load_json(denominator_path)
    denominator_record = next(
        item for item in denominator["records"] if item["record_id"] == record["record_id"]
    )
    denominator_record["route_alternatives"] = deepcopy(record["route_alternatives"])
    write_json(denominator_path, denominator)
    artifact_index = load_json(root / "artifact_index.json")
    artifact_index["denominator_hash"] = sha256_json(denominator)
    write_json(root / "artifact_index.json", artifact_index)

    certificate = certify_dataset(validator_root=root)
    assert certificate["status"] == "FAIL"
    assert any(item["code"] == "CERT-ROUTE" for item in certificate["issues"])
