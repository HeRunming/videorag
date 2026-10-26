#!/usr/bin/env python3
"""Finalize Task180 from retained local evidence only.

This program performs no network access.  It records the official downloader
semantics, the one completed route resolution emitted during Task180, the
subsequent interrupted probe attempts, and fail-closed MP4/audio conclusions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "data/source_recon/captaincook4d_access_v1"
V2 = ROOT / "data/source_recon/captaincook4d_access_v2"
V3 = ROOT / "data/source_recon/captaincook4d_access_v3"
DERIVED = V3 / "derived"
REGISTRY = ROOT / "data/rehearsal_plan/captaincook4d_access_registry_v3.json"
REPORT = ROOT / "docs/review/captaincook4d_route_repair_v3.md"
RESULT = ROOT / "orchestration/results/180_captaincook4d_route_repair_v3.txt"

TASK_ID = 180
DATE = "2026-10-08"
DECISION = "CAPTAINCOOK4D_ROUTE_REPAIR"
PROXY = "https://proxy.example.invalid:3128"
BYTE_CAP = 16 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def file_record(path: Path, role: str) -> dict[str, Any]:
    return {
        "path": rel(path),
        "role": role,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def load_probe(asset_id: str) -> dict[str, Any] | None:
    path = V3 / "probes" / asset_id / "probe.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    DERIVED.mkdir(parents=True, exist_ok=True)

    inventory_v2_path = (
        V2 / "derived/selected_media_route_inventory_v2.json"
    )
    inventory_v2 = json.loads(inventory_v2_path.read_text(encoding="utf-8"))
    assets_v2 = inventory_v2["media_assets"]
    if len(assets_v2) != 20:
        raise RuntimeError("Frozen inventory is not the expected 20 routes")

    official_files = {
        "download_gopro_data.py": {
            "path": V3 / "official_source/download_gopro_data.py",
            "git_blob_sha": "d4bb4086f61e4991c14da2387eddde6e73fd4648",
            "expected_bytes": 2821,
        },
        "util.py": {
            "path": V3 / "official_source/util.py",
            "git_blob_sha": "c481510d900e53c4704e81cb2d4b5141e91789f6",
            "expected_bytes": 15605,
        },
        "requirements.txt": {
            "path": V3 / "official_source/requirements.txt",
            "git_blob_sha": "2c8b74ebd07f400fcaf34fb5ebbd5139310e831b",
            "expected_bytes": 13,
        },
    }
    for name, item in official_files.items():
        path = item["path"]
        if path.stat().st_size != item["expected_bytes"]:
            raise RuntimeError(f"Unexpected official source size: {name}")

    semantics = {
        "schema_version": "av-trace.captaincook4d-downloader-semantics/3.0",
        "task_id": TASK_ID,
        "created_at": DATE,
        "official_downloader_tree_sha": "cf248fe2139fc6e37f9737141ec719948fbd1747",
        "source_files": {
            name: {
                "path": rel(item["path"]),
                "git_blob_sha": item["git_blob_sha"],
                "bytes": item["path"].stat().st_size,
                "sha256": sha256(item["path"]),
                "commit_pinned_blob_verified": True,
            }
            for name, item in official_files.items()
        },
        "requirements": ["requests", "tqdm"],
        "selection_and_dispatch": {
            "manifest": "metadata/download_links.json",
            "gopro_360p_key": "gopro_360p",
            "fallback_if_gopro_360p_missing": "hololens_sync_pv_video",
            "urls_passed_to": "util.download_data -> util.download_url",
        },
        "http_semantics": {
            "exact_call": "requests.get(url, stream=True)",
            "method": "GET",
            "stream": True,
            "explicit_session": False,
            "explicit_headers": False,
            "explicit_user_agent": False,
            "explicit_query_parameters": False,
            "explicit_cookies": False,
            "redirect_policy": (
                "requests GET default allow_redirects=True; response is the final "
                "response after automatic redirects"
            ),
            "redirect_cookie_behavior": (
                "requests automatically extracts and forwards eligible Set-Cookie "
                "values during the redirect chain of the call"
            ),
            "status_handling": "response.raise_for_status()",
            "retry_count": 5,
            "retry_delay_seconds": 5,
            "final_size_source": "final response Content-Length header",
            "head_request": False,
            "range_request": False,
            "resume_range_request": False,
            "body_iteration_bytes": 1048576,
            "partial_path": "<target>.part",
            "partial_open_mode": "wb",
            "publish_operation": "os.replace(<target>.part, <target>)",
            "important_correction": (
                "The code provides retry plus atomic .part publication, but it does "
                "not resume a partial body with Range and overwrites an existing "
                ".part file. The README's 'resumable' wording must not be read as "
                "byte-range resume semantics."
            ),
        },
        "task180_runtime_observation": {
            "requests_version": "2.32.5",
            "default_headers": {
                "User-Agent": "python-requests/2.32.5",
                "Accept-Encoding": "gzip, deflate",
                "Accept": "*/*",
                "Connection": "keep-alive",
            },
            "note": (
                "The repository does not pin a requests version, so the User-Agent "
                "is an environment observation rather than an upstream invariant."
            ),
        },
    }
    semantics_path = DERIVED / "official_downloader_semantics_v3.json"
    write_json(semantics_path, semantics)

    manual_success = {
        "schema_version": "av-trace.captaincook4d-route-observation/3.0",
        "task_id": TASK_ID,
        "created_at": DATE,
        "asset_id": "primary-1-16_20-gopro_360p",
        "recording_id": "16_20",
        "source_group_id": "cc4d_p01_e08",
        "person_id": 1,
        "environment_id": 8,
        "stream": "gopro_360p",
        "official_shared_link": (
            "https://utdallas.box.com/shared/static/"
            "btsy8iyqoztk0yt3006dqb4n5yfzj8rh.mp4"
        ),
        "evidence_basis": (
            "Reconstructed from the structured result emitted by the completed "
            "Task180 unified-exec probe. Its original local probe.json was later "
            "overwritten by the interrupted retry batch. Ephemeral URL and cookie "
            "values are intentionally not reproduced."
        ),
        "request": {
            "method": "GET",
            "stream": True,
            "proxy": PROXY,
            "headers": {
                "User-Agent": "python-requests/2.32.5",
                "Accept-Encoding": "gzip, deflate",
                "Accept": "*/*",
                "Connection": "keep-alive",
            },
            "explicit_query_parameters": False,
            "caller_supplied_cookies": False,
            "body_bytes_consumed": 0,
        },
        "redirect_chain": [
            {
                "status": 301,
                "from": (
                    "https://utdallas.box.com/shared/static/"
                    "btsy8iyqoztk0yt3006dqb4n5yfzj8rh.mp4"
                ),
                "to": (
                    "https://utdallas.box.com/public/static/"
                    "btsy8iyqoztk0yt3006dqb4n5yfzj8rh.mp4"
                ),
            },
            {
                "status": 301,
                "from": (
                    "https://utdallas.box.com/public/static/"
                    "btsy8iyqoztk0yt3006dqb4n5yfzj8rh.mp4"
                ),
                "to": (
                    "https://utdallas.app.box.com/public/static/"
                    "btsy8iyqoztk0yt3006dqb4n5yfzj8rh.mp4"
                ),
            },
            {
                "status": 302,
                "from": (
                    "https://utdallas.app.box.com/public/static/"
                    "btsy8iyqoztk0yt3006dqb4n5yfzj8rh.mp4"
                ),
                "to": (
                    "https://public.boxcloud.com/d/1/"
                    "[REDACTED_EPHEMERAL_OBJECT_CAPABILITY]/download"
                ),
                "set_cookie_names_observed": [
                    "z",
                    "box_visitor_id",
                    "bv",
                    "cn",
                    "site_preference",
                ],
            },
        ],
        "final_object": {
            "status": 200,
            "scheme": "https",
            "host": "public.boxcloud.com",
            "path_template": (
                "/d/1/[REDACTED_EPHEMERAL_OBJECT_CAPABILITY]/download"
            ),
            "full_ephemeral_path_retained": False,
            "query_present": False,
            "identity_strength": (
                "Host, path class, content-disposition filename, exact byte size, "
                "and response date retained; exact ephemeral capability redacted."
            ),
            "content_type": "video/mp4",
            "content_disposition_filename": "16_20_360p.mp4",
            "content_length_bytes": 230486870,
            "accept_ranges": "bytes",
            "etag": None,
            "last_modified": None,
            "response_date": "Thu, 08 Oct 2026 03:24:44 GMT",
            "set_cookie_names_observed": ["b"],
        },
        "range_behavior": {
            "accept_ranges_advertised": True,
            "bounded_range_get_completed": False,
            "status_206_observed": False,
            "content_range_observed": False,
            "conclusion": (
                "Byte ranges are advertised, but actual range behavior was not "
                "established before the network stop."
            ),
        },
        "retained_media_bytes": 0,
    }
    manual_success_path = DERIVED / "manual_success_observation_v3.json"
    write_json(manual_success_path, manual_success)

    attempted_ids = [
        "primary-1-16_20-gopro_360p",
        "primary-1-16_20-hololens_sync_pv_video",
        "primary-2-15_29-gopro_360p",
    ]
    failed_probe_summary = []
    for asset_id in attempted_ids:
        probe = load_probe(asset_id)
        if probe is None:
            continue
        failed_probe_summary.append(
            {
                "asset_id": asset_id,
                "recording_id": probe["recording_id"],
                "stream": probe["stream"],
                "attempt_count": len(probe["official_resolution_attempts"]),
                "outcomes": sorted(
                    {
                        row["error_type"]
                        for row in probe["official_resolution_attempts"]
                    }
                ),
                "last_reached_host_from_error": "utdallas.app.box.com",
                "successful_final_response": False,
                "retained_media_bytes": 0,
                "evidence": rel(
                    V3 / "probes" / asset_id / "probe.json"
                ),
            }
        )

    probe_summary = {
        "schema_version": "av-trace.captaincook4d-route-probe-summary/3.0",
        "task_id": TASK_ID,
        "created_at": DATE,
        "decision_token": DECISION,
        "network_stopped": True,
        "frozen_recording_count": 10,
        "frozen_route_count": 20,
        "unique_routes_attempted": 3,
        "unique_recordings_attempted": 2,
        "completed_final_object_resolutions": 1,
        "routes_with_exact_content_length": 1,
        "routes_advertising_accept_ranges": 1,
        "routes_with_completed_206_range_exchange": 0,
        "routes_with_etag": 0,
        "routes_with_last_modified": 0,
        "routes_with_mp4_atoms": 0,
        "representative_recordings_with_stream_parse": 0,
        "successful_observation": rel(manual_success_path),
        "subsequent_failed_retry_batches": failed_probe_summary,
        "important_interpretation": (
            "The same 16_20 GoPro route resolved once and subsequently timed out "
            "during five official-style attempts at utdallas.app.box.com. This "
            "establishes the redirect semantics and one live object, but not stable "
            "availability for the frozen route set."
        ),
    }
    probe_summary_path = DERIVED / "route_probe_summary_v3.json"
    write_json(probe_summary_path, probe_summary)

    assets_v3 = []
    for source in assets_v2:
        row = dict(source)
        asset_id = row["asset_id"]
        row.update(
            {
                "task180_probe_status": "NOT_ATTEMPTED_AFTER_NETWORK_STOP",
                "task180_official_get_attempts": 0,
                "task180_final_object_resolution_observed": False,
                "task180_final_object_identity": None,
                "task180_range_exchange_observed": False,
                "task180_mp4_atoms_retained": 0,
            }
        )
        probe = load_probe(asset_id)
        if probe is not None:
            row["task180_probe_status"] = "OFFICIAL_STYLE_GET_TIMEOUT"
            row["task180_official_get_attempts"] = len(
                probe["official_resolution_attempts"]
            )
            row["task180_probe_evidence"] = rel(
                V3 / "probes" / asset_id / "probe.json"
            )
        if asset_id == manual_success["asset_id"]:
            row.update(
                {
                    "task180_probe_status": (
                        "RESOLVED_ONCE_THEN_SUBSEQUENTLY_TIMED_OUT"
                    ),
                    "task180_final_object_resolution_observed": True,
                    "task180_final_object_identity": {
                        "host": "public.boxcloud.com",
                        "path_template": (
                            "/d/1/[REDACTED_EPHEMERAL_OBJECT_CAPABILITY]/download"
                        ),
                        "content_disposition_filename": "16_20_360p.mp4",
                        "content_length_bytes": 230486870,
                        "content_type": "video/mp4",
                        "accept_ranges": "bytes",
                        "etag": None,
                        "last_modified": None,
                    },
                    "task180_success_evidence": rel(manual_success_path),
                }
            )
        assets_v3.append(row)

    inventory_v3 = {
        "schema_version": "av-trace.captaincook4d-selected-media-routes/3.0",
        "task_id": TASK_ID,
        "created_at": DATE,
        "decision_token": DECISION,
        "status": "FROZEN_POOL_PARTIALLY_PROBED_NETWORK_STOPPED",
        "source_inventory": rel(inventory_v2_path),
        "recording_count": 10,
        "media_asset_count": 20,
        "recordings": inventory_v2["recordings"],
        "media_assets": assets_v3,
    }
    inventory_v3_path = DERIVED / "selected_media_route_inventory_v3.json"
    write_json(inventory_v3_path, inventory_v3)

    audio_evidence = {
        "schema_version": "av-trace.captaincook4d-audio-mp4-evidence/3.0",
        "task_id": TASK_ID,
        "created_at": DATE,
        "decision_token": DECISION,
        "retained_media_bytes": 0,
        "head_atom_bytes": 0,
        "tail_atom_bytes": 0,
        "parsed_recordings": 0,
        "required_representative_recordings": 3,
        "duration_from_container": None,
        "video_streams": None,
        "video_codecs": None,
        "audio_streams": None,
        "audio_codecs": None,
        "audio_channels": None,
        "audio_sample_rates_hz": None,
        "native_audio_availability": "UNRESOLVED",
        "standalone_microphone_manifest_key_count": 0,
        "conclusion": (
            "No media body or MP4 atom was retained before the stop. Content-Type "
            "video/mp4 does not establish tracks. Native audio cannot be claimed "
            "present or absent for either GoPro 360p or HoloLens PV."
        ),
    }
    audio_path = DERIVED / "audio_and_mp4_evidence_v3.json"
    write_json(audio_path, audio_evidence)

    byte_budget = {
        "schema_version": "av-trace.captaincook4d-media-byte-budget/3.0",
        "task_id": TASK_ID,
        "created_at": DATE,
        "maximum_allowed_retained_media_bytes": BYTE_CAP,
        "retained_media_bytes": 0,
        "retained_head_atom_bytes": 0,
        "retained_tail_atom_bytes": 0,
        "remaining_bytes": BYTE_CAP,
        "within_budget": True,
        "full_media_downloads": 0,
    }
    byte_budget_path = DERIVED / "media_byte_budget_v3.json"
    write_json(byte_budget_path, byte_budget)

    network_stop = {
        "schema_version": "av-trace.network-stop-record/3.0",
        "task_id": TASK_ID,
        "created_at": DATE,
        "user_stop_instruction_observed": True,
        "stop_scope": "ALL_TASK180_NETWORK_ACTIVITY",
        "targeted_process_audit_after_stop": {
            "captaincook4d_route_probe_v3": 0,
            "cc4d_single_probe": 0,
            "utdallas_box_or_public_boxcloud_command_lines": 0,
        },
        "new_network_requests_after_final_stop": 0,
        "retained_media_bytes": 0,
        "no_bulk_download": True,
        "no_h_tier_work": True,
    }
    network_stop_path = DERIVED / "network_stop_record_v3.json"
    write_json(network_stop_path, network_stop)

    registry = {
        "schema_version": "av-trace.captaincook4d-access-registry/3.0",
        "task_id": TASK_ID,
        "registry_id": "av-trace-captaincook4d-route-repair-v3-20261008",
        "created_at": DATE,
        "decision_token": DECISION,
        "scope": "OFFICIAL_DOWNLOADER_SEMANTICS_AND_BOUNDED_ROUTE_EVIDENCE_ONLY",
        "decision_summary": (
            "REPAIR. Commit-pinned official source establishes the exact GET and "
            "redirect semantics, and one selected GoPro route resolved through "
            "Box to a 230,486,870-byte public.boxcloud.com object. The later retry "
            "batch timed out, only 3/20 routes were attempted, no actual range "
            "exchange or MP4 atoms completed, and native audio remains unresolved."
        ),
        "route_readiness": {
            "status": "REPAIR_REQUIRED",
            "ready": False,
            "official_request_semantics_reproduced": True,
            "frozen_recordings": 10,
            "frozen_media_routes": 20,
            "routes_attempted": 3,
            "recordings_attempted": 2,
            "routes_with_final_object_resolution": 1,
            "routes_with_content_length": 1,
            "routes_with_accept_ranges_advertisement": 1,
            "routes_with_completed_range_exchange": 0,
            "routes_with_validators": 0,
            "routes_with_mp4_technical_evidence": 0,
            "representative_recordings_parsed": 0,
            "why_not_ready": [
                "Only one selected asset reached a final object response.",
                "The same route later timed out, so stable availability is not established.",
                "No 206 Content-Range exchange was completed.",
                "No head/tail MP4 atoms were retained.",
                "The requested three-recording codec/audio sample was not completed.",
            ],
            "why_not_no_go": (
                "An exact selected official link successfully resolved through the "
                "official GET redirect path to a live MP4 object, so the route class "
                "is not disproven or categorically inaccessible."
            ),
        },
        "official_downloader_semantics": semantics,
        "successful_route_observation": manual_success,
        "probe_summary": probe_summary,
        "native_audio": audio_evidence,
        "byte_budget": byte_budget,
        "network_stop": network_stop,
        "authorization": {
            "route_readiness_does_not_grant_acquisition_authorization": True,
            "bulk_media_download": "NOT_AUTHORIZED",
            "h_tiers": "NOT_STARTED_AND_NOT_AUTHORIZED",
            "internal_media_processing": "NOT_AUTHORIZED_BY_TASK180",
            "raw_or_derived_media_redistribution": "NOT_AUTHORIZED_BY_TASK180",
            "task174_governance_hold_remains": True,
        },
        "artifacts": {
            "route_inventory": rel(inventory_v3_path),
            "semantics": rel(semantics_path),
            "successful_route_observation": rel(manual_success_path),
            "probe_summary": rel(probe_summary_path),
            "audio_and_mp4": rel(audio_path),
            "byte_budget": rel(byte_budget_path),
            "network_stop": rel(network_stop_path),
            "evidence_manifest": rel(V3 / "evidence_manifest.json"),
            "report": rel(REPORT),
            "result": rel(RESULT),
        },
    }
    write_json(REGISTRY, registry)

    report = f"""# CaptainCook4D official downloader route repair v3

