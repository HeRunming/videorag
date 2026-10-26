"""Fail-closed binding of the v2 run to checked-in validator artifacts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from av_trace.util import load_json, sha256_json
from av_trace_mvp.index import GeneratedCorpus
from av_trace_validation.certifier import certify_dataset
from av_trace_validation.schemas import require_valid


PINNED_CERTIFICATE_HASH = "sha256:48a91b1e459b22048badf72d6142779f11045c1203213041a4867be60f030f24"


@dataclass(frozen=True)
class CertificationBinding:
    certificate: dict[str, Any]
    artifact_index: dict[str, Any]
    denominator: dict[str, Any]
    fixed_call_case: dict[str, Any]
    fixed_call_family: dict[str, Any]


def _safe_child(root: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts:
        raise ValueError(f"Validator artifact path escapes bundle: {relative}")
    path = (root / value).resolve()
    if root.resolve() not in path.parents and path != root.resolve():
        raise ValueError(f"Validator artifact path escapes bundle: {relative}")
    return path


def verify_certified_dataset(
    corpus: GeneratedCorpus,
    *,
    validator_root: str | Path,
) -> CertificationBinding:
    """Re-certify and bind live corpus, denominator, and fixed-call fixture."""

    root = Path(validator_root)
    stored = load_json(root / "dataset_certificate.json")
    require_valid("dataset_certificate", stored)
    body = deepcopy(stored)
    claimed_hash = body.pop("certificate_hash")
    if sha256_json(body) != claimed_hash:
        raise ValueError("Stored dataset certificate self-hash mismatch.")
    if claimed_hash != PINNED_CERTIFICATE_HASH:
        raise ValueError("Stored dataset certificate does not match the v2 trust anchor.")
    recomputed = certify_dataset(validator_root=root, strict=True)
    if recomputed != stored:
        raise ValueError("Stored dataset certificate differs from fresh certification.")

    artifact_index = load_json(root / "artifact_index.json")
    if sha256_json(artifact_index) != stored["artifact_index_hash"]:
        raise ValueError("Artifact-index hash does not match dataset certificate.")
    denominator_path = _safe_child(root, artifact_index["denominator_path"])
    denominator = load_json(denominator_path)
    require_valid("denominator", denominator)
    if sha256_json(denominator) != artifact_index["denominator_hash"]:
        raise ValueError("Premature-stop denominator hash mismatch.")

    manifest_hash = corpus.manifest.manifest_hash
    index_hash = corpus.index.index_hash
    if not all(
        value == manifest_hash
        for value in (
            stored["backend_manifest_hash"],
            artifact_index["backend_manifest_hash"],
            denominator["provenance"]["backend_manifest_hash"],
        )
    ):
        raise ValueError("Certified backend-manifest binding mismatch.")
    if not all(
        value == index_hash
        for value in (
            stored["index_hash"],
            artifact_index["index_hash"],
            denominator["provenance"]["index_hash"],
        )
    ):
        raise ValueError("Certified backend-index binding mismatch.")

    entries = {item["family_id"]: item for item in artifact_index["families"]}
    for family in corpus.families:
        family_id = family["family_id"]
        actual = sha256_json(family)
        if family_id not in entries:
            raise ValueError(f"Family {family_id} is absent from validator artifact index.")
        if actual != entries[family_id]["family_hash"]:
            raise ValueError(f"Certified family hash mismatch for {family_id}.")
        if actual != denominator["provenance"]["family_hashes"].get(family_id):
            raise ValueError(f"Denominator family hash mismatch for {family_id}.")

    fixed_case = next(
        (
            item
            for item in artifact_index.get("validator_cases", ())
            if item.get("case_id") == "fixed-call-restoration"
        ),
        None,
    )
    if fixed_case is None:
        raise ValueError("Certified fixed-call validator case is missing.")
    fixed_family = load_json(_safe_child(root, fixed_case["family_path"]))
    if sha256_json(fixed_family) != fixed_case["family_hash"]:
        raise ValueError("Fixed-call family hash mismatch.")
    return CertificationBinding(
        certificate=stored,
        artifact_index=artifact_index,
        denominator=denominator,
        fixed_call_case=fixed_case,
        fixed_call_family=fixed_family,
    )
