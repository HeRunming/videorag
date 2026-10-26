#!/usr/bin/env python3
"""Finalize Task187 after the frozen curl schedule yields no media bytes.

This is deliberately local-only. It validates the already-retained Task187
frozen decision and curl attempt log, then emits a complete REPAIR record
without inventing media hashes, technical-audit results, or Task153 samples.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import av
import cv2


ROOT = Path(__file__).resolve().parents[1]
TASK_ID = 187
TASK_DATE = "2026-10-09"
TOKEN = "CAPTAINCOOK4D_WAVE0_ACQUISITION_REPAIR"
PROXY = "https://proxy.example.invalid:3128"
CONNECT_TIMEOUT_SECONDS = 120
TRANSFER_TIMEOUT_SECONDS = 14400

BASE = ROOT / "data/restricted/captaincook4d_wave0_sources_v2"
LOGS = BASE / "logs"
MANIFESTS = BASE / "manifests"
PRESCREEN = BASE / "prescreen"
FROZEN = MANIFESTS / "task187_frozen_repair_decision.json"
TRANSFER = LOGS / "task187_curl_acquisition_log.json"
FAILURE = LOGS / "task187_failure.json"
HASH_LOG = LOGS / "task187_final_hashes.json"
AUDIT_LOG = LOGS / "task187_technical_audit.json"
ROOT_MANIFEST = MANIFESTS / "captaincook4d_wave0_acquisition_manifest.json"
INVENTORY = PRESCREEN / "captaincook4d_wave0_semantic_source_prescreen_inventory.json"
PLAN = PRESCREEN / "captaincook4d_wave0_semantic_source_prescreen_plan.json"
REVIEW = ROOT / "docs/review/captaincook4d_wave0_exact_acquisition_v2.md"
RESULT = ROOT / "orchestration/results/187_captaincook4d_wave0_acquisition_v2.txt"
TASK180_LIVE_OBJECT = (
    ROOT
    / "data/source_recon/captaincook4d_access_v3/derived"
    / "manual_success_observation_v3.json"
)

EXPECTED_ORDER = [
    "16_20",
    "15_29",
    "26_22",
    "25_1",
    "25_109",
    "2_13",
    "16_23",
    "23_19",
]


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
        fsync_directory(path.parent)
    except BaseException:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise


def write_json(path: Path, value: Any) -> None:
    atomic_write(path, canonical_json_bytes(value), 0o600)


def write_text(path: Path, value: str) -> None:
    atomic_write(path, value.encode("utf-8"), 0o644)


def validate_evidence(
    frozen: dict[str, Any], transfer: dict[str, Any]
) -> list[dict[str, Any]]:
    if frozen.get("task_id") != TASK_ID or not frozen.get("frozen_before_network"):
        raise RuntimeError("INVALID_OR_UNFROZEN_REPAIR_DECISION")
    repair = frozen.get("repair_decision", {})
    if repair.get("recording_16_20_mandatory") is not False:
        raise RuntimeError("REPAIR_DECISION_DID_NOT_REMOVE_16_20_REQUIREMENT")
    frozen_ids = [
        row["recording_id"]
        for row in frozen["frozen_candidate_revalidation"]["candidates"]
    ]
    if frozen_ids != EXPECTED_ORDER:
        raise RuntimeError("FROZEN_CANDIDATE_ORDER_MISMATCH")
    if transfer.get("task_id") != TASK_ID:
        raise RuntimeError("TRANSFER_TASK_ID_MISMATCH")
    if transfer.get("required_prefix") != f"curl --proxy {PROXY} -L":
        raise RuntimeError("CURL_PREFIX_NOT_VERIFIED")
    if transfer.get("connect_timeout_seconds") != CONNECT_TIMEOUT_SECONDS:
        raise RuntimeError("CONNECT_TIMEOUT_MISMATCH")
    if transfer.get("transfer_timeout_seconds") != TRANSFER_TIMEOUT_SECONDS:
        raise RuntimeError("TRANSFER_TIMEOUT_MISMATCH")
    if transfer.get("cookie_engine_overrides") is not False:
        raise RuntimeError("NONDEFAULT_COOKIE_OVERRIDE_DETECTED")
    if transfer.get("guessed_url") is not False:
        raise RuntimeError("GUESSED_URL_FLAGGED")
    candidates = transfer.get("candidates", [])
    if [row["recording_id"] for row in candidates] != EXPECTED_ORDER:
        raise RuntimeError("ATTEMPTED_ORDER_MISMATCH")
    for candidate in candidates:
        attempts = candidate.get("attempts", [])
        if (
            candidate.get("status")
            != "SKIPPED_AFTER_EXACTLY_THREE_DOCUMENTED_FAILURES"
            or len(attempts) != 3
        ):
            raise RuntimeError(
                f"INVALID_SKIP_RECORD:{candidate.get('recording_id')}"
            )
        if [row.get("attempt") for row in attempts] != [1, 2, 3]:
            raise RuntimeError(
                f"ATTEMPT_NUMBER_MISMATCH:{candidate['recording_id']}"
            )
        for attempt in attempts:
            if (
                attempt.get("outcome") != "FAILED"
                or attempt.get("curl_exit_code") != 28
                or attempt.get("effective_final_host")
                != "utdallas.app.box.com"
                or attempt.get("redirect_count") != 2
                or attempt.get("part_bytes") != 0
                or attempt.get("reported_download_bytes") != 0
            ):
                raise RuntimeError(
                    f"UNEXPECTED_ATTEMPT_RESULT:{candidate['recording_id']}"
                )
    if (
        transfer.get("source_count") != 0
        or transfer.get("selected_recording_ids") != []
        or transfer.get("aggregate_final_bytes") != 0
        or transfer.get("failed_candidates") != 8
        or transfer.get("failed_attempts") != 24
    ):
        raise RuntimeError("TRANSFER_SUMMARY_MISMATCH")
    if list(BASE.glob("*.mp4")) or list(BASE.glob("*.part")):
        raise RuntimeError("UNEXPECTED_AUTHORITATIVE_MEDIA_OR_PART")
    concurrent_part = BASE / "media/16_20_360p.mp4.part"
    if concurrent_part.exists():
        raise RuntimeError("CONCURRENT_PART_STILL_PRESENT")
    return candidates


def enforce_permissions() -> None:
    for directory in [BASE, *[path for path in BASE.rglob("*") if path.is_dir()]]:
        directory.chmod(0o700)
    for path in BASE.rglob("*"):
        if path.is_file():
            path.chmod(0o600)


def main() -> int:
    os.umask(0o077)
    for directory in (BASE, LOGS, MANIFESTS, PRESCREEN):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    frozen = load_json(FROZEN)
    transfer = load_json(TRANSFER)
    candidates = validate_evidence(frozen, transfer)

    hash_record = {
        "schema_version": "av-trace.captaincook4d-wave0-hashes/2.0",
        "task_id": TASK_ID,
        "created_at": utc_now(),
        "status": "BLOCKED_NO_ACQUIRED_MEDIA",
        "source_count": 0,
        "aggregate_bytes": 0,
        "sources": [],
    }
    write_json(HASH_LOG, hash_record)

    audit_record = {
        "schema_version": "av-trace.captaincook4d-wave0-technical-audit/2.0",
        "task_id": TASK_ID,
        "created_at": utc_now(),
        "status": "BLOCKED_NO_ACQUIRED_MEDIA",
        "pyav_version": av.__version__,
        "opencv_version": cv2.__version__,
        "duration_tolerance_seconds": 1.0,
        "sync_tolerance_seconds": 0.25,
        "source_count": 0,
        "all_sources_passed": False,
        "checks_not_performed": [
            "file hash verification",
            "container duration comparison to official metadata",
            "video/audio codec and time-base inspection",
            "beginning/middle/end decode",
            "A/V timestamp synchronization",
            "full PyAV decode through EOF",
            "full OpenCV traversal through EOF",
            "no-truncation verification",
        ],
        "reason": (
            "No candidate returned media bytes after the frozen "
            "three-attempt schedule."
        ),
        "sources": [],
    }
    write_json(AUDIT_LOG, audit_record)

    frozen_candidates = frozen["frozen_candidate_revalidation"]["candidates"]
    inventory = {
        "schema_version": "av-trace.task153-source-inventory/repair-1.0",
        "record_type": "semantic_av_source_prescreen_inventory_repair",
        "task_id": TASK_ID,
        "created_at": utc_now(),
        "status": "BLOCKED_NO_ACQUIRED_MEDIA",
        "inventory_id": "captaincook4d-wave0-task187-task153-inventory-v2",
        "candidate_sources": [
            {
                "prospective_order": row["prospective_order"],
                "source_id": row["recording_id"],
                "source_group_id": row["source_group_id"],
                "person_id": row["person_id"],
                "environment_id": row["environment_id"],
                "official_duration_seconds": row[
                    "official_metadata_duration_seconds"
                ],
                "content_sha256": None,
                "media_acquired": False,
            }
            for row in frozen_candidates
        ],
        "human_review_performed": False,
        "semantic_metadata_included": False,
    }
    write_json(INVENTORY, inventory)

    plan = {
        "schema_version": "av-trace.task153-prescreen-plan/repair-1.0",
        "record_type": "semantic_av_source_prescreen_plan_repair",
        "task_id": TASK_ID,
        "created_at": utc_now(),
        "status": "BLOCKED_NO_ACQUIRED_MEDIA",
        "plan_id": "captaincook4d-wave0-task187-task153-plan-v2",
        "inventory_id": inventory["inventory_id"],
        "inventory_sha256": f"sha256:{sha256_file(INVENTORY)}",
        "activation_condition": (
            "Exactly three acquired sources with distinct person_id and "
            "environment_id, exact content hashes, and passed technical audits."
        ),
        "algorithm": "source-uniform-temporal-bin-sha256-jitter-v1",
        "seed": "AVTRACE-CAPTAINCOOK4D-WAVE0-TASK187-TASK153-V2",
        "intended_interval_duration_seconds": 12.0,
        "intended_samples_per_acquired_source": 3,
        "samples": [],
        "extract_media": False,
        "semantic_labels_present": False,
        "human_review_performed": False,
        "annotations_produced": False,
        "h_tiers_assigned": False,
        "blocking_reason": (
            "A hash-bound executable Task153 sample plan cannot be generated "
            "without acquired source bytes."
        ),
    }
    write_json(PLAN, plan)

    attempt_rows = [
        attempt for candidate in candidates for attempt in candidate["attempts"]
    ]
    prior_live = load_json(TASK180_LIVE_OBJECT)
    root_manifest = {
        "schema_version": "2.0",
        "record_type": "captaincook4d_wave0_acquisition_manifest",
        "task_id": TASK_ID,
        "generated_at_utc": utc_now(),
        "decision": TOKEN,
        "repair_decision_frozen_before_network": True,
        "frozen_repair_decision_path": FROZEN.relative_to(ROOT).as_posix(),
        "frozen_repair_decision_sha256": sha256_file(FROZEN),
        "source_count": 0,
        "selected_recording_ids": [],
        "recording_16_20_mandatory": False,
        "attempted_candidate_count": 8,
        "documented_failed_attempt_count": 24,
        "route_failure_summary": {
            "all_eight_primaries_exhausted": True,
            "exactly_three_attempts_per_candidate": True,
            "all_attempts_stalled_at_utdallas_app_box_com": True,
            "all_attempts_curl_exit_28": True,
            "all_attempts_zero_media_bytes": True,
            "aggregate_media_bytes_acquired": 0,
            "prior_task180_live_object_evidence": {
                "path": TASK180_LIVE_OBJECT.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(TASK180_LIVE_OBJECT),
                "recording_id": prior_live["recording_id"],
                "final_status": prior_live["final_object"]["status"],
                "final_host": prior_live["final_object"]["host"],
                "content_length_bytes": prior_live["final_object"][
                    "content_length_bytes"
                ],
            },
        },
        "input_evidence": frozen["input_integrity"],
        "rights_and_use": frozen["rights_evidence"],
        "curl_acquisition": {
            "log_path": TRANSFER.relative_to(ROOT).as_posix(),
            "log_sha256": sha256_file(TRANSFER),
            "required_prefix": f"curl --proxy {PROXY} -L",
            "connect_timeout_seconds": CONNECT_TIMEOUT_SECONDS,
            "transfer_timeout_seconds": TRANSFER_TIMEOUT_SECONDS,
            "default_redirect_cookie_handling": True,
            "guessed_url": False,
            "failed_candidates": 8,
            "failed_attempts": 24,
            "incomplete_transfers": 0,
        },
        "technical_audit": {
            "path": AUDIT_LOG.relative_to(ROOT).as_posix(),
            "status": "BLOCKED_NO_ACQUIRED_MEDIA",
            "pyav_version": av.__version__,
            "opencv_version": cv2.__version__,
        },
        "task153_prescreen": {
            "inventory_path": INVENTORY.relative_to(ROOT).as_posix(),
            "inventory_sha256": f"sha256:{sha256_file(INVENTORY)}",
            "plan_path": PLAN.relative_to(ROOT).as_posix(),
            "plan_sha256": f"sha256:{sha256_file(PLAN)}",
            "status": "BLOCKED_NO_ACQUIRED_MEDIA",
            "human_review_performed": False,
        },
        "authoritative_media_files": [],
        "readiness_checks": {
            "exact_three_sources": False,
            "three_distinct_source_groups": False,
            "three_distinct_people": False,
            "three_distinct_environments": False,
            "full_technical_audits_passed": False,
            "no_annotations": True,
            "no_h_tiers": True,
            "no_human_review": True,
            "public_release_not_authorized": True,
        },
        "repair_required": (
            "The exact official shared links consistently reached "
            "utdallas.app.box.com, but that redirect hop timed out through "
            "the approved proxy before returning a BoxCloud object capability. "
            "The approximately 120-second failures are consistent with the "
            "configured connect timeout or a proxy-side limit at that hop."
        ),
        "no_go_not_asserted": (
            "Task180 previously reached a live exact MP4 object, so this "
            "uniform failure is a route defect rather than proof that the "
            "official source objects no longer exist."
        ),
        "concurrency_boundary": frozen["concurrency_boundary"],
    }
    if len(attempt_rows) != 24:
        raise RuntimeError("ATTEMPT_COUNT_CHANGED_DURING_FINALIZATION")
    write_json(ROOT_MANIFEST, root_manifest)

    failure = {
        "schema_version": "av-trace.captaincook4d-wave0-failure/2.0",
        "task_id": TASK_ID,
        "created_at": utc_now(),
        "decision": TOKEN,
        "error": "FEWER_THAN_THREE_SUCCESSFUL_DISTINCT_FROZEN_PRIMARIES",
        "error_type": "AcquisitionError",
        "failed_candidate_count": 8,
        "failed_attempt_count": 24,
        "public_release_or_redistribution": "NOT_AUTHORIZED",
    }
    write_json(FAILURE, failure)
    enforce_permissions()

    table_rows = []
    for candidate in candidates:
        attempt_times = ", ".join(
            f"{attempt['elapsed_seconds']:.3f}s"
            for attempt in candidate["attempts"]
        )
        table_rows.append(
            f"| `{candidate['recording_id']}` | {candidate['person_id']} | "
            f"{candidate['environment_id']} | 3 | {attempt_times} | "
            "`utdallas.app.box.com` | 0 |"
        )

    review = f"""# CaptainCook4D Wave-0 exact acquisition v2

