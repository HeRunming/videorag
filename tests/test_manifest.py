from __future__ import annotations

import unittest

from av_trace.manifest import GateProfile, validate_manifest_gate
from av_trace.schemas import SchemaRegistry

from tests.helpers import ROOT, fixture, positive_manifest


class ManifestGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = SchemaRegistry(ROOT)

    def test_positive_manifest_passes_all_gates(self) -> None:
        manifest = positive_manifest()
        for gate in GateProfile:
            with self.subTest(gate=gate.value):
                self.assertTrue(validate_manifest_gate(manifest, gate, self.registry).ok)

    def test_unknown_release_decision_fails_closed(self) -> None:
        manifest = fixture("docs/data/fixtures/negative_manifest_unknown_release.json")
        report = validate_manifest_gate(manifest, GateProfile.PUBLIC_RELEASE, self.registry)
        self.assertFalse(report.ok)
        self.assertIn("SCHEMA-VALIDATION", {issue.code for issue in report.issues})

    def test_unknown_rights_decision_fails_annotation_gate(self) -> None:
        manifest = positive_manifest()
        manifest["audit"]["gate_status"] = "annotation_approved"
        manifest["rights"]["decisions"]["transcript_release"] = "unknown_hold"
        report = validate_manifest_gate(manifest, GateProfile.ANNOTATION, self.registry)
        self.assertFalse(report.ok)
        self.assertIn("GATE-002", {issue.code for issue in report.issues})

    def test_annotation_gate_rejects_metadata_only_status(self) -> None:
        manifest = positive_manifest()
        manifest["audit"]["gate_status"] = "metadata_only"
        report = validate_manifest_gate(manifest, GateProfile.ANNOTATION, self.registry)
        self.assertFalse(report.ok)
        self.assertIn("GATE-001", {issue.code for issue in report.issues})

    def test_public_release_requires_allowed_release_decisions(self) -> None:
        manifest = positive_manifest()
        manifest["rights"]["decisions"]["raw_media_release"] = "prohibited"
        report = validate_manifest_gate(manifest, GateProfile.PUBLIC_RELEASE, self.registry)
        self.assertFalse(report.ok)
        self.assertIn("SCHEMA-VALIDATION", {issue.code for issue in report.issues})

    def test_annotation_requires_completed_acquisition(self) -> None:
        manifest = positive_manifest()
        manifest["acquisition"]["status"] = "planned"
        report = validate_manifest_gate(manifest, GateProfile.ANNOTATION, self.registry)
        self.assertIn("GATE-007", {issue.code for issue in report.issues})

    def test_approved_gate_rejects_no_acquisition_method(self) -> None:
        manifest = positive_manifest()
        manifest["acquisition"]["method"] = "none"
        report = validate_manifest_gate(manifest, GateProfile.ACQUISITION, self.registry)
        self.assertIn("GATE-007", {issue.code for issue in report.issues})

    def test_public_artifact_requires_allowed_release(self) -> None:
        manifest = positive_manifest()
        manifest["derived_artifacts"] = [
            {
                "artifact_id": "artifact1",
                "artifact_type": "annotation",
                "source_asset_id": manifest["asset_id"],
                "uri": "https://example.test/artifact.json",
                "sha256": "sha256:" + "7" * 64,
                "created_at": "2026-09-05T00:00:00Z",
                "tool_or_protocol": "synthetic",
                "rights_basis": {
                    "license_or_grant_name": "Direct grant",
                    "version": "1",
                    "licensor_or_grantor": "Owner",
                    "uri": "https://example.test/grant",
                    "scope": "Research release",
                },
                "release_decision": "unknown_hold",
                "release_audience": "public",
                "evidence_snapshot_hash": "sha256:" + "8" * 64,
                "contains_personal_data": False,
                "substitution_risk_reviewed": True,
            }
        ]
        report = validate_manifest_gate(manifest, GateProfile.PUBLIC_RELEASE, self.registry)
        self.assertIn("GATE-010", {issue.code for issue in report.issues})

    def test_public_core_release_is_not_implied_by_acquisition_approval(self) -> None:
        manifest = positive_manifest()
        manifest["audit"]["gate_status"] = "acquisition_approved"
        manifest["rights"]["decisions"]["raw_media_release"] = "prohibited"
        self.assertTrue(
            validate_manifest_gate(
                manifest, GateProfile.ACQUISITION, self.registry
            ).ok
        )
        report = validate_manifest_gate(
            manifest, GateProfile.PUBLIC_CORE_RELEASE, self.registry
        )
        self.assertFalse(report.ok)
        self.assertTrue({"GATE-001", "GATE-003"} & {i.code for i in report.issues})

    def test_restricted_compatibility_profile_does_not_require_public_release(self) -> None:
        manifest = positive_manifest()
        manifest["source"]["source_family"] = "COMPATIBILITY_ONLY"
        manifest["audit"]["gate_status"] = "annotation_approved"
        manifest["rights"]["copyright_basis"] = "restricted_agreement"
        manifest["rights"]["decisions"]["derivative_release"] = "prohibited"
        manifest["rights"]["decisions"]["transcript_release"] = "prohibited"
        manifest["rights"]["decisions"]["raw_media_release"] = "prohibited"
        report = validate_manifest_gate(
            manifest,
            GateProfile.EXTERNAL_COMPATIBILITY_UNPOOLED,
            self.registry,
        )
        self.assertTrue(report.ok, report.to_dict())


if __name__ == "__main__":
    unittest.main()