**Task:** 180  
**Date:** {DATE}  
**Decision:** `{DECISION}`  
**Network state:** stopped; zero targeted Task180 clients remained in the final process audit

## 1. Decision

`{DECISION}`

The repair is **partially successful but not route-ready**. Commit-pinned
official source now closes the downloader-semantics question, and one frozen
selected GoPro route reached a live final MP4 object. Coverage, stability,
actual range behavior, MP4 stream parsing, and native audio remain incomplete.

This is not `NO_GO`: recording `16_20` GoPro 360p resolved to a
`public.boxcloud.com` object with HTTP 200 and an exact size. It is not
`READY`: only 3 of 20 routes were attempted, later attempts timed out, no 206
range response was retained, and zero MP4 atoms were fetched.

## 2. Exact official downloader semantics

The official blobs were fetched through `{PROXY}` and verified against the
tree's Git blob IDs:

| File | Git blob | Bytes |
|---|---|---:|
| `download_gopro_data.py` | `d4bb4086f61e4991c14da2387eddde6e73fd4648` | 2,821 |
| `util.py` | `c481510d900e53c4704e81cb2d4b5141e91789f6` | 15,605 |
| `requirements.txt` | `2c8b74ebd07f400fcaf34fb5ebbd5139310e831b` | 13 |

