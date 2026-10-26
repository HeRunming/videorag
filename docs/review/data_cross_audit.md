# Data planning package cross-audit

**Review date:** 2026-09-07  
**Reviewer posture:** independent internal cross-document audit; no web browsing and no network access  
**Scope:** the data-reconnaissance, adapter, rehearsal, and upstream-reproduction artifacts named in Task 26, checked against the project charter, accepted decisions, normative schemas, Pilot-0 plan, and media-v2 gate decision  
**Conflict register:** `docs/review/data_cross_conflicts.csv`

## Executive decision

**Overall: CONDITIONAL PASS for metadata-only candidate resolution; FAIL for candidate freeze, media download, content review, or annotation.**

The package is directionally sound: it consistently treats existing benchmark labels as inputs or seeds rather than AV-TRACE truth, separates compatibility data from the public core, and usually marks media rights and file-level audio as unresolved. The 12-slot design is balanced on paper across modality, hop count, temporal span, intervention mechanism, and alternative-SES requirements.

However, candidate freeze is blocked by five critical findings and multiple high-severity conflicts. The main blockers are wrong configured dataset IDs, a mathematically inconsistent video cap, forced Boolean invention for unknown audio/media facts, inadequate cross-dataset deduplication, and the absence of an implemented acquisition-manifest-to-episode provenance bridge. The rehearsal plan and candidate funnel are also stale relative to the completed 2026-09-07 reconnaissance.

**The current package does not authorize media download. It also does not authorize media playback, content review, annotation, or model execution on real media.** The controlling statements are the charter at `docs/project_charter.md:98-109` and the standing NO-GO at `docs/review/media_v2_gate_decision.md:15-17,57-71`.

## Component verdicts

| Component | Verdict | Basis |
|---|---|---|
| Normative rights and track contract | **PASS** | The charter and decisions clearly require asset-level, fail-closed review and keep external benchmarks unpooled (`docs/project_charter.md:92-109`; `docs/decisions.md:20,30-33`). |
| HF/official-release reconnaissance | **CONDITIONAL PASS** | Strong uncertainty labeling and useful release detail, but some revisions are short/file-level or mutable, count conflicts remain open, and terminology can imply authorization (`docs/data/hf_dataset_recon.md:440-457`; `data/hf_recon/dataset_releases.csv:2-15`). |
| Upstream reproduction audit/components | **CONDITIONAL PASS** | Good separation of code, annotations, and media rights, but its access/license state is stale relative to the later live reconnaissance and many components remain unpinned (`docs/research/upstream_reproduction_audit.md:19-29`; `data/hf_recon/upstream_components.csv:2-25`). |
| Artifact-field mapping | **CONDITIONAL PASS** | The mapping identifies useful seeds and warns against blind label reuse, but several `direct`/`direct_near` statuses exceed the inspected evidence (`data/hf_recon/artifact_field_mapping.csv:3,14,19,35,39,42-44`). |
| Implemented metadata adapter | **FAIL** | Four official release IDs disagree with the verified inventory; unknown audio/license states are not representable without invention; family-specific normalization described in architecture is not implemented (`src/av_trace_data/configs.py:56-66`; `src/av_trace_data/adapters.py:124-143,261-347`). |
| Selection and deduplication | **FAIL** | Deduplication uses an unnamespaced `upstream_id` that may silently fall back to a local ID, so known cross-release lineage cannot be reliably detected (`src/av_trace_data/adapters.py:261-267`; `src/av_trace_data/selection.py:115-126`). |
| Draft acquisition manifests | **CONDITIONAL PASS** | Drafts are correctly `unknown_hold`, but they hard-code verified audiovisual presence and collapse unknown speech/ambient status to false (`src/av_trace_data/manifests.py:64-101`). |
| Download planning/CLI | **CONDITIONAL PASS** | The shipped CLI performs no transfer and validates explicit approval, but the library exposes a backend-capable execution function and the surrounding recommendation document is too operationally worded (`docs/engineering/data_adapter.md:220-250`; `src/av_trace_data/download.py:324-342`). |
| Rehearsal operations plan/funnel | **FAIL** | The plan claims the completed recon is absent, leaves all item IDs/revisions as `TBD`, has a Stage 1/Stage 2 transfer-gate error, and contradicts its own three-slots-per-video cap (`docs/pilot/real_rehearsal_plan.md:26-30,54-57,115-140`). |
| Rehearsal acceptance criteria | **CONDITIONAL PASS** | Strong fail-closed criteria and full-source/SES requirements, but package-level alternative-SES wording can be read as weaker than the frozen slot matrix (`docs/pilot/rehearsal_acceptance_criteria.md:149-183,325-345`). |
| 12-slot coverage design | **CONDITIONAL PASS** | Structurally balanced: 3 slots per modality; 5 one-hop/7 two-hop; 6 near/6 far; 6 per mechanism; 8 requiring an alternative SES. Feasibility is unproven because source audio and source-time evidence remain unverified. |
| Source-schema to AV-TRACE-schema path | **FAIL** | The architecture is plausible, but the implemented candidate/manifests do not produce episode-required stream hashes, source-time evidence, transformations, access class, or mandatory referential checks (`docs/spec/episode_schema.json:99-133,190-208`; `docs/engineering/upstream_ingestion_architecture.md:80-108`). |
| Date handling | **CONDITIONAL PASS** | The dates can be reconciled, but their meanings are not stated package-wide: 2026-09-05 normative freeze, 2026-09-06 evidence cutoff, 2026-09-07 live inspection/preparation. |

