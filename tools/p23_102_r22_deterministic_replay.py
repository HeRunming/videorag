#!/usr/bin/env python3
"""Replay retained R22 query-authoring evidence without running any model."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CURRENT_DATE = "2026-10-23"
DEFAULT_AUDIT = Path(
    "data/restricted/p23_102_canary2_r22_terminal_detailed_audit.json"
)
DEFAULT_CAPSULE = Path(
    "data/restricted/"
    "p23_102_query_authoring_v2_canary2_run_v1.failure-"
    "P23QAV2-CANARY2-R22F-ONE-SHOT-20261022T143848Z"
)
DEFAULT_REPORT = Path(
    "data/restricted/p23_102_canary2_r22_deterministic_replay_report.json"
)
PARENT_TOOL = Path("tools/p23_102_query_authoring_v2.py")


class ReplayError(RuntimeError):
    """Fail-closed deterministic replay error."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def semantic_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReplayError(f"R22_REPLAY_JSON_INVALID:{path}") from exc


def load_parent(root: Path) -> Any:
    path = root / PARENT_TOOL
    spec = importlib.util.spec_from_file_location(
        "p23_102_query_authoring_v2_r23a_replay", path
    )
    if spec is None or spec.loader is None:
        raise ReplayError("R22_REPLAY_PARENT_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_seal_manifest(
    root: Path, audit: Mapping[str, Any]
) -> list[dict[str, Any]]:
    rows = audit.get("seal_manifest")
    if not isinstance(rows, list) or not rows:
        raise ReplayError("R22_REPLAY_SEAL_MANIFEST_MISSING")
    verified = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ReplayError("R22_REPLAY_SEAL_ROW_INVALID")
        path_value = row.get("path")
        expected_hash = row.get("sha256")
        expected_bytes = row.get("bytes")
        if (
            not isinstance(path_value, str)
            or not isinstance(expected_hash, str)
            or not isinstance(expected_bytes, int)
        ):
            raise ReplayError("R22_REPLAY_SEAL_ROW_INVALID")
        path = root / path_value
        if not path.is_file():
            raise ReplayError(f"R22_REPLAY_SEALED_FILE_MISSING:{path_value}")
        observed_bytes = path.stat().st_size
        observed_hash = file_sha256(path)
        if observed_bytes != expected_bytes or observed_hash != expected_hash:
            raise ReplayError(f"R22_REPLAY_HASH_MISMATCH:{path_value}")
        verified.append(
            {
                "role": row.get("role"),
                "path": path_value,
                "bytes": observed_bytes,
                "sha256": observed_hash,
                "status": "PASS",
            }
        )
    return verified


def verify_capsule_manifest(
    capsule: Path, failure_capsule: Mapping[str, Any]
) -> list[dict[str, Any]]:
    preserved = failure_capsule.get("preserved_files_before_capsule_manifest")
    if not isinstance(preserved, Mapping) or not preserved:
        raise ReplayError("R22_REPLAY_CAPSULE_MANIFEST_MISSING")
    verified = []
    for name, record in sorted(preserved.items()):
        if (
            not isinstance(name, str)
            or not isinstance(record, Mapping)
            or not isinstance(record.get("bytes"), int)
            or not isinstance(record.get("sha256"), str)
        ):
            raise ReplayError("R22_REPLAY_CAPSULE_MANIFEST_INVALID")
        path = capsule / name
        if not path.is_file():
            raise ReplayError(f"R22_REPLAY_CAPSULE_FILE_MISSING:{name}")
        observed_bytes = path.stat().st_size
        observed_hash = file_sha256(path)
        if (
            observed_bytes != record["bytes"]
            or observed_hash != record["sha256"]
        ):
            raise ReplayError(f"R22_REPLAY_HASH_MISMATCH:{name}")
        verified.append(
            {
                "path": name,
                "bytes": observed_bytes,
                "sha256": observed_hash,
                "status": "PASS",
            }
        )
    return verified