The exact transfer call is `requests.get(url, stream=True)`, followed by
`raise_for_status()`. There is no explicit session, header, User-Agent, query,
cookie, HEAD, or Range logic. Requests follows GET redirects by default and
handles eligible redirect cookies internally. The final response's
`Content-Length` is used for a pre-existing complete-file comparison.

The code retries up to five times with five seconds between failures and reads
the body in 1 MiB chunks. It writes `<target>.part` with mode `wb`, then uses
`os.replace`. Therefore it has retry and atomic-publication behavior, but **no
byte-range resume**: an interrupted `.part` is overwritten rather than resumed.

In the Task180 environment, Requests 2.32.5 supplied:
`User-Agent: python-requests/2.32.5`, `Accept-Encoding: gzip, deflate`,
`Accept: */*`, and `Connection: keep-alive`. The dependency is unpinned, so
that exact User-Agent is a runtime observation, not an upstream invariant.

## 3. Completed selected-route observation

The completed streaming GET for primary recording `16_20`, GoPro 360p,
followed this chain:

1. `utdallas.box.com/shared/static/<token>.mp4` — 301
2. `utdallas.box.com/public/static/<token>.mp4` — 301
3. `utdallas.app.box.com/public/static/<token>.mp4` — 302
4. `public.boxcloud.com/d/1/[REDACTED_EPHEMERAL_OBJECT_CAPABILITY]/download` — 200

