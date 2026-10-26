# Remediation integration report

**Date:** 2026-09-07  
**Scope:** integration of Tasks 30–33  
**Network access:** none  
**Media/data transfer:** none

## Outcome

The four remediation workstreams are integrated and the required repository
test suite is green. The integration preserved the stricter fail-closed
controls for unknown metadata, immutable revisions, transfer authorization,
provenance, and release gating.

The software is ready to continue **metadata candidate resolution**, but the
current real candidate pool is not ready for candidate freeze, media download,
or annotation.

## Initial validation

The exact required command was run before integration edits:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
python -m pytest \
  tests tests_mvp tests_media tests_agent_runtime \
  tests_validation tests_media_pipeline tests_data \
  -q -o addopts=''
```

Initial result:

```text
228 passed, 32 subtests passed in 269.44s (0:04:29)
```

There were no failing tests at integration start. The audit nevertheless found
interface and coverage gaps that could allow the parallel workstreams to
diverge in production even though their individual tests passed.

Git status/diff inspection was unavailable because the supplied `.git`
directory does not contain usable repository metadata. File-content,
timestamp, test, parser, import, and artifact checks were used instead.

## Integration findings, root causes, and fixes

### 1. Public package API was incomplete

**Root cause:** Tasks 31 and 33 added public download, approval, audit, and
provenance APIs in parallel, but `src/av_trace_data/__init__.py` exported the
provenance additions and only part of the download surface. In particular,
`ApprovalSignatureVerifier`, `ResolvedDownload`, `load_approval`,
`append_audit_log`, `audit_event`, and `verify_audit_log` were absent from the
package root.

**Fix:** Exported the integrated public API from `av_trace_data` and added a
regression test that checks these package-level symbols.

### 2. Selection artifacts did not natively retain inspection snapshot hashes

**Root cause:** The download planner preserved and validated snapshot hashes
when present, but the selection API/CLI did not carry the
`InspectionResult.snapshot_sha256` values into the version-2 selection
artifact. As a result, normal CLI output reached download planning without an
available source-snapshot binding.

**Fix:**

- Added an optional, validated `source_snapshots` mapping to
  `select_candidates`.
- Added the mapping to the selection body before `selection_sha256` is
  computed.
- Updated `select_rehearsal_candidates.py` to collect each input inspection's
  snapshot hash under a provider/repository/revision key and pass it into
  selection.
- Rejected empty source keys, malformed SHA-256 values, and conflicting hashes
  for the same inspection source.
- Added selection and CLI regression tests.

This makes the ordinary inspection → selection → download-plan path bind every
available local source snapshot without making up a hash when no inspection
artifact exists.

### 3. Provenance identity comparison conflicted with adapter serialization

**Root cause:** Task 30 defines a candidate's canonical identity as the
namespaced value `upstream_namespace:upstream_asset_id`, and manifest drafting
writes that value to `source.source_identifier`. The Task 33 bridge instead
compared:

- `canonical_upstream.namespace` to the manifest's local `dataset_id`; and
- `canonical_upstream.asset_id` to `source.source_identifier`.

That worked for the older synthetic fixture, where namespace and local dataset
ID happened to be the same and the source identifier was unnamespaced, but it
would reject manifests produced by the updated adapter path.

**Fix:** The bridge now accepts the canonical Task 30 representation only when
`source.source_identifier` exactly equals
`namespace:asset_id`. It retains safe compatibility for the prior schema-valid
split representation only when `manifest.dataset_id` exactly equals the
namespace and the manifest source identifier exactly equals the asset ID. It
does not infer a namespace from an unrelated local dataset ID. Positive and
mismatch tests were added.

### 4. Audit append did not reapply secret checks to existing chain entries

**Root cause:** `verify_audit_log` rejected sensitive fields in existing
records, and new events were checked before append, but the append-time
locked-chain verification did not call the sensitive-field checker on old
records. A correctly rehashed legacy record containing secret-shaped data
could therefore receive another record through the append API.

**Fix:** Reapplied recursive sensitive-field validation to every pre-existing
record while the log is locked and before append. Added an adversarial test
using a correctly hashed legacy record containing an authorization header.

### 5. Engineering documentation lagged the integrated contracts

**Root cause:** Task ownership kept the download controls out of the adapter
engineering document and the verified-asset handoff out of the ingestion
architecture document.

**Fix:**

- Documented selection version 2 source-snapshot binding, download plan version
  2 controls, signer/staging-root requirements, hash-chained audit logs, and
  the absence of a concrete transfer backend in
  `docs/engineering/data_adapter.md`.
- Kept the `VerifiedAssetRecord` contract in the Task 33 semantic
  specification and review rather than changing the Task 32 planning
  artifacts during integration.

## Interface verification

The integrated behavior was checked as follows:

- Candidate serialization preserves tri-state video/audio/speech/ambient
  values, license-evidence arrays and resolution status, namespaced upstream
  identity, lineage, technical access, rights status, and episode class.
- Selection version `2.0` hashes its complete body, including exact normalized
  candidates and available source snapshot bindings.
- Download plan version `2.0` binds the complete verified selection artifact,
  policy/summary hashes, snapshot hashes, exact candidate records, manifests,
  byte limits/ranges, canonical URLs, destinations, and full immutable
  revisions.
- Executable planning and execution continue to require full 40- or 64-hex
  revisions. Legacy mutable/short revisions remain metadata-only and cannot
  cross the transfer boundary.
- Manifest drafting refuses unknown normative media fields and does not promote
  release-level license evidence into asset-level rights approval.
- Audit records remain hash-chained, sequence-bound, and secret-rejecting.
- `public_core_release` and
  `external_compatibility_unpooled` remain distinct. The legacy
  `public_release` spelling remains an alias with public-core requirements; it
  does not collapse the compatibility profile.
- `validate_family(..., verified_asset=...)` invokes bridge referential checks
  in addition to the annotation manifest gate.

## Validation results

### Focused integration tests

```text
56 passed, 23 subtests passed in 2.53s
```

This covered selection/manifests, CLI propagation, download planning and
authorization, adversarial security checks, audit logs, and the provenance
bridge.

### Final exact full suite

The exact required command was rerun after all fixes:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
python -m pytest \
  tests tests_mvp tests_media tests_agent_runtime \
  tests_validation tests_media_pipeline tests_data \
  -q -o addopts=''
```