**Task:** 187  
**Date:** {TASK_DATE}  
**Decision:** `{TOKEN}`

## Frozen repair decision

Before authoritative Task187 network acquisition, the preliminary version of
this report and
`{FROZEN.relative_to(ROOT).as_posix()}` froze the following decision:

- select any three successful source groups with different `person_id` and
  different `environment_id` from the prospectively ordered eight Task174
  primaries;
- `16_20` is not mandatory because its repeated Box app timeout is a route
  defect rather than a scientific criterion;
- use the exact official GoPro 360p URL in frozen rank order;
- skip only after exactly three documented failures; and
- stop after three successful distinct groups.

## Curl execution

Every authoritative attempt used explicit
`curl --proxy {PROXY} -L`, connect/transfer timeouts of
`{CONNECT_TIMEOUT_SECONDS}/{TRANSFER_TIMEOUT_SECONDS}` seconds, curl's
default redirect/cookie handling, no guessed URL, and a same-directory
`.part` target. The planned successful path required size/container checks,
mode `0600`, `fsync`, and atomic rename.

All eight primaries exhausted exactly three attempts. All 24 attempts followed
two redirects to `utdallas.app.box.com`, then failed with curl exit 28 after
about 120 seconds without receiving media bytes. This is consistent with the
configured connect timeout or a proxy-side limit at the failing redirect hop;
the longer total transfer timeout never became relevant.

