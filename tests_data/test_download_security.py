from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from av_trace_data.audit import append_audit_log, audit_event, verify_audit_log
from av_trace_data.download import (
    ApprovalSignatureVerifier,
    ByteTransferBackend,
    DownloadURLResolver,
    ResolvedDownload,
    create_download_plan,
    execute_download_plan,
    validate_execution_approval,
)
from av_trace_data.errors import DownloadPlanError, DownloadRefused
from av_trace_data.io import load_json
from av_trace_data.manifests import draft_acquisition_manifest
from av_trace_data.models import LicenseMetadata, NormalizedCandidate
from av_trace_data.selection import SelectionPolicy, select_candidates

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests_data" / "fixtures"
NOW = datetime(2026, 9, 7, 2, 0, tzinfo=timezone.utc)


def candidate() -> NormalizedCandidate:
    return NormalizedCandidate(
        dataset_id="lovr",
        adapter_id="lovr",
        provider="huggingface",
        repository_id="TechNomad-ds/LoVR",
        source_id="lovr-001",
        split="validation",
        duration_s=2400.0,
        canonical_url="https://example.invalid/source/lvs-original-001",
        media_url=(
            "https://huggingface.co/datasets/TechNomad-ds/LoVR/resolve/"
            "4f9b37e1d2a64e879f9236c5ac871d0123456789/videos/lovr-001.mp4"
        ),
        has_video=True,
        has_audio=True,
        has_speech=True,
        has_ambient_audio=False,
        transcript_available=True,
        evidence_available=True,
        revision="4f9b37e1d2a64e879f9236c5ac871d0123456789",
        license_evidence=(
            LicenseMetadata(
                artifact_class="repository_metadata",
                name="CC-BY-4.0",
                version="4.0",
                url="https://creativecommons.org/licenses/by/4.0/",
                scope="Repository metadata only; upstream media unresolved",
                source="repository",
            ),
        ),
        license_resolution_status="consistent",
        technical_access_status="public_ungated",
        access_gate="public",
        payload_state="release_payload_available",
        media_rights_status="asset_reviewed",
        source_family="COMPATIBILITY_ONLY",
        publisher="TechNomad-ds",
        rightsholder_or_status="Synthetic Rights Holder",
        upstream_namespace="longvideobench",
        upstream_asset_id="lvs-original-001",
        identity_resolution_status="resolved",
        byte_size=4000,
        checksum="sha256:" + "1" * 64,
        config="default",
        title="Forty minute candidate",
        retrieval={"etag": '"fixture-etag-001"'},
        source_metadata={
            "repository_url": "https://huggingface.co/datasets/TechNomad-ds/LoVR",
            "license_is_not_rights_approval": True,
        },
    )


def changed_candidate(**changes: object) -> NormalizedCandidate:
    value = candidate().to_dict()
    value.update(changes)
    return NormalizedCandidate.from_dict(value)


def approved_manifest(item: NormalizedCandidate | None = None) -> dict:
    item = item or candidate()
    manifest = load_json(ROOT / "docs/data/fixtures/positive_acquisition_manifest.json")
    manifest["asset_id"] = f"{item.dataset_id}:{item.source_id}"
    manifest["dataset_id"] = item.dataset_id
    manifest["source"]["canonical_url"] = item.canonical_url
    manifest["source"]["source_identifier"] = item.upstream_id
    manifest["source"]["source_revision"] = item.revision
    manifest["source"]["publisher"] = item.publisher
    manifest["source"]["source_family"] = item.source_family
    manifest["integrity"]["content_sha256"] = item.checksum
    manifest["integrity"]["byte_size"] = item.byte_size
    manifest["audit"]["gate_status"] = "acquisition_approved"
    return manifest


def selection(item: NormalizedCandidate | None = None) -> dict:
    item = item or candidate()
    return select_candidates(
        [item],
        SelectionPolicy(
            max_item_bytes=10_000,
            max_total_bytes=10_000,
            require_media_url=True,
        ),
        source_snapshots={
            f"{item.provider}:{item.repository_id}@{item.revision}":
            "sha256:" + "a" * 64,
        },
    )


def manifest_map(item: NormalizedCandidate | None = None) -> dict[str, dict]:
    item = item or candidate()
    return {f"{item.dataset_id}:{item.source_id}": approved_manifest(item)}


