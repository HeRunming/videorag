#!/usr/bin/env python3
"""Finalize Task178 from retained local evidence after the network stop order.

This script performs no network access.  It reads Task174's retained official
metadata and probe artifacts, freezes the same 8+2 recording pool, and writes
the fail-closed Task178 route/audiovisual technical-evidence outputs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "data/source_recon/captaincook4d_access_v1"
V2 = ROOT / "data/source_recon/captaincook4d_access_v2"
DERIVED = V2 / "derived"
REGISTRY = ROOT / "data/rehearsal_plan/captaincook4d_access_registry_v2.json"
REVIEW = ROOT / "docs/review/captaincook4d_route_repair_v2.md"
RESULT = ROOT / "orchestration/results/178_captaincook4d_route_repair.txt"

TASK_ID = 178
DATE = "2026-10-02"
DECISION = "CAPTAINCOOK4D_ROUTE_REPAIR"
PROXY = "https://proxy.example.invalid:3128"
MP4_BUDGET_BYTES = 16 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, role: str) -> dict[str, object]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "role": role,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def selected_recordings(selection: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key in ("primary", "replacement"):
        for source in selection[key]:
            rows.append(
                {
                    "role": str(source["role"]),
                    "rank": int(source["rank"]),
                    "source_group_id": str(source["source_group_id"]),
                    "person_id": int(source["person_id"]),
                    "environment_id": int(source["environment_id"]),
                    "recording_id": str(source["representative_recording_id"]),
                    "official_metadata_duration_seconds": float(
                        source["duration_seconds"]
                    ),
                    "replacement_for_source_group_id": source.get(
                        "replacement_for_source_group_id"
                    ),
                    "gopro_360p_url": source["official_stream_urls"]["gopro_360p"],
                    "hololens_sync_pv_video_url": source[
                        "official_stream_urls"
                    ]["hololens_sync_pv_video"],
                }
            )
    return rows


def media_assets(recordings: list[dict[str, object]]) -> list[dict[str, object]]:
    assets: list[dict[str, object]] = []
    stream_specs = (
        ("gopro_360p", "gopro_360p_url"),
        ("hololens_sync_pv_video", "hololens_sync_pv_video_url"),
    )
    for recording in recordings:
        for stream_name, url_key in stream_specs:
            url = str(recording[url_key])
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.netloc != "utdallas.box.com":
                raise RuntimeError(f"Non-official media route in frozen pool: {url}")
            assets.append(
                {
                    "asset_id": (
                        f"{recording['role'].lower()}-{recording['rank']}-"
                        f"{recording['recording_id']}-{stream_name}"
                    ),
                    "role": recording["role"],
                    "rank": recording["rank"],
                    "source_group_id": recording["source_group_id"],
                    "recording_id": recording["recording_id"],
                    "stream": stream_name,
                    "official_shared_link": url,
                    "official_entrypoint_host": parsed.netloc,
                    "official_shared_token_filename": Path(parsed.path).name,
                    "probe_scope": "NOT_PROBED_AFTER_TASK178_STOP_ORDER",
                    "entrypoint_status": None,
                    "redirect_count": None,
                    "final_url": None,
                    "final_host": None,
                    "final_cdn_or_object_identity": None,
                    "content_type": None,
                    "content_length_bytes": None,
                    "accept_ranges": None,
                    "etag": None,
                    "last_modified": None,
                    "content_range": None,
                    "metadata_duration_seconds": recording[
                        "official_metadata_duration_seconds"
                    ],
                    "container_duration_seconds": None,
                    "video_codec": None,
                    "audio_track_present": None,
                    "audio_codec": None,
                    "audio_channels": None,
                    "audio_sample_rate_hz": None,
                    "head_atom_bytes_fetched": 0,
                    "tail_atom_bytes_fetched": 0,
                    "technical_evidence_status": "UNRESOLVED_NO_MEDIA_BYTES",
                }
            )
    return assets


def main() -> None:
    DERIVED.mkdir(parents=True, exist_ok=True)

    selection_path = V1 / "derived/selection_v1.json"
    links_path = V1 / "download_links.json"
    tree_path = V1 / "downloader_tree.json"
    readme_path = V1 / "downloader_README.md"
    probe_headers_path = V1 / "probe_test_15_5_gopro360.headers"
    probe_metrics_path = V1 / "probe_test_15_5_gopro360.metrics"

    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    links = json.loads(links_path.read_text(encoding="utf-8"))
    downloader_tree = json.loads(tree_path.read_text(encoding="utf-8"))
    recordings = selected_recordings(selection)
    assets = media_assets(recordings)

    if len(recordings) != 10 or len(assets) != 20:
        raise RuntimeError("Expected frozen 8+2 recordings and two MP4 routes each")
    if any(row["recording_id"] not in links for row in recordings):
        raise RuntimeError("Frozen recording missing from official link manifest")

    source_blob_paths = {
        item["path"]: {
            "git_blob_sha": item["sha"],
            "size": item.get("size"),
        }
        for item in downloader_tree["tree"]
        if item["type"] == "blob"
    }

    route_inventory = {
        "schema_version": "av-trace.captaincook4d-selected-media-routes/2.0",
        "task_id": TASK_ID,
        "created_at": DATE,
        "decision_token": DECISION,
        "status": "FROZEN_POOL_ROUTE_TECHNICAL_FIELDS_UNRESOLVED",
        "source_selection": selection_path.relative_to(ROOT).as_posix(),
        "recording_count": len(recordings),
        "media_asset_count": len(assets),
        "official_entrypoint_hosts": ["utdallas.box.com"],
        "recordings": recordings,
        "media_assets": assets,
    }
    route_inventory_path = DERIVED / "selected_media_route_inventory_v2.json"
    write_json(route_inventory_path, route_inventory)

    route_diagnosis = {
        "schema_version": "av-trace.captaincook4d-route-diagnosis/2.0",
        "task_id": TASK_ID,
        "created_at": DATE,
        "decision_token": DECISION,
        "observed_task174_head": {
            "selected_pool_asset": False,
            "recording_id": "15_5",
            "stream": "gopro_360p",
            "method": "HEAD",
            "proxy": PROXY,
            "official_url": (
                "https://utdallas.box.com/shared/static/"
                "e42myf2y7oacwxqyt4m15pofrrsacku3.mp4"
            ),
            "status": 404,
            "redirect_count": 0,
            "effective_url_unchanged": True,
            "content_type": "text/html; charset=UTF-8",
            "content_length": None,
            "accept_ranges": None,
            "etag": None,
            "last_modified": None,
            "response_body_bytes": 0,
            "evidence": [
                probe_headers_path.relative_to(ROOT).as_posix(),
                probe_metrics_path.relative_to(ROOT).as_posix(),
            ],
        },
        "bounded_diagnosis": {
            "established": [
                "The failed request exercised only HTTP HEAD against the opaque Box /shared/static entrypoint.",
                "It did not reach or reveal a final CDN/object URL: the response had zero redirects.",
                "The response therefore proves that this direct HEAD invocation was not a usable object-identity or range-discovery method for that URL at that time.",
                "It does not prove that the frozen selected links are absent, because the sole retained probe targeted recording 15_5 outside the frozen 8+2 pool.",
            ],
            "architectural_interpretation_not_network_verified": (
                "A Box shared/static URL is an entrypoint whose successful transfer "
                "may depend on the downloader's GET handling, including any redirects "
                "or cookies produced during that GET. The retained HEAD never exercised "
                "that path. This explains why the HEAD result cannot be promoted to "
                "final object status, but the exact Box-side cause of the 404 is not "
                "proven by retained evidence."
            ),
            "not_distinguishable_from_retained_evidence": [
                "method-specific rejection or different HEAD versus GET handling",
                "stale, revoked, replaced, or mistyped shared token",
                "a redirect/cookie flow reached only by GET",
                "another Box resolver or policy condition",
            ],
        },
        "official_downloader_semantics_review": {
            "commit_tree_sha": downloader_tree["sha"],
            "retained_tree_manifest": True,
            "retained_link_manifest": True,
            "retained_readme": True,
            "retained_source_code_bodies": False,
            "code_paths_and_blob_ids": {
                path: source_blob_paths[path]
                for path in (
                    "download_gopro_data.py",
                    "download_hololens_data.py",
                    "download_hololens_3d_data.py",
                    "util.py",
                )
            },
            "readme_establishes": [
                "All downloader programs read metadata/download_links.json.",
                "Downloads are described as resumable.",
                "A file whose size already matches the server is skipped.",
                "Partial transfers use a .part file.",
            ],
            "exact_request_semantics_established": False,
            "unresolved_semantics": [
                "HTTP method used for initial size discovery",
                "redirect policy",
                "cookie/session persistence",
                "request headers and user agent",
                "range/resume header behavior",
            ],
            "task178_replay_status": (
                "NOT_EXECUTED_BEFORE_USER_NETWORK_STOP; no claim of reproducing "
                "the official script is made"
            ),
        },
    }
    route_diagnosis_path = DERIVED / "route_diagnosis_v2.json"
    write_json(route_diagnosis_path, route_diagnosis)

    stop_record = {
        "schema_version": "av-trace.network-stop-record/2.0",
        "task_id": TASK_ID,
        "created_at": DATE,
        "user_stop_instruction_observed": True,
        "stop_scope": "ALL_TASK178_NETWORK_ACTIVITY",
        "active_targeted_network_processes_after_local_audit": 0,
        "task178_box_head_requests_completed": 0,
        "task178_box_range_requests_completed": 0,
        "task178_box_media_get_requests_completed": 0,
        "task178_final_cdn_requests_completed": 0,
        "task178_media_payload_bytes_persisted": 0,
        "task178_mp4_atom_bytes_persisted": 0,
        "official_downloader_source_fetch": {
            "retained_response_files": 0,
            "retained_response_bytes": 0,
            "local_sandbox_attempt": (
                "Failed before connection because the explicit proxy hostname "
                "could not be resolved in the sandbox."
            ),
            "escalated_attempt": (
                "Interrupted by the user; no retained file or response evidence."
            ),
        },
        "carryforward_task174_probe_only": {
            "head_requests": 1,
            "range_requests": 0,
            "media_get_requests": 0,
            "media_payload_bytes": 0,
            "selected_pool_asset": False,
        },
        "no_bulk_download": True,
        "no_h_tier_work": True,
    }
    stop_record_path = DERIVED / "network_stop_record_v2.json"
    write_json(stop_record_path, stop_record)

    byte_budget = {
        "schema_version": "av-trace.captaincook4d-mp4-byte-budget/2.0",
        "task_id": TASK_ID,
        "created_at": DATE,
        "maximum_allowed_bytes": MP4_BUDGET_BYTES,
        "head_atom_bytes_fetched": 0,
        "tail_atom_bytes_fetched": 0,
        "total_mp4_bytes_fetched": 0,
        "remaining_bytes": MP4_BUDGET_BYTES,
        "within_budget": True,
        "full_media_downloads": 0,
        "parsed_mp4_assets": 0,
    }
    byte_budget_path = DERIVED / "mp4_byte_budget_v2.json"
    write_json(byte_budget_path, byte_budget)

    registry = {
        "schema_version": "av-trace.captaincook4d-access-registry/2.0",
        "task_id": TASK_ID,
        "registry_id": "av-trace-captaincook4d-route-repair-v2-20261002",
        "created_at": DATE,
        "decision_token": DECISION,
        "scope": "OFFICIAL_BOX_ROUTE_AND_BOUNDED_MP4_TECHNICAL_EVIDENCE_ONLY",
        "decision_summary": (
            "Fail-closed REPAIR. Task174's official metadata and exact 8+2 pool "
            "remain valid, but Task178 stopped before any selected Box route was "
            "replayed with official downloader semantics. No final CDN/object "
            "identity, size, validator, range behavior, MP4 duration, codec, or "
            "native-audio fact was established for the 20 selected MP4 routes."
        ),
        "route_readiness": {
            "status": "REPAIR_REQUIRED",
            "ready": False,
            "selected_recordings": 10,
            "selected_media_routes": 20,
            "routes_with_final_object_identity": 0,
            "routes_with_content_length": 0,
            "routes_with_range_evidence": 0,
            "routes_with_mp4_technical_evidence": 0,
            "reason": (
                "The only retained Box probe is Task174's HTTP 404 HEAD for an "
                "unselected recording; it cannot establish selected-route failure "
                "or success and did not expose final object identity."
            ),
        },
        "acquisition_authorization": {
            "status": "NOT_AUTHORIZED_BY_TASK178",
            "route_readiness_does_not_grant_authorization": True,
            "bounded_route_probes_only_if_separately_resumed": True,
            "bulk_media_download": "PROHIBITED",
            "h_tiers": "NOT_STARTED_AND_NOT_AUTHORIZED",
            "internal_media_processing": "NOT_AUTHORIZED_BY_TASK178",
            "raw_media_redistribution": "NOT_AUTHORIZED_BY_TASK178",
            "clip_frame_audio_redistribution": "NOT_AUTHORIZED_BY_TASK178",
            "feature_embedding_redistribution": "NOT_AUTHORIZED_BY_TASK178",
            "governance_hold_from_task174_remains": True,
        },
        "network_policy": {
            "required_proxy": PROXY,
            "allowed_media_entrypoint_host": "utdallas.box.com",
            "access_control_bypass": False,
            "task178_network_stopped": True,
        },
        "task174_carryforward": {
            "selection_path": selection_path.relative_to(ROOT).as_posix(),
            "official_link_manifest_path": links_path.relative_to(ROOT).as_posix(),
            "official_link_manifest_bytes": links_path.stat().st_size,
            "official_link_manifest_sha256": sha256(links_path),
            "downloader_tree_sha": downloader_tree["sha"],
            "download_links_git_blob_sha": source_blob_paths[
                "metadata/download_links.json"
            ]["git_blob_sha"],
            "frozen_pool_status": "UNCHANGED_8_PRIMARY_PLUS_2_REPLACEMENTS",
        },
        "box_head_diagnosis": route_diagnosis["bounded_diagnosis"],
        "official_downloader_request_semantics": route_diagnosis[
            "official_downloader_semantics_review"
        ],
        "technical_evidence": {
            "mp4_byte_budget_bytes": MP4_BUDGET_BYTES,
            "mp4_bytes_fetched": 0,
            "media_payload_bytes_persisted": 0,
            "container_duration_status": "UNRESOLVED",
            "video_codec_status": "UNRESOLVED",
            "native_audio_presence_status": "UNRESOLVED",
            "audio_codec_status": "UNRESOLVED",
            "audio_channels_status": "UNRESOLVED",
            "audio_sample_rate_status": "UNRESOLVED",
            "metadata_durations_are_not_treated_as_container_probe_results": True,
        },
        "frozen_recordings": recordings,
        "selected_media_routes": assets,
        "repair_requirements": [
            "Retain the exact commit-pinned official downloader source bodies.",
            "Replay the downloader's actual GET/redirect/cookie semantics through the explicit proxy, without adding browser emulation or bypass behavior.",
            "For each of the 20 official selected links, retain the entrypoint and redirect chain and resolve the exact final CDN/object identity where available.",
            "Use bounded HEAD or Range only after matching official semantics; record Content-Length or Content-Range total, Accept-Ranges, ETag, and Last-Modified.",
            "Fetch only the minimum head/tail MP4 atom bytes, keeping the aggregate at or below 16 MiB, to establish container duration, video codec, audio-track presence, and audio codec/channel/rate fields.",
            "Keep route readiness separate from media acquisition, processing, and redistribution authorization.",
        ],
        "evidence": {
            "route_inventory": route_inventory_path.relative_to(ROOT).as_posix(),
            "route_diagnosis": route_diagnosis_path.relative_to(ROOT).as_posix(),
            "network_stop_record": stop_record_path.relative_to(ROOT).as_posix(),
            "mp4_byte_budget": byte_budget_path.relative_to(ROOT).as_posix(),
            "evidence_manifest": (
                V2 / "evidence_manifest.json"
            ).relative_to(ROOT).as_posix(),
        },
    }
    write_json(REGISTRY, registry)

    recording_table = "\n".join(
        "| {role} | {rank} | `{source_group_id}` | `{recording_id}` | "
        "{official_metadata_duration_seconds:.2f} | 2 | unresolved |".format(**row)
        for row in recordings
    )
    review = f"""# CaptainCook4D official Box route repair v2

