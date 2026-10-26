#!/usr/bin/env python3
"""Audit post-freeze files against source exposure alias manifest v2.

The frozen v2 manifest is never rebuilt or modified.  This audit imports the
v2 scanner and classification primitives so that the pinned and current
eligible inventories are evaluated with the same policy.  Downstream
governance products and technical custody metadata are reported but do not
become source exposures merely because they restate governance state.

The v3.1 private ledger is read only inside the custodian boundary.  Public
JSON and Markdown expose aggregate selected-commitment/closure hit counts, not
selected identities, aliases, paths containing selected identities, salts, or
commitment values.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SCHEMA_VERSION = (
    "av-trace.source-exposure-alias-manifest-v2-supplemental-audit/1.0"
)
AUDIT_ID = "SOURCE_EXPOSURE_ALIAS_MANIFEST_V2_SUPPLEMENTAL_AUDIT"
CREATED_DATE = "2026-10-15"
FINAL_PASS = "SOURCE_EXPOSURE_ALIAS_MANIFEST_V2_SUPPLEMENTAL_AUDIT_PASS"
FINAL_REPAIR = "SOURCE_EXPOSURE_ALIAS_MANIFEST_V2_SUPPLEMENTAL_AUDIT_REPAIR"

OUTPUT_REL = Path(
    "data/rehearsal_plan/"
    "source_exposure_alias_manifest_v2_supplemental_audit.json"
)
REVIEW_REL = Path(
    "docs/review/"
    "source_exposure_alias_manifest_v2_supplemental_audit.md"
)
MANIFEST_REL = Path(
    "data/rehearsal_plan/source_exposure_alias_manifest_v2.json"
)
LEDGER_V2_REL = Path(
    "data/rehearsal_plan/untouched_test_group_ledger_v2.json"
)
PRIVATE_V3_1_REL = Path(
    "data/restricted/untouched_test_group_ledger_v3_1_private.json"
)
V2_TOOL_REL = Path("tools/source_exposure_alias_manifest_v2.py")

# These bind the audit to the frozen inputs without changing those inputs.
EXPECTED_MANIFEST_SHA256 = (
    "2c631f070505f60a49862a05d879c83e856d7dd60bca99fb34bfa16e8c064618"
)
EXPECTED_LEDGER_V2_SHA256 = (
    "9f9d12628f6e928c458db89d9a76cf46d8d602198efe90cc104e6b6bc2bc9c63"
)
EXPECTED_PRIVATE_V3_1_SHA256 = (
    "11f87b1d3d39c5ca12859b7cb5385eaae923add03075a0bd0984155cf403a149"
)
EXPECTED_PINNED_INVENTORY_SHA256 = (
    "361efdbd8af0c0d3cacf471d846ce551207c415ed51299b5e0f40c30875ab379"
)

AUDIT_SELF_OUTPUTS = {OUTPUT_REL.as_posix(), REVIEW_REL.as_posix()}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SEMANTIC_LINE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "semantic_prompt",
        re.compile(r"\b(?:semantic[_ -]?prompt|prompted to|prompt target)\b", re.I),
    ),
    (
        "semantic_routing_target",
        re.compile(
            r"\b(?:semantic[_ -]?routing|routing target|source_ids_or_pool|"
            r"exact_ids_or_pool|candidate route)\b",
            re.I,
        ),
    ),
    (
        "selection_rationale",
        re.compile(r"\b(?:selection|ranking)[_ -]?rationale\b", re.I),
    ),
    (
        "semantic_dossier_description",
        re.compile(r"\b(?:semantic dossier|dossier description)\b", re.I),
    ),
    (
        "candidate_queue_review_or_mining",
        re.compile(
            r"\b(?:candidate queue|candidate review|candidate mining)\b", re.I
        ),
    ),
    (
        "learned_ranking",
        re.compile(r"\b(?:learned ranking|learned model ranking)\b", re.I),
    ),
)

SOURCE_AUTHORITY_GOVERNANCE_PATHS = {
    "data/restricted/holoassist_opaque_group_universe_v1.json",
    "data/restricted/untouched_test_group_ledger_v3_private.json",
    PRIVATE_V3_1_REL.as_posix(),
}


class SupplementalAuditError(ValueError):
    """Raised when the supplemental audit must fail closed."""


def _load_v2_tool(root: Path):
    path = root / V2_TOOL_REL
    spec = importlib.util.spec_from_file_location(
        "_source_exposure_alias_manifest_v2_for_supplemental_audit", path
    )
    if spec is None or spec.loader is None:
        raise SupplementalAuditError("V2_TOOL_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SupplementalAuditError(f"JSON_OBJECT_REQUIRED:{path.as_posix()}")
    return value


def _iter_scalar_strings(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for child in value.values():
            yield from _iter_scalar_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_scalar_strings(child)
    elif isinstance(value, str) and value:
        yield value


def selected_identity_strings(private: dict[str, Any]) -> set[str]:
    """Return private selected identity tokens for internal leak checks only."""
    values: set[str] = set()
    for group in private.get("selected_groups", []):
        evidence = group.get("identity_and_evidence", {})
        if group.get("dataset_lineage") == "HOLOASSIST":
            source = evidence.get("opaque_universe_group", {})
            recording_root = source.get("recording_root")
            if recording_root:
                values.add(str(recording_root))
            for variant in source.get("variants", []):
                for field in ("folder", "timing_path", "pose_path"):
                    if variant.get(field):
                        values.add(str(variant[field]))
        else:
            for field in (
                "closure_root",
                "exact_object_or_session_id",
                "production_lineage_id",
            ):
                if evidence.get(field):
                    values.add(str(evidence[field]))
            values.update(
                str(value)
                for value in evidence.get("closure_aliases", [])
                if value
            )
    return values


def _selected_groups(
    private: dict[str, Any],
) -> tuple[
    dict[str, set[str]],
    dict[str, str],
    dict[str, str],
    set[str],
]:
    """Build private token maps keyed by opaque internal group commitments."""
    aliases_by_commitment: dict[str, set[str]] = {}
    alias_to_commitment: dict[str, str] = {}
    direct_commitment_to_group: dict[str, str] = {}
    selected_v2_roots: set[str] = set()
    for group in private.get("selected_groups", []):
        commitment = str(group.get("v3_1_group_commitment_sha256", ""))
        if not SHA256_RE.fullmatch(commitment):
            raise SupplementalAuditError("INVALID_PRIVATE_SELECTED_COMMITMENT")
        aliases: set[str] = set()
        evidence = group.get("identity_and_evidence", {})
        if group.get("dataset_lineage") == "HOLOASSIST":
            source = evidence.get("opaque_universe_group", {})
            for field in ("recording_root",):
                if source.get(field):
                    aliases.add(str(source[field]))
            for variant in source.get("variants", []):
                for field in ("folder", "timing_path", "pose_path"):
                    if variant.get(field):
                        aliases.add(str(variant[field]))
        else:
            root = evidence.get("closure_root")
            if root:
                selected_v2_roots.add(str(root))
            for field in (
                "closure_root",
                "exact_object_or_session_id",
                "production_lineage_id",
            ):
                if evidence.get(field):
                    aliases.add(str(evidence[field]))
            aliases.update(
                str(value)
                for value in evidence.get("closure_aliases", [])
                if value
            )
        aliases_by_commitment[commitment] = aliases
        for alias in sorted(aliases, key=lambda value: (-len(value), value)):
            alias_to_commitment.setdefault(alias.casefold(), commitment)
        for field in (
            "v3_1_group_commitment_sha256",
            "source_commitment_sha256",
        ):
            value = str(group.get(field, ""))
            if SHA256_RE.fullmatch(value):
                direct_commitment_to_group[value] = commitment
    if len(aliases_by_commitment) != len(private.get("selected_groups", [])):
        raise SupplementalAuditError("DUPLICATE_PRIVATE_SELECTED_COMMITMENT")
    return (
        aliases_by_commitment,
        alias_to_commitment,
        direct_commitment_to_group,
        selected_v2_roots,
    )


def _token_present(text: str, token: str) -> bool:
    if not token:
        return False
    pattern = re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])",
        re.IGNORECASE,
    )
    return pattern.search(text) is not None


def _selected_groups_in_text(
    text: str, aliases_by_commitment: dict[str, set[str]]
) -> set[str]:
    hits: set[str] = set()
    for commitment, aliases in aliases_by_commitment.items():
        if any(_token_present(text, alias) for alias in aliases):
            hits.add(commitment)
    return hits


def _direct_commitment_groups_in_text(
    text: str, direct_commitment_to_group: dict[str, str]
) -> set[str]:
    lower = text.lower()
    return {
        group
        for commitment, group in direct_commitment_to_group.items()
        if commitment in lower
    }


def _path_contains_selected_identity(
    relative: str, selected_identities: set[str]
) -> bool:
    lower = relative.casefold()
    return any(value.casefold() in lower for value in selected_identities)


def public_path_ref(
    relative: str, selected_identities: set[str]
) -> tuple[str, str]:
    path_hash = hashlib.sha256(relative.encode("utf-8")).hexdigest()
    if (
        _path_contains_selected_identity(relative, selected_identities)
        or relative.lower().startswith(
            "data/restricted/holoassist_technical_timing_cache_v1/"
        )
    ):
        return f"custodian-private-path:{path_hash[:16]}", path_hash
    return relative, path_hash


def governance_reason(relative: str) -> str | None:
    lower = relative.lower()
    if lower.startswith(
        "data/restricted/holoassist_technical_timing_cache_v1/"
    ):
        return (
            "technical custody timing metadata; no media or semantic body was "
            "opened and this source-authority cache is not a routing exposure"
        )
    if relative in SOURCE_AUTHORITY_GOVERNANCE_PATHS:
        return (
            "custodian-private source-authority governance input; comparison "
            "against itself is excluded to avoid a tautological exposure"
        )
    if lower.startswith("docs/review/"):
        return (
            "downstream review/governance artifact; ignored unless an exact "
            "selected identity and semantic-routing category co-occur"
        )
    if lower.startswith(("data/rehearsal_plan/", "data/restricted/")) and any(
        token in Path(lower).name
        for token in (
            "audit",
            "commitment",
            "ledger",
            "manifest",
            "preflight",
            "supplement",
            "universe",
        )
    ):
        return (
            "downstream manifest/ledger/audit governance artifact; ignored "
            "unless it reveals selected identity routing"
        )
    return None


def _semantic_event_types_for_line(
    relative: str, line: str, v2_tool: Any
) -> set[str]:
    event_types = set(v2_tool.path_event_types(relative))
    event_types.update(
        event_type
        for event_type, pattern in SEMANTIC_LINE_PATTERNS
        if pattern.search(line)
    )
    return event_types


def _read_eligible_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def classify_added_file(
    *,
    root: Path,
    inventory_row: dict[str, Any],
    v2_tool: Any,
    v2_lookup: dict[str, str],
    selected_aliases_by_commitment: dict[str, set[str]],
    direct_commitment_to_group: dict[str, str],
    selected_v2_roots: set[str],
    selected_identities: set[str],
) -> tuple[dict[str, Any], list[dict[str, Any]], set[str], set[str]]:
    """Classify one eligible post-freeze file without returning private IDs."""
    relative = inventory_row["path"]
    path = root / relative
    text = _read_eligible_text(path)
    public_path, path_hash = public_path_ref(relative, selected_identities)
    governance = governance_reason(relative)

    observed_v2_roots: set[str] = set()
    observed_selected_groups = _selected_groups_in_text(
        text, selected_aliases_by_commitment
    )
    observed_direct_groups = _direct_commitment_groups_in_text(
        text, direct_commitment_to_group
    )
    for line in text.splitlines():
        for alias in v2_tool.aliases_in_value(line, v2_lookup):
            root_name = v2_lookup.get(v2_tool.normalize_alias(alias))
            if root_name:
                observed_v2_roots.add(root_name)

    events: list[dict[str, Any]] = []
    exposure_selected_groups: set[str] = set()
    exposure_v2_roots: set[str] = set()
    source_authority = relative in SOURCE_AUTHORITY_GOVERNANCE_PATHS or (
        relative.lower().startswith(
            "data/restricted/holoassist_technical_timing_cache_v1/"
        )
    )
    for line_number, line in enumerate(text.splitlines(), 1):
        event_types = _semantic_event_types_for_line(relative, line, v2_tool)
        if not event_types or source_authority:
            continue
        line_selected_groups = _selected_groups_in_text(
            line, selected_aliases_by_commitment
        )
        line_selected_groups.update(
            _direct_commitment_groups_in_text(
                line, direct_commitment_to_group
            )
        )
        line_v2_roots = {
            v2_lookup[v2_tool.normalize_alias(alias)]
            for alias in v2_tool.aliases_in_value(line, v2_lookup)
            if v2_tool.normalize_alias(alias) in v2_lookup
        }
        # A governance product is non-authoritative for exposure unless it
        # actually couples selected identity material to semantic routing.
        if governance and not line_selected_groups:
            continue
        for event_type in sorted(event_types):
            for group in sorted(line_selected_groups):
                events.append(
                    {
                        "closure_class": "V3_1_SELECTED_PRIVATE_REDACTED",
                        "event_type": event_type,
                        "evidence": {
                            "locator": f"line:{line_number}",
                            "path": public_path,
                            "path_sha256": path_hash,
                            "sha256": inventory_row["sha256"],
                        },
                        "selected_v3_1_hit": True,
                    }
                )
                exposure_selected_groups.add(group)
            for root_name in sorted(line_v2_roots):
                if root_name in selected_v2_roots:
                    # Selected v2 roots are represented only by the aggregate
                    # selected-hit channel, never by their identity.
                    continue
                events.append(
                    {
                        "closure_class": "V2_ALIAS_CLOSURE",
                        "closure_root": root_name,
                        "event_type": event_type,
                        "evidence": {
                            "locator": f"line:{line_number}",
                            "path": public_path,
                            "path_sha256": path_hash,
                            "sha256": inventory_row["sha256"],
                        },
                        "selected_v3_1_hit": False,
                    }
                )
                exposure_v2_roots.add(root_name)

    deduplicated_events: list[dict[str, Any]] = []
    seen_event_keys: set[tuple[Any, ...]] = set()
    for event in events:
        key = (
            event["closure_class"],
            event.get("closure_root"),
            event["event_type"],
            event["evidence"]["path_sha256"],
            event["evidence"]["locator"],
        )
        if key not in seen_event_keys:
            seen_event_keys.add(key)
            deduplicated_events.append(event)

    if deduplicated_events:
        classification = "SOURCE_EXPOSURE_CONTAMINATION"
        rationale = (
            "strict v2 semantic exposure category co-occurs with an alias or "
            "private selected closure/commitment reference"
        )
    elif governance:
        classification = "IGNORED_GOVERNANCE_ARTIFACT"
        rationale = governance
    else:
        classification = "NO_SOURCE_EXPOSURE"
        rationale = (
            "eligible post-freeze text has no strict v2 semantic exposure "
            "event coupled to a known alias closure"
        )

    row = {
        "bytes": inventory_row["bytes"],
        "classification": classification,
        "path": public_path,
        "path_sha256": path_hash,
        "rationale": rationale,
        "sha256": inventory_row["sha256"],
        "reference_counts": {
            "direct_selected_commitment_group_count": len(
                observed_direct_groups
            ),
            "selected_private_group_count": len(observed_selected_groups),
            "v2_alias_closure_count": len(observed_v2_roots),
        },
        "strict_contamination_event_count": len(deduplicated_events),
    }
    return (
        row,
        deduplicated_events,
        exposure_selected_groups,
        exposure_v2_roots,
    )


def _validate_scanner_policy(v2_tool: Any, manifest: dict[str, Any]) -> None:
    freeze = manifest.get("scan_freeze", {})
    expected = {
        "allowlisted_extensions": sorted(v2_tool.ALLOWLISTED_EXTENSIONS),
        "max_file_bytes": v2_tool.MAX_FILE_BYTES,
        "roots": list(v2_tool.SCAN_ROOTS),
    }
    for field, value in expected.items():
        if freeze.get(field) != value:
            raise SupplementalAuditError(
                f"FROZEN_SCANNER_POLICY_MISMATCH:{field}"
            )
    if freeze.get("pinned_inventory_sha256") != (
        EXPECTED_PINNED_INVENTORY_SHA256
    ):
        raise SupplementalAuditError("FROZEN_PINNED_INVENTORY_ID_MISMATCH")


def _frozen_inventory_audit(
    *,
    current_inventory: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    pinned = manifest["scan_freeze"]["pinned_files"]
    current_by_path = {row["path"]: row for row in current_inventory}
    missing: list[str] = []
    changed: list[str] = []
    for row in pinned:
        current = current_by_path.get(row["path"])
        if current is None:
            missing.append(row["path"])
        elif current != row:
            changed.append(row["path"])
    unchanged = not missing and not changed
    return {
        "changed_file_count": len(changed),
        "missing_file_count": len(missing),
        "pinned_file_count": len(pinned),
        "pinned_file_hashes_unchanged": unchanged,
        "pinned_inventory_sha256": sha256_value(pinned),
        # Paths are intentionally omitted from public output. A non-zero count
        # fails closed and directs the custodian to a private comparison.
        "status": "UNCHANGED" if unchanged else "REPAIR_REQUIRED",
    }


def build_audit(root: Path) -> dict[str, Any]:
    root = root.resolve()
    v2_tool = _load_v2_tool(root)
    manifest_path = root / MANIFEST_REL
    ledger_v2_path = root / LEDGER_V2_REL
    private_path = root / PRIVATE_V3_1_REL
    manifest = load_json(manifest_path)
    private = load_json(private_path)

    input_hashes = {
        "frozen_manifest_v2": sha256_file(manifest_path),
        "frozen_ledger_v2": sha256_file(ledger_v2_path),
        "custodian_private_v3_1": sha256_file(private_path),
    }
    _validate_scanner_policy(v2_tool, manifest)

    raw_current_inventory, skipped = v2_tool.discover_inventory(root)
    # The v2 scanner is used unchanged. As v2 excludes its own outputs, this
    # supplemental audit removes only its two own public outputs after the
    # scanner returns, preventing self-referential hashes and preserving a
    # stable post-freeze count.
    current_inventory = [
        row
        for row in raw_current_inventory
        if row["path"] not in AUDIT_SELF_OUTPUTS
    ]
    frozen_audit = _frozen_inventory_audit(
        current_inventory=current_inventory,
        manifest=manifest,
    )
    pinned_paths = {
        row["path"] for row in manifest["scan_freeze"]["pinned_files"]
    }
    added_inventory = sorted(
        (
            row
            for row in current_inventory
            if row["path"] not in pinned_paths
        ),
        key=lambda row: row["path"],
    )

    components = manifest["alias_graph"]["components"]
    v2_lookup = {
        alias: component["closure_root"]
        for component in components
        for alias in component["aliases"]
    }
    (
        selected_aliases,
        _alias_to_commitment,
        direct_commitments,
        selected_v2_roots,
    ) = _selected_groups(private)
    selected_identities = selected_identity_strings(private)

    public_added_files: list[dict[str, Any]] = []
    contamination_events: list[dict[str, Any]] = []
    selected_exposure_groups: set[str] = set()
    exposed_v2_roots: set[str] = set()
    for inventory_row in added_inventory:
        (
            public_row,
            file_events,
            file_selected_groups,
            file_v2_roots,
        ) = classify_added_file(
            root=root,
            inventory_row=inventory_row,
            v2_tool=v2_tool,
            v2_lookup=v2_lookup,
            selected_aliases_by_commitment=selected_aliases,
            direct_commitment_to_group=direct_commitments,
            selected_v2_roots=selected_v2_roots,
            selected_identities=selected_identities,
        )
        public_added_files.append(public_row)
        contamination_events.extend(file_events)
        selected_exposure_groups.update(file_selected_groups)
        exposed_v2_roots.update(file_v2_roots)

    contamination_events.sort(
        key=lambda row: (
            row["evidence"]["path_sha256"],
            row["evidence"]["locator"],
            row["event_type"],
            row.get("closure_root", ""),
            row["closure_class"],
        )
    )
    for index, event in enumerate(contamination_events, 1):
        event["event_id"] = f"MXE2S-{index:04d}"

    classification_counts = Counter(
        row["classification"] for row in public_added_files
    )
    ignored = [
        {
            "bytes": row["bytes"],
            "path": row["path"],
            "path_sha256": row["path_sha256"],
            "rationale": row["rationale"],
            "sha256": row["sha256"],
        }
        for row in public_added_files
        if row["classification"] == "IGNORED_GOVERNANCE_ARTIFACT"
    ]
    direct_exposure_groups = {
        group
        for row in contamination_events
        if row["selected_v3_1_hit"]
        for group in selected_exposure_groups
    }
    selected_hit_count = len(selected_exposure_groups)

    input_integrity_ok = (
        input_hashes["frozen_manifest_v2"] == EXPECTED_MANIFEST_SHA256
        and input_hashes["frozen_ledger_v2"] == EXPECTED_LEDGER_V2_SHA256
        and input_hashes["custodian_private_v3_1"]
        == EXPECTED_PRIVATE_V3_1_SHA256
    )
    pass_status = (
        input_integrity_ok
        and frozen_audit["pinned_file_hashes_unchanged"]
        and not contamination_events
        and selected_hit_count == 0
    )
    final_marker = FINAL_PASS if pass_status else FINAL_REPAIR

    audit = {
        "alias_closure_audit": {
            "nonselected_v2_contaminated_closure_count": len(
                exposed_v2_roots
            ),
            "nonselected_v2_contaminated_closures": sorted(exposed_v2_roots),
            "selected_v3_1_contaminated_closure_count": selected_hit_count,
            "status": "CLEAR" if not contamination_events else "HIT",
            "v2_alias_graph_component_count": len(components),
        },
        "audit_id": AUDIT_ID,
        "contamination_events": contamination_events,
        "created_date": CREATED_DATE,
        "decision": {
            "decision": "PASS" if pass_status else "REPAIR",
            "frozen_inputs_unchanged": input_integrity_ok
            and frozen_audit["pinned_file_hashes_unchanged"],
            "reason": (
                "frozen inputs are unchanged; all current post-freeze files "
                "are governance/technical artifacts; no strict exposure or "
                "selected v3.1 hit was found"
                if pass_status
                else "a frozen-input mismatch or supplemental exposure hit "
                "requires custodian repair"
            ),
            "selected_v3_1_hit": selected_hit_count > 0,
        },
        "final_marker": final_marker,
        "frozen_input_integrity": {
            "custodian_private_v3_1_sha256_matches": input_hashes[
                "custodian_private_v3_1"
            ]
            == EXPECTED_PRIVATE_V3_1_SHA256,
            "frozen_ledger_v2_sha256_matches": input_hashes[
                "frozen_ledger_v2"
            ]
            == EXPECTED_LEDGER_V2_SHA256,
            "frozen_manifest_v2_sha256_matches": input_hashes[
                "frozen_manifest_v2"
            ]
            == EXPECTED_MANIFEST_SHA256,
            "pinned_inventory": frozen_audit,
        },
        "ignored_governance_artifacts": ignored,
        "safety_boundary": {
            "custodian_private_identity_comparison_performed": True,
            "media_opened_or_inspected": False,
            "network_used": False,
            "public_selected_commitment_values_exposed": False,
            "public_selected_identities_exposed": False,
            "semantic_annotation_bodies_opened": False,
            "transcript_or_caption_bodies_opened": False,
        },
        "scanner_policy": {
            "allowlisted_extensions": sorted(
                v2_tool.ALLOWLISTED_EXTENSIONS
            ),
            "audit_self_output_rule": (
                "Run the unchanged v2 scanner, then omit only this audit's "
                "JSON and Markdown outputs to prevent self-referential hashes."
            ),
            "excluded_directory_names": sorted(
                v2_tool.EXCLUDED_DIRECTORY_NAMES
            ),
            "max_file_bytes": v2_tool.MAX_FILE_BYTES,
            "roots": list(v2_tool.SCAN_ROOTS),
            "same_as_frozen_manifest_v2": True,
            "semantic_body_name_tokens": sorted(
                v2_tool.SEMANTIC_BODY_NAME_TOKENS
            ),
            "skipped_by_reason_current_scan": skipped,
            "source_tool": V2_TOOL_REL.as_posix(),
        },
        "schema_version": SCHEMA_VERSION,
        "selected_v3_1_private_comparison": {
            "direct_selected_commitment_exposure_hit_count": len(
                direct_exposure_groups
            ),
            "selected_commitment_count": len(selected_aliases),
            "selected_commitment_or_closure_exposure_hit_count": (
                selected_hit_count
            ),
            "selected_closure_exposure_hit_count": selected_hit_count,
            "status": "CLEAR" if selected_hit_count == 0 else "HIT",
        },
        "supplemental_inventory": {
            "added_files": public_added_files,
            "classification_counts": dict(sorted(classification_counts.items())),
            "ignored_governance_artifact_count": len(ignored),
            "post_freeze_file_count": len(public_added_files),
            "post_freeze_public_inventory_sha256": sha256_value(
                public_added_files
            ),
            "strict_contamination_event_count": len(contamination_events),
        },
    }
    validate_public_non_disclosure(
        private,
        public_json_text=json.dumps(audit, indent=2, sort_keys=True) + "\n",
        public_markdown_text=render_markdown(audit),
    )
    validate_audit(audit)
    return audit


def validate_public_non_disclosure(
    private: dict[str, Any],
    *,
    public_json_text: str,
    public_markdown_text: str,
) -> None:
    combined = public_json_text + "\n" + public_markdown_text
    for identity in selected_identity_strings(private):
        if identity and identity.casefold() in combined.casefold():
            raise SupplementalAuditError("PUBLIC_SELECTED_IDENTITY_LEAK")
    for group in private.get("selected_groups", []):
        for field in (
            "v3_1_group_commitment_sha256",
            "source_commitment_sha256",
            "v3_1_commitment_salt_hex",
        ):
            value = str(group.get(field, ""))
            if value and value in combined:
                raise SupplementalAuditError(
                    "PUBLIC_SELECTED_COMMITMENT_VALUE_LEAK"
                )
    for forbidden in (
        '"identity_and_evidence"',
        '"closure_aliases"',
        '"v3_1_commitment_salt_hex"',
        "VideoMp4Timing",
        "Pose_sync",
        "extracted_videos/",
    ):
        if forbidden.casefold() in combined.casefold():
            raise SupplementalAuditError("PUBLIC_PRIVATE_STRUCTURE_LEAK")


def validate_audit(audit: dict[str, Any]) -> None:
    if audit.get("schema_version") != SCHEMA_VERSION:
        raise SupplementalAuditError("SCHEMA_VERSION_MISMATCH")
    if audit.get("final_marker") not in {FINAL_PASS, FINAL_REPAIR}:
        raise SupplementalAuditError("FINAL_MARKER_INVALID")
    inventory = audit["supplemental_inventory"]
    if inventory["post_freeze_file_count"] != len(inventory["added_files"]):
        raise SupplementalAuditError("SUPPLEMENTAL_FILE_COUNT_MISMATCH")
    if inventory["post_freeze_public_inventory_sha256"] != sha256_value(
        inventory["added_files"]
    ):
        raise SupplementalAuditError("SUPPLEMENTAL_INVENTORY_HASH_MISMATCH")
    selected = audit["selected_v3_1_private_comparison"]
    if selected["status"] == "CLEAR" and (
        selected["selected_commitment_or_closure_exposure_hit_count"] != 0
    ):
        raise SupplementalAuditError("SELECTED_STATUS_COUNT_MISMATCH")
    if audit["final_marker"] == FINAL_PASS:
        if inventory["strict_contamination_event_count"] != 0:
            raise SupplementalAuditError("PASS_WITH_CONTAMINATION")
        if not audit["frozen_input_integrity"]["pinned_inventory"][
            "pinned_file_hashes_unchanged"
        ]:
            raise SupplementalAuditError("PASS_WITH_CHANGED_PINNED_FILE")


def render_markdown(audit: dict[str, Any]) -> str:
    inventory = audit["supplemental_inventory"]
    selected = audit["selected_v3_1_private_comparison"]
    frozen = audit["frozen_input_integrity"]
    lines = [
        "# Source exposure alias manifest v2 supplemental audit",
        "",
        f"- Final marker: `{audit['final_marker']}`",
        f"- Date: `{audit['created_date']}`",
        f"- Post-freeze eligible files: {inventory['post_freeze_file_count']}",
        (
            "- Ignored governance/technical artifacts: "
            f"{inventory['ignored_governance_artifact_count']}"
        ),
        (
            "- Strict supplemental contamination events: "
            f"{inventory['strict_contamination_event_count']}"
        ),
        (
            "- Selected v3.1 commitment/closure exposure hits: "
            f"{selected['selected_commitment_or_closure_exposure_hit_count']}"
        ),
        "",
        "## Frozen boundary",
        "",
        (
            "- Frozen manifest v2 hash unchanged: "
            f"`{str(frozen['frozen_manifest_v2_sha256_matches']).lower()}`"
        ),
        (
            "- Frozen ledger v2 hash unchanged: "
            f"`{str(frozen['frozen_ledger_v2_sha256_matches']).lower()}`"
        ),
        (
            "- All pinned file hashes unchanged: "
            f"`{str(frozen['pinned_inventory']['pinned_file_hashes_unchanged']).lower()}`"
        ),
        (
            "- Pinned files checked: "
            f"{frozen['pinned_inventory']['pinned_file_count']}"
        ),
        "",
        "The unchanged v2 scanner policy is used. Network, media, semantic "
        "annotation bodies, transcripts/captions, and learned payloads are "
        "outside the audit boundary. The two supplemental audit outputs are "
        "removed after scanning solely to avoid self-referential hashes.",
        "",
        "## Added files and classifications",
        "",
        "| File or private path commitment | SHA-256 | Classification | Rationale |",
        "|---|---|---|---|",
    ]
    for row in inventory["added_files"]:
        rationale = row["rationale"].replace("|", "\\|")
        lines.append(
            f"| `{row['path']}` | `{row['sha256']}` | "
            f"`{row['classification']}` | {rationale} |"
        )
    lines.extend(
        [
            "",
            "## Alias-closure and selected-roster result",
            "",
            (
                "- v2 alias graph components checked: "
                f"{audit['alias_closure_audit']['v2_alias_graph_component_count']}"
            ),
            (
                "- Non-selected v2 contaminated closures: "
                f"{audit['alias_closure_audit']['nonselected_v2_contaminated_closure_count']}"
            ),
            (
                "- Selected v3.1 contaminated closures: "
                f"{audit['alias_closure_audit']['selected_v3_1_contaminated_closure_count']}"
            ),
            f"- Selected comparison status: `{selected['status']}`",
            "",
            "No selected identity, alias, private path, salt, or commitment "
            "value is published. Only aggregate selected hit counts and status "
            "leave the custodian-private comparison boundary.",
            "",
            "## Contamination events",
            "",
        ]
    )
    if not audit["contamination_events"]:
        lines.append("None.")
    else:
        lines.extend(
            [
                "| Event | Type | Closure class | Evidence |",
                "|---|---|---|---|",
            ]
        )
        for event in audit["contamination_events"]:
            evidence = event["evidence"]
            lines.append(
                f"| `{event['event_id']}` | `{event['event_type']}` | "
                f"`{event['closure_class']}` | "
                f"`{evidence['path']}:{evidence['locator']}` |"
            )
    lines.extend(["", f"`{audit['final_marker']}`", ""])
    return "\n".join(lines)


def write_outputs(root: Path, audit: dict[str, Any]) -> None:
    output = root / OUTPUT_REL
    review = root / REVIEW_REL
    output.parent.mkdir(parents=True, exist_ok=True)
    review.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    review.write_text(render_markdown(audit), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed public outputs instead of writing",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    audit = build_audit(root)
    expected_json = json.dumps(audit, indent=2, sort_keys=True) + "\n"
    expected_markdown = render_markdown(audit)
    if args.check:
        if (root / OUTPUT_REL).read_text(encoding="utf-8") != expected_json:
            raise SupplementalAuditError("COMMITTED_JSON_IS_STALE")
        if (root / REVIEW_REL).read_text(encoding="utf-8") != expected_markdown:
            raise SupplementalAuditError("COMMITTED_MARKDOWN_IS_STALE")
    else:
        write_outputs(root, audit)
    print(audit["final_marker"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
