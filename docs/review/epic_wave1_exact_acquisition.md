# EPIC Wave-1 exact acquisition review

**Task:** 162  
**Date:** 2026-09-28  
**Decision:** `EPIC_WAVE1_ACQUISITION_READY`

## Scope and boundaries

Task 162 finalized the two already-acquired EPIC-KITCHENS-100 Wave-1
recordings. It did not issue any new network request or redownload media.
The work was limited to:

- validating the completed initial partials and ordered range chunks;
- assembling exact final MP4s in the restricted media tree;
- verifying official MD5 values and computing SHA-256 values;
- running PyAV and OpenCV technical audits;
- publishing acquisition and per-source manifests;
- producing the deterministic Task 153 nonsemantic inventory and sample
  plan; and
- removing redundant transfer pieces after the final media and manifests
  had been verified and frozen.

No human semantic review was performed. This decision does not assign a human
construct tier, determine modality necessity, decide Gate A, authorize
scientific execution, or authorize public release or redistribution.

## Inputs and contracts reviewed

- `orchestration/results/149_cvpr_pivot_v2_addendum.txt`
- `orchestration/results/153_semantic_av_source_prescreen_tooling.txt`
- `orchestration/results/161_assembly_epic_access_preflight_v2.txt`
- `orchestration/results/163_epic_wave1_index_implementation.txt`
- `data/restricted/epic_wave1_sources_v1/.staging/fetch_range.sh`
- `data/restricted/epic_wave1_sources_v1/.staging/run_parallel_ranges.sh`
- range response headers and attempt logs under
  `data/restricted/epic_wave1_sources_v1/logs/`
- the Task 163 acquisition-manifest loader in
  `src/av_trace_epic_wave1_index/sources.py`

## Exact assembly

Both sources were assembled with umask `0077`. For each source, the initial
`.part` was copied first and the `chunk-*.bin` files were then copied in
lexicographic order. The output was written to a temporary file in the final
source directory, flushed with `fsync`, changed to mode `0600`, promoted with
atomic `os.replace`, and followed by a parent-directory `fsync`.

| Source | Initial partial | Ordered chunks | Chunk bytes | Final bytes |
| --- | ---: | ---: | ---: | ---: |
| `P28_103` | 66,543,616 | 21 | 5,462,996,756 | 5,529,540,372 |
| `P27_101` | 17,653,760 | 16 | 4,102,704,788 | 4,120,358,548 |

Every chunk had the expected size and a matching `Content-Range`. `P27_101`
chunk 6 had one recoverable curl return code 18 after 9,715,408 bytes and then
resumed at the exact next byte. It completed at the intended total. Across
both sources there were 37 completed chunks and no terminal `FAIL_*` records.

## Integrity results

| Source | Official MD5 | MD5 result | SHA-256 |
| --- | --- | --- | --- |
| `P28_103` | `30258174e4ae5cee495170d2748efc4e` | PASS | `a2f1023ab698f790430ed126f9fddfd9b0de6258f57f6f89cdfb0ab131f9cf8e` |
| `P27_101` | `f3e40c9216ab5f05cddb762bd70278d5` | PASS | `3b843787ad5906fe48d6b440b305a4dd31346e9a1569211286b3705a3baa1c0d` |

The exact final paths are:

- `data/restricted/epic_wave1_sources_v1/media/P28/P28_103.MP4`
- `data/restricted/epic_wave1_sources_v1/media/P27/P27_101.MP4`

Both files are mode `0600`; both source directories are mode `0700`.

## Technical audit

The audit used PyAV `16.1.0` and OpenCV `4.13.0`.

### `P28_103`

- Official video duration: exactly `1825.16` seconds.
- Video: HEVC Main, `1920x1080`, 50 fps, time base `1/90000`,
  91,258 declared and decoded frames.
- Audio: AAC LC, stereo, 48 kHz, time base `1/48000`,
  85,555 declared and decoded frames, duration `1825.1733333333334`
  seconds.
- Additional data streams: GoPro metadata at time base `1/1000` and
  timecode data at time base `1/90000`.
- Beginning/middle/end A/V timestamp deltas:
  `0.01866666666666672`, `0.0`, and `0.002666666666755191` seconds.
- PyAV reached EOF with monotonic timestamps, exact declared frame counts,
  and final frame ends matching stream durations.
- OpenCV opened through FFmpeg and grabbed exactly 91,258 of 91,258 frames
  through EOF.

