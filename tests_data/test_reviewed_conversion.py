from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from av_trace_data.io import sha256_json
from av_trace_data.reviewed_conversion import (
    REQUIRED_REVIEWER_ATTESTATION,
    ReviewedConversionError,
    convert_reviewed_candidates,
    reviewer_decision_signature,
    reviewer_evidence_sha256,
)
from av_trace_data.snapshot_importer import SnapshotImporter, SnapshotInput

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests_data" / "fixtures"
PYTHON = sys.executable
REVISION = "0123456789abcdef0123456789abcdef01234567"
REVIEWED_AT = "2026-09-07T00:00:00Z"
EXPIRES_AT = "2026-09-14T00:00:00Z"
AS_OF = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
SECRET = "local-test-review-key"


def imported_artifact(*, revision: str = REVISION, promote: bool = True) -> dict:
    return SnapshotImporter().build(
        [
            SnapshotInput(
                FIXTURES / "reviewed_conversion_source.jsonl",
                provider="local",
                repository_id="example/reviewed",
                repository_revision=revision,
                repository_path="records.jsonl",
                source_family="generic_metadata",
            )
        ],
        promote=promote,
    )


def registry(*, reviewer_id: str = "reviewer-1") -> dict:
    return {
        "registry_version": "1.0",
        "reviewers": [
            {
                "reviewer_id": reviewer_id,
                "roles": ["candidate_reviewer"],
                "keys": [
                    {
                        "key_id": "reviewer-1-key",
                        "algorithm": "hmac-sha256",
                        "secret": SECRET,
                    }
                ],
            }
        ],
    }


def candidate(*, revision: str = REVISION, complete: bool = True) -> dict:
    return {
        "dataset_id": "reviewed-local",
        "adapter_id": "reviewed_candidate_conversion",
        "provider": "local",
        "repository_id": "example/reviewed",
        "source_id": "review-source-1",
        "split": "test",
        "duration_s": 2400.0,
        "canonical_url": "https://example.invalid/review-source-1",
        "media_url": None,
        "has_video": True if complete else None,
        "has_audio": True if complete else None,
        "has_speech": True if complete else None,
        "has_ambient_audio": False if complete else None,
        "transcript_available": False,
        "evidence_available": True,
        "revision": revision,
        "license_evidence": (
            [
                {
                    "source": "reviewer-local-license-copy",
                    "artifact_class": "source_media_usage_terms",
                    "name": "Test restricted terms",
                    "version": "1",
                    "url": "https://example.invalid/terms",
                    "scope": "source media",
                    "observed_revision": REVISION,
                }
            ]
            if complete
            else []
        ),
        "license_resolution_status": "consistent" if complete else "unresolved",
        "technical_access_status": (
            "metadata_reference_only" if complete else "unresolved"
        ),
        "access_gate": "review_required" if complete else "unresolved",
        "payload_state": "not_acquired" if complete else "unresolved",
        "media_rights_status": "restricted" if complete else "unknown_hold",
        "source_family": "reviewed_fixture",
        "publisher": "example",
        "rightsholder_or_status": "restricted_unknown_rightsholder",
        "upstream_namespace": "example-source",
        "upstream_asset_id": "review-source-1",
        "identity_resolution_status": "resolved",
        "parent_dataset_id": None,
        "parent_upstream_namespace": None,
        "parent_upstream_asset_id": None,
        "lineage_relation": None,
        "episode_access_class": None,
        "byte_size": None,
        "checksum": None,
        "fingerprint": None,
        "config": None,
        "title": "Reviewed source one",
        "retrieval": {"mode": "none"},
        "source_metadata": {"review_scope": "metadata_only"},
        "future_candidate_field": {"retained": True},
    }


