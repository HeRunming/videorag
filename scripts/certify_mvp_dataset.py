#!/usr/bin/env python3
"""Fail-closed certification entry point for MVP validator artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from av_trace.schemas import SchemaRegistry
from av_trace.semantic import validate_family
from av_trace.util import load_json, sha256_json
from av_trace_validation.certifier import CertificationError, certify_dataset


def _certify_real_media_bridge(validator_root: str | Path) -> dict:
    """Fail closed unless every indexed real-media family has a verified asset."""

    root = Path(validator_root).resolve()
    index = load_json(root / "artifact_index.json")
    registry = SchemaRegistry()
    issues: list[dict] = []
    family_results: list[dict] = []
    for entry in index.get("families", ()):
        family_id = entry.get("family_id", "unknown")
        verified_path = entry.get("verified_asset_path")
        verified_hash = entry.get("verified_asset_hash")
        if not isinstance(verified_path, str) or not verified_path:
            issues.append(
                {
                    "code": "CERT-VERIFIED-ASSET",
                    "family_id": family_id,
                    "message": "Real-media certification requires verified_asset_path.",
                }
            )
            family_results.append({"family_id": family_id, "status": "FAIL"})
            continue
        try:
            family = load_json(root / entry["family_path"])
            manifest = load_json(root / entry["source_manifest_path"])
            verified_asset = load_json(root / verified_path)
        except Exception as exc:
            issues.append(
                {
                    "code": "CERT-VERIFIED-ASSET",
                    "family_id": family_id,
                    "message": f"Could not load real-media provenance inputs: {exc}",
                }
            )
            family_results.append({"family_id": family_id, "status": "FAIL"})
            continue
        if sha256_json(verified_asset) != verified_hash:
            issues.append(
                {
                    "code": "CERT-VERIFIED-ASSET-HASH",
                    "family_id": family_id,
                    "message": "Verified-asset snapshot hash mismatch.",
                }
            )
        report = validate_family(
            family,
            manifest,
            registry,
            verified_asset=verified_asset,
            media_mode="real",
        )
        if not report.ok:
            first = report.issues[0]
            issues.append(
                {
                    "code": "CERT-FAMILY-SEMANTIC",
                    "family_id": family_id,
                    "message": f"{first.code}: {first.message}",
                }
            )
        family_results.append(
            {"family_id": family_id, "status": "PASS" if report.ok else "FAIL"}
        )
    return {
        "status": "PASS" if not issues else "FAIL",
        "mode": "real",
        "family_results": family_results,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validator-root", default="mvp/validator/generated")
    parser.add_argument("--certificate", default=None)
    parser.add_argument(
        "--mode",
        choices=("real", "synthetic-testing"),
        default="real",
        help="Real media requires verified-asset records; synthetic testing is explicit.",
    )
    args = parser.parse_args()
    certificate_path = args.certificate or str(
        Path(args.validator_root) / "dataset_certificate.json"
    )
    try:
        if args.mode == "real":
            bridge_certificate = _certify_real_media_bridge(args.validator_root)
            if bridge_certificate["status"] != "PASS":
                print(json.dumps(bridge_certificate, indent=2, sort_keys=True))
                return 1
        certificate = certify_dataset(
            validator_root=args.validator_root,
            certificate_path=certificate_path,
            strict=True,
        )
    except CertificationError as exc:
        print(json.dumps(exc.certificate, indent=2, sort_keys=True))
        return 1
    certificate = {**certificate, "certification_mode": args.mode}
    print(json.dumps(certificate, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
