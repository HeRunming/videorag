# EPIC P23_102 parallel range acquisition

**Date:** 2026-10-13  
**Scope:** exact acquisition accelerator for the single official
`P23/videos/P23_102.MP4` object.

## Purpose

`tools/epic_p23_102_parallel_acquisition.py` accelerates the remaining transfer
without changing the canonical resumable staging file during acquisition. It
uses a short edge range followed by fixed 64 MiB grid ranges, downloads them
concurrently into individually named files, and records crash-resumable state
in an atomic manifest.

The existing exact-acquisition implementation remains the authority for:

- frozen source/evidence and rights checks;
- exact byte count;
- official MD5 and local SHA-256;
- ffprobe stream and duration validation;
- final manifests/reports; and
- atomic promotion of the canonical staging file to final media.

The new tool imports and calls those validation/finalization functions only
after a separate assembly phase has constructed the exact canonical staging
file.

## Fixed identity

| Field | Value |
|---|---|
| Asset | `P23_102` |
| Expected bytes | `10814161307` |
| Official MD5 | `4698fcbf13782f6396029761eb3bd5f2` |
| Expected ETag | `"5ea771bb-28493019b"` |
| Fixed segment grid | `67108864` bytes (64 MiB) |
| Default concurrency | `8` |
| Proxy order per attempt round | `https://proxy.example.invalid:3128`, then `https://proxy.example.invalid:3128` |

## Files

The canonical resumable prefix remains:

```text
data/restricted/epic_p23_102_source_v1/staging/P23_102.MP4.part
```

Parallel state is isolated under:

```text
data/restricted/epic_p23_102_source_v1/staging/parallel_segments/
```

Segment names encode exact inclusive byte bounds:

```text
P23_102.MP4.bytes-000134217728-000201326591.segment
```

The crash-resumable manifest is:

```text
data/restricted/epic_p23_102_source_v1/staging/parallel_segments/manifest.json
```

Directories are mode `0700`; segment, manifest, lock, journal, staging, and
media files are mode `0600`.

## Safety model

### Prefix gate

Before planning or acquisition, an existing canonical staging file must be:

1. a regular non-symlink file;
2. no larger than the frozen expected size; and
3. readable as an exact prefix whose current length and SHA-256 can be
   snapshotted.

An incomplete prefix may have any byte length. Its first pending segment starts
exactly at that length and ends immediately before the next fixed 64 MiB grid
boundary (or at EOF). Every later segment begins on the fixed grid. For
example, a prefix ending at byte offset `70 MiB` produces a first range from
`70 MiB` through `128 MiB - 1`, followed by the normal `128–192 MiB` range.

The manifest records the exact planning prefix length, SHA-256, and a derived
identity. Every segment record is bound to that prefix provenance. A later
acquisition may reuse a fixed-grid segment only when the canonical file still
has the exact provenance prefix as its leading bytes. A conflicting
same-range record is discarded and replanned instead of being silently reused.

### Acquisition isolation

`--acquire` never opens the canonical staging file for writing. It snapshots
its current length and SHA-256, creates the edge range plus all remaining
fixed-grid range records, and downloads only to per-range temporary files and
final segment files.

Consequently, `--acquire` may run while the existing sequential downloader is
active. If the sequential downloader subsequently advances the prefix,
already downloaded ranges wholly covered by the longer prefix are skipped.
If the longer prefix stops inside a downloaded segment, assembly rejects the
partial overlap rather than slicing or appending a suffix from that stale
segment. A new acquisition from the longer prefix creates the exact edge range
needed to rejoin the fixed grid.

### Locks

The parallel tool takes an exclusive advisory `flock` on:

```text
staging/.parallel_acquisition.lock
```

This prevents two parallel acquisition/assembly invocations from running at
the same time. The lock file may persist, but only the held `flock` denotes an
active process; this avoids stale PID-file deadlocks after crashes.

Assembly additionally creates the existing exact tool's canonical lock with
`O_EXCL`:

```text
staging/.acquisition.lock
```

If the sequential downloader holds or has left that path, assembly refuses to
run. The parallel tool removes only the canonical lock that it successfully
created itself. Acquisition does not create or remove this canonical lock.

### Strict HTTP acceptance

Every segment must satisfy all of the following:

- curl exits successfully;
- the response carrying `Content-Range` is HTTP `206`;
- `Content-Range` start and end exactly equal the requested inclusive bounds;
- the total equals `10814161307`;
- `Content-Length` exists and equals the requested range length;
- the output file size equals the requested range length;
- `Content-Type` is `video/mp4`;
- ETag exists and equals the frozen expected ETag; and
- every accepted segment has the same manifest object ETag.

Partial bodies are never accepted as segments.

### Retry and proxy policy

For each segment, each bounded attempt round tries:

1. `https://proxy.example.invalid:3128`
2. `https://proxy.example.invalid:3128`

The number of rounds, connect timeout, and total request timeout are bounded
and configurable. Failed temporary bodies are removed. Each attempt appends a
record to the existing restricted range-attempt journal.

### Crash-resumable manifest

Manifest updates are written to a temporary mode-`0600` file, fsynced,
atomically renamed, and followed by a directory fsync. Segment commit uses:

1. strict response validation;
2. temporary-body fsync;
3. SHA-256 calculation;
4. manifest state `committing`;
5. atomic rename to the deterministic segment name;
6. segment-directory fsync; and
7. manifest state `complete`.

On restart, a `committing` record whose segment exists with exact size, ETag
metadata, and matching SHA-256 is reconciled to `complete`. A recorded complete
segment that is missing becomes pending. Wrong-sized or digest-mismatched
segments are rejected rather than silently reused. Manifest schema `2.0`
requires prefix provenance on every range, so schema `1.0` manifests cannot be
mixed with the arbitrary-prefix layout.

### Disk-space gates

Acquisition requires free space for all missing segment bytes plus a 1 GiB
margin. Assembly separately requires space for the bytes still to append to
canonical staging plus a 1 GiB margin.

This is deliberately conservative: acquisition preserves segment files after
assembly for audit/resume purposes.

## Atomic assembly phase

`--assemble` performs no network acquisition. It requires:

1. the parallel lock;
2. successful creation of the canonical exact-tool lock;
3. a valid existing segment manifest;
4. a valid current canonical prefix of any length;
5. prefix-provenance-compatible, contiguous complete segment coverage from
   that exact byte through EOF;
6. matching exact segment sizes, SHA-256 values, and ETags; and
7. adequate disk space.

Assembly selects records by exact next start offset. Records ending before the
current canonical prefix are safely ignored. A record crossing the current
prefix is a stale partial overlap and is rejected; assembly never slices a
segment. This preserves exact inclusive range boundaries while allowing the
sequential downloader to grow canonical staging between parallel acquisition
and assembly.

Segments are appended in ascending byte order. Before each append, the
manifest stores an `appending` checkpoint with the last stable prefix. The
append is fsynced, its streamed SHA-256 is compared again to the manifest
digest, and the checkpoint advances only after success.

If a write or source-read failure occurs, the canonical file is immediately
truncated back to the segment's stable start and fsynced. If the process is
killed before that rollback, the next `--assemble` sees the `appending`
checkpoint and truncates the incomplete append before validating the prefix.
The checkpoint may itself be at an arbitrary byte offset. Thus segment-level
appends are restart-safe even though an append itself is not a filesystem
rename.

After exact EOF is reached, assembly reuses the existing exact tool to:

1. verify evidence and frozen identity;
2. compute exact MD5 and SHA-256;
3. require the official MD5;
4. atomically rename canonical staging to final media;
5. run ffprobe and enforce the established stream gates; and
6. write the canonical validation, provenance, manifest, review, and result
   outputs.

If an exact final media file already exists, `--assemble` skips canonical
append and reuses the exact tool's full validation path.

## Commands

Plan only; this performs no transfer and writes no state:

```bash
python tools/epic_p23_102_parallel_acquisition.py --plan-only
```

Acquire missing segments with defaults:

```bash
python tools/epic_p23_102_parallel_acquisition.py --acquire
```

Acquire with explicit bounds:

```bash
python tools/epic_p23_102_parallel_acquisition.py \
  --acquire \
  --concurrency 8 \
  --attempt-rounds 3 \
  --connect-timeout 20 \
  --max-time 600
```

After the sequential exact downloader has stopped and
`staging/.acquisition.lock` is absent, assemble and run exact validation:

```bash
python tools/epic_p23_102_parallel_acquisition.py \
  --assemble \
  --ffprobe "$(command -v ffprobe)"
```

Tests and lint:

```bash
pytest -q tooling/tests/test_epic_p23_102_parallel_acquisition.py
pytest -q \
  tooling/tests/test_epic_p23_102_exact_acquisition.py \
  tooling/tests/test_epic_p23_102_parallel_acquisition.py
ruff check \
  tools/epic_p23_102_parallel_acquisition.py \
  tooling/tests/test_epic_p23_102_parallel_acquisition.py
```

## Operational cautions

- Do not run `--assemble` while the sequential exact downloader is active.
  The lock check enforces this.
- Do not manually concatenate segment files.
- Do not delete or edit the manifest independently of segment files.
- Do not treat `EPIC_P23_102_PARALLEL_SEGMENTS_READY` as final media
  completion. Only successful assembly and exact validation emit
  `EPIC_P23_102_PARALLEL_ACQUISITION_READY`.
- No live download is performed by the test suite or by `--plan-only`.