def make_decision(
    artifact: dict,
    *,
    output_mode: str = "freeze_ready",
    candidate_value: dict | None = None,
    evidence_hashed: bool = True,
    reviewer_id: str = "reviewer-1",
    reviewed_at: str = REVIEWED_AT,
    expires_at: str = EXPIRES_AT,
) -> dict:
    record_id = artifact["records"][0]["record_id"]
    candidate_value = deepcopy(candidate_value or candidate())
    duration_provenance = {
        "method": "reviewed_metadata_field",
        "unit": "seconds",
        "source_description": "local reviewer evidence",
    }
    claims = deepcopy(candidate_value)
    claims["duration_provenance"] = deepcopy(duration_provenance)
    evidence = {
        "evidence_id": "review-evidence-1",
        "evidence_type": "local_review_note",
        "source": "tests_data/fixtures/reviewed_conversion_source.jsonl",
        "observed_at": REVIEWED_AT,
        "claims": claims,
        "future_evidence_field": "retained",
    }
    if evidence_hashed:
        evidence["evidence_sha256"] = reviewer_evidence_sha256(evidence)
    claim_evidence = {
        f"/{key}": [
            {
                "kind": "reviewer_evidence",
                "evidence_id": evidence["evidence_id"],
                "claim_path": f"/{key}",
            }
        ]
        for key in candidate_value
    }
    claim_evidence["/duration_provenance"] = [
        {
            "kind": "reviewer_evidence",
            "evidence_id": evidence["evidence_id"],
            "claim_path": "/duration_provenance",
        }
    ]
    decision = {
        "decision_version": "1.0",
        "artifact_class": "reviewed_candidate_decision",
        "imported_inspection_sha256": artifact["inspection_sha256"],
        "output_mode": output_mode,
        "selected_source_record_ids": [record_id],
        "reviewer_evidence": [evidence],
        "candidate_decisions": [
            {
                "source_record_ids": [record_id],
                "candidate": candidate_value,
                "claim_evidence": claim_evidence,
                "duration_provenance": duration_provenance,
                "future_decision_field": ["retained"],
            }
        ],
        "reviewer": {
            "reviewer_id": reviewer_id,
            "role": "candidate_reviewer",
            "reviewed_at": reviewed_at,
            "attestation": REQUIRED_REVIEWER_ATTESTATION,
            "future_reviewer_field": True,
        },
        "decision_expires_at": expires_at,
        "future_root_field": {"retained": True},
        "signature": {
            "algorithm": "hmac-sha256",
            "key_id": "reviewer-1-key",
            "value": "hmac-sha256:" + "0" * 64,
            "future_signature_field": "retained",
        },
    }
    decision["signature"]["value"] = reviewer_decision_signature(
        decision, secret=SECRET
    )
    return decision


def resign(decision: dict) -> None:
    decision["signature"]["value"] = reviewer_decision_signature(
        decision, secret=SECRET
    )