**Task:** 178  
**Date:** {DATE}  
**Decision:** `{DECISION}`  
**Mode:** immediate fail-closed finalization after user network-stop order

## 1. Decision

`{DECISION}`

CaptainCook4D remains **metadata-ready but media-route-not-ready**. The
Task174 8-primary + 2-replacement pool is unchanged, and all 20 selected MP4
entrypoints are exact links from the retained official
`metadata/download_links.json` on `utdallas.box.com`. However, Task178 stopped
before a selected link was successfully replayed with the official
downloader's request semantics.

Consequently, no selected asset has an established final CDN/object identity,
`Content-Length`, range behavior, ETag, Last-Modified value, MP4 duration,
video codec, audio track, audio codec, channel count, or sample rate.

This is `REPAIR`, not `NO_GO`: the official manifest and frozen pool still
provide concrete repair targets, and the single 404 was for an unselected
recording and a HEAD method that did not exercise a successful downloader GET.

## 2. Network stop and byte accounting

The user ordered all Task178 network activity stopped on {DATE}. A local
process audit found **zero active targeted network processes**.

| Counter | Value |
|---|---:|
| Task178 selected Box HEAD requests completed | 0 |
| Task178 selected Box range requests completed | 0 |
| Task178 media GET requests completed | 0 |
| Final CDN requests completed | 0 |
| Persisted media payload | 0 bytes |
| Persisted head/tail MP4 atoms | 0 bytes |
| Aggregate MP4 atom cap | {MP4_BUDGET_BYTES:,} bytes |
| Full media downloads | 0 |
| H-tier work | 0 |