No query was added. Box set cookies during the app/final redirects; only cookie
names are retained, never values. The final ephemeral capability path is
redacted.

| Field | Observation |
|---|---|
| Final host | `public.boxcloud.com` |
| Status | 200 |
| Content-Type | `video/mp4` |
| Content-Disposition filename | `16_20_360p.mp4` |
| Content-Length | 230,486,870 bytes |
| Accept-Ranges | `bytes` |
| ETag | absent |
| Last-Modified | absent |
| Media body consumed | 0 bytes |

`Accept-Ranges: bytes` is an advertisement, not proof of actual range
behavior. No bounded request completed with HTTP 206/`Content-Range`.

## 4. Interrupted focused probe status

The later probe batch was stopped. It retained five timeout attempts for each
of three routes: `16_20` GoPro, `16_20` HoloLens PV, and `15_29` GoPro. The
errors occurred while resolving `utdallas.app.box.com`. Thus the same `16_20`
GoPro route succeeded once and later timed out, establishing the redirect
semantics but not stable route availability.

| Counter | Value |
|---|---:|
| Frozen recordings/routes | 10 / 20 |
| Unique recordings/routes attempted | 2 / 3 |
| Routes reaching final object | 1 |
| Routes with exact size | 1 |
| Routes advertising ranges | 1 |
| Completed 206 range exchanges | 0 |
| Routes with ETag or Last-Modified | 0 |
| Unattempted routes after stop | 17 |