class ReviewedConversionTests(unittest.TestCase):
    def test_freeze_ready_conversion_is_selectable_and_snapshot_bound(self) -> None:
        artifact = imported_artifact()
        decision = make_decision(artifact)
        converted = convert_reviewed_candidates(
            artifact, decision, registry(), as_of=AS_OF
        )
        self.assertTrue(converted["freeze_ready"])
        self.assertEqual(converted["freeze_readiness"]["state"], "freeze_ready")
        self.assertEqual(
            converted["snapshot_sha256"], artifact["inspection_sha256"]
        )
        self.assertEqual(converted["acquisition_authorization"], "none")
        self.assertEqual(converted["annotation_authorization"], "none")
        self.assertEqual(converted["release_authorization"], "none")
        self.assertFalse(converted["network_access_performed"])
        self.assertFalse(converted["contains_media"])

        with tempfile.TemporaryDirectory() as temporary:
            inspection = Path(temporary) / "candidate-inspection.json"
            selection = Path(temporary) / "selection.json"
            inspection.write_text(json.dumps(converted))
            result = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts" / "select_rehearsal_candidates.py"),
                    str(inspection),
                    "--output",
                    str(selection),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            selected = json.loads(selection.read_text())
            source_key = f"local:example/reviewed@{REVISION}"
            self.assertEqual(
                selected["source_snapshots"],
                {source_key: artifact["inspection_sha256"]},
            )

    def test_tampered_importer_artifact_is_rejected(self) -> None:
        artifact = imported_artifact()
        decision = make_decision(artifact)
        artifact["records"][0]["fields"]["duration_s"] = 2500.0
        with self.assertRaisesRegex(ReviewedConversionError, "tampered"):
            convert_reviewed_candidates(artifact, decision, registry(), as_of=AS_OF)

    def test_unsigned_and_unrecognized_reviewers_are_rejected(self) -> None:
        artifact = imported_artifact()
        unsigned = make_decision(artifact)
        unsigned["signature"]["value"] = ""
        with self.assertRaisesRegex(
            ReviewedConversionError, "non-empty|unsigned|schema violation"
        ):
            convert_reviewed_candidates(artifact, unsigned, registry(), as_of=AS_OF)

        unrecognized = make_decision(artifact, reviewer_id="intruder")
        with self.assertRaisesRegex(ReviewedConversionError, "not uniquely recognized"):
            convert_reviewed_candidates(
                artifact, unrecognized, registry(), as_of=AS_OF
            )

    def test_stale_decision_is_rejected(self) -> None:
        artifact = imported_artifact()
        decision = make_decision(
            artifact,
            reviewed_at="2026-07-01T00:00:00Z",
            expires_at="2026-07-08T00:00:00Z",
        )
        with self.assertRaisesRegex(ReviewedConversionError, "stale"):
            convert_reviewed_candidates(artifact, decision, registry(), as_of=AS_OF)

    def test_fabricated_source_id_is_rejected(self) -> None:
        artifact = imported_artifact()
        decision = make_decision(artifact)
        fabricated = "generic:source-file:" + "f" * 64 + ":fabricated"
        decision["selected_source_record_ids"] = [fabricated]
        decision["candidate_decisions"][0]["source_record_ids"] = [fabricated]
        resign(decision)
        with self.assertRaisesRegex(ReviewedConversionError, "unrecognized"):
            convert_reviewed_candidates(artifact, decision, registry(), as_of=AS_OF)

    def test_unsupported_media_assertion_is_rejected(self) -> None:
        artifact = imported_artifact()
        decision = make_decision(artifact)
        decision["candidate_decisions"][0]["candidate"]["has_audio"] = False
        resign(decision)
        with self.assertRaisesRegex(
            ReviewedConversionError, "does not support candidate claim /has_audio"
        ):
            convert_reviewed_candidates(artifact, decision, registry(), as_of=AS_OF)

    def test_conflicting_license_evidence_is_rejected(self) -> None:
        artifact = imported_artifact()
        changed = candidate()
        changed["license_evidence"].append(
            {
                "source": "other-local-terms",
                "artifact_class": "source_media_usage_terms",
                "name": "Different terms",
                "version": "2",
                "url": "https://example.invalid/other-terms",
                "scope": "source media",
                "observed_revision": REVISION,
            }
        )
        decision = make_decision(artifact, candidate_value=changed)
        with self.assertRaisesRegex(ReviewedConversionError, "conflicts"):
            convert_reviewed_candidates(artifact, decision, registry(), as_of=AS_OF)

    def test_exploratory_output_retains_unknown_fields(self) -> None:
        artifact = imported_artifact()
        artifact["future_importer_field"] = {"retained": True}
        artifact["inspection_sha256"] = sha256_json(
            {key: value for key, value in artifact.items() if key != "inspection_sha256"}
        )
        exploratory_candidate = candidate(complete=False)
        decision = make_decision(
            artifact,
            output_mode="exploratory",
            candidate_value=exploratory_candidate,
            evidence_hashed=False,
        )
        converted = convert_reviewed_candidates(
            artifact, decision, registry(), as_of=AS_OF
        )
        self.assertFalse(converted["freeze_ready"])
        self.assertIn(
            "exploratory_mode_requested",
            converted["freeze_readiness"]["reasons"],
        )
        preserved = converted["preserved_unknown_fields"]
        self.assertEqual(
            preserved["reviewer_decision"]["future_root_field"],
            {"retained": True},
        )
        self.assertTrue(preserved["reviewer"]["future_reviewer_field"])
        self.assertEqual(
            preserved["signature"]["future_signature_field"], "retained"
        )
        self.assertEqual(
            preserved["imported_inspection"]["future_importer_field"],
            {"retained": True},
        )
        review_metadata = converted["candidates"][0]["source_metadata"][
            "reviewed_conversion"
        ]
        self.assertEqual(
            review_metadata["candidate_unknown_fields"]["future_candidate_field"],
            {"retained": True},
        )
        self.assertEqual(
            review_metadata["candidate_decision_extensions"][
                "future_decision_field"
            ],
            ["retained"],
        )
        self.assertEqual(
            converted["reviewer_evidence"][0]["future_evidence_field"],
            "retained",
        )

    def test_freeze_ready_requires_immutable_revision_and_evidence(self) -> None:
        mutable_artifact = imported_artifact(revision="main", promote=False)
        mutable_decision = make_decision(
            mutable_artifact,
            candidate_value=candidate(revision="main"),
        )
        with self.assertRaisesRegex(ReviewedConversionError, "mutable revision"):
            convert_reviewed_candidates(
                mutable_artifact, mutable_decision, registry(), as_of=AS_OF
            )

        artifact = imported_artifact()
        unhashed = make_decision(artifact, evidence_hashed=False)
        with self.assertRaisesRegex(
            ReviewedConversionError, "requires immutable reviewer evidence"
        ):
            convert_reviewed_candidates(artifact, unhashed, registry(), as_of=AS_OF)

    def test_local_only_conversion_cli_and_no_media_output(self) -> None:
        artifact = imported_artifact()
        decision = make_decision(artifact)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inspection = root / "importer.json"
            decision_path = root / "decision.json"
            registry_path = root / "registry.json"
            output = root / "converted.json"
            inspection.write_text(json.dumps(artifact))
            decision_path.write_text(json.dumps(decision))
            registry_path.write_text(json.dumps(registry()))
            result = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts" / "convert_reviewed_candidates.py"),
                    "--inspection",
                    str(inspection),
                    "--decision",
                    str(decision_path),
                    "--reviewer-registry",
                    str(registry_path),
                    "--output",
                    str(output),
                    "--as-of",
                    "2026-09-07T12:00:00Z",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            converted = json.loads(output.read_text())
            self.assertEqual(converted["acquisition_authorization"], "none")
            self.assertFalse(converted["network_access_performed"])
            self.assertFalse(converted["contains_media"])
            self.assertFalse(
                any(
                    path.suffix.lower()
                    in {".mp4", ".webm", ".wav", ".mp3", ".mkv", ".mov"}
                    for path in root.rglob("*")
                )
            )

            rejected = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts" / "convert_reviewed_candidates.py"),
                    "--inspection",
                    "https://example.invalid/importer.json",
                    "--decision",
                    str(decision_path),
                    "--reviewer-registry",
                    str(registry_path),
                    "--output",
                    str(root / "should-not-exist.json"),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("only local filesystem paths", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