An attempted commit-pinned downloader-source fetch retained no response file:
the sandbox attempt failed before connection because the explicit proxy name
could not be resolved, and the escalated attempt was interrupted. No source
body or media byte from that attempt is used as evidence.

## 3. What was reviewed

Task178 reviewed the retained Task174 artifacts:

- official downloader tree at
  `cf248fe2139fc6e37f9737141ec719948fbd1747`;
- exact 700,705-byte `download_links.json`;
- official downloader README;
- frozen `selection_v1.json`;
- the prior 404 response headers and metrics; and
- the 8+2 recording IDs and their exact GoPro 360p and synchronized HoloLens
  PV URLs.

The tree manifest identifies `download_gopro_data.py`,
`download_hololens_data.py`, `download_hololens_3d_data.py`, and `util.py`
with exact Git blob IDs, but Task174 did **not** retain those source bodies.
Therefore Task178 cannot honestly claim that exact method, redirect, cookie,
header, or resume semantics were reproduced.

The README does establish that the scripts consume
`metadata/download_links.json`, use resumable downloads, compare a local file
size with a server size, and write interrupted transfers to `.part` files.
Those statements do not establish the exact HTTP exchange.

## 4. Why the raw HEAD did not repair the route

Task174's sole completed media probe was:

- recording `15_5`, GoPro 360p;
- official
  `https://utdallas.box.com/shared/static/e42myf2y7oacwxqyt4m15pofrrsacku3.mp4`;
