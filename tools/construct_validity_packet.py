#!/usr/bin/env python3
"""Build a portable, offline-fillable reviewer packet without asserting review."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

try:
    from .construct_validity_common import (
        ADJUDICATION_SCHEMA,
        ANNOTATION_SCHEMA,
        REVIEWER_ASSIGNMENT_SCHEMA,
        ROLES,
        SATURATION_AUDIT_SCHEMA,
        SOURCE_EXPOSURE_LEDGER_SCHEMA,
        ConstructValidityError,
        blank_adjudication,
        blank_annotation,
        blank_reviewer_assignment_ledger,
        blank_saturation_audit,
        blank_source_exposure_ledger,
        freeze_reviewer_assignment_ledger,
        load_json,
        now_utc,
        sha256_file,
        source_level_assignment_conflicts,
        validate_adjudication,
        validate_annotation,
        validate_registry,
        validate_reviewer_assignment_ledger,
        validate_saturation_audit,
        validate_source_exposure_ledger,
        write_json,
    )
except ImportError:
    from construct_validity_common import (
        ADJUDICATION_SCHEMA,
        ANNOTATION_SCHEMA,
        REVIEWER_ASSIGNMENT_SCHEMA,
        ROLES,
        SATURATION_AUDIT_SCHEMA,
        SOURCE_EXPOSURE_LEDGER_SCHEMA,
        ConstructValidityError,
        blank_adjudication,
        blank_annotation,
        blank_reviewer_assignment_ledger,
        blank_saturation_audit,
        blank_source_exposure_ledger,
        freeze_reviewer_assignment_ledger,
        load_json,
        now_utc,
        sha256_file,
        source_level_assignment_conflicts,
        validate_adjudication,
        validate_annotation,
        validate_registry,
        validate_reviewer_assignment_ledger,
        validate_saturation_audit,
        validate_source_exposure_ledger,
        write_json,
    )


README = """# AV-TRACE deferred construct-validity packet

This packet is an unfilled assignment. It is **not human review** and contains
no human-gold labels.

## Offline workflow

1. Copy the entire packet directory and the referenced source media to a
   reviewer workstation. If `media/` is present, verify it against
   `packet_manifest.json`.
2. Before distributing any role directory, update
   `coordinator/source_exposure_ledger.json` with every known prior exposure,
   assign real pseudonymous reviewer IDs in
   `coordinator/reviewer_assignments.json`, validate source-group conflicts,
   and freeze the assignment ledger. The generated blank draft is deliberately
   not distributable.
3. Preserve the blind alternative finder's packet until their full-source
   search is finished; do not disclose the machine-preferred SES first.
4. Give each person only their directory under `reviewer_packets/<family>/`;
   never give the blind finder the coordinator directory or another role's
   packet.
5. Edit that role's `form.json`; set `completion_status` to `completed`, fill
   every required field, and do not alter IDs or assignment provenance.
6. Validators must not read one another's decisions before submission.
7. The adjudicator acts only after all four pre-adjudication role forms are
   complete.
8. Freeze adjudication, then give the saturation auditor only their directory
   and the source. Never disclose accepted/preferred SESs, machine ranks, or
   validator/adjudicator decisions.
9. Append each actual packet exposure to the source exposure ledger. Copy the
   packet back and run `tools/construct_validity_import.py`.