## Severity-ranked findings and canonical decisions

The CSV conflict register is authoritative for row-level status, canonical decision, required action, and freeze/download blockers. The most consequential findings are summarized below.

### Critical

1. **DXA-001 — configured release IDs are wrong.** `src/av_trace_data/configs.py:57-63` configures `TechNomad-ds/LoVR`, `FLARE-Benchmark/FLARE`, `MBZUAI/LongShOTBench`, and `buaa-colalab/VES-Bench`, whereas the verified release inventory records `debugger123/LoVR-benchmark`, `AnonymousFLARE/FLARE`, `MBZUAI/longshot-bench`, and `buaaplay/VES-Bench` at `data/hf_recon/dataset_releases.csv:5,9,11`. Because repository equality is enforced at `src/av_trace_data/adapters.py:168-175`, real snapshots from the verified releases would fail or be misattributed. **Canonical decision:** use the verified dataset identifiers; model code repositories separately.

2. **DXA-006 — the 12-family/three-video statement violates the slot cap.** The plan limits a video to three slots but says three videos can provide four families each (`docs/pilot/real_rehearsal_plan.md:54-57`). **Canonical decision:** 12 retained families require at least four source-disjoint videos unless the cap is formally changed.

3. **DXA-008 — unknown media facts are coerced into asserted Booleans.** The adapter requires explicit Boolean audio, defaults missing video to true, and the manifest writes video/audio true while converting unknown speech/ambient to false (`src/av_trace_data/adapters.py:283-286,320-324`; `src/av_trace_data/manifests.py:95-101`). This conflicts with the release inventory, where file-level audio is commonly `unverified`. **Canonical decision:** preserve unknown in reconnaissance and create a normative media assertion only after asset-level verification.

4. **DXA-010 — cross-dataset deduplication is not reliable.** `upstream_id` can fall back to a local `source_id`, and selection deduplicates only the raw string (`src/av_trace_data/adapters.py:261-267`; `src/av_trace_data/selection.py:115-126`). **Canonical decision:** require namespaced upstream identities and an explicit lineage graph, augmented by hashes/fingerprints and human review.

5. **DXA-014 — no implemented bridge reaches the episode schema.** Episode families require content and stream hashes, at least two stream records, source-time intervals, and transformation provenance (`docs/spec/episode_schema.json:99-133,190-208`). The adapter outputs metadata candidates and fail-closed draft manifests only. **Canonical decision:** metadata resolution is permissible; episode/family authoring is not ready.

### High