- explicit proxy `{PROXY}`;
- method `HEAD`;
- HTTP 404;
- zero redirects;
- `text/html; charset=UTF-8`;
- no Content-Length, Accept-Ranges, ETag, or Last-Modified; and
- zero response-body bytes.

The bounded diagnosis is that the request tested only the opaque Box
`/shared/static` entrypoint. It did not execute a successful streaming GET and
did not reach a signed/final CDN or object URL. Thus it cannot identify the
object and cannot distinguish a method-specific HEAD difference from a stale
token, a GET-only redirect/cookie flow, or another Box resolver condition.

This diagnosis is deliberately limited: retained evidence does **not** prove
the exact Box-side reason for the 404. It also does not prove that any frozen
selected link fails, because `15_5` is outside the selected pool.

## 5. Frozen 8+2 route inventory

Each row has two exact official MP4 entrypoints: GoPro 360p and synchronized
HoloLens PV. Exact URLs and all null technical fields are recorded in
`selected_media_route_inventory_v2.json` and the v2 registry.

| Role | Rank | Source group | Recording | Official metadata duration (s) | MP4 routes | Technical status |
|---|---:|---|---|---:|---:|---|
{recording_table}

The official metadata duration is retained for identity and selection only.
It is **not** represented as container-duration evidence.

