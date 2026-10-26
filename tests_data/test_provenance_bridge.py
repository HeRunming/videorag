from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from av_trace.manifest import GateProfile
from av_trace.schemas import SchemaRegistry
from av_trace.semantic import validate_family
from av_trace.util import load_json, sha256_json
from av_trace_data.provenance import (
    ProvenanceBridgeError,
    episode_source_from_verified_asset,
    validate_episode_provenance,
    validate_verified_asset_record,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REVISION = "1" * 40
MANIFEST_REVISION = "2" * 40


def fixture(relative: str) -> dict:
    return load_json(ROOT / relative)


def manifest() -> dict:
    value = fixture("docs/data/fixtures/positive_acquisition_manifest.json")
    value["source"]["source_revision"] = SOURCE_REVISION
    value["manifest_revision"] = MANIFEST_REVISION
    return value


def family() -> dict:
    value = fixture("docs/spec/fixtures/positive_episode_family.json")
    value["source"]["manifest_revision"] = MANIFEST_REVISION
    return value


def record() -> dict:
    value = fixture("tests_data/fixtures/positive_verified_asset.json")
    value["canonical_upstream"]["revision"] = SOURCE_REVISION
    value["manifest"]["revision"] = MANIFEST_REVISION
    value["manifest"]["sha256"] = sha256_json(manifest())
    return value


def codes(report) -> set[str]:
    return {issue.code for issue in report.issues}


def registered_derivative() -> tuple[dict, dict, dict]:
    derived_manifest = manifest()
    derived_manifest["derived_artifacts"] = [
        {
            "artifact_id": "artifact_clip",
            "artifact_type": "clip",
            "source_asset_id": "asset_syn",
            "uri": "https://example.invalid/artifact-clip.mp4",
            "sha256": "sha256:" + "7" * 64,
            "created_at": "2026-09-05T00:00:00Z",
            "tool_or_protocol": "synthetic-clipper",
            "rights_basis": {
                "license_or_grant_name": "Synthetic fixture grant",
                "version": "1",
                "licensor_or_grantor": "Synthetic Rights Holder",
                "uri": "https://example.invalid/synthetic-grant",
                "scope": "Public derivative release.",
            },
            "release_decision": "allowed",
            "release_audience": "public",
            "evidence_snapshot_hash": "sha256:" + "8" * 64,
            "contains_personal_data": False,
            "substitution_risk_reviewed": True,
        }
    ]
    value = record()
    value["manifest"]["sha256"] = sha256_json(derived_manifest)
    value["acquired_asset"] = {
        "asset_id": "artifact_clip",
        "relationship_to_manifest": "registered_derivative",
        "manifest_artifact_id": "artifact_clip",
        "content_sha256": "sha256:" + "7" * 64,
        "duration_s": 1200.0,
    }
    value["lineage"] = {
        "relationship": "derived",
        "parents": [
            {
                "namespace": "synthetic_direct_grant",
                "asset_id": "synthetic-asset-001",
                "revision": "3" * 40,
                "relation": "excerpt_of",
                "content_sha256": "sha256:" + "0" * 64,
                "source_time_mapping": {
                    "mapping_type": "piecewise_linear",
                    "segments": [
                        {
                            "derived_start_s": 0.0,
                            "derived_end_s": 1200.0,
                            "source_start_s": 10.0,
                            "source_end_s": 1210.0,
                        }
                    ],
                },
            }
        ],
    }
    derived_family = family()
    derived_family["source"] = episode_source_from_verified_asset(
        value, derived_manifest
    )
    for evidence in derived_family["claim_evidence_graph"]["evidence_units"]:
        evidence["provenance"]["asset_id"] = "artifact_clip"
    return derived_manifest, value, derived_family


def test_positive_bridge_converts_to_frozen_episode_source() -> None:
    registry = SchemaRegistry(ROOT)
    value = record()
    report = validate_verified_asset_record(value, manifest(), registry=registry)
    assert report.ok, report.to_dict()
    source = episode_source_from_verified_asset(value, manifest(), registry=registry)
    assert source == family()["source"]
    assert registry.validator("episode-family").schema["$defs"]["source"]


def test_namespaced_manifest_identity_is_independent_of_local_dataset_id() -> None:
    modern_manifest = manifest()
    modern_manifest["dataset_id"] = "synthetic_local_release"
    modern_manifest["source"][
        "source_identifier"
    ] = "synthetic_direct_grant:synthetic-asset-001"
    value = record()
    value["manifest"]["sha256"] = sha256_json(modern_manifest)

    report = validate_verified_asset_record(value, modern_manifest)

    assert report.ok, report.to_dict()


def test_namespaced_manifest_identity_mismatch_is_rejected() -> None:
    modern_manifest = manifest()
    modern_manifest["dataset_id"] = "synthetic_local_release"
    modern_manifest["source"][
        "source_identifier"
    ] = "different_namespace:synthetic-asset-001"
    value = record()
    value["manifest"]["sha256"] = sha256_json(modern_manifest)

    report = validate_verified_asset_record(value, modern_manifest)

    assert not report.ok
    assert "BRIDGE-002" in codes(report)


def test_registered_derivative_lineage_passes_with_auditable_mapping() -> None:
    derived_manifest, value, derived_family = registered_derivative()
    report = validate_episode_provenance(derived_family, derived_manifest, value)
    assert report.ok, report.to_dict()
    semantic_report = validate_family(
        derived_family,
        derived_manifest,
        SchemaRegistry(ROOT),
        verified_asset=value,
    )
    assert semantic_report.ok, semantic_report.to_dict()


def test_semantic_validator_accepts_matching_verified_asset() -> None:
    report = validate_family(
        family(),
        manifest(),
        SchemaRegistry(ROOT),
        verified_asset=record(),
    )
    assert report.ok, report.to_dict()


def test_real_media_validation_requires_verified_asset() -> None:
    report = validate_family(
        family(), manifest(), SchemaRegistry(ROOT), media_mode="real"
    )
    assert not report.ok
    assert "PROV-005" in codes(report)


def test_consistent_stream_hash_tampering_fails_without_bridge_evidence() -> None:
    item = family()
    tampered = "sha256:" + "a" * 64
    item["source"]["streams"][0]["hash"] = tampered
    for evidence in item["claim_evidence_graph"]["evidence_units"]:
        if evidence["stream_id"] == item["source"]["streams"][0]["stream_id"]:
            evidence["provenance"]["stream_hash"] = tampered
    report = validate_family(item, manifest(), SchemaRegistry(ROOT), media_mode="real")
    assert not report.ok
    assert "PROV-005" in codes(report)


def test_synthetic_testing_mode_preserves_fixture_compatibility() -> None:
    report = validate_family(
        family(),
        manifest(),
        SchemaRegistry(ROOT),
        media_mode="synthetic_testing",
    )
    assert report.ok, report.to_dict()


@pytest.mark.parametrize("revision", ["main", "abcdef1", "a" * 40 + " (main)"])
def test_bridge_rejects_mutable_short_and_compound_revisions(revision: str) -> None:
    value = record()
    value["canonical_upstream"]["revision"] = revision
    report = validate_verified_asset_record(value, manifest())
    assert not report.ok
    assert "BRIDGE-002" in codes(report)


@pytest.mark.parametrize("field", ["source", "manifest"])
def test_bridge_rejects_nonimmutable_manifest_revisions(field: str) -> None:
    value = record()
    source_manifest = manifest()
    if field == "source":
        source_manifest["source"]["source_revision"] = "main"
    else:
        source_manifest["manifest_revision"] = "abcdef1"
        value["manifest"]["revision"] = "abcdef1"
    value["manifest"]["sha256"] = sha256_json(source_manifest)
    report = validate_verified_asset_record(value, source_manifest)
    assert not report.ok
    assert "BRIDGE-002" in codes(report)


def test_tampered_stream_hash_is_rejected() -> None:
    value = record()
    value["streams"][1]["sha256"] = "sha256:" + "a" * 64
    report = validate_episode_provenance(family(), manifest(), value)
    assert not report.ok
    assert "PROV-002" in codes(report)


def test_wrong_manifest_revision_is_rejected() -> None:
    value = record()
    value["manifest"]["revision"] = "wrong-revision"
    report = validate_verified_asset_record(value, manifest())
    assert not report.ok
    assert "BRIDGE-002" in codes(report)


def test_unknown_canonical_identity_is_rejected() -> None:
    value = record()
    value["canonical_upstream"]["namespace"] = ""
    report = validate_verified_asset_record(value, manifest())
    assert not report.ok
    assert "BRIDGE-002" in codes(report)


def test_missing_hash_refuses_conversion() -> None:
    value = record()
    value["streams"][0]["sha256"] = None
    with pytest.raises(ProvenanceBridgeError) as raised:
        episode_source_from_verified_asset(value, manifest())
    assert "BRIDGE-004" in codes(raised.value.report)


def test_invalid_evidence_interval_is_rejected() -> None:
    item = family()
    item["claim_evidence_graph"]["evidence_units"][0]["intervals"][0]["end_s"] = 1300.0
    report = validate_episode_provenance(item, manifest(), record())
    assert "TIME-002" in codes(report)


def test_missing_transformation_mapping_is_rejected() -> None:
    value = record()
    value["transformations"][0]["source_time_mapping"]["segments"] = []
    report = validate_episode_provenance(family(), manifest(), value)
    assert "BRIDGE-006" in codes(report)
    assert "TIME-004" in codes(report)


def test_derived_interval_requires_parent_source_time_mapping() -> None:
    value = record()
    value["lineage"] = {
        "relationship": "derived",
        "parents": [
            {
                "namespace": "synthetic_parent",
                "asset_id": "parent1",
                "revision": "p1",
                "relation": "excerpt_of",
                "content_sha256": "sha256:" + "b" * 64,
                "source_time_mapping": {
                    "mapping_type": "piecewise_linear",
                    "segments": [
                        {
                            "derived_start_s": 0.0,
                            "derived_end_s": 90.0,
                            "source_start_s": 500.0,
                            "source_end_s": 590.0,
                        }
                    ],
                },
            }
        ],
    }
    report = validate_episode_provenance(family(), manifest(), value)
    assert "TIME-004" in codes(report)


def test_public_core_is_not_inferred_from_acquisition_approval() -> None:
    acquisition_only = manifest()
    acquisition_only["audit"]["gate_status"] = "acquisition_approved"
    acquisition_only["rights"]["decisions"]["derivative_release"] = "prohibited"
    acquisition_only["rights"]["decisions"]["annotation_release"] = "prohibited"
    acquisition_only["rights"]["decisions"]["transcript_release"] = "prohibited"
    acquisition_only["rights"]["decisions"]["raw_media_release"] = "prohibited"
    value = record()
    value["manifest"]["sha256"] = sha256_json(acquisition_only)
    report = validate_verified_asset_record(
        value,
        acquisition_only,
        GateProfile.PUBLIC_CORE_RELEASE,
    )
    assert not report.ok
    assert {"GATE-001", "GATE-003"} & codes(report)


def test_restricted_compatibility_asset_passes_only_unpooled_profile() -> None:
    restricted_manifest = manifest()
    restricted_manifest["source"]["source_family"] = "COMPATIBILITY_ONLY"
    restricted_manifest["audit"]["gate_status"] = "annotation_approved"
    restricted_manifest["rights"]["copyright_basis"] = "restricted_agreement"
    restricted_manifest["rights"]["decisions"]["derivative_release"] = "prohibited"
    restricted_manifest["rights"]["decisions"]["transcript_release"] = "prohibited"
    restricted_manifest["rights"]["decisions"]["raw_media_release"] = "prohibited"
    value = record()
    value["manifest"]["sha256"] = sha256_json(restricted_manifest)
    value["access"]["rights_status"]["status"] = "approved_restricted_use"
    value["access"]["episode_access_class"] = "restricted_compatibility"

    compatible = validate_verified_asset_record(
        value,
        restricted_manifest,
        GateProfile.EXTERNAL_COMPATIBILITY_UNPOOLED,
    )
    assert compatible.ok, compatible.to_dict()

    public_core = validate_verified_asset_record(
        value,
        restricted_manifest,
        GateProfile.PUBLIC_CORE_RELEASE,
    )
    assert not public_core.ok
    assert {"BRIDGE-007", "GATE-001", "GATE-003"} & codes(public_core)


def test_conflicting_rights_and_technical_access_fail_closed() -> None:
    value = record()
    value["access"]["technical_access"]["status"] = "conflicting"
    value["access"]["rights_status"]["status"] = "conflicting"
    report = validate_verified_asset_record(value, manifest())
    assert not report.ok
    assert "BRIDGE-007" in codes(report)


def test_malformed_bridge_fails_closed_without_exception() -> None:
    value = record()
    value["streams"] = None
    value["acquired_asset"] = []
    report = validate_episode_provenance(family(), manifest(), value)
    assert not report.ok
    assert {"BRIDGE-001", "BRIDGE-004"} <= codes(report)