Only the importer may derive H1/H2 status. Manually typing a human tier into a
machine registry is invalid.
"""


def build_packet(
    registry: dict,
    sample: dict,
    output_dir: Path,
    *,
    media_mode: str = "none",
    generated_at: str | None = None,
) -> dict:
    validate_registry(registry)
    registry_by_id = {record["family_id"]: record for record in registry["records"]}
    selected_ids = sample.get("selected_family_ids", [])
    if selected_ids != [r["family_id"] for r in sample.get("selected_records", [])]:
        raise ConstructValidityError("sample selected IDs and records disagree")
    if any(family_id not in registry_by_id for family_id in selected_ids):
        raise ConstructValidityError("sample references a family absent from registry")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ConstructValidityError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    forms_dir = output_dir / "reviewer_packets"
    forms_dir.mkdir()
    artifacts: list[tuple[Path, bool]] = []
    packet_id = f"cv-packet-{sample['sample_id']}"
    packet_generated_at = generated_at or now_utc()
    selected_records = [registry_by_id[family_id] for family_id in selected_ids]

    for family_id in selected_ids:
        record = registry_by_id[family_id]
        family_dir = forms_dir / family_id
        family_dir.mkdir()
        for role in ROLES:
            form = blank_annotation(packet_id=packet_id, record=record, role=role)
            validate_annotation(form)
            role_dir = family_dir / role
            role_dir.mkdir()
            path = role_dir / "form.json"
            write_json(path, form)
            role_readme = role_dir / "README.md"
            role_readme.write_text(
                "# Offline review assignment\n\n"
                f"Family: `{family_id}`\n\nRole: `{role}`\n\n"
                "Open only this role directory plus the source media. Do not "
                "inspect coordinator files or another reviewer's form. "
                "Machine labels are provisional and this blank assignment "
                "does not imply human validation.\n",
                encoding="utf-8",
            )
            artifacts.extend([(path, True), (role_readme, False)])
        adjudication = blank_adjudication(packet_id=packet_id, record=record)
        validate_adjudication(adjudication)
        role_dir = family_dir / "adjudicator"
        role_dir.mkdir()
        path = role_dir / "form.json"
        write_json(path, adjudication)
        role_readme = role_dir / "README.md"
        role_readme.write_text(
            "# Offline adjudication assignment\n\n"
            "Do not begin until the coordinator has collected all four "
            "independent completed role forms. You must be a fifth person and "
            "must document every critical conflict resolution.\n",
            encoding="utf-8",
        )
        artifacts.extend([(path, True), (role_readme, False)])
        saturation_audit = blank_saturation_audit(
            packet_id=packet_id, record=record
        )
        validate_saturation_audit(saturation_audit)
        role_dir = family_dir / "blind_post_adjudication_saturation_auditor"
        role_dir.mkdir()
        path = role_dir / "form.json"
        write_json(path, saturation_audit)
        role_readme = role_dir / "README.md"
        role_readme.write_text(
            "# Blind post-adjudication saturation audit\n\n"
            "Begin only after the coordinator confirms adjudication is frozen. "
            "You must be a sixth person. Open only this directory and the full "
            "source. Do not inspect coordinator files, accepted or preferred "
            "SESs, machine ranks, validator forms, or adjudication decisions. "
            "Before distribution, the coordinator must record the SHA-256 of "
            "the frozen adjudicator form in `frozen_adjudication_sha256`. "
            "Log chronological full-source coverage and every newly discovered "
            "plausible sufficient route.\n",
            encoding="utf-8",
        )
        artifacts.extend([(path, True), (role_readme, False)])

    copied_media = []
    if media_mode == "copy":
        media_dir = output_dir / "media"
        media_dir.mkdir()
        copied_sources: set[str] = set()
        for family_id in selected_ids:
            source = Path(registry_by_id[family_id].get("source_reference") or "")
            if not source.is_absolute():
                source = Path.cwd() / source
            if not source.is_file():
                raise ConstructValidityError(f"cannot copy missing source: {source}")
            source_key = str(source.resolve())
            if source_key in copied_sources:
                continue
            destination = media_dir / source.name
            if destination.exists():
                raise ConstructValidityError(
                    f"media basename collision for {destination.name}"
                )
            shutil.copy2(source, destination)
            copied_sources.add(source_key)
            copied_media.append(destination)
    elif media_mode != "none":
        raise ConstructValidityError(f"unsupported media_mode: {media_mode}")

    (output_dir / "README.md").write_text(README, encoding="utf-8")
    shutil.copy2(ANNOTATION_SCHEMA, output_dir / ANNOTATION_SCHEMA.name)
    shutil.copy2(ADJUDICATION_SCHEMA, output_dir / ADJUDICATION_SCHEMA.name)
    shutil.copy2(
        SATURATION_AUDIT_SCHEMA, output_dir / SATURATION_AUDIT_SCHEMA.name
    )
    shutil.copy2(
        REVIEWER_ASSIGNMENT_SCHEMA, output_dir / REVIEWER_ASSIGNMENT_SCHEMA.name
    )
    shutil.copy2(
        SOURCE_EXPOSURE_LEDGER_SCHEMA,
        output_dir / SOURCE_EXPOSURE_LEDGER_SCHEMA.name,
    )
    assignment_registry = {
        **registry,
        "records": [registry_by_id[family_id] for family_id in selected_ids],
    }
    coordinator_dir = output_dir / "coordinator"
    coordinator_dir.mkdir()
    write_json(coordinator_dir / "assignment_registry.json", assignment_registry)
    write_json(coordinator_dir / "sample.json", sample)
    source_exposure_ledger = blank_source_exposure_ledger(
        packet_id=packet_id,
        records=selected_records,
        generated_at=packet_generated_at,
    )
    validate_source_exposure_ledger(source_exposure_ledger)
    source_exposure_path = coordinator_dir / "source_exposure_ledger.json"
    write_json(source_exposure_path, source_exposure_ledger, restricted=True)
    reviewer_assignment_ledger = blank_reviewer_assignment_ledger(
        packet_id=packet_id,
        records=selected_records,
        pre_distribution_exposure_snapshot_sha256=source_exposure_ledger[
            "pre_distribution_snapshot_sha256"
        ],
        generated_at=packet_generated_at,
    )
    validate_reviewer_assignment_ledger(reviewer_assignment_ledger)
    reviewer_assignment_path = coordinator_dir / "reviewer_assignments.json"
    write_json(
        reviewer_assignment_path, reviewer_assignment_ledger, restricted=True
    )
    artifacts.extend(
        [
            (output_dir / "README.md", False),
            (output_dir / ANNOTATION_SCHEMA.name, False),
            (output_dir / ADJUDICATION_SCHEMA.name, False),
            (output_dir / SATURATION_AUDIT_SCHEMA.name, False),
            (output_dir / REVIEWER_ASSIGNMENT_SCHEMA.name, False),
            (output_dir / SOURCE_EXPOSURE_LEDGER_SCHEMA.name, False),
            (coordinator_dir / "assignment_registry.json", False),
            (coordinator_dir / "sample.json", False),
            (source_exposure_path, True),
            (reviewer_assignment_path, True),
        ]
    )
    artifacts.extend((path, False) for path in copied_media)
    manifest = {
        "schema_version": "1.0.0",
        "packet_id": packet_id,
        "generated_at": packet_generated_at,
        "packet_status": "UNFILLED_DEFERRED_HUMAN_ASSIGNMENT",
        "human_review_completed": False,
        "human_gold": False,
        "required_distinct_people_per_family": 6,
        "pre_adjudication_roles": list(ROLES),
        "adjudication_role": "adjudicator",
        "post_adjudication_role": "blind_post_adjudication_saturation_auditor",
        "assignment_ledger_status": "DRAFT_NOT_DISTRIBUTABLE",
        "packet_distribution_authorized": False,
        "source_level_blindness_required": True,
        "family_count": len(selected_ids),
        "source_count": len(
            {registry_by_id[family_id]["source_id"] for family_id in selected_ids}
        ),
        "media_mode": media_mode,
        "artifacts": [
            {
                "path": str(path.relative_to(output_dir)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "mutable_completed_form": mutable,
            }
            for path, mutable in sorted(artifacts, key=lambda item: str(item[0]))
        ],
    }
    write_json(output_dir / "packet_manifest.json", manifest)
    return manifest


def freeze_packet_assignments(
    packet_dir: Path, *, frozen_at: str
) -> dict:
    """Validate and freeze populated reviewer assignments before distribution."""
    assignment_path = packet_dir / "coordinator/reviewer_assignments.json"
    exposure_path = packet_dir / "coordinator/source_exposure_ledger.json"
    assignment_ledger = load_json(assignment_path)
    exposure_ledger = load_json(exposure_path)
    frozen = freeze_reviewer_assignment_ledger(
        assignment_ledger, frozen_at=frozen_at
    )
    conflicts = source_level_assignment_conflicts(frozen, exposure_ledger)
    rendered = {
        family_id: sorted(reason_codes)
        for family_id, reason_codes in conflicts.items()
        if reason_codes
    }
    if rendered:
        raise ConstructValidityError(
            "source-level reviewer assignment conflict: "
            + json.dumps(rendered, sort_keys=True)
        )
    write_json(assignment_path, frozen, restricted=True)
    manifest_path = packet_dir / "packet_manifest.json"
    manifest = load_json(manifest_path)
    if manifest.get("packet_id") != frozen["packet_id"]:
        raise ConstructValidityError("packet manifest and assignment packet_id differ")
    manifest["assignment_ledger_status"] = frozen["assignment_status"]
    manifest["packet_distribution_authorized"] = True
    manifest["assignment_freeze_sha256"] = frozen["assignment_freeze_sha256"]
    write_json(manifest_path, manifest)
    return frozen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--sample", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--media-mode", choices=("none", "copy"), default="none")
    parser.add_argument(
        "--generated-at",
        help="optional fixed packet timestamp for deterministic fixture generation",
    )
    parser.add_argument(
        "--freeze-existing-packet",
        action="store_true",
        help="freeze populated coordinator reviewer assignments instead of building",
    )
    parser.add_argument("--frozen-at")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.freeze_existing_packet:
            if not args.frozen_at:
                raise ConstructValidityError(
                    "--frozen-at is required with --freeze-existing-packet"
                )
            frozen = freeze_packet_assignments(
                args.output_dir, frozen_at=args.frozen_at
            )
            print(
                f"FROZEN {args.output_dir}: "
                f"{len(frozen['assignments'])} role assignments"
            )
            return 0
        if args.registry is None or args.sample is None:
            raise ConstructValidityError(
                "--registry and --sample are required when building a packet"
            )
        manifest = build_packet(
            load_json(args.registry),
            load_json(args.sample),
            args.output_dir,
            media_mode=args.media_mode,
            generated_at=args.generated_at,
        )
    except ConstructValidityError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(
        f"WROTE {args.output_dir}: {manifest['family_count']} families, "
        "UNFILLED_DEFERRED_HUMAN_ASSIGNMENT"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