## 5. MP4 and native audio

No media body, head atom, or tail atom was retained. Consequently:

- container duration is unresolved;
- video stream count and codec are unresolved;
- audio stream presence is unresolved;
- audio codec, channels, and sample rate are unresolved; and
- the requested three representative recordings across people/environments
  were not parsed.

Native audio availability is therefore **UNRESOLVED**, not absent. The official
manifest still has zero standalone `mc`/microphone URL keys, but that does not
determine whether either MP4 stream contains an audio track.

## 6. Byte, authorization, and stop controls

| Control | Result |
|---|---:|
| Retained media/atom cap | 16,777,216 bytes |
| Retained media/atom bytes | 0 |
| Full media downloads | 0 |
| Bulk acquisition | not authorized |
| H tiers | not started; not authorized |
| Targeted network clients after stop | 0 |

Task180 route evidence does not grant acquisition, processing, publication, or
redistribution authorization. The Task174 governance hold remains.

## 7. Outputs

- `data/rehearsal_plan/captaincook4d_access_registry_v3.json`
- `data/source_recon/captaincook4d_access_v3/evidence_manifest.json`
- `data/source_recon/captaincook4d_access_v3/derived/official_downloader_semantics_v3.json`
- `data/source_recon/captaincook4d_access_v3/derived/manual_success_observation_v3.json`
- `data/source_recon/captaincook4d_access_v3/derived/route_probe_summary_v3.json`
- `data/source_recon/captaincook4d_access_v3/derived/selected_media_route_inventory_v3.json`
- `data/source_recon/captaincook4d_access_v3/derived/audio_and_mp4_evidence_v3.json`
- `data/source_recon/captaincook4d_access_v3/derived/media_byte_budget_v3.json`
- `data/source_recon/captaincook4d_access_v3/derived/network_stop_record_v3.json`
- `orchestration/results/180_captaincook4d_route_repair_v3.txt`

