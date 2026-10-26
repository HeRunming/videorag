# Minimal upstream ingestion architecture

**Status:** proposed engineering design, derived from the upstream audit dated 2026-09-07.
**Non-goal:** this design does not authorize or perform media transfer.

## Design rules

1. Pin every repository/dataset to an immutable revision before parsing.
2. Keep repository/code license, annotation license, model license, and source-media rights as separate records.
3. Preserve upstream payloads losslessly while mapping stable fields into a common schema.
4. Use seconds only as a presentation layer; retain original time base and decoded PTS for all media-derived artifacts.
5. Isolate external services behind interfaces and log model/checkpoint, prompt hash, decoding parameters, request ID, and response hash.
6. Never load upstream pickle files, execute upstream shell scripts, or resolve platform URLs during metadata inspection.
7. All ingestion is two phase: `recon` creates immutable metadata plans; `materialize` exists only after rights and transfer approval.

## Pipeline

```text
OfficialSourceLocator
  -> RevisionResolver
  -> MetadataSnapshotter (text/JSON/parquet schema only)
  -> SourceFamilyAdapter
  -> NormalizedRecords + source_payload
  -> Referential/temporal/schema validation
  -> Rights & privacy gate
  -> TransferPlan (still no bytes)
  -> [separate approved process] MediaMaterializer
  -> StreamProbe -> DerivativeBuilder -> QA/Evidence validators
  -> Versioned AV-TRACE package
```

### 1. Official source locator

Input is a reviewed registry entry, never a search result at runtime:

```yaml
source_key: longvidsearch
repository_url: https://github.com/yrywill/LongVidSearch
repository_revision: <40-hex-sha>
dataset_url: null
dataset_revision: null
accessed_at: 2026-09-07
allowed_hosts: [github.com, raw.githubusercontent.com]
```

The resolver rejects `main`, `master`, `HEAD`, `latest`, short SHAs in final manifests, redirects to unapproved hosts, and missing access/license evidence.

### 2. Metadata snapshotter

Allowed objects before approval:

- repository metadata, tree listing, README, LICENSE, dependency/config/source text;
- HF dataset card, `dataset_info`, sibling names, file sizes, LFS OIDs, parquet schema/statistics if available without downloading rows;
- paper/project HTML and small JSON examples.

Denied by default:

- video/audio/subtitle archives, large parquet shards, model weights, embedding arrays, pickle files, and scripts that make secondary network calls.

Every snapshot records URL, resolved revision, ETag/OID where available, byte count, SHA-256, MIME type, access time, and command/tool version.

Snapshot assertions are typed as `verified_fact`, `source_claim`, `inference`,
or `unresolved`. A mapping is `direct` only when an inspected serialized field
path, units/semantics, and schema fingerprint are bound to a pinned revision.

## Common normalized schema

Use newline-delimited JSON or Parquet tables with stable IDs. Raw upstream fields live under `source_payload_json` so an adapter upgrade is lossless.

### `source_release`

| Field | Type | Meaning |
|---|---|---|
| `source_key` | string | Adapter family identifier. |
| `release_id` | string | Content-addressed release identifier. |
| `official_url` | string | Canonical official repository/card URL. |
| `revision` | string | Full Git SHA or HF dataset commit. |
| `accessed_at` | timestamp | UTC inspection time. |
| `repo_license_spdx` | nullable string | Code/repository license only. |
| `data_license_expression` | nullable string | Annotation/release license. |
| `media_rights_status` | enum | `unknown_hold`, `restricted`, `asset_reviewed`. |
| `access_gate` | enum | `public`, `token`, `terms_acceptance`, `external_agreement`. |
| `observed_official_access_route` | string | Technical route observed at an official surface; never an authorization decision. |
| `artifact_license_status` | string | Verified fact, source claim, conflict, or unresolved license state for the release artifact. |
| `source_media_rights_status` | string | Rights state for underlying media, independent of code/annotation licensing. |
| `episode_publication_class` | enum | `metadata_only`, `restricted_compatibility`, `external_compatibility_unpooled`, `public_core_eligible`, or `unresolved`. |

### `asset`