def plan(
    item: NormalizedCandidate | None = None,
    *,
    root: str = "/approved/staging",
    **kwargs: object,
) -> dict:
    item = item or candidate()
    return create_download_plan(
        selection(item),
        manifest_map(item),
        output_root=root,
        **kwargs,
    )


def approval(value: dict, **changes: object) -> dict:
    result = {
        "approval_version": "1.0",
        "action": "approve_download_execution",
        "plan_sha256": value["plan_sha256"],
        "approved_by": "reviewer1",
        "approved_role": "acquisition_reviewer",
        "approved_at": "2026-09-07T01:00:00Z",
        "approved_asset_ids": [item["asset_id"] for item in value["items"]],
        "attestation": "I approve acquisition of the exact assets in this frozen plan.",
    }
    result.update(changes)
    return result


def approval_kwargs(root: str = "/approved/staging") -> dict:
    return {
        "authorized_signers": {"reviewer1": ["acquisition_reviewer"]},
        "authorization_time": NOW,
        "approved_staging_roots": [root],
    }


class StaticResolver(DownloadURLResolver):
    def __init__(self, resolved: ResolvedDownload):
        self.resolved = resolved

    def resolve(self, candidate: NormalizedCandidate) -> ResolvedDownload:
        return self.resolved


class StaticBackend(ByteTransferBackend):
    def __init__(self, result: dict):
        self.result = result

    def transfer(self, item: dict) -> dict:
        return deepcopy(self.result)


