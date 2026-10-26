# Rehearsal metadata reconciliation

**Reconciliation date:** 2026-09-07  
**Normative design freeze:** 2026-09-05  
**Claims/evidence cutoff:** 2026-09-06  
**Mode:** metadata only  
**Media downloaded:** false

## Decision

**Metadata reconciliation: conditional pass. Candidate freeze, media transfer,
technical media inspection, content review, and annotation: no-go.** Every
candidate remains `PROVISIONAL_NOT_APPROVED`.

The official release inventory now separates technical access route, rights
status, artifact-license evidence, source-media rights, and episode publication
class. Verified surface facts, source claims, inferences, and unresolved values
are no longer intentionally collapsed. `authorized_acquisition_method` was
renamed to `observed_official_access_route`; only an asset-level acquisition
manifest approved at Stage 2 / Gate A can authorize transfer.

## Fixed findings

| Finding | Reconciliation |
|---|---|
| DXA-002 | LongShOTBench is recorded as public ungated annotations; V-RAGBench is a public card with no usable payload. Annotation/card access is separate from source-media access. |
| DXA-003 | FLARE's CC BY 4.0 card claim and TraceAV's CC BY 4.0 annotation/code statement are recorded with narrow scope; upstream media remain `unknown_hold`. |
| DXA-004 | Full provider revisions are distinguished from short, file-level, compound, and mutable references. Non-full revisions carry `UNRESOLVED_FULL_REVISION` and cannot freeze a candidate. |
| DXA-005 | Stale `hf_recon_absent` and `TBD` funnel values were replaced by official release/item evidence or explicit `UNRESOLVED_*` codes. |
| DXA-006 | The plan and acceptance criteria require 4–5 videos for 12 families under the maximum-three-slots-per-video rule. |
| DXA-007 | Stage 3 technical/media inspection now follows Stage 2 / Gate A, never Stage 1. |
| DXA-011 | Candidate records now include canonical namespace/status, parent asset, lineage relation/evidence, complete-source availability, source-time join, checked-against scope, and dedup disposition. |
| DXA-012 | Slot coverage is labeled `PLANNED_NOT_ACHIEVED`; speech and ambient slots require authorized stream probes and human classification plus source-disjoint reserves. |
| DXA-015 | Unsupported direct mappings were downgraded where exact field paths, timestamp units, joins, or schema fingerprints were absent. |
| DXA-016 / DXA-020 / DXA-024 | Discovery suggestions are separated from executable allowlists. The executable metadata allowlist is empty and no executable media allowlist exists. The package is explicitly non-authorizing. |
| DXA-019 | The 2026-09-05 / 2026-09-06 / 2026-09-07 date semantics are stated explicitly. |
| DXA-021 | Complete-source availability and source-time join status are explicit candidate/funnel fields and unresolved values block authoring. |
| DXA-022 | LongVidSearch preserves 447 reported versus 444 observed; exact released IDs may seed metadata rows, but the population discrepancy blocks population-level assumptions. V-RAGBench stays protocol-only. |
| DXA-023 | Planning documents no longer treat the synthetic LoVR fixture as release evidence; real-release unknown/conflict states remain controlling. No implementation/test file was changed in this task. |
| DXA-026 | Misleading authorization terminology was removed from the release inventory and downstream planning language. |

## Candidate count by resolution level

| Resolution level | Count | Candidate IDs |
|---|---:|---|
| Released annotation-row identity | 2 | `ccp-001`, `ccp-002` |
| Released source-like QA identity | 1 | `ccp-003` |
| Released derived-artifact/source-like identity | 1 | `ccp-004` |
| Released package-item identity | 2 | `ccp-005`, `ccp-006` |
| Official pipeline-filename lead | 1 | `ccp-007` |
| Official per-video filename identity | 3 | `ccp-008`, `ccp-009`, `ccp-010` |
| Asset-freeze-ready complete source | **0** | none |