- **DXA-002 / DXA-003 — stale access and license statements.** The 2026-09-07 live recon supersedes earlier observations about whether LongShOTBench and V-RAGBench are gated and whether FLARE/TraceAV license statements were visible. It does not expand the scope of those licenses to upstream media.
- **DXA-004 — revision evidence is not freeze-grade.** Short SHAs, file revisions, and `main` appear across `dataset_releases.csv` and `upstream_components.csv`; the architecture requires a full immutable revision (`docs/engineering/upstream_ingestion_architecture.md:8,46,60,73`).
- **DXA-005 — rehearsal artifacts are stale.** The plan says recon is absent (`docs/pilot/real_rehearsal_plan.md:26-30`), while the recon exists; all 12 funnel rows still contain `TBD` and stale `hf_recon_absent` reasons (`data/rehearsal_plan/candidate_funnel.csv:2-13`).
- **DXA-007 — transfer gate is misreferenced.** Stage 3 says Stage 1 permits transfer (`docs/pilot/real_rehearsal_plan.md:137-140`), but Stage 2 is the rights/access gate (`115-135`).
- **DXA-009 — the license model cannot represent unknown/conflict.** Inspection rejects missing or non-singular license metadata (`src/av_trace_data/adapters.py:124-143`), although Video-MME, LoVR, VES-Bench, EgoLife, and Ego4D have absent, conflicting, or agreement-based evidence in `dataset_releases.csv:4-7,11-14`.
- **DXA-011 — the funnel lacks dedup evidence fields.** It has no canonical namespace, lineage edge, content hash/fingerprint, or checked-against scope despite requiring duplicate review (`docs/pilot/real_rehearsal_plan.md:65-76,93-94`).
- **DXA-012 — speech/ambient coverage is only hypothetical.** The matrix is balanced, but six speech/ambient slots rely primarily on releases with unverified file-level audio or no hosted media (`data/rehearsal_plan/family_slot_matrix.csv:4-9`; `data/hf_recon/dataset_releases.csv:5,8-11`).
- **DXA-015 — mapping certainty is overstated.** Ordinal slices, uninspected nested timestamp keys, and paper-only Parquet concepts are sometimes marked `direct` (`data/hf_recon/artifact_field_mapping.csv:3,14,19,35,39,42-44`).
- **DXA-016 / DXA-024 — planning language is not a grant.** `recommended_download_plan.md` calls some file fetches immediate and describes a first real rehearsal (`:8-23,44-74`), but the standing gate authorizes review preparation only (`docs/review/media_v2_gate_decision.md:15-17,57-64`).
- **DXA-017 — the library has a transfer-capable seam.** The CLI supplies no backend, but `execute_download_plan` calls a provided backend (`src/av_trace_data/download.py:324-342`). This is a future capability, not present authorization.
- **DXA-018 — acquisition approval is not public-core eligibility.** The manifest schema permits several release decisions to remain prohibited/not-applicable at `acquisition_approved` (`docs/data/acquisition_manifest_schema.json:50-109`), while public-core use has stricter requirements.
- **DXA-020 — several recommendations are discovery tasks, not executable actions.** Mutable or compound revisions, unknown exact paths, and uninspected schemas mean fields must be resolved before an allowlist can be frozen.
- **DXA-021 — complete-source review is not assured.** The acceptance criteria require complete-source alternative search (`docs/pilot/rehearsal_acceptance_criteria.md:149-160`), but several sources expose only clips, IDs, mappings, or unavailable payloads.
- **DXA-022 — unresolved counts/payloads cannot produce frozen candidates.** LongVidSearch remains 447 reported versus 444 observed; V-RAGBench has no item payload or source IDs (`docs/data/hf_dataset_recon.md:237-241,331-338`).
- **DXA-023 — tests are synthetic, not release-conformance evidence.** The LoVR fixture asserts a different namespace, settled license, direct MP4, transcript, and audio facts not established by the real release (`tests_data/fixtures/hf_lovr_snapshot.json:4-18,41-96`).
- **DXA-026 — `authorized_acquisition_method` is misleading.** The inventory field contains technical routes even when rights are unresolved (`data/hf_recon/dataset_releases.csv:1-15`). It must not be treated as a gate decision.
- **DXA-027 — access vocabularies do not align.** Adapter access modes, inventory status, architecture gates/rights, and episode access class are distinct and currently lack a lossless crosswalk.
- **DXA-028 — implementation coverage is narrower than the plan.** V-RAGBench, EgoLife, Ego4D, and OmniVideoBench are absent from `PRIORITY_ADAPTERS`, and the generic adapter does not implement the architecture's source-specific normalization.

### Medium