| Recording | Person | Environment | Attempts | Elapsed attempts | Last host | Media bytes |
| --- | ---: | ---: | ---: | --- | --- | ---: |
{chr(10).join(table_rows)}

The preexisting concurrent `logs/16_20.headers` artifact was preserved and
excluded from authoritative Task187 evidence. No concurrent process was
terminated and no other worker's artifact was reverted.

## Acquisition and audit result

- Successfully acquired sources: **0**
- Persisted authoritative media bytes: **0**
- Remaining authoritative root `.part` files: **0**
- Full PyAV/OpenCV hash, duration, audio, beginning/middle/end,
  synchronization, and EOF audit: **blocked because no media was acquired**
- Official-duration comparison: **not performed; no container duration exists**
- Annotation access: **none**
- Human review: **none**
- H tiers: **none**
- Public release or redistribution: **not authorized**

This is REPAIR, not NO_GO. Task180 previously reached a live exact MP4 object
for `16_20` at `public.boxcloud.com` with HTTP 200 and a 230,486,870-byte
content length. The uniform Task187 failure is therefore an approved-proxy to
Box-app route defect, not evidence that the official objects are scientifically
ineligible or permanently absent.

## Task153 prescreen plan

`{PLAN.relative_to(ROOT).as_posix()}` records a no-human,
hash-bound Task153 plan in `BLOCKED_NO_ACQUIRED_MEDIA` state. It freezes the
algorithm, seed, interval duration, per-source quota, candidate order, and
activation condition. It contains no fabricated sample intervals because no
acquired source content hash exists.