The pool contains ten concrete metadata identities and zero approved or
source-disjoint complete videos. Dataset-local IDs and distinct duplicate-group
strings are not proof of source disjointness.

## Remaining requirements to select 4–5 source-disjoint videos

For at least four and at most five candidates, all of the following must be
closed without inference:

1. Resolve the exact official dataset/repository and a **full immutable provider
   revision** for every file/row used.
2. Resolve a stable item ID and canonical upstream namespace/ID, including the
   FLARE→Video-MME, LongVidSearch→LoVR→LongVideoBench, and
   TraceAV→mapped-upstream lineage edges.
3. Verify that an authorized rendition is the **complete source**, not an
   annotation-only record, package label, excerpt, reconstructed-only proxy, or
   unidentified alternate encode.
4. Resolve metadata-backed duration to 1,200–5,400 seconds; later confirm the
   duration by an authorized probe.
5. Resolve source-time joins: TraceAV exact nested timestamp fields/units,
   LongVidSearch ordinal slice→LoVR clip→LongVideoBench source seconds, and
   FLARE scene/clip→Video-MME source seconds.
6. Complete cross-dataset duplicate review against every scoped family using
   canonical IDs, URLs/titles/durations, lineage, and—only after authorized
   acquisition—content hashes or robust fingerprints. Select at most one video
   from any earliest-underlying-source group.
7. Obtain an asset-level rights decision covering acquisition, local
   processing, derivatives, annotations, transcripts, raw-media release,
   privacy/safety, and embedded components. Repository/card licenses cannot
   substitute for source-media authority.
8. After Stage 2 / Gate A, acquire only the approved rendition and perform Stage
   3 stream, decode, duration, timestamp, speech, ambient, and subtitle checks.
9. Demonstrate slot feasibility and retain source-disjoint reserves. Four
   videos can supply 12 families only at three families each; with five videos,
   no video may exceed three.
10. Preserve `EXTERNAL_COMPATIBILITY_UNPOOLED` unless a later independent review
    establishes public-core eligibility.

## Unresolved findings and blockers

- No current candidate has a full immutable revision for every bound artifact.
- No candidate has a complete asset-level rights approval.
- No candidate has verified complete-source availability plus a stable
  source-time join.
- No candidate has authorized file-level video/audio probe results.
- Speech, ambient, and cross-modal suitability are hypotheses, not achieved
  coverage.
- Cross-family overlap remains unresolved for TraceAV/OmniVideoBench,
  LongShOTBench, and VES-Bench; FLARE and LongVidSearch family chains are known
  but not fully crosswalked.
- VES-Bench exact rows remain inside a prohibited Parquet payload; V-RAGBench
  exposes no usable row payload; LongShOT row IDs were not fetched.
- Network attempts on 2026-09-07 failed before response bytes because the
  explicitly supplied proxy host did not resolve. The required HF mirror retry
  failed for the same proxy-resolution reason. No remote snapshot was saved.

## Download and annotation authorization state

| Action | State | Controlling condition |
|---|---|---|
| Use existing local metadata for reconciliation | Allowed | Metadata-only; no media interpretation |
| Execute new metadata fetches | Not authorized by current planning documents | Requires exact small-file allowlist, full revision, path, expected bytes/OID, destination, and named approval |
| Download media, clips, archives, Parquet, embeddings, thumbnails, or weights | **NO-GO** | No executable media allowlist; Stage 2 / Gate A not passed |
| Play or technically inspect media | **NO-GO** | Requires transfer authorization for exact asset/rendition, then Stage 3 |
| Review content or annotate real media | **NO-GO** | Requires Stage 3 pass and separate `annotation_approved` decision |
| Publish raw/derived media or annotations | **NO-GO / unresolved** | Requires artifact- and asset-specific release decisions |

No action in the release inventory, discovery plan, candidate pool, or slot
matrix is an authorization grant.