`{DECISION}`
"""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")

    result = f"""Task180 CaptainCook4D official downloader semantics and exact-route repair v3
Date: {DATE}
Final token: {DECISION}

DECISION
--------
REPAIR_REQUIRED.

Commit-pinned official downloader source was obtained and verified. The exact
media request is `requests.get(url, stream=True)` with Requests-default GET
redirect handling, default headers, and redirect-cookie handling. The script
adds no query, caller cookie, HEAD, or Range request. It retries five times,
uses final Content-Length, writes 1 MiB chunks to `.part` with `wb`, and
atomically replaces the target. It does not implement byte-range resume.

ONE COMPLETED SELECTED ROUTE
----------------------------
Recording 16_20 GoPro 360p resolved:

utdallas.box.com/shared/static -> utdallas.box.com/public/static
-> utdallas.app.box.com/public/static
-> public.boxcloud.com/d/1/[REDACTED_EPHEMERAL_OBJECT_CAPABILITY]/download

- redirect statuses: 301, 301, 302
- final status: 200
- final type: video/mp4
- final filename: 16_20_360p.mp4
- exact size: 230,486,870 bytes
- Accept-Ranges: bytes
- ETag: absent
- Last-Modified: absent
- retained body bytes: 0

The exact ephemeral BoxCloud capability and all cookie values are redacted.
No actual 206/Content-Range exchange completed.