`asset_id`, `source_key`, `release_id`, `upstream_asset_namespace`,
`upstream_asset_id`, `canonical_source_url`, `upstream_dataset`, `split`,
`duration_s`, `original_time_base_num`, `original_time_base_den`,
`video_available`, `audio_available`, `subtitle_available`,
`complete_source_availability`, `source_time_join_status`, `parent_asset_id`,
`lineage_relation`, `checked_against_scope`, `dedup_disposition`,
`media_object_ref`, `rights_manifest_asset_id`, `source_payload_json`.

`media_object_ref` remains null during pre-download reconnaissance.
Availability fields are tri-state or reason-coded; absence of evidence must not
be coerced to `false`. Lineage covers parent-source, segment-of,
reconstruction-of, alternate-encode, excerpt-of, and re-upload relations.
Source-disjointness is evaluated at the earliest verified underlying asset.

### `segment`

`segment_id`, `asset_id`, `upstream_segment_id`, `start_s`, `end_s`, `start_pts`, `end_pts`, `segmentation_method`, `parent_segment_id`, `modality_mask`, `source_payload_json`.

Intervals are half-open `[start_s,end_s)`. Adapter validation rejects negative, inverted, or duration-exceeding intervals beyond a documented tolerance.

### `text_track`

`text_id`, `asset_id`, `segment_id`, `kind` (`subtitle`, `asr`, `visual_caption`, `audio_caption`, `av_caption`, `video_summary`), `language`, `text`, `start_s`, `end_s`, `speaker`, `generator_run_id`, `source_payload_json`.

Upstream subtitles and generated ASR are never conflated. Preserve whether timestamps are original, shifted, inferred, or chunk-relative.

### `item`

`item_id`, `asset_id`, `task_family`, `question`, `answer_type`, `choices_json`, `reference_answer`, `category`, `hop_count`, `turns_json`, `rubric_json`, `generation_run_id`, `validation_status`, `source_payload_json`.

### `evidence_set`

`evidence_set_id`, `item_id`, `semantics` (`relevant`, `sufficient`, `jointly_necessary`, `ordered_trajectory`, `single_gold_chunk`), `validation_protocol`, `validation_run_id`.

### `evidence_member`

`evidence_set_id`, `evidence_id`, `segment_id`, `ordinal`, `modality`, `necessity_group`, `weight`, `start_s`, `end_s`, `source_payload_json`.

### `generation_run`

`run_id`, `purpose`, `provider`, `model_id`, `model_revision`, `endpoint_class`, `prompt_sha256`, `prompt_text_ref`, `parameters_json`, `seed`, `code_revision`, `container_digest`, `input_manifest_sha256`, `output_sha256`, `created_at`.

### `evaluation_record`

`run_id`, `item_id`, `prediction`, `score_json`, `decoded_observations_json`, `retrieved_segment_ids`, `judge_run_id`, `latency_ms`, `token_cost`, `frame_cost`, `error_state`.

## Source-family adapters

All adapters implement:

```python
class UpstreamAdapter(Protocol):
    def inspect_release(self, snapshot) -> ReleaseDescriptor: ...
    def discover_schema(self, snapshot) -> SchemaFingerprint: ...
    def normalize(self, rows) -> Iterable[NormalizedBundle]: ...
    def validate(self, bundle) -> list[Finding]: ...
```

### `lovr_adapter`

- Inputs: HF file manifest/caption tables and repository schemas.
- Maps long-video and clip IDs, clip intervals, clip captions, merged video descriptions.
- Optional compatibility evaluator wraps Recall@K/pass@k.
- Rejects inferred audio availability and reconstructed clips without an original-asset mapping.

### `longvidsearch_adapter`

- Inputs: `full-QA(3000).json` or `dataset/*_qa.json`, caption parquet schema, embedding manifest.
- Maps category, hop count, exact necessary clip set, and answer.
- Verifies `hop_count == count(distinct necessity groups)` and no missing clip references.
- Ignores `cache_llm.pkl`; embeddings are accepted only with checkpoint/dimension/hash metadata.

### `flare_adapter`

- Inputs: clip table, modality captions, query table, hard-bimodal validation outputs.
- Maps query modality and visual/audio/fused pass/fail matrix.
- Requires parent Video-MME asset mapping and disallows media-rights inheritance by assumption.

### `videomme_adapter`

- Inputs: official JSON/table and output template.
- Maps duration group, domain/subcategory/task type, three MCQs, subtitles/audio flags.
- Versions replacement history; never joins by filename alone.
- Provides grouped accuracy compatible with `eval_your_results.py`.