Final result:

```text
234 passed, 38 subtests passed in 270.48s (0:04:30)
```

### Imports, syntax, and planning artifacts

- Parsed all 106 Python files in the requested source/script/test trees with
  `ast.parse`.
- Imported all seven package roots successfully.
- Verified the integrated `av_trace_data.__all__` surface.
- Parsed 37 JSON files.
- Parsed 14 CSV files and verified uniform row widths.
- Verified all 15 local evidence entries in
  `metadata_snapshot_manifest.json` against exact byte sizes and SHA-256
  hashes.
- Confirmed `media_downloaded: false`, an empty remote-artifact list, and all
  prohibited-payload flags false.
- Removed generated `__pycache__`/`.pyc` files after checks.

## Security and artifact assertions

- No concrete `ByteTransferBackend` subclass exists under shipped `src/` or
  `scripts/`.
- No network transfer primitive was found in shipped Python source/scripts.
- The download CLI explicitly calls `execute_download_plan(..., backend=None)`;
  successful authorization therefore remains `authorized_not_executed` with
  `network_access_performed: false`.
- Unknown media, unresolved/conflicting identity, unresolved rights, missing
  sizes, mutable revisions, and insufficient gate decisions remain blocked.
- No media, archive, Parquet, embedding, thumbnail, model-weight, NumPy payload,
  or similar prohibited artifact was created during the remediation window.
- No network access or data download was performed by this integration task.

## Unresolved scientific and data issues

The integration did not alter source-research conclusions, candidate facts, or
rights decisions. The following blockers remain:

1. The real pool has ten concrete metadata identities but **zero**
   asset-freeze-ready complete sources.
2. Full immutable revisions are unresolved for every artifact chain needed to
   freeze 4–5 source-disjoint videos.
3. No real candidate has complete asset-level rights approval covering
   acquisition, processing, derivatives, annotations, transcripts, raw media,
   privacy/safety, and embedded components.
4. Complete-source availability and exact source-time joins remain unresolved.
5. No authorized file-level stream, decode, duration, speech, ambient, or
   subtitle probe has been performed.
6. Modality/slot coverage is planned rather than demonstrated.
7. Cross-dataset identity and duplicate resolution remains incomplete for the
   scoped source families.
8. LongVidSearch still has the reported 447 versus observed 444 population
   discrepancy.
9. VES-Bench exact rows remain in a prohibited Parquet payload; V-RAGBench
   remains protocol-only; LongShOT exact released row IDs remain unresolved.
10. No real verified-asset bridge records can be produced until exact approved
    bytes and probe results exist.

## Readiness decision

| Milestone | Decision | Reason |
|---|---|---|
| Continue metadata candidate resolution | **READY** | Implementation, tests, planning formats, and metadata integrity checks are coherent. |
| Metadata candidate freeze | **NOT READY** | Zero complete sources satisfy immutable revision, identity, complete-source, time-join, dedup, and rights requirements. |
| Media download | **NO-GO** | No executable media allowlist, no approved real acquisition manifest, and no shipped transfer backend. |
| Annotation | **NO-GO** | Requires approved acquisition, verified local bytes/streams, a valid bridge record, Stage 3 checks, and an annotation gate pass. |