## Outputs

- `{ROOT_MANIFEST.relative_to(ROOT).as_posix()}`
- `{FROZEN.relative_to(ROOT).as_posix()}`
- `{TRANSFER.relative_to(ROOT).as_posix()}`
- `{HASH_LOG.relative_to(ROOT).as_posix()}`
- `{AUDIT_LOG.relative_to(ROOT).as_posix()}`
- `{INVENTORY.relative_to(ROOT).as_posix()}`
- `{PLAN.relative_to(ROOT).as_posix()}`
- `{FAILURE.relative_to(ROOT).as_posix()}`

`{TOKEN}`
"""
    write_text(REVIEW, review)

    result = f"""Task187 pragmatic CaptainCook4D Wave-0 curl acquisition repair
Date: {TASK_DATE}
Decision: {TOKEN}

FROZEN REPAIR
- Frozen before authoritative network acquisition in:
  {FROZEN.relative_to(ROOT).as_posix()}
- Goal: any 3 distinct person_id/environment_id groups from 8 ordered primaries.
- 16_20 not mandatory; repeated Box app timeout classified as a route defect.
- Skip only after 3 documented failures; stop after 3 successes.

CURL RESULT
- Exact frozen primary URLs attempted: 8/8.
- Attempts: 24/24 failed; exactly 3 per candidate.
- Every attempt used curl --proxy {PROXY} -L.
- Connect/transfer timeout settings: {CONNECT_TIMEOUT_SECONDS}/{TRANSFER_TIMEOUT_SECONDS} seconds.
- Every attempt reached utdallas.app.box.com after 2 redirects and timed out with 0 bytes.
- Successful distinct groups: 0/3.

AUDIT
- Acquired authoritative media bytes: 0.
- Hash/duration/audio/BME/sync/EOF audit: BLOCKED_NO_ACQUIRED_MEDIA.
- Official-duration comparison: not possible without container bytes.

TASK153
- No-human deferred inventory and plan generated.
- No fabricated hash-bound samples, annotations, or H tiers.

BOUNDARY
- Restricted internal work only.
- No public release or redistribution.
- REPAIR, not NO_GO: common approved-proxy/Box-app route defect.

OUTPUTS
- {REVIEW.relative_to(ROOT).as_posix()}
- {ROOT_MANIFEST.relative_to(ROOT).as_posix()}
- {FROZEN.relative_to(ROOT).as_posix()}
- {TRANSFER.relative_to(ROOT).as_posix()}
- {HASH_LOG.relative_to(ROOT).as_posix()}
- {AUDIT_LOG.relative_to(ROOT).as_posix()}
- {INVENTORY.relative_to(ROOT).as_posix()}
- {PLAN.relative_to(ROOT).as_posix()}

{TOKEN}
"""
    write_text(RESULT, result)
    print(TOKEN)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