def load_attempts(path: Path) -> list[dict[str, Any]]:
    attempts = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ReplayError("R22_REPLAY_ATTEMPTS_UNREADABLE") from exc
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReplayError(
                f"R22_REPLAY_ATTEMPT_JSON_INVALID:{line_number}"
            ) from exc
        if not isinstance(row, dict):
            raise ReplayError(
                f"R22_REPLAY_ATTEMPT_ROW_INVALID:{line_number}"
            )
        attempts.append(row)
    return attempts


def retained_constraint_context(
    attempts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    fields = sorted(
        key
        for key in attempts[0]
        if str(key).startswith("constraint_")
    )
    ambient = next(
        (row for row in attempts if row.get("factor_kind") == "ambient"),
        None,
    )
    visual = next(
        (row for row in attempts if row.get("factor_kind") == "visual"),
        None,
    )
    if ambient is None or visual is None or not fields:
        raise ReplayError("R22_REPLAY_CONSTRAINT_EVIDENCE_MISSING")
    return {
        "attempt_constraint": {key: ambient.get(key) for key in fields},
        "json_boundary_constraint": {key: visual.get(key) for key in fields},
        "context_build_seconds": 0.0,
        "source": "retained_r22_attempt_metadata",
    }


def parse_retained_factors(
    parent: Any,
    structural: Mapping[str, Any],
    attempts: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    family_by_key = {
        str(row["family_key"]): row for row in structural["families"]
    }
    parsed = {}
    for row in attempts:
        factor_key = row.get("factor_key")
        factor_kind = row.get("factor_kind")
        family_key = row.get("family_key")
        raw = row.get("raw_output")
        if (
            not isinstance(factor_key, str)
            or not isinstance(factor_kind, str)
            or not isinstance(family_key, str)
            or not isinstance(raw, str)
        ):
            raise ReplayError("R22_REPLAY_ATTEMPT_BINDING_INVALID")
        observed_hash = "sha256:" + hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()
        if observed_hash != row.get("raw_output_sha256"):
            raise ReplayError(
                f"R22_REPLAY_RAW_OUTPUT_HASH_MISMATCH:{factor_key}"
            )
        try:
            value = parent._strict_json_output(raw)
            if factor_kind == "visual":
                accepted = parent.validate_visual_factor_output(value)
            elif factor_kind == "ambient":
                accepted = parent.validate_ambient_factor_output(value)
            elif factor_kind == "family_composition":
                family = family_by_key[family_key]
                accepted = parent.validate_composition_factor_output(
                    value,
                    component_count=len(family["intervals"]),
                    family_shape=str(family["shape"]),
                )
            else:
                raise ReplayError(
                    f"R22_REPLAY_FACTOR_KIND_INVALID:{factor_kind}"
                )
        except parent.AuthoringError as exc:
            raise ReplayError(
                f"R22_REPLAY_FACTOR_VALIDATION_FAILED:{factor_key}:{exc}"
            ) from exc
        if (
            parent._parsed_output_binding_hash(factor_kind, accepted)
            != row.get("parsed_output_sha256")
        ):
            raise ReplayError(
                f"R22_REPLAY_PARSED_OUTPUT_HASH_MISMATCH:{factor_key}"
            )
        if factor_key in parsed:
            raise ReplayError(f"R22_REPLAY_FACTOR_DUPLICATE:{factor_key}")
        parsed[factor_key] = accepted
    return parsed


def assemble_families(
    parent: Any,
    structural: Mapping[str, Any],
    factors: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    parsed_by_family = {}
    local_results = {}
    for family in structural["families"]:
        family_key = str(family["family_key"])
        components = []
        for ordinal in range(1, len(family["intervals"]) + 1):
            components.append(
                {
                    "ordinal": ordinal,
                    **factors[
                        f"{family_key}:component:{ordinal}:visual"
                    ],
                    **factors[
                        f"{family_key}:component:{ordinal}:ambient"
                    ],
                }
            )
        composition = factors[f"{family_key}:family_composition"]
        mechanical = parent._mechanical_composition_texts(
            components,
            composition,
            family_shape=str(family["shape"]),
        )
        assembled = {
            "components": components,
            "composition_factor": composition,
            **composition,
            **mechanical,
        }
        try:
            local_results[family_key] = (
                parent.validate_component_local_composition(
                    family, components, assembled
                )
            )
        except parent.AuthoringError as exc:
            raise ReplayError(
                f"R22_REPLAY_COMPONENT_LOCAL_GATE_FAILED:"
                f"{family_key}:{exc}"
            ) from exc
        parsed_by_family[family_key] = assembled
    return parsed_by_family, local_results


def run_replay(
    root: Path,
    *,
    audit_path: Path,
    capsule_path: Path,
) -> dict[str, Any]:
    audit = load_json(root / audit_path)
    if audit.get("decision_token") != (
        "R22_SCIENTIFIC_NO_GO_PERMANENT_R23_REQUIRED"
    ):
        raise ReplayError("R22_REPLAY_TERMINAL_DECISION_MISMATCH")
    seal_checks = verify_seal_manifest(root, audit)
    capsule = root / capsule_path
    failure_capsule = load_json(capsule / "failure_capsule.json")
    capsule_checks = verify_capsule_manifest(capsule, failure_capsule)
    subset = load_json(capsule / "canary2_subset_bundle.json")
    prompt_manifest = load_json(capsule / "prompt_manifest.json")
    attempts = load_attempts(capsule / "raw_attempts.jsonl")
    if len(attempts) != 13:
        raise ReplayError("R22_REPLAY_FACTOR_COUNT_MISMATCH")

    parent = load_parent(root)
    constraint_context = retained_constraint_context(attempts)
    parent._TRUSTED_AMBIENT_CONSTRAINT_CONTEXT = constraint_context
    factors = parse_retained_factors(parent, subset, attempts)
    if len(factors) != 13:
        raise ReplayError("R22_REPLAY_FACTOR_COUNT_MISMATCH")
    parsed_by_family, local_results = assemble_families(
        parent, subset, factors
    )
    accepted = parent.build_accepted_factor_manifest(
        subset, parsed_by_family, attempts
    )
    expected_manifest_hash = audit["top_level_exception"][
        "exact_binding_and_provenance"
    ]["reconstructed_manifest_payload_sha256"]
    if accepted.get("manifest_payload_sha256") != expected_manifest_hash:
        raise ReplayError("R22_REPLAY_ACCEPTED_MANIFEST_HASH_MISMATCH")
    with parent._temporary_expected_counts(families=3, queries=13):
        queries, descriptions = parent.materialize_query_records(
            subset, parsed_by_family, accepted
        )
    provenance = parent.validate_accepted_factor_provenance(
        accepted,
        attempts,
        queries,
        descriptions,
        structural=subset,
        prompt_manifest=prompt_manifest,
        trusted_constraint_context=constraint_context,
    )
    if provenance["bound_final_row_count"] != 26:
        raise ReplayError("R22_REPLAY_FINAL_ROW_COUNT_MISMATCH")

    tuple_duplicates = parent.ambient_semantic_tuple_duplicate_audit(
        accepted, queries, scope="r22_deterministic_replay"
    )
    lexical = parent.lexical_collision_findings(queries)
    standalone = parent.standalone_reference_audit(queries)
    identity = parent.query_description_identity_audit(
        queries, descriptions
    )
    far_coverage = parent.far_composition_audit(
        subset, queries, descriptions
    )
    exact_duplicates = [
        row for row in lexical if row["kind"] == "exact_duplicate"
    ]
    near_collisions = [
        row for row in lexical if row["kind"] == "lexical_near_collision"
    ]
    cross_family_tuple_duplicates = [
        row
        for row in tuple_duplicates["collision_ledger"]
        if not row["same_family"]
    ]
    blocking = bool(exact_duplicates or near_collisions)
    if not blocking:
        raise ReplayError("R22_REPLAY_BLOCKING_COLLISIONS_NOT_REPRODUCED")
    if (
        standalone["status"] != "PASS"
        or identity["status"] != "PASS"
        or far_coverage["status"] != "PASS"
    ):
        raise ReplayError("R22_REPLAY_NONCOLLISION_GATE_REGRESSION")

    return {
        "schema_version": (
            "av-trace.p23-102-r22-deterministic-replay-report/1.0"
        ),
        "report_date": CURRENT_DATE,
        "classification": "RESTRICTED",
        "replay_id": "P23_102_R22_DETERMINISTIC_REPLAY_R23_A",
        "decision": "NO-GO",
        "permanent_r22_disposition": (
            "R22_SCIENTIFIC_NO_GO_PERMANENT_R23_REQUIRED"
        ),
        "r23_status": "R23_A_IMPLEMENTATION_READY",
        "scope": {
            "retained_evidence_only": True,
            "model_execution": False,
            "media_decode": False,
            "asr_executed": False,
            "embedding_executed": False,
            "siglip_executed": False,
            "clap_executed": False,
            "retrieval_or_scoring_executed": False,
            "network_requests": 0,
            "failure_capsule_modified": False,
            "authorization_or_marker_modified": False,
            "inference_from_unexecuted_models": False,
        },
        "integrity": {
            "status": "PASS",
            "terminal_seal_checks": seal_checks,
            "failure_capsule_checks": capsule_checks,
            "tamper_or_hash_mismatch_policy": "FAIL_CLOSED",
        },
        "reconstruction": {
            "status": "PASS",
            "accepted_factor_count": len(factors),
            "query_row_count": len(queries),
            "description_row_count": len(descriptions),
            "bound_final_row_count": provenance["bound_final_row_count"],
            "cross_factor_fill_or_substitution_detected": provenance[
                "cross_factor_fill_or_substitution_detected"
            ],
            "accepted_factor_manifest_payload_sha256": accepted[
                "manifest_payload_sha256"
            ],
            "queries_payload_sha256": parent.semantic_hash(queries),
            "descriptions_payload_sha256": parent.semantic_hash(
                descriptions
            ),
            "component_local_results": local_results,
        },
        "deterministic_gates": {
            "exact_binding": {
                "status": "PASS",
                **provenance,
            },
            "ambient_tuple_duplicates": tuple_duplicates,
            "lexical_exact_and_near_collision": {
                "status": "FAIL_BLOCKING",
                "threshold": parent.LEXICAL_COLLISION_THRESHOLD,
                "exact_duplicate_count": len(exact_duplicates),
                "near_collision_count": len(near_collisions),
                "findings": lexical,
            },
            "standalone_reference": standalone,
            "query_description_identity": identity,
            "far_ordered_query_coverage": far_coverage,
        },
        "blocking_collision_summary": {
            "exact_duplicate_pair_count": len(exact_duplicates),
            "near_collision_count": len(near_collisions),
            "cross_family_ambient_tuple_duplicate_count": len(
                cross_family_tuple_duplicates
            ),
            "cross_family_ambient_tuple_duplicates": (
                cross_family_tuple_duplicates
            ),
            "blocking_collisions_reproduced": True,
        },
        "conclusion": (
            "The R23-A implementation repair accepts the retained local "
            "sentence-bound pronoun and reconstructs all 13 factors and 26 "
            "final rows exactly. Independent retained lexical collisions "
            "still block R22. R22 remains permanently NO-GO and this report "
            "does not authorize or perform any rerun."
        ),
    }


def write_report(path: Path, report: Mapping[str, Any]) -> str:
    payload = dict(report)
    payload["report_payload_sha256"] = semantic_hash(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return file_sha256(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--capsule", type=Path, default=DEFAULT_CAPSULE)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--self-test", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.repo_root.resolve()
    try:
        report = run_replay(
            root,
            audit_path=args.audit,
            capsule_path=args.capsule,
        )
        output = root / args.output
        report_file_hash = write_report(output, report)
    except ReplayError as exc:
        print(
            json.dumps(
                {"status": "FAIL_CLOSED", "error": str(exc)},
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    result = {
        "status": "PASS",
        "decision": report["decision"],
        "permanent_r22_disposition": report[
            "permanent_r22_disposition"
        ],
        "report_path": args.output.as_posix(),
        "report_file_sha256": report_file_hash,
        "accepted_factor_count": report["reconstruction"][
            "accepted_factor_count"
        ],
        "bound_final_row_count": report["reconstruction"][
            "bound_final_row_count"
        ],
        "model_calls": 0,
        "asr_calls": 0,
        "embedding_calls": 0,
        "clap_calls": 0,
    }
    if args.self_test and result["decision"] != "NO-GO":
        raise ReplayError("R22_REPLAY_SELF_TEST_DECISION_MISMATCH")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