### `P27_101`

- Official video duration: exactly `1360.20` seconds.
- Video: HEVC Main, `1920x1080`, 50 fps, time base `1/90000`,
  68,010 declared and decoded frames.
- Audio: AAC LC, stereo, 48 kHz, time base `1/48000`,
  63,760 declared and decoded frames, duration `1360.2133333333334`
  seconds.
- Additional data streams: GoPro metadata at time base `1/1000` and
  timecode data at time base `1/90000`.
- Beginning/middle/end A/V timestamp deltas:
  `0.01866666666666672`, `0.0`, and `0.005333333333283008` seconds.
- PyAV reached EOF with monotonic timestamps, exact declared frame counts,
  and final frame ends matching stream durations.
- OpenCV opened through FFmpeg and grabbed exactly 68,010 of 68,010 frames
  through EOF.

All required full-open, duration, stream, codec, time-base, finite
beginning/middle/end A/V decode, synchronization, EOF, and no-truncation
checks passed.

## Manifests and Task 153 plan

The root acquisition manifest is:

`data/restricted/epic_wave1_sources_v1/manifests/epic_wave1_acquisition_manifest.json`

Its decision is `EPIC_WAVE1_ACQUISITION_READY`. It records two complete
sources, 9,649,898,920 aggregate media bytes, 3,185.36 aggregate seconds,
zero failed transfers, zero incomplete transfers, exact hashes, technical
evidence, and permission checks.

Per-source manifests:

- `data/restricted/epic_wave1_sources_v1/manifests/P28_103.source_manifest.json`
- `data/restricted/epic_wave1_sources_v1/manifests/P27_101.source_manifest.json`

The Task 153 artifacts are:

- `data/restricted/epic_wave1_sources_v1/prescreen/epic_wave1_semantic_source_prescreen_inventory.json`
- `data/restricted/epic_wave1_sources_v1/prescreen/epic_wave1_semantic_source_prescreen_plan.json`

The inventory contains only source ID, source-group ID, duration, exact
source SHA-256, and adapter reference. Media and semantic metadata are not
embedded. The plan uses
`source-uniform-temporal-bin-sha256-jitter-v1`, six unlabeled 12-second
intervals, exactly three per source, and `extract_media=false`. No human form
was completed or imported.

## Task 163 contract check

The Task 163 loader recomputed both media hashes and accepted the final
manifest. Its offline dry preflight returned:

- decision: `EPIC_WAVE1_INDEX_IMPLEMENTATION_READY`;
- acquisition gate passed: `true`;
- media decoded: `false`;
- artifacts written: `false`; and
- staging tree read: `false`.

This was a contract validation only. Task 162 did not execute an index build.

## Cleanup and custody

After exact final-media hashes, per-source manifests, the root manifest, and
technical evidence were safely written, Task 162 deleted 39 redundant
transfer files totaling 9,649,898,920 bytes: the two initial partials and all
37 chunks. Small response headers, attempt logs, source metadata/license
evidence, technical audit logs, and the two small staging scripts were
retained. No `.part` or `chunk-*.bin` file remains.

Restricted directories are mode `0700`; restricted files are mode `0600`.

## Key artifact SHA-256 values

- `6658c99ccf807c83d9a0fce8509c2643ba13b1434a2309fcf13a4bd4c07b3aad`
  — root acquisition manifest
- `ab9fa24786b86202dff7903601a389a6147f39cef6f4297c4cc696f53500249b`
  — `P28_103` source manifest
- `cccc045f0df226c2b629a8466035148b4df2d5f81388464651976946a06ed524`
  — `P27_101` source manifest
- `31a0eb0bfd3f8343def7d703e666dafe7d2cd5e3388ec2e34a79114954ef7f73`
  — technical audit
- `d414a0a5c79856030f55014da7c183b2b2b9c75a4d9098943d7f5d9d3a6245dc`
  — semantic source inventory
- `1cb1acc06e9e46a5103e8bd701077cf8dd9221d8607270b0877df28509e39525`
  — semantic source-prescreen plan
- `2f12422975447a6a8f185d35449571a2ac2d594e4fdc9fb2adfc86295457fb1a`
  — Task 163 contract-validation record

## Decision

The exact restricted acquisition and technical validation requirements for
these two Wave-1 sources are satisfied.

`EPIC_WAVE1_ACQUISITION_READY`