STOPPED PROBE COVERAGE
----------------------
- Frozen pool: 10 recordings / 20 MP4 routes.
- Attempted: 2 recordings / 3 unique routes.
- Final object resolutions: 1.
- The later five-attempt batches for 16_20 GoPro, 16_20 HoloLens PV, and
  15_29 GoPro timed out at utdallas.app.box.com.
- Unattempted after stop: 17 routes.
- Targeted network clients after final audit: 0.

AUDIO / MP4
-----------
- Retained media and MP4 atom bytes: 0 (cap 16,777,216).
- Parsed representative recordings: 0 of requested 3.
- Container duration/video codec/audio tracks: unresolved.
- Native audio availability: UNRESOLVED.
- Standalone microphone/mc keys in official manifest: 0.

WHY REPAIR
----------
Not READY because stable 8+2 coverage, actual range behavior, validators, and
three-recording MP4/audio parsing were not completed. Not NO_GO because one
exact selected official route reached a live final MP4 object.

No bulk media, H tiers, or acquisition authorization.

OUTPUTS
-------
- data/rehearsal_plan/captaincook4d_access_registry_v3.json
- docs/review/captaincook4d_route_repair_v3.md
- data/source_recon/captaincook4d_access_v3/evidence_manifest.json
- data/source_recon/captaincook4d_access_v3/derived/

{DECISION}
"""
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(result, encoding="utf-8")

    evidence_files: list[tuple[Path, str]] = [
        (V1 / "downloader_README.md", "retained official downloader README"),
        (V1 / "downloader_tree.json", "retained official downloader tree"),
        (V1 / "download_links.json", "official link manifest"),
        (inventory_v2_path, "frozen v2 route inventory source"),
        *[
            (item["path"], f"commit-pinned official {name}")
            for name, item in official_files.items()
        ],
        *[
            (
                V3 / "official_source" / f"{name}.api.json",
                f"GitHub blob API envelope for {name}",
            )
            for name in (
                "download_gopro_data",
                "util",
                "requirements",
            )
        ],
        *[
            (
                V3 / "official_source" / f"{name}.api.headers",
                f"GitHub blob API response headers for {name}",
            )
            for name in (
                "download_gopro_data",
                "util",
                "requirements",
            )
        ],
        *[
            (
                V3 / "probes" / asset_id / "probe.json",
                "interrupted official-style GET attempts",
            )
            for asset_id in attempted_ids
        ],
        (semantics_path, "derived exact official request semantics"),
        (manual_success_path, "redacted completed route observation"),
        (probe_summary_path, "derived bounded probe summary"),
        (inventory_v3_path, "v3 frozen route inventory and statuses"),
        (audio_path, "fail-closed audio and MP4 evidence"),
        (byte_budget_path, "retained media byte accounting"),
        (network_stop_path, "network stop audit"),
        (REGISTRY, "v3 access registry"),
        (REPORT, "Task180 review"),
        (RESULT, "Task180 result"),
    ]
    manifest = {
        "schema_version": "av-trace.evidence-manifest/3.0",
        "task_id": TASK_ID,
        "created_at": DATE,
        "decision_token": DECISION,
        "network_stopped": True,
        "retained_media_bytes": 0,
        "files": [
            file_record(path, role)
            for path, role in evidence_files
            if path.exists()
        ],
        "important_limitation": (
            "The successful route observation is a redacted reconstruction from "
            "the structured command result; its first local JSON was overwritten "
            "by the interrupted retry batch. No raw ephemeral capability or cookie "
            "value is retained."
        ),
    }
    write_json(V3 / "evidence_manifest.json", manifest)


if __name__ == "__main__":
    main()