## 6. Audio and codec evidence

No MP4 atom bytes were fetched. Therefore native audio remains
`UNRESOLVED` for both camera streams across all ten recordings. No claim is
made for:

- audio-track presence or absence;
- AAC or any other audio codec;
- channels or sample rate;
- H.264/AVC, HEVC, or any other video codec;
- exact container duration; or
- A/V alignment.

The Task174 observation also remains unchanged: the official link manifest
has no standalone `mc`/microphone key, despite the README describing raw
HoloLens microphone capture.

## 7. Route readiness versus authorization

| Surface | Task178 status |
|---|---|
| Official metadata and frozen-pool identity | `READY` |
| Selected Box entrypoint enumeration | `READY` |
| Final CDN/object identity | `REPAIR_REQUIRED` |
| Size, validators, and range behavior | `REPAIR_REQUIRED` |
| MP4 duration/video codec/native audio | `REPAIR_REQUIRED` |
| Bulk media acquisition | `NOT_AUTHORIZED_BY_TASK178` |
| Internal media processing | `NOT_AUTHORIZED_BY_TASK178` |
| Raw media redistribution | `NOT_AUTHORIZED_BY_TASK178` |
| Clip/frame/audio redistribution | `NOT_AUTHORIZED_BY_TASK178` |
| H tiers | `NOT_STARTED_AND_NOT_AUTHORIZED` |

