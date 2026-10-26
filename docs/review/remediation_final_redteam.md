# Final independent red-team of remediation

**Review date:** 2026-09-07  
**Reviewer posture:** independent/adversarial; Tasks 30–34 were not implemented by this reviewer  
**Network/media activity:** none; no browsing and no downloads  
**Finding register:** `docs/review/remediation_final_findings.csv`

## Executive decision

**Software remediation is materially improved but not ready to authorize real
download or real annotation.**

The exact required suite is green:

```text
234 passed, 38 subtests passed in 265.00s (0:04:25)
```

That result supports continued offline metadata resolution. It does **not**
resolve dataset facts, source-media rights, gated-access scope, complete-source
availability, cross-dataset identity, or stream/evidence facts. It is therefore
not permission to request gated media, download 3–5 videos, inspect/play real
media, or annotate it.

Of the 12 Critical findings re-tested:

- **5 CLOSED:** DXA-001, DXA-006, DXA-008, DXA-010, and RT-035. DXA-010 is
  closed as an implementation defect, while current candidates remain unproven
  source-disjoint because the required real crosswalk evidence is absent.
- **1 PARTIALLY_CLOSED:** DXA-014. A strong verified-asset bridge exists, but it
  is optional in family validation and accepts mutable canonical/source
  revisions.
- **6 OPEN dataset/rights findings:** RT-001, RT-005, RT-021, RT-024, RT-028,
  and RT-032. These are not cured by code because the missing evidence or rights
  grants still do not exist in the local package.

There were no Critical findings classified `NOT_APPLICABLE_TO_CODE`; the
dataset/rights findings remain applicable to project readiness even when their
ultimate closure requires external evidence rather than a code patch.

## Scope and method

The review examined the required cross-audit, red-team, remediation, planning,
implementation, test, and documentation artifacts. Because the supplied
`.git` directory is not usable repository metadata, exact Task 30–34 diffs
could not be reconstructed with Git. Scope was reconstructed from report
references, file contents, modification times, tests, and the post-remediation
artifact manifest. This limitation is recorded as `NEW-007`.

The review:

1. mapped and re-tested the five Critical cross-audit findings and seven
   Critical red-team findings;
2. inspected every security/semantic area named in Task 35;
3. ran the exact full suite;
4. ran additional in-memory and temporary-directory adversarial probes without
   changing implementation or tests;
5. parsed all current CSV/JSON artifacts under `data`, `docs`, and `mvp`;
6. verified the local metadata snapshot manifest; and
7. scanned the tree for prohibited payload types and concrete network-transfer
   primitives.

## Critical finding dispositions

### Cross-audit Critical findings

| Finding | Status | Red-team conclusion |
|---|---|---|
| DXA-001 — wrong configured release IDs | **CLOSED** | The four official dataset IDs are corrected, code repositories are separate provenance, and fixtures exercise each corrected ID. |
| DXA-006 — three-video/four-family arithmetic conflict | **CLOSED** | The plan now requires 4–5 source-disjoint videos and a maximum of three slots per video. The eventual package certifier still needs to enforce the rule. |
| DXA-008 — unknown media facts coerced to Booleans | **CLOSED** | Video/audio/speech/ambient are tri-state in candidates; selection rejects required unknowns; manifest drafting refuses unknown normative assertions. |
| DXA-010 — unnamespaced/non-lineage dedup | **CLOSED** for implementation | Namespaced identities, explicit parent edges, union-find lineage components, hashes, and reviewed fingerprints are supported. Current real rows still lack enough crosswalk evidence, so candidate freeze remains blocked by facts rather than this code defect. |
| DXA-014 — no manifest-to-episode bridge | **PARTIALLY_CLOSED** | The bridge is implemented and well tested, but `validate_family` still accepts real-shaped families when `verified_asset` is omitted. A consistent stream-hash tamper also passed without the bridge. The bridge separately accepted canonical/source revision `main`. |

### Red-team Critical findings

| Finding | Status | Red-team conclusion |
|---|---|---|
| RT-001 — FLARE license treated as Video-MME media authority | **OPEN** | Planning now correctly holds the assets, but no asset-level sublicense or authority was added. |
| RT-005 — LoVR license known and consistent | **OPEN** | The conflict is now represented correctly; it is not resolved. |
| RT-021 — VES hosting proves authority | **OPEN** | Official ID handling improved, but immutable release/source provenance and media rights remain absent. |
| RT-024 — V-RAGBench is executable metadata | **OPEN** | Correctly classified protocol-only; there is still no usable immutable row payload. |
| RT-028 — EgoLife license scope is uniform | **OPEN** | Correctly restricted/manual; the artifact-by-artifact license and participant-media scope conflict remains unresolved. |
| RT-032 — minimal V-RAGBench/Ego4D request is possible | **OPEN** | Exact Ego4D UIDs and a pinned mapping remain unavailable; no request should be made. |
| RT-035 — configured IDs match official releases | **CLOSED** | Same code/evidence closure as DXA-001. |