### `longvideobench_adapter`

- Inputs: `lvb_val.json`, test metadata, subtitle JSON.
- Supports both upstream subtitle forms and explicit subtitle offset.
- Compatibility mode reproduces Decord uniform sampling/interleaving; canonical mode uses PTS-aware sampling.
- Keeps validation labels separate from test records.

### `longshot_adapter`

- Inputs: gated metadata, conversations, rubrics, preprocessing manifests.
- Maps weighted rubric trees and modality requirements.
- Requires `version_namespace` because v1 and v2 counts differ.
- Rejects downloader/cookie fields as acquisition authority.

### `traceav_adapter`

- Inputs: question table and ordered trajectory annotations.
- Maps trajectory steps, timestamps, modalities, question dimensions, and QA decisions.
- Requires generation/QA provenance for regenerated data; missing prompt/model metadata is a warning or hard error depending on release mode.

### `vesbench_adapter`

- Inputs: parquet metadata and evidence intervals.
- Maps jointly necessary intervals and strictness levels.
- Evaluation accepts actual decoded PTS, not just requested windows.
- Handles frame/interval boundary tolerance explicitly and emits accuracy, evidence coverage, evidence-supported correctness, and frame cost.

### `vragbench_adapter`

- Inputs: gated HF triplets and separately authorized Ego4D/EgoLife manifests.
- Maps one localized two-minute evidence chunk, source family, query, and answer.
- Refuses normalization if source agreement identifiers are absent.
- Keeps retrieval and generation metrics separate and records judge provenance.

## Media materialization after approval

A later, separately approved process may implement:

1. acquire exact approved bytes through an authorized official route;
2. hash and probe with pinned `ffprobe`;
3. preserve original bytes read-only;
4. create normalized audio (`pcm_s16le`, 16 kHz mono only when required) and PTS-indexed frame tables;
5. run ASR/caption/segmentation jobs as content-addressed transformations;
6. validate duration, stream presence, timestamp monotonicity, and source-to-derivative mapping.

No adapter should shell out to `yt-dlp`, concatenate archives, or invoke a model endpoint. Those are separate capabilities governed by policy and manifests.

## Compatibility metrics

- Retrieval: Recall@K/pass@k with explicit query and corpus unit.
- Multiple choice: exact option accuracy and source-defined grouped slices.
- Open answer: rubric or judge score with frozen judge run.
- Evidence: interval precision/recall/IoU where defined; exact necessary-set success; decoded-frame coverage under named tolerance; evidence-supported correctness.
- Efficiency: decoded frames, media seconds read, retrieval calls, tokens, wall time, and failures.

Metric implementations need golden fixtures generated from small upstream examples. Any discrepancy becomes an adapter-version change, not a silent patch.

## Dependency and reproducibility controls

- Lock Python and system packages; record FFmpeg/Decord/PyAV builds and CUDA driver.
- Use OCI image digests, not image tags.
- Treat model weights as separate licensed inputs with exact hashes/revisions.
- Store prompts as files and hash them.
- Require deterministic seeds where supported; mark nondeterministic remote APIs.
- Cache JSON responses only after redaction and hashing; never commit secrets or session cookies.
- Use JSON/Parquet, never upstream pickle, as interchange.
- Maintain golden schema fingerprints and fail on upstream drift.
- Run all evaluation in an offline network namespace after artifacts are staged.

## Minimal implementation sequence

1. Add release descriptors and schema-only fixtures for all nine targets.
2. Implement `videomme`, `longvideobench`, and `longvidsearch` adapters first because their public metadata/evaluation surfaces are clearest.
3. Implement LoVR and FLARE as a shared `clip_retrieval` family.
4. Implement LongShOT and TraceAV as `trajectory_rubric` family variants.
5. Implement VES-Bench metrics independently from the unreleased TRACE method code.
6. Add V-RAGBench only in the restricted compatibility partition after agreements are recorded.
7. Keep every `media_object_ref` null until the existing AV-TRACE acquisition gate approves transfer.

## Discovery versus execution

Repository and file suggestions belong to a discovery queue. They become an
executable metadata allowlist only after full revisions, exact paths,
provider-reported sizes/OIDs, output bindings, and a named small-snapshot
approval are recorded. Media paths never enter that metadata allowlist. No
executable media allowlist is part of the current package.