class WritingBackend(StaticBackend):
    def __init__(self, result: dict, payload: bytes):
        super().__init__(result)
        self.payload = payload

    def transfer(self, item: dict) -> dict:
        destination = Path(item["destination"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.payload)
        return super().transfer(item)


class SymlinkBackend(StaticBackend):
    def __init__(self, result: dict, target: Path):
        super().__init__(result)
        self.target = target

    def transfer(self, item: dict) -> dict:
        destination = Path(item["destination"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(self.target)
        return super().transfer(item)


class AcceptingVerifier(ApprovalSignatureVerifier):
    def verify(self, signed_payload: dict, detached_signature: str) -> bool:
        return detached_signature == "fixture-valid"


def backend_result(value: dict) -> dict:
    item = value["items"][0]
    return {
        "requested_url": item["url"],
        "effective_url": item["url"],
        "destination": item["destination"],
        "destination_preexisted": False,
        "filesystem_attestation": {
            "attestation_version": "1.0",
            "exclusive_create": True,
            "symlink_safe": True,
            "destination_contained": True,
            "staging_root": item["staging_root"],
        },
        "bytes_written": item["planned_transfer_bytes"],
        "byte_range": item["byte_range"],
        "provider_revision": item["source_revision"],
        "etag": item["resume"]["etag"],
        "sha256": item["expected_sha256"],
        "endpoint_attestation": {
            "attestation_version": "1.0",
            "requested_url": item["url"],
            "effective_url": item["url"],
            "redirect_chain": [item["url"]],
            "redirect_count": 0,
            "peer_ip": "8.8.8.8",
            "peer_ips": ["8.8.8.8"],
            "dns_rebinding_protected": True,
        },
    }


def checkpoint(path: Path) -> dict:
    record = append_audit_log(path, audit_event("transfer_authorization_ready"))
    return {
        "checkpoint_version": "1.0",
        "record_count": record["sequence"],
        "head_sha256": record["entry_sha256"],
    }


class DownloadSecurityTests(unittest.TestCase):
    def test_public_package_exports_integrated_download_and_audit_api(self) -> None:
        import av_trace_data

        for name in (
            "ApprovalSignatureVerifier",
            "ResolvedDownload",
            "append_audit_log",
            "audit_event",
            "load_approval",
            "verify_audit_log",
        ):
            with self.subTest(name=name):
                self.assertTrue(hasattr(av_trace_data, name))

    def test_selection_tampering_is_rejected_and_exact_records_are_bound(self) -> None:
        selected = selection()
        selected["policy"]["limit"] = 99
        with self.assertRaisesRegex(DownloadPlanError, "selection hash"):
            create_download_plan(
                selected,
                manifest_map(),
                output_root="/approved/staging",
            )
        frozen = plan()
        self.assertEqual(
            frozen["selection_binding"]["selected_normalized_records"],
            selection()["selected"],
        )
        self.assertEqual(
            frozen["selection_binding"]["source_snapshot_sha256s"],
            ["sha256:" + "a" * 64],
        )

    def test_executable_plan_requires_snapshot_bindings_and_source_coverage(self) -> None:
        item = candidate()
        without_snapshot = select_candidates(
            [item],
            SelectionPolicy(
                max_item_bytes=10_000,
                max_total_bytes=10_000,
                require_media_url=True,
            ),
        )
        with self.assertRaisesRegex(DownloadPlanError, "source snapshot binding"):
            create_download_plan(
                without_snapshot,
                manifest_map(item),
                output_root="/approved/staging",
            )
        preview = create_download_plan(
            without_snapshot,
            manifest_map(item),
            output_root="/approved/staging",
            plan_mode="metadata_preview",
        )
        self.assertEqual(preview["plan_mode"], "metadata_preview")
        self.assertFalse(preview["executable"])

        wrong_source = select_candidates(
            [item],
            SelectionPolicy(
                max_item_bytes=10_000,
                max_total_bytes=10_000,
                require_media_url=True,
            ),
            source_snapshots={
                f"{item.provider}:other/repository@{item.revision}":
                    "sha256:" + "b" * 64
            },
        )
        with self.assertRaisesRegex(DownloadPlanError, "coverage is missing"):
            create_download_plan(
                wrong_source,
                manifest_map(item),
                output_root="/approved/staging",
            )

    def test_direct_candidate_plan_is_review_only_and_not_executable(self) -> None:
        item = candidate()
        frozen = create_download_plan(
            [item],
            manifest_map(item),
            output_root="/approved/staging",
            plan_mode="metadata_preview",
        )
        self.assertEqual(frozen["plan_mode"], "metadata_preview")
        self.assertFalse(frozen["executable"])
        with self.assertRaisesRegex(DownloadRefused, "complete selection"):
            validate_execution_approval(
                frozen,
                manifest_map(item),
                approval(frozen),
                **approval_kwargs(),
            )

    def test_mutable_short_and_composite_revisions_are_rejected(self) -> None:
        for revision in ("main", "abcdef1", "refs/heads/main", "a" * 40 + "^"):
            with self.subTest(revision=revision):
                item = changed_candidate(
                    revision=revision,
                    media_url=(
                        "https://huggingface.co/datasets/TechNomad-ds/LoVR/"
                        f"resolve/{revision}/videos/lovr-001.mp4"
                    ),
                )
                with self.assertRaisesRegex(DownloadPlanError, "full immutable"):
                    create_download_plan(
                        [item],
                        manifest_map(item),
                        output_root="/approved/staging",
                        plan_mode="metadata_preview",
                    )

    def test_url_revision_host_credentials_and_private_targets_are_rejected(self) -> None:
        item = candidate()
        attacks = [
            (
                "https://huggingface.co/datasets/TechNomad-ds/LoVR/resolve/main/"
                "videos/lovr-001.mp4",
                None,
                "not bound",
            ),
            (
                "http://huggingface.co/datasets/TechNomad-ds/LoVR/resolve/"
                f"{item.revision}/videos/lovr-001.mp4",
                None,
                "HTTPS",
            ),
            (
                "https://user:password@huggingface.co/datasets/TechNomad-ds/LoVR/"
                f"resolve/{item.revision}/videos/lovr-001.mp4",
                None,
                "credentials",
            ),
            (
                "https://evil.example/datasets/TechNomad-ds/LoVR/resolve/"
                f"{item.revision}/videos/lovr-001.mp4",
                None,
                "host is not allowed",
            ),
            (
                f"https://127.0.0.1/datasets/TechNomad-ds/LoVR/resolve/"
                f"{item.revision}/videos/lovr-001.mp4",
                {"huggingface": ["127.0.0.1"]},
                "private or local",
            ),
        ]
        for url, allowlist, message in attacks:
            with self.subTest(url=url):
                attacked = changed_candidate(media_url=url)
                with self.assertRaisesRegex(DownloadPlanError, message):
                    create_download_plan(
                        selection(attacked),
                        manifest_map(attacked),
                        output_root="/approved/staging",
                        provider_host_allowlist=allowlist,
                    )

    def test_final_redteam_url_canonicalization_probes_are_rejected(self) -> None:
        item = candidate()
        prefix = (
            "https://huggingface.co/datasets/TechNomad-ds/LoVR/resolve/"
            f"{item.revision}/videos/"
        )
        probes = (
            prefix + "%252e%252e/lovr-001.mp4",
            prefix + "nested%252fescape.mp4",
            prefix + "%00lovr-001.mp4",
            prefix + "file.mp4/extra",
            prefix + "lovr-001.mp4\n",
        )
        for url in probes:
            with self.subTest(url=url):
                attacked = changed_candidate(media_url=url)
                with self.assertRaises(DownloadPlanError):
                    create_download_plan(
                        selection(attacked),
                        manifest_map(attacked),
                        output_root="/approved/staging",
                    )

    def test_credential_headers_and_query_tokens_are_never_planned(self) -> None:
        item = candidate()
        resolved = ResolvedDownload(
            url=item.media_url or "",
            headers={"Authorization": "Bearer secret"},
            provider_revision=item.revision,
            expected_size=item.byte_size,
            expected_sha256=item.checksum,
        )
        with self.assertRaisesRegex(DownloadPlanError, "credential headers"):
            create_download_plan(
                selection(item),
                manifest_map(item),
                output_root="/approved/staging",
                resolver=StaticResolver(resolved),
            )
        token_url = (item.media_url or "") + "?token=secret"
        with self.assertRaisesRegex(DownloadPlanError, "credential-like"):
            plan(changed_candidate(media_url=token_url))

    def test_unknown_size_is_always_rejected_and_range_is_clamped_exactly(self) -> None:
        unknown = changed_candidate(byte_size=None)
        draft = draft_acquisition_manifest(
            unknown,
            created_by="fixture",
            created_at="2026-09-07T00:00:00Z",
        )
        with self.assertRaisesRegex(DownloadPlanError, "unknown or invalid"):
            create_download_plan(
                selection(unknown),
                {"lovr:lovr-001": draft},
                output_root="/approved/staging",
            )
        ranged = plan(range_start=1000, range_end=9999)
        self.assertEqual(
            ranged["items"][0]["byte_range"],
            {"start": 1000, "end_inclusive": 3999},
        )
        self.assertEqual(ranged["items"][0]["planned_transfer_bytes"], 3000)
        self.assertEqual(ranged["limits"]["known_total_bytes"], 3000)

    def test_executable_plan_requires_explicit_item_and_total_caps(self) -> None:
        selected = selection()
        selected["policy"]["max_item_bytes"] = None
        selected["policy"]["max_total_bytes"] = None
        body = dict(selected)
        body.pop("selection_sha256")
        from av_trace_data.io import sha256_json

        selected["selection_sha256"] = sha256_json(body)
        with self.assertRaisesRegex(DownloadPlanError, "explicit positive"):
            create_download_plan(
                selected,
                manifest_map(),
                output_root="/approved/staging",
            )

    def test_destination_traversal_and_collision_are_rejected(self) -> None:
        with self.assertRaisesRegex(DownloadPlanError, "absolute approved staging"):
            plan(root="../escape")

        first = candidate()
        second = changed_candidate(
            source_id="lovr/001",
            upstream_asset_id="lvs-original-002",
            canonical_url="https://example.invalid/source/lvs-original-002",
            checksum="sha256:" + "2" * 64,
            media_url=(
                "https://huggingface.co/datasets/TechNomad-ds/LoVR/resolve/"
                f"{first.revision}/videos/lovr-001.mp4"
            ),
        )
        third = changed_candidate(
            source_id="lovr-001",
            upstream_asset_id="lvs-original-003",
            canonical_url="https://example.invalid/source/lvs-original-003",
            checksum="sha256:" + "3" * 64,
            media_url=(
                "https://huggingface.co/datasets/TechNomad-ds/LoVR/resolve/"
                f"{first.revision}/videos/lovr-001.mp4"
            ),
        )
        selected = select_candidates(
            [second, third],
            SelectionPolicy(
                max_item_bytes=10_000,
                max_total_bytes=10_000,
                require_media_url=True,
            ),
            source_snapshots={
                f"{first.provider}:{first.repository_id}@{first.revision}":
                    "sha256:" + "a" * 64
            },
        )
        manifests = {
            "lovr:lovr/001": approved_manifest(second),
            "lovr:lovr-001": approved_manifest(third),
        }
        with self.assertRaisesRegex(DownloadPlanError, "destination collision"):
            create_download_plan(
                selected,
                manifests,
                output_root="/approved/staging",
            )

    def test_manifest_binding_and_unresolved_rightsholder_are_rejected(self) -> None:
        item = candidate()
        manifest = approved_manifest(item)
        manifest["source"]["canonical_url"] = "https://example.invalid/wrong"
        with self.assertRaisesRegex(DownloadPlanError, "canonical_url mismatch"):
            create_download_plan(
                selection(item),
                {"lovr:lovr-001": manifest},
                output_root="/approved/staging",
            )

        manifest = approved_manifest(item)
        frozen = create_download_plan(
            selection(item),
            {"lovr:lovr-001": manifest},
            output_root="/approved/staging",
        )
        unresolved = deepcopy(manifest)
        unresolved["source"]["rightsholder_or_status"] = "unknown_hold"
        # Re-freeze the exact unresolved manifest to test the rights boundary,
        # rather than merely triggering the manifest hash.
        frozen = create_download_plan(
            selection(item),
            {"lovr:lovr-001": unresolved},
            output_root="/approved/staging",
        )
        with self.assertRaisesRegex(DownloadRefused, "unresolved asset-level"):
            validate_execution_approval(
                frozen,
                {"lovr:lovr-001": unresolved},
                approval(frozen),
                **approval_kwargs(),
            )

    def test_approval_identity_role_time_assets_and_signature_are_strict(self) -> None:
        frozen = plan()
        manifests = manifest_map()
        with self.assertRaisesRegex(DownloadRefused, "independently authorized"):
            validate_execution_approval(
                frozen,
                manifests,
                approval(frozen, approved_by="attacker"),
                **approval_kwargs(),
            )
        with self.assertRaisesRegex(DownloadRefused, "strict RFC3339"):
            validate_execution_approval(
                frozen,
                manifests,
                approval(frozen, approved_at="yesterday"),
                **approval_kwargs(),
            )
        with self.assertRaisesRegex(DownloadRefused, "stale"):
            validate_execution_approval(
                frozen,
                manifests,
                approval(frozen, approved_at="2026-09-05T00:00:00Z"),
                **approval_kwargs(),
            )
        with self.assertRaisesRegex(DownloadRefused, "exact ordered"):
            validate_execution_approval(
                frozen,
                manifests,
                approval(frozen, approved_asset_ids=[]),
                **approval_kwargs(),
            )
        with self.assertRaisesRegex(DownloadRefused, "staging-root allowlist"):
            validate_execution_approval(
                frozen,
                manifests,
                approval(frozen),
                authorized_signers={"reviewer1": ["acquisition_reviewer"]},
                authorization_time=NOW,
            )
        signed = approval(frozen, detached_signature="fixture-valid")
        result = validate_execution_approval(
            frozen,
            manifests,
            signed,
            signature_verifier=AcceptingVerifier(),
            **approval_kwargs(),
        )
        self.assertEqual(result["status"], "authorized_not_executed")
        self.assertTrue(result["approval_signature_verified"])

        unsigned = validate_execution_approval(
            frozen,
            manifests,
            approval(frozen),
            **approval_kwargs(),
        )
        self.assertEqual(unsigned["status"], "validated_not_authorized")
        self.assertFalse(unsigned["approval_signature_verified"])

    def test_backend_result_mismatch_and_endpoint_attestation_fail_closed(self) -> None:
        payload = b"x" * 4000
        item = changed_candidate(
            checksum="sha256:" + hashlib.sha256(payload).hexdigest()
        )
        manifests = manifest_map(item)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staging"
            audit_path = root / "audit.jsonl"
            frozen = plan(item, root=str(staging))
            good = backend_result(frozen)
            signed = approval(frozen, detached_signature="fixture-valid")
            execution_kwargs = {
                **approval_kwargs(str(staging)),
                "signature_verifier": AcceptingVerifier(),
                "audit_log_path": audit_path,
                "audit_checkpoint": checkpoint(audit_path),
            }
            result = execute_download_plan(
                frozen,
                manifests,
                signed,
                backend=WritingBackend(good, payload),
                **execution_kwargs,
            )
            self.assertEqual(result["status"], "executed")
            self.assertTrue(
                result["results"][0]["independent_filesystem_verification"][
                    "regular_file"
                ]
            )
            Path(frozen["items"][0]["destination"]).unlink()

            attacks = [
                ("bytes_written", 3999, "byte count"),
                ("destination", "/tmp/elsewhere", "destination"),
                ("provider_revision", "f" * 40, "revision"),
                ("sha256", "sha256:" + "f" * 64, "checksum"),
            ]
            for key, bad_value, message in attacks:
                with self.subTest(key=key):
                    bad = deepcopy(good)
                    bad[key] = bad_value
                    with self.assertRaisesRegex(DownloadRefused, message):
                        execute_download_plan(
                            frozen,
                            manifests,
                            signed,
                            backend=StaticBackend(bad),
                            **execution_kwargs,
                        )
            private = deepcopy(good)
            private["endpoint_attestation"]["peer_ip"] = "127.0.0.1"
            with self.assertRaisesRegex(DownloadRefused, "peer IP is not public"):
                execute_download_plan(
                    frozen,
                    manifests,
                    signed,
                    backend=StaticBackend(private),
                    **execution_kwargs,
                )

            incomplete = deepcopy(good)
            incomplete["endpoint_attestation"].pop("peer_ips")
            with self.assertRaisesRegex(DownloadRefused, "per-hop peer"):
                execute_download_plan(
                    frozen,
                    manifests,
                    signed,
                    backend=StaticBackend(incomplete),
                    **execution_kwargs,
                )

            with self.assertRaisesRegex(DownloadRefused, "destination does not exist"):
                execute_download_plan(
                    frozen,
                    manifests,
                    signed,
                    backend=StaticBackend(good),
                    **execution_kwargs,
                )

    def test_backend_filesystem_verification_rejects_wrong_bytes_and_symlink(self) -> None:
        payload = b"x" * 4000
        item = changed_candidate(
            checksum="sha256:" + hashlib.sha256(payload).hexdigest()
        )
        manifests = manifest_map(item)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staging"
            audit_path = root / "audit.jsonl"
            frozen = plan(item, root=str(staging))
            signed = approval(frozen, detached_signature="fixture-valid")
            execution_kwargs = {
                **approval_kwargs(str(staging)),
                "signature_verifier": AcceptingVerifier(),
                "audit_log_path": audit_path,
                "audit_checkpoint": checkpoint(audit_path),
            }
            with self.assertRaisesRegex(DownloadRefused, "checksum"):
                execute_download_plan(
                    frozen,
                    manifests,
                    signed,
                    backend=WritingBackend(backend_result(frozen), b"y" * 4000),
                    **execution_kwargs,
                )

            destination = Path(frozen["items"][0]["destination"])
            destination.unlink()
            target = root / "outside.bin"
            target.write_bytes(payload)
            with self.assertRaisesRegex(DownloadRefused, "non-symlink"):
                execute_download_plan(
                    frozen,
                    manifests,
                    signed,
                    backend=SymlinkBackend(backend_result(frozen), target),
                    **execution_kwargs,
                )

    def test_backend_requires_signature_and_external_audit_checkpoint(self) -> None:
        frozen = plan()
        with self.assertRaisesRegex(DownloadRefused, "signature verifier"):
            execute_download_plan(
                frozen,
                manifest_map(),
                approval(frozen),
                backend=StaticBackend(backend_result(frozen)),
                **approval_kwargs(),
            )
        with self.assertRaisesRegex(DownloadRefused, "external audit checkpoint"):
            execute_download_plan(
                frozen,
                manifest_map(),
                approval(frozen, detached_signature="fixture-valid"),
                backend=StaticBackend(backend_result(frozen)),
                signature_verifier=AcceptingVerifier(),
                **approval_kwargs(),
            )
        with tempfile.TemporaryDirectory() as temporary:
            audit_path = Path(temporary) / "audit.jsonl"
            with self.assertRaisesRegex(DownloadRefused, "signature is invalid"):
                execute_download_plan(
                    frozen,
                    manifest_map(),
                    approval(frozen, detached_signature="fixture-invalid"),
                    backend=StaticBackend(backend_result(frozen)),
                    signature_verifier=AcceptingVerifier(),
                    audit_log_path=audit_path,
                    audit_checkpoint=checkpoint(audit_path),
                    **approval_kwargs(),
                )

    def test_audit_chain_verifies_and_detects_tampering_and_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "audit.jsonl"
            first = append_audit_log(path, audit_event("first", value=1))
            second = append_audit_log(path, audit_event("second", value=2))
            report = verify_audit_log(path)
            self.assertEqual(report["record_count"], 2)
            self.assertEqual(report["head_sha256"], second["entry_sha256"])
            self.assertEqual(
                second["previous_entry_sha256"], first["entry_sha256"]
            )
            self.assertFalse(report["checkpoint_verified"])
            anchored = verify_audit_log(
                path,
                expected_head_sha256=second["entry_sha256"],
                expected_record_count=2,
            )
            self.assertTrue(anchored["checkpoint_verified"])

            path.write_text(
                path.read_text(encoding="utf-8").splitlines()[0] + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "record count"):
                verify_audit_log(
                    path,
                    expected_head_sha256=second["entry_sha256"],
                    expected_record_count=2,
                )

            lines = path.read_text(encoding="utf-8").splitlines()
            record = json.loads(lines[0])
            record["value"] = 999
            lines[0] = json.dumps(record, sort_keys=True, separators=(",", ":"))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash does not match"):
                verify_audit_log(path)

            with self.assertRaisesRegex(ValueError, "sensitive field"):
                audit_event("bad", headers={"Authorization": "secret"})
            with self.assertRaisesRegex(ValueError, "credential-like URL"):
                audit_event("bad-url", url="https://example.invalid/file?token=secret")

    def test_append_rejects_a_validly_hashed_legacy_record_with_secrets(self) -> None:
        from av_trace_data.io import canonical_json
        import hashlib

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "audit.jsonl"
            body = {
                "audit_version": "2.0",
                "at": "2026-09-07T00:00:00Z",
                "event": "legacy_bad",
                "headers": {"Authorization": "secret"},
                "audit_chain_version": "1.0",
                "sequence": 1,
                "previous_entry_sha256": "sha256:" + "0" * 64,
            }
            record = {
                **body,
                "entry_sha256": "sha256:"
                + hashlib.sha256(canonical_json(body)).hexdigest(),
            }
            path.write_text(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "sensitive field"):
                append_audit_log(path, audit_event("safe"))

    def test_no_backend_preserves_no_download_default(self) -> None:
        frozen = plan()
        result = execute_download_plan(
            frozen,
            manifest_map(),
            approval(frozen),
            backend=None,
            **approval_kwargs(),
        )
        self.assertEqual(result["status"], "validated_not_authorized")
        self.assertFalse(result["approval_signature_verified"])
        self.assertFalse(result["network_access_performed"])

    def test_cli_authorizes_but_never_transfers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staging"
            manifests = root / "manifests"
            manifests.mkdir()
            selection_path = root / "selection.json"
            manifest_path = manifests / "lovr:lovr-001.json"
            plan_path = root / "plan.json"
            approval_path = root / "approval.json"
            signers_path = root / "signers.json"
            selection_path.write_text(
                json.dumps(selection()), encoding="utf-8"
            )
            manifest_path.write_text(
                json.dumps(approved_manifest()), encoding="utf-8"
            )
            environment = {"PYTHONPATH": str(ROOT / "src")}
            plan_result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "plan_dataset_download.py"),
                    "plan",
                    "--selection",
                    str(selection_path),
                    "--manifest-dir",
                    str(manifests),
                    "--output",
                    str(plan_path),
                    "--output-root",
                    str(staging),
                    "--max-item-bytes",
                    "5000",
                    "--max-total-bytes",
                    "5000",
                ],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(plan_result.returncode, 0, plan_result.stdout)
            frozen = json.loads(plan_path.read_text(encoding="utf-8"))
            approval_path.write_text(
                json.dumps(
                    approval(
                        frozen,
                        approved_at=datetime.now(timezone.utc)
                        .isoformat()
                        .replace("+00:00", "Z"),
                    )
                ),
                encoding="utf-8",
            )
            signers_path.write_text(
                json.dumps(
                    {"authorized_signers": {"reviewer1": ["acquisition_reviewer"]}}
                ),
                encoding="utf-8",
            )
            execute_result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "plan_dataset_download.py"),
                    "execute",
                    "--selection",
                    str(selection_path),
                    "--manifest-dir",
                    str(manifests),
                    "--plan",
                    str(plan_path),
                    "--approval-file",
                    str(approval_path),
                    "--authorized-signers",
                    str(signers_path),
                    "--approved-staging-root",
                    str(staging),
                ],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(execute_result.returncode, 0, execute_result.stdout)
            result = json.loads(execute_result.stdout)
            self.assertEqual(result["status"], "validated_not_authorized")
            self.assertFalse(result["network_access_performed"])
            self.assertFalse(staging.exists())


if __name__ == "__main__":
    unittest.main()