## Required area review

### Tri-state media semantics

**Pass.** `NormalizedCandidate` preserves `True`, `False`, or `None` for
video/audio/speech/ambient. Adapters no longer invent video or audio presence.
Selection reports `video_unknown`/`audio_unknown`, and manifest drafting rejects
unknown values rather than mapping them to false.

### License evidence and conflict handling

**Pass as a software representation; unresolved as dataset rights.** Multiple
evidence records and `consistent`/`unresolved`/`conflicting` states are
preserved. A release/card statement is not promoted into an asset-level grant.
FLARE, LoVR, VES-Bench, and EgoLife still lack the external facts needed for
approval.

### Official repository configuration

**Pass.** The four audited mismatches are corrected and distinct code
repositories are modeled separately. Manual/protocol-only targets cannot be
instantiated as active adapters.

### Namespaced lineage-aware deduplication

**Pass in code; not demonstrated on the real pool.** Local IDs no longer become
guessed upstream identities. Explicit lineage nodes are transitively unioned,
and exact hashes or reviewed fingerprints add duplicate evidence. All current
planning candidates still say `HOLD_NOT_PROVEN_SOURCE_DISJOINT`.

### Selection/snapshot binding

**Partial.** The ordinary CLI requires each inspection's `snapshot_sha256` and
includes it in selection version 2. However, the library accepts
`source_snapshots={}` and the resulting plan is still executable. The frozen
plan then contains an empty snapshot-hash list. This is `NEW-005`.

### Immutable revision validation

**Partial.** The transfer boundary correctly rejects branches, short hashes,
ref expressions, and composite revisions, and checks URL/revision equality.
Adversarial probes found that inspection, selection, metadata manifest
drafting, and the verified-asset bridge accept short or mutable revisions.
Specifically:

- a local inspection with revision `abcdef1` was selected and drafted into a
  metadata manifest; and
- `validate_verified_asset_record` accepted canonical/source revision `main`
  and allowed episode-source conversion.

This is `NEW-001` and blocks freeze/annotation even though download planning
would later reject the same revision.

### URL and destination safety

**Mostly fail-closed, with a residual canonicalization gap.** The planner
rejects HTTP, credentials, non-default ports, fragments, unapproved hosts,
private literal IPs, direct dot-segments, encoded `/` or `\`, queries,
destination escapes, and collisions. It binds known provider URL structures to
the exact revision.

Additional probes were accepted for:

- `%252e%252e` path segments;
- `%252f` nested encoded separators;
- `%00` in a path; and
- a path shaped as `file.mp4/extra`.

No request was made, but these demonstrate that planner canonicalization is not
fully equivalent to every possible provider/proxy decode path. This is
`NEW-006`.

### Approval authenticity and freshness

**Freshness passes; authenticity remains incomplete.** Exact plan hash, ordered
asset IDs, signer/role membership, strict UTC time, maximum age, future skew,
and exact attestation are enforced. Detached signatures are supported when a
trusted verifier is provided.

An unsigned approval nevertheless passed with only an independently supplied
JSON signer/role map. The shipped CLI has no signature verifier or authenticated
approval-service integration. This verifies authorization data consistency,
not the human signer's identity. This is `NEW-002`.

### Audit-chain integrity

**Partial.** Content edits, reordering, malformed records, truncated final
lines, and secret-shaped data are rejected, including secret-bearing legacy
entries during append. An adversarial valid-suffix deletion was accepted:
after two records were written, deleting the complete second line caused
`verify_audit_log` to report a valid one-record chain. This known limitation is
`NEW-003`.

### Backend attestation

**Not sufficient for a real backend.** The validator checks a broad attestation
schema. But a fake backend returning self-consistent fields caused
`execute_download_plan` to return `executed` and
`network_access_performed: true` even though the destination file did not
exist. The current code validates claims from the backend rather than
independently verifying transfer effects. No concrete backend ships, so the
current CLI remains no-download; enabling one is blocked by `NEW-004`.

### Verified-asset to episode conversion

**Strong implementation, incomplete enforcement.** The converter binds the
whole manifest hash, manifest asset/revision, namespaced upstream identity,
rights decision, acquired content hash/duration, stream hashes,
transformations, and source-time mappings. It cleanly separates public-core
and restricted compatibility. The bypass is that callers may omit the record:

```text
validate_family(positive_family, positive_manifest) -> ok
consistent source/evidence stream-hash tamper without verified_asset -> ok
```

Real-media validation and freeze must require the bridge rather than expose it
as an optional strengthening.

### Public-core versus restricted compatibility profiles

**Pass.** Public core requires `public_release_approved`, all six release
decisions allowed, public-release rights status, and
`public_core_redistributable`. Restricted compatibility can pass the explicit
unpooled profile with restricted decisions, but cannot pass public core.
Backend tracks are also checked against episode access class.

## Test and probe results

### Exact required full suite

Command:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
python -m pytest \
  tests tests_mvp tests_media tests_agent_runtime \
  tests_validation tests_media_pipeline tests_data \
  -q -o addopts=''
```