Even a future `ROUTE_READY` result would not itself authorize acquisition,
processing, publication, or redistribution. Task174's governance hold remains.

## 8. Required repair

1. Retain the exact commit-pinned official downloader source bodies.
2. Reproduce only the downloader's actual GET, redirect, cookie, and resume
   behavior through `{PROXY}`; do not add access-control bypasses.
3. Probe each of the 20 exact `utdallas.box.com` entrypoints with bounded
   requests and record the complete redirect chain and final object identity.
4. Record exact object size, Accept-Ranges/Content-Range, ETag, and
   Last-Modified where exposed.
5. Fetch only enough head/tail MP4 atoms to establish duration and video/audio
   tracks while keeping the aggregate at or below 16 MiB.
6. Run a separate authorization/governance decision before any bulk download
   or H-tier work.

## 9. Outputs

- `data/rehearsal_plan/captaincook4d_access_registry_v2.json`
- `data/source_recon/captaincook4d_access_v2/evidence_manifest.json`
- `data/source_recon/captaincook4d_access_v2/derived/selected_media_route_inventory_v2.json`
- `data/source_recon/captaincook4d_access_v2/derived/route_diagnosis_v2.json`
- `data/source_recon/captaincook4d_access_v2/derived/network_stop_record_v2.json`
- `data/source_recon/captaincook4d_access_v2/derived/mp4_byte_budget_v2.json`
- `orchestration/results/178_captaincook4d_route_repair.txt`

`{DECISION}`
"""
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text(review, encoding="utf-8")

    result = f"""Task178 CaptainCook4D official Box route and audio evidence repair
Date: {DATE}
Final token: {DECISION}

DECISION
--------
CaptainCook4D remains metadata-ready but media-route-not-ready.

ROUTE READINESS
---------------
Status: REPAIR_REQUIRED

- Frozen pool: 8 primary + 2 replacement recordings, unchanged from Task174.
- Exact official MP4 entrypoints: 20 (GoPro 360p + HoloLens sync PV).
- Entrypoint host: utdallas.box.com only.
- Selected routes with final CDN/object identity: 0/20.
- Selected routes with Content-Length: 0/20.
- Selected routes with range evidence: 0/20.
- Selected routes with MP4 technical evidence: 0/20.

