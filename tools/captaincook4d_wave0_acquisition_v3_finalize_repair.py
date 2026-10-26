#!/usr/bin/env python3
"""Local-only immediate REPAIR finalizer for Task188.

This finalizer performs no network request. It records the interrupted
outside-sandbox execution boundary, preserves the pre-network frozen decision,
emits blocked technical/Task153 records without fabricating media evidence,
and leaves ``captaincook4d_wave0_acquisition_v3.py`` as the deterministic
range/resume downloader for a later authorized run.
"""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from typing import Any

import av
import cv2

import captaincook4d_wave0_acquisition_v3 as acq


TOKEN = acq.TOKEN_REPAIR
BLOCKER_CODE = (
    "OUTSIDE_SANDBOX_NETWORK_EXECUTION_NOT_COMPLETED_USER_INTERRUPTED"
)
BLOCKER = (
    "The escalated outside-sandbox Task188 execution was interrupted by the "
    "user before it produced a Task188 curl route log, media file, or "
    "canonical .part file. Network acquisition and media validation therefore "
    "cannot be claimed."
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def restricted_state() -> dict[str, Any]:
    media = sorted(acq.BASE.glob("*.mp4"))
    parts = sorted(acq.BASE.glob("*.mp4.part"))
    range_segments = sorted(acq.BASE.glob(".*.range.part"))
    return {
        "route_log_exists": acq.ROUTE_LOG.exists(),
        "media_files": [
            {
                "path": path.relative_to(acq.ROOT).as_posix(),
                "bytes": path.stat().st_size,
            }
            for path in media
        ],
        "canonical_part_files": [
            {
                "path": path.relative_to(acq.ROOT).as_posix(),
                "bytes": path.stat().st_size,
            }
            for path in parts
        ],
        "range_segment_files": [
            {
                "path": path.relative_to(acq.ROOT).as_posix(),
                "bytes": path.stat().st_size,
            }
            for path in range_segments
        ],
    }


def main() -> int:
    acq.secure_directories()
    if not acq.FROZEN_MANIFEST.is_file():
        raise RuntimeError("TASK188_FROZEN_SELECTION_MISSING")
    frozen = acq.load_json(acq.FROZEN_MANIFEST)
    if (
        frozen.get("task_id") != acq.TASK_ID
        or not frozen.get("frozen_before_task188_network")
        or frozen.get("initial_recording_ids") != list(acq.FROZEN_INITIAL_IDS)
    ):
        raise RuntimeError("TASK188_FROZEN_SELECTION_INVALID")

    state = restricted_state()
    if (
        state["route_log_exists"]
        or state["media_files"]
        or state["canonical_part_files"]
        or state["range_segment_files"]
    ):
        raise RuntimeError(
            "REPAIR_FINALIZER_EXPECTED_NO_RETAINED_NETWORK_OR_MEDIA_ARTIFACTS"
        )

    hash_record = {
        "schema_version": "av-trace.captaincook4d-wave0-hashes/3.0",
        "task_id": acq.TASK_ID,
        "created_at": acq.utc_now(),
        "status": "BLOCKED_NO_ACQUIRED_MEDIA",
        "source_count": 0,
        "aggregate_bytes": 0,
        "sources": [],
        "blocking_code": BLOCKER_CODE,
    }
    acq.write_restricted_json(acq.HASH_LOG, hash_record)

    audit_record = {
        "schema_version": (
            "av-trace.captaincook4d-wave0-technical-audit/3.0"
        ),
        "task_id": acq.TASK_ID,
        "created_at": acq.utc_now(),
        "status": "BLOCKED_NO_ACQUIRED_MEDIA",
        "pyav_version": av.__version__,
        "opencv_version": cv2.__version__,
        "duration_tolerance_seconds": acq.DURATION_TOLERANCE_SECONDS,
        "sync_tolerance_seconds": acq.SYNC_TOLERANCE_SECONDS,
        "source_count": 0,
        "all_sources_passed": False,
        "checks_not_performed": [
            "exact Content-Range total and final byte-size verification",
            "SHA-256 verification",
            "PyAV container and official-duration comparison",
            "video/audio stream codec and time-base inspection",
            "beginning/middle/end decode and A/V synchronization",
            "full PyAV decode through EOF",
            "full OpenCV traversal through EOF",
            "no-truncation verification",
        ],
        "blocking_code": BLOCKER_CODE,
        "blocking_reason": BLOCKER,
        "sources": [],
    }
    acq.write_restricted_json(acq.AUDIT_LOG, audit_record)

    initial_rows = {
        row["recording_id"]: row for row in frozen["candidate_rows"]
    }
    prospective = [initial_rows[item] for item in acq.FROZEN_INITIAL_IDS]
    inventory = {
        "schema_version": (
            "av-trace.task153-source-inventory/repair-3.0"
        ),
        "record_type": "semantic_av_source_prescreen_inventory_repair",
        "task_id": acq.TASK_ID,
        "created_at": acq.utc_now(),
        "status": "BLOCKED_NO_ACQUIRED_MEDIA",
        "inventory_id": (
            "captaincook4d-wave0-task188-task153-inventory-v3"
        ),
        "frozen_candidate_sources": [
            {
                "frozen_order": index,
                "source_id": row["recording_id"],
                "source_group_id": row["source_group_id"],
                "person_id": row["person_id"],
                "environment_id": row["environment_id"],
                "official_duration_seconds": row[
                    "official_duration_seconds"
                ],
                "source_content_sha256": None,
                "media_acquired": False,
            }
            for index, row in enumerate(prospective, 1)
        ],
        "conditional_replacement_order": list(acq.FALLBACK_PRIMARY_IDS),
        "human_review_performed": False,
        "semantic_metadata_included": False,
        "annotations_included": False,
        "blocking_code": BLOCKER_CODE,
    }
    acq.write_restricted_json(acq.INVENTORY, inventory)

    plan = {
        "schema_version": "av-trace.task153-prescreen-plan/repair-3.0",
        "record_type": "semantic_av_source_prescreen_plan_repair",
        "task_id": acq.TASK_ID,
        "created_at": acq.utc_now(),
        "status": "BLOCKED_NO_ACQUIRED_MEDIA",
        "plan_id": "captaincook4d-wave0-task188-task153-plan-v3",
        "inventory_id": inventory["inventory_id"],
        "inventory_sha256": f"sha256:{sha256_file(acq.INVENTORY)}",
        "activation_condition": (
            "Three acquired and technically passed GoPro 360p sources under "
            "the Task188 frozen/replacement rule, each bound to an exact "
            "content SHA-256."
        ),
        "algorithm": "source-uniform-temporal-bin-sha256-jitter-v1",
        "seed": "AVTRACE-CAPTAINCOOK4D-WAVE0-TASK188-TASK153-V3",
        "intended_interval_duration_seconds": 12.0,
        "intended_samples_per_acquired_source": 3,
        "samples": [],
        "extract_media": False,
        "semantic_labels_present": False,
        "human_review_performed": False,
        "annotations_produced": False,
        "h_tiers_assigned": False,
        "blocking_code": BLOCKER_CODE,
        "blocking_reason": (
            "Hash-bound sample intervals cannot be generated before exact "
            "source bytes are acquired and audited."
        ),
    }
    acq.write_restricted_json(acq.PLAN, plan)

    downloader = (
        acq.ROOT / "tools/captaincook4d_wave0_acquisition_v3.py"
    )
    failure = {
        "schema_version": "av-trace.captaincook4d-wave0-failure/3.0",
        "task_id": acq.TASK_ID,
        "created_at": acq.utc_now(),
        "decision": TOKEN,
        "error_type": "InterruptedOutsideSandboxExecution",
        "blocking_code": BLOCKER_CODE,
        "blocking_reason": BLOCKER,
        "retained_state": state,
        "authoritative_media_bytes": 0,
        "frozen_selection_path": (
            acq.FROZEN_MANIFEST.relative_to(acq.ROOT).as_posix()
        ),
        "frozen_selection_sha256": sha256_file(acq.FROZEN_MANIFEST),
        "deterministic_downloader": {
            "path": downloader.relative_to(acq.ROOT).as_posix(),
            "sha256": sha256_file(downloader),
            "resume_command": (
                "python tools/captaincook4d_wave0_acquisition_v3.py --execute"
            ),
            "network_requirement": (
                "Outside-sandbox access to "
                "https://proxy.example.invalid:3128"
            ),
        },
        "annotations_accessed_or_produced": False,
        "human_review_performed": False,
        "h_tiers_assigned": False,
        "public_release_or_redistribution": "NOT_AUTHORIZED",
    }
    acq.write_restricted_json(acq.FAILURE_LOG, failure)

    manifest = {
        "schema_version": "3.0",
        "record_type": "captaincook4d_wave0_acquisition_manifest",
        "task_id": acq.TASK_ID,
        "generated_at_utc": acq.utc_now(),
        "decision": TOKEN,
        "status": "BLOCKED_NO_ACQUIRED_MEDIA",
        "source_count": 0,
        "authoritative_media_bytes": 0,
        "initial_frozen_recording_ids": list(acq.FROZEN_INITIAL_IDS),
        "mandatory_recording_ids": ["16_20", "15_29"],
        "conditionally_replaceable_recording_id": "26_22",
        "prospective_fallback_primary_order": list(
            acq.FALLBACK_PRIMARY_IDS
        ),
        "provided_2026_10_08_range_evidence": frozen[
            "provided_2026_10_08_range_evidence"
        ],
        "current_task188_network_evidence": {
            "route_log_exists": False,
            "retained_network_response_records": 0,
            "retained_media_or_part_files": 0,
            "blocking_code": BLOCKER_CODE,
            "blocking_reason": BLOCKER,
        },
        "frozen_selection": {
            "path": acq.FROZEN_MANIFEST.relative_to(acq.ROOT).as_posix(),
            "sha256": sha256_file(acq.FROZEN_MANIFEST),
        },
        "deterministic_downloader": failure["deterministic_downloader"],
        "hashes": {
            "path": acq.HASH_LOG.relative_to(acq.ROOT).as_posix(),
            "sha256": sha256_file(acq.HASH_LOG),
            "status": "BLOCKED_NO_ACQUIRED_MEDIA",
        },
        "technical_audit": {
            "path": acq.AUDIT_LOG.relative_to(acq.ROOT).as_posix(),
            "sha256": sha256_file(acq.AUDIT_LOG),
            "status": "BLOCKED_NO_ACQUIRED_MEDIA",
        },
        "task153_prescreen": {
            "inventory_path": acq.INVENTORY.relative_to(acq.ROOT).as_posix(),
            "inventory_sha256": f"sha256:{sha256_file(acq.INVENTORY)}",
            "plan_path": acq.PLAN.relative_to(acq.ROOT).as_posix(),
            "plan_sha256": f"sha256:{sha256_file(acq.PLAN)}",
            "status": "BLOCKED_NO_ACQUIRED_MEDIA",
            "human_review_performed": False,
        },
        "failure": {
            "path": acq.FAILURE_LOG.relative_to(acq.ROOT).as_posix(),
            "sha256": sha256_file(acq.FAILURE_LOG),
        },
        "readiness_checks": {
            "exact_three_sources": False,
            "exact_content_range_totals_verified_in_task188": False,
            "sha256_verified": False,
            "full_technical_audits_passed": False,
            "no_annotations": True,
            "no_h_tiers": True,
            "no_human_review": True,
            "public_release_not_authorized": True,
        },
        "repair_not_no_go_reason": (
            "The user-provided October 8, 2026 https://proxy.example.invalid:3128 evidence establishes "
            "HTTP 206 for the two mandatory official links, and a deterministic "
            "range/resume implementation is retained. The blocker is execution "
            "authorization/completion, not evidence of an absent or ineligible "
            "source."
        ),
    }
    acq.write_restricted_json(acq.ROOT_MANIFEST, manifest)

    acq.enforce_restricted_permissions()
    all_files_0600 = all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in acq.BASE.rglob("*")
        if path.is_file()
    )
    all_dirs_0700 = all(
        stat.S_IMODE(path.stat().st_mode) == 0o700
        for path in [
            acq.BASE,
            *[item for item in acq.BASE.rglob("*") if item.is_dir()],
        ]
    )
    if not all_files_0600 or not all_dirs_0700:
        raise RuntimeError("RESTRICTED_PERMISSION_FINALIZATION_FAILED")

    report = f"""# CaptainCook4D Wave-0 exact acquisition v3

**Task:** 188  
**Date:** {acq.TASK_DATE}  
**Decision:** `{TOKEN}`

## Immediate final status

Task188 is **REPAIR**, not READY. The escalated outside-sandbox execution was
interrupted by the user before it produced a Task188 curl route log, MP4, or
canonical `.part` file. Consequently, Task188 retained **0 authoritative media
bytes**, and no hash, duration, stream, decode, synchronization, EOF, or
no-truncation result can be asserted.

Exact blocker code: `{BLOCKER_CODE}`.

## Frozen scope retained

The pre-network freeze remains:

1. `16_20` — mandatory; provided October 8, 2026 HTTP 206 total:
   230,486,870 bytes.
2. `15_29` — mandatory; provided October 8, 2026 HTTP 206 total:
   181,454,428 bytes.
3. `26_22` — replace only if its official route fails, using later Task174
   primaries in order: `25_1`, `25_109`, `2_13`, `16_23`, `23_19`, while
   preserving distinct person and environment IDs.

## Deterministic repair path

The retained local downloader is
`tools/captaincook4d_wave0_acquisition_v3.py`
(SHA-256 `{sha256_file(downloader)}`). It uses the required
`curl --proxy {acq.PROXY} -L` route, bounded `bytes=0-0` probes, exact totals
from `Content-Range`, resumable `.part` acquisition, fsync, atomic rename,
0600/0700 permissions, URL/cookie redaction, SHA-256, full PyAV/OpenCV
duration/stream/B-M-E/sync/EOF/no-truncation validation, and Task153 generation.

Resume only with authorized outside-sandbox network access:

```text
python tools/captaincook4d_wave0_acquisition_v3.py --execute
```

## Task153 and boundary

A deterministic blocked inventory and plan were generated without fabricated
content hashes or intervals. Humans were not used. No annotations, H tiers,
public release, redistribution, or Ray jobs were touched.

## Outputs

- `{acq.ROOT_MANIFEST.relative_to(acq.ROOT).as_posix()}`
- `{acq.FROZEN_MANIFEST.relative_to(acq.ROOT).as_posix()}`
- `{acq.FAILURE_LOG.relative_to(acq.ROOT).as_posix()}`
- `{acq.HASH_LOG.relative_to(acq.ROOT).as_posix()}`
- `{acq.AUDIT_LOG.relative_to(acq.ROOT).as_posix()}`
- `{acq.INVENTORY.relative_to(acq.ROOT).as_posix()}`
- `{acq.PLAN.relative_to(acq.ROOT).as_posix()}`

`{TOKEN}`
"""
    acq.write_public_text(acq.REVIEW, report)

    result = f"""Task188 CaptainCook4D Wave-0 exact acquisition v3
Date: {acq.TASK_DATE}
Decision: {TOKEN}

BLOCKER
- Code: {BLOCKER_CODE}
- Outside-sandbox execution was interrupted before any Task188 route log,
  MP4, or canonical .part file was retained.
- Authoritative media bytes: 0.
- Full PyAV/OpenCV technical audit: BLOCKED_NO_ACQUIRED_MEDIA.

FROZEN SCOPE
- 16_20 and 15_29 remain mandatory.
- Only 26_22 may be replaced, using later Task174 primary order.
- Provided 2026-10-08 HTTP 206 totals retained: 230,486,870 and 181,454,428.

DETERMINISTIC REPAIR
- Downloader: tools/captaincook4d_wave0_acquisition_v3.py
- Resume: python tools/captaincook4d_wave0_acquisition_v3.py --execute
- Requires authorized outside-sandbox access to {acq.PROXY}.

BOUNDARY
- Task153 blocked inventory/plan generated; no humans.
- No annotations, H tiers, public release, redistribution, or Ray jobs.

{TOKEN}
"""
    acq.write_public_text(acq.RESULT, result)
    print(TOKEN)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