- **DXA-013 — alternative-SES package wording is weaker than the matrix.** Eight slots require an alternative SES, although the executive/package requirement says only at least one (`docs/pilot/real_rehearsal_plan.md:44-48,226-237`; `docs/pilot/rehearsal_acceptance_criteria.md:325-345`). Every retained required slot must satisfy its own requirement.
- **DXA-019 — date semantics need one explicit convention.** Canonical interpretation: 2026-09-05 = frozen normative design; 2026-09-06 = evidence/claim cutoff; 2026-09-07 = access observation and package-preparation date.
- **DXA-025 — upstream IDs are preserved only indirectly in episodes.** The acquisition manifest must be a mandatory, immutable referential bridge from episode `asset_id`/`manifest_revision` to canonical upstream identity.

## Duplicate-upstream-media assessment

The current package recognizes the major lineage chains but does not operationalize them sufficiently for freeze.

| Family chain | Established relationship | Current risk | Required canonical treatment |
|---|---|---|---|
| FLARE ↔ Video-MME | FLARE reports 399 screened Video-MME sources (`docs/data/hf_dataset_recon.md:102-118`). | FLARE and direct Video-MME candidates can select the same underlying video under different IDs/encodes. | Resolve FLARE parent IDs to a namespaced Video-MME identity; compare exact hashes/fingerprints and rendition lineage before selection. |
| LongVidSearch ↔ LoVR ↔ LongVideoBench | LongVidSearch uses LoVR; LoVR is derived from LongVideoBench (`docs/data/hf_dataset_recon.md:143-178,203-241`). | Three dataset-local IDs may represent one source; reconstructed LoVR full videos may differ bytewise from upstream sources. | Maintain parent-source, segment-of, reconstruction-of, alternate-encode, and excerpt relations; source-disjointness is evaluated at the earliest verified underlying asset. |
| LongShOTBench ↔ Video-MME/YouTube | The package records Video-MME/public-collection and curated YouTube provenance, but lacks a released item-level crosswalk. | Possible overlap with FLARE/Video-MME and other web-derived sets cannot be excluded. | Hold as unresolved until source IDs/URLs and versioned provenance are available; do not rely on dataset-local `video_id` alone. |
| TraceAV-Bench ↔ OmniVideoBench/heterogeneous upstreams | TraceAV publishes a mapping but not canonical media (`docs/data/hf_dataset_recon.md:276-308`). | The same source may appear in other benchmarks or alternate encodes. | Resolve each mapped source to its upstream namespace and rendition; include mapping revision and source hash/fingerprint. |
| TRACE/VES-Bench | Media are hosted, but upstream source identities/provenance are unverified (`docs/data/hf_dataset_recon.md:310-325`). | Cross-benchmark and re-upload duplication is presently unknowable. | No candidate freeze until the Parquet/source mapping exposes stable upstream identity or human provenance review supplies it. |
| V-RAGBench ↔ Ego4D/EgoLife | The card states both upstream families, but current payload has no source IDs (`docs/data/hf_dataset_recon.md:327-366`). | No candidate-level dedup or rights join is possible. | Protocol-only; no candidate rows until exact Ego4D/EgoLife IDs and agreements are available. |

No evidence in the reviewed package establishes that LongShOTBench, TraceAV-Bench, or VES-Bench are disjoint from one another or from Video-MME/LongVideoBench-derived media. Absence of a documented relationship is not evidence of disjointness.

## Schema and field actionability assessment

### What is usable now

The release inventory, field mapping, and upstream component register can support **manual metadata-only candidate resolution** when operators use only fields actually observed at pinned official surfaces. Useful current fields include repository/release locator, observed revision evidence, dataset-local item IDs where present, reported duration, technical access state, and explicit uncertainty notes.

### What cannot be produced without new evidence

The following episode/acquisition fields cannot be safely populated from current reconnaissance alone:

- verified `media.has_audio`, `media.has_speech`, and `media.has_ambient_audio` for most real files;
- `integrity.content_sha256`, acquired byte size, stream hashes, and probed duration;
- episode `source.streams`, `source.content_hash`, and final `access_class`;
- source-time evidence intervals for ordinal-only LongVidSearch/LoVR records and uninspected TraceAV/VES schemas;
- transformation IDs tying reconstructed clips, ASR, subtitles, or generated captions to exact source bytes;
- asset-level rights decisions and public-core release eligibility;
- canonical cross-dataset upstream identities where no crosswalk is released.