WHY THE PRIOR HEAD WAS NOT SUFFICIENT
-------------------------------------
Task174's only completed media request was a HEAD for unselected recording
15_5. Through {PROXY}, the official Box shared/static entrypoint returned
HTTP 404 with zero redirects and no Content-Length, Accept-Ranges, ETag, or
Last-Modified.

That result proves only that direct HEAD was not a usable object-discovery
exchange for that URL at that time. It never reached a final CDN/object URL
and did not exercise the downloader's streaming GET path. Retained evidence
cannot distinguish method-specific HEAD behavior, a stale token, a GET-only
redirect/cookie flow, or another Box resolver condition. It does not establish
failure of any frozen selected route.

OFFICIAL DOWNLOADER SEMANTICS
-----------------------------
The retained official tree pins the downloader paths and Git blob IDs, and
the README/link manifest were reviewed. The source code bodies were not
retained. A Task178 source fetch produced no retained response and network
activity was then stopped. Exact method, redirect, cookie, header, and resume
semantics were therefore not reproduced; no contrary claim is made.

TECHNICAL / AUDIO EVIDENCE
--------------------------
- MP4 atom budget: 16,777,216 bytes.
- MP4 atom bytes fetched: 0.
- Full media downloads: 0.
- Container duration: unresolved for 20/20.
- Video codec: unresolved for 20/20.
- Native audio presence: unresolved for 20/20.
- Audio codec/channels/sample rate: unresolved for 20/20.

The official metadata durations remain selection metadata, not container
probe results. The manifest still has no standalone microphone/mc URL key.

NETWORK STOP
------------
The user ordered immediate finalization and all Task178 network activity
stopped.

- Active targeted network processes after local audit: 0.
- Task178 selected Box HEAD requests completed: 0.
- Task178 selected Box range requests completed: 0.
- Task178 media GET requests completed: 0.
- Persisted Task178 media payload: 0 bytes.
- Persisted Task178 MP4 atoms: 0 bytes.
- No bulk download and no H-tier work occurred.

AUTHORIZATION
-------------
Route readiness is separate from acquisition authorization.

- Bulk acquisition: NOT_AUTHORIZED_BY_TASK178.
- Internal media processing: NOT_AUTHORIZED_BY_TASK178.
- Raw/clip/frame/audio redistribution: NOT_AUTHORIZED_BY_TASK178.
- H tiers: NOT_STARTED_AND_NOT_AUTHORIZED.
- Task174 governance hold remains.

OUTPUTS
-------
- data/rehearsal_plan/captaincook4d_access_registry_v2.json
- docs/review/captaincook4d_route_repair_v2.md
- data/source_recon/captaincook4d_access_v2/evidence_manifest.json
- data/source_recon/captaincook4d_access_v2/derived/selected_media_route_inventory_v2.json
- data/source_recon/captaincook4d_access_v2/derived/route_diagnosis_v2.json
- data/source_recon/captaincook4d_access_v2/derived/network_stop_record_v2.json
- data/source_recon/captaincook4d_access_v2/derived/mp4_byte_budget_v2.json

{DECISION}
"""
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(result, encoding="utf-8")

    evidence_files = [
        route_inventory_path,
        route_diagnosis_path,
        stop_record_path,
        byte_budget_path,
    ]
    source_files = [
        selection_path,
        links_path,
        tree_path,
        readme_path,
        probe_headers_path,
        probe_metrics_path,
    ]
    manifest = {
        "schema_version": "av-trace.evidence-manifest/2.0",
        "task_id": TASK_ID,
        "created_at": DATE,
        "decision_token": DECISION,
        "network_stopped": True,
        "official_media_route_policy": (
            "Only exact official utdallas.box.com links from the retained "
            "CaptainCook4D manifest are accepted as media entrypoints."
        ),
        "media_bytes_persisted": 0,
        "mp4_atom_bytes_persisted": 0,
        "files": [
            *(file_record(path, "task174_retained_source") for path in source_files),
            *(file_record(path, "task178_derived") for path in evidence_files),
            file_record(REGISTRY, "task178_registry"),
            file_record(REVIEW, "task178_review"),
            file_record(RESULT, "task178_result"),
        ],
    }
    write_json(V2 / "evidence_manifest.json", manifest)


if __name__ == "__main__":
    main()