Result:

```text
234 passed, 38 subtests passed in 265.00s (0:04:25)
```

### Additional adversarial probes

All probes were local and used existing fixtures or temporary files.

| Probe | Result |
|---|---|
| Short revision through inspection → selection → draft manifest | **Accepted** (`abcdef1`) |
| Executable selection/plan with no source snapshot hashes | **Accepted**, `source_snapshot_sha256s=[]` |
| Unsigned approval with local signer/role allowlist | **Accepted** as `authorized_not_executed` |
| Delete valid final audit record | **Accepted** as a valid shorter chain |
| Fake backend attests success without creating destination | **Accepted** as `executed` |
| Verified-asset canonical/source revision set to `main` | **Accepted** |
| Double-encoded traversal/separator and encoded NUL URL paths | **Accepted** |
| Family validation without bridge, including consistent stream-hash tamper | **Accepted** |

These results do not negate the green regression suite; they identify controls
not represented by the existing tests.

## Planning-artifact and prohibited-file checks

- Parsed **529 JSON** files under `data`, `docs`, and `mvp`: no parse errors.
- Parsed **29 CSV** files under the same roots: no parse errors or row-width
  mismatches.
- Recomputed all **15** local entries in
  `data/rehearsal_plan/metadata_snapshot_manifest.json`: all byte sizes and
  SHA-256 values matched.
- The snapshot manifest reports `media_downloaded: false`, an empty
  `fetched_remote_artifacts` list, and all prohibited-payload flags false.
- The tree contains **10 pre-existing synthetic MP4 fixtures/generated files**,
  all dated September 5–6, 2026. No media, archive, shard, embedding, model,
  or similar prohibited file had a September 7, 2026 modification time.
- No concrete request/socket/download primitive or concrete
  `ByteTransferBackend` implementation was found in shipped `src` or `scripts`.
- Test-created `__pycache__`/`.pyc` artifacts were removed after the checks.

Because Git metadata is unusable, “not added by Tasks 30–34” is supported by
timestamps and the artifact manifest, not by a version-control diff.

## Readiness by milestone

| Milestone | Decision | Software readiness | Dataset facts/rights |
|---|---|---|---|
| Continued metadata resolution | **READY, offline/local only** | Adapters, tri-state records, conflict representation, lineage fields, and parsing are suitable for continued local reconciliation. | New metadata fetches are not authorized by the current package; use existing local evidence unless a separate small-file metadata approval is created. |
| Metadata candidate freeze | **NOT READY** | Freeze controls need mandatory snapshot coverage, immutable revisions at all promotion/bridge boundaries, and mandatory verified-asset use for real families. | Zero candidates have complete source identity, source-time join, proven source-disjointness, streams, and asset-level rights. |
| Request for gated access | **NOT READY / NO-GO for a media request** | Manual/protocol states correctly prevent accidental adapter execution. | Exact asset/UID lists, minimum scope, pinned release versions, agreement terms, purpose, storage/retention, and rights/privacy review are missing—especially for V-RAGBench/Ego4D and mapped OmniVideoBench routes. |
| Download of 3–5 real videos | **NO-GO** | No concrete backend ships; approval authenticity, audit checkpointing, backend trust, URL normalization, and snapshot coverage require closure before enabling one. | No executable media allowlist or approved real acquisition manifests exist; current rights remain unresolved. |
| Real annotation | **NO-GO** | Real-family validation must require an immutable verified-asset bridge and later backend/trajectory certification. | No approved acquired bytes, stream probes, source-time mappings, complete-source review, privacy review, or `annotation_approved` assets exist. |

## Final conclusion

Tasks 30–34 successfully repaired the most dangerous representation errors:
official repository identity, tri-state media semantics, license conflicts,
lineage-aware deduplication, fail-closed rights separation, and the core
verified-asset bridge. The full suite passes.

The remediation is **sufficient for continued local metadata resolution**.
It is **not sufficient for candidate freeze, gated-media requests, download,
or annotation**. The most important software follow-ups are mandatory
immutable revision validation and bridge enforcement, authenticated approvals,
externally checkpointed audit chains, and a trusted end-to-end transport
implementation. Independently, the controlling dataset and rights facts remain
unresolved. Passing tests cannot substitute for those facts or grant
permission.