Therefore, recommendations that depend on those values are not yet executable. They must be classified as **resolution tasks**, not filled by defaults, aliases, paper claims, or repository-level licenses.

## Rehearsal-slot assessment

The frozen matrix itself genuinely requests all named dimensions:

- **Modalities:** 3 vision, 3 speech, 3 ambient, 3 cross-modal.
- **Hop counts:** 5 one-hop and 7 two-hop.
- **Temporal classes:** 6 near and 6 far.
- **Interventions:** 6 necessity-group withholding and 6 modality-channel outage.
- **Alternative SES:** 8 slots require at least one genuinely distinct alternative SES; 4 require an exhaustive search record even if none exists.

Thus the **design coverage passes**. The **candidate feasibility does not yet pass**. Metadata does not verify usable ambient audio, distinguish speech from ambient audio at file level, establish complete source access, or prove alternative SESs. In particular, LongVidSearch provides ordinal evidence over LoVR, LoVR audio is unverified, VES-Bench is vision-focused, LongShOT has no hosted media/evidence spans, and TraceAV depends on mapped upstream media. The package must report these as hypotheses and maintain rights-cleared substitutes rather than counting a slot as tested before technical and annotation gates.

## Required corrections before candidate freeze

All CSV rows with `blocks_candidate_freeze=yes` must be closed. At minimum:

1. Correct official dataset IDs and split repository-code provenance from dataset-release provenance.
2. Refresh the rehearsal plan/funnel against the completed recon; remove stale absence claims and replace every `TBD` with verified values or explicit unresolved status.
3. Resolve full immutable repository/dataset revisions and exact item IDs; distinguish commit, dataset revision, and file blob/OID.
4. Introduce tri-state unknown handling for video/audio/speech/ambient and conflicting/missing license evidence.
5. Add canonical upstream namespace/ID plus lineage and duplicate-check evidence; cover every known chain listed above.
6. Correct the four-video minimum for a 12-family package under the three-slot cap.
7. Correct the transfer gate sequence so only Stage 2/Gate A can authorize transfer.
8. Downgrade unsupported `direct` field mappings and capture exact schema fingerprints before using them.
9. Define the access-status/rights-status/access-class crosswalk and a separate public-core eligibility gate.
10. Add complete-source availability and source-time mapping requirements to candidate records.
11. Specify the manifest-to-episode referential and transformation bridge and its validator tests.
12. Make every recommendation executable only from a full revision, exact path/item ID, expected size/OID, rights status, and named output record; otherwise label it discovery only.
13. Add schema-faithful fixtures/tests for the canonical releases and for unknown/conflicting states.
14. Align the alternative-SES package criterion with all eight slot-level obligations.

## Can the package proceed to metadata-only candidate resolution?

**Yes, conditionally.** It may proceed to a bounded, human-supervised metadata-only resolution pass that:

- reads the existing internal recon artifacts and already available small metadata;
- resolves canonical release IDs, full immutable revisions, exact item IDs, upstream namespaces/IDs, duration evidence, and lineage;
- preserves unknown/conflicting values without Boolean or license invention;
- updates candidate records only as `PROVISIONAL_NOT_APPROVED` / `unknown_hold`;
- performs no media transfer, playback, probing, content review, or annotation;
- produces no claim that a slot is technically feasible merely from modality labels or generated captions.

The current generic adapter **must not be the sole mechanism** for that pass until DXA-001, DXA-008, DXA-009, DXA-010, and DXA-027 are corrected. Manual reconciliation against the documented release inventory is acceptable as an interim method if every unresolved field remains explicit.

## Authorization statement

**This audit and the reviewed package do not authorize media download.** They also do not authorize subtitle/archive/large-parquet/embedding/model-weight transfer, media playback, content annotation, or execution of an injected `ByteTransferBackend`. A future transfer requires a new asset-level Gate A decision, a schema-valid reviewed manifest for the exact rendition, a frozen plan, and separate explicit execution approval. Real annotation additionally requires `annotation_approved` and the other normative prerequisites.

## Review limits

No web browsing was used because this task was an internal cross-document audit. Consequently, this report resolves conflicts by normative precedence and by the package's own stated live-check dates; it does not independently re-verify external services on 2026-09-07. No reviewed implementation or source-planning artifact was modified.
