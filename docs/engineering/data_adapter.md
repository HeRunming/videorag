# Metadata-only dataset adapter and acquisition preflight

## Scope

`src/av_trace_data/` performs offline release inspection, normalization,
deterministic candidate selection, fail-closed acquisition-manifest drafting,
and frozen-plan validation. It does not fetch repository metadata, download or
probe media, or grant permission to acquire or publish an asset.

The normative acquisition schema is unchanged. A draft is emitted only when
all four media facts required by that schema have already been verified:
video, audio, speech, and ambient-audio presence/absence.

## Production metadata snapshot importer

`src/av_trace_data/snapshot_importer.py` is the provider-neutral boundary for
the official text snapshots already captured in `data/hf_recon/snapshots/`.
It emits `metadata_reconnaissance_inspection` version `1.0`, not
`InspectionResult` candidate records and not acquisition manifests. This keeps
raw repository reconnaissance separate from the reviewed candidate adapter and
all downstream authorization controls.

The importer accepts local:

- Hugging Face dataset API JSON;
- GitHub commit and tree API JSON;
- bounded JSON, JSONL, and CSV metadata;
- metadata-only Parquet when PyArrow is already available.

It has no URL input mode and no networking dependency. URL-shaped paths,
symbolic links, unsupported extensions, media, archives, embeddings, and model
payloads are rejected before parsing. Every accepted input records its exact
SHA-256 and byte size. A configurable per-file byte cap is enforced before and
after reading.

Repository, file, and blob revisions have separate fields. Promotion requires
a full immutable repository revision (40/64-hex Git/HF object ID or the
existing typed object-store revision form); mutable names and short hashes are
rejected. File and blob revisions, when supplied, receive the same immutable
revision check. HF LFS SHA-256 values are stored as file revisions, while Git
blob IDs remain blob revisions.

All reconnaissance records preserve:

- tri-state media facts as unknown unless actually verified;
- declared modality strings without converting declarations into stream facts;
- identity state independently from local IDs;
- license metadata as evidence only;
- media-rights state as unknown;
- explicit source/lineage joins, including TraceAV mapping joins, FLARE clip
  ancestry, and QA-to-source-video references.

The importer never derives rights, access approval, or redistribution authority
from a license tag. Its output carries
`"acquisition_authorization": "none"`, `"contains_media": false`, and
`"network_access_performed": false`.

Supported source-family row parsers are:

- LongVideoBench-Meta;
- Video-MME;
- LongVidSearch QA JSON;
- TraceAV mapping and task JSONL;
- FLARE demo query/caption JSONL;
- LongShOT annotation JSONL, when supplied.

Unknown small metadata schemas can be imported with `generic_metadata`; unknown
modalities remain declarations and all media facts remain null. Tabular byte
columns, media data URIs, binary signatures, and suspicious base64 values in
binary/media-named fields fail closed.

### Snapshot import CLI

For files whose repository context is present in a captured API snapshot:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
python scripts/import_metadata_snapshots.py \
  data/hf_recon/snapshots/hf_api_Fishiing_LongVidSearch.json \
  data/hf_recon/snapshots/hf_Fishiing_LongVidSearch_full-QA_3000.json \
  --output /tmp/longvidsearch-recon.json
```

For a standalone local metadata file, provide its immutable repository context:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
python scripts/import_metadata_snapshots.py metadata.jsonl \
  --output /tmp/metadata-recon.json \
  --provider huggingface \
  --repository-id owner/release \
  --repository-revision 0123456789abcdef0123456789abcdef01234567 \
  --repository-path data/metadata.jsonl \
  --source-family longshot
```

`--allow-unpromoted` permits an explicitly unpromoted reconnaissance artifact
when revision provenance is absent or mutable. It never upgrades the artifact
to an acquisition approval.

### Reviewed conversion boundary

Snapshot-importer output is not accepted directly by
`select_rehearsal_candidates.py`, even if a caller injects a `candidates`
array. Before selection, a human-reviewed conversion must create a normal
candidate inspection whose entries satisfy the complete
`NormalizedCandidate` schema. That review must explicitly resolve each chosen
record's dataset-local and namespaced identity, immutable repository revision,
duration, stream facts, technical access status, lineage, and source snapshot
binding. Unknown importer fields must remain unknown; the conversion must not
infer media availability, rights, or acquisition authority from a modality
declaration, URL, filename, license tag, or repository listing.

The converted inspection's `snapshot_sha256` must bind the exact imported
reconnaissance artifact used by the reviewer. Selection then copies that
digest into its `source_snapshots` map. This is a metadata-review transition
only: candidate conversion does not approve acquisition, processing,
publication, or annotation.

## Audited release registry

Dataset and code repositories are separate provenance surfaces. The active
dataset configurations use the audited release IDs:

| Adapter | Dataset release | Separate code repository |
|---|---|---|
| `lovr` | `debugger123/LoVR-benchmark` | `TechNomad-ds/LoVR-benchmark` |
| `flare` | `AnonymousFLARE/FLARE` | `YqjMartin/FLARE` |
| `longshotbench` | `MBZUAI/longshot-bench` | `mbzuai-oryx/LongShOT` |
| `trace_vesbench` | `buaaplay/VES-Bench` | `buaa-colalab/TRACE` |
| `longvidsearch` | `Fishiing/LongVidSearch` | `yrywill/LongVidSearch` |
| `traceav_bench` | `Heinz217/TraceAV-Bench` | `Heinz217/TraceAV-Bench` |

The registry also distinguishes the LongVideoBench full and metadata-only
releases.

The following are represented, but are deliberately not executable through
the generic adapter:

- `vragbench`: `protocol_only`, because the audited card had no usable
  candidate payload/source IDs;
- `egolife`: `manual_resolution`, because artifact-specific license conflict,
  privacy, and media identity require review;
- `ego4d`: `manual_resolution`, because access is an external licensed
  distribution rather than an HF/GitHub snapshot;
- `omnivideobench`: `manual_resolution`, pending gated item-level resolution.

`adapter_for_config()` refuses those states instead of suggesting implemented
candidate normalization.

## Normalized reconnaissance semantics

### Tri-state media facts

`has_video`, `has_audio`, `has_speech`, and `has_ambient_audio` are each:

- `true`: verified present in the represented asset/rendition;
- `false`: verified absent;
- `null`: unknown or unverified.

Inspection preserves missing values and explicit strings such as `unknown` or
`unverified` as `null`. It never defaults video to true or turns unknown into
false.

The default selection policy requires verified video and audio. Therefore:

- `false` is rejected as `video_unavailable` or `audio_unavailable`;
- `null` is held separately as `video_unknown` or `audio_unknown`.

Acquisition-manifest drafting is stricter because the normative schema contains
Boolean assertions for all four fields. Drafting refuses any candidate whose
video, audio, speech, or ambient state is unknown.

### License and terms evidence

Reconnaissance stores zero or more `LicenseEvidence` records. Each record has:

- evidence source;
- artifact class;
- nullable name, version, URL, scope, and observed revision.

`license_resolution_status` is `consistent`, `unresolved`, or `conflicting`.
Missing evidence and conflicts are valid reconnaissance outcomes.

These records are not rights decisions. Draft manifests hash the full
candidate/evidence bundle but use the placeholder
`UNRESOLVED_RECONNAISSANCE_EVIDENCE` in the normative
`rights.license_or_grant` slot. They never copy a repository/card label into an
asset-level grant. Acquisition and release decisions remain `unknown_hold`.

The old singular `license` object can be read for migration. It becomes one
evidence record with resolution status `unresolved`; it does not become
approved rights evidence.

### Namespaced identity and lineage

Every candidate records:

- `upstream_namespace`;
- `upstream_asset_id`;
- `identity_resolution_status` (`resolved`, `unresolved`, or `conflicting`);
- optional `parent_dataset_id`;
- optional parent namespace/asset ID;
- optional lineage relation.

A resolved identity requires both namespace and asset ID. The adapter never
falls back from a missing upstream identity to the dataset-local `source_id`.
Legacy unnamespaced `upstream_id` values can be read, but are marked unresolved
and are not selectable under the default policy.

Supported explicit lineage relations include `same_asset`, `derived_from`,
`segment_of`, `reconstruction_of`, `alternate_encode`, `excerpt_of`, and
`mapped_from`.

Selection builds connected identity components from direct and parent nodes,
then deduplicates by component, exact checksum, and fingerprint. This covers:

- FLARE clips/derivatives linked to a Video-MME parent;
- LongVidSearch and LoVR records linked to a LongVideoBench parent;
- TraceAV records linked to the mapped upstream source, including
  OmniVideoBench when the mapping is known.

Unresolved identities are held; no parent or cross-source mapping is guessed.

### Access taxonomy

Technical access, payload availability, media rights, and episode publication
class are orthogonal:

- `technical_access_status` preserves the audited inventory term exactly;
- `access_gate` records `public`, `token`, `terms_acceptance`,
  `external_agreement`, or `unresolved`;
- `payload_state` records whether a release payload, metadata, annotations,
  only a card, or a manual distribution is available;
- `media_rights_status` records `unknown_hold`, `restricted`, or
  `asset_reviewed`;
- `episode_access_class` is nullable and is never derived from access.

`ACCESS_STATUS_CROSSWALK` is an explicit table from audited technical status to
gate and payload state. Unknown statuses and contradictory overrides are
rejected instead of mapped to a nearest value. The deprecated `access_mode`
property is retained only as a compatibility view and must not be interpreted
as a rights or publication decision.

## Local snapshot format

```json
{
  "provider": "huggingface",
  "repository": {
    "id": "owner/dataset-release",
    "url": "https://...",
    "revision": "immutable-provider-revision",
    "publisher": "Publisher",
    "technical_access_status": "public_ungated",
    "media_rights_status": "unknown_hold",
    "license_resolution_status": "conflicting",
    "license_evidence": [
      {
        "source": "hf_current_header",
        "artifact_class": "dataset_release",
        "name": "CC-BY-NC-SA-4.0",
        "version": "4.0",
        "url": "https://...",
        "scope": "Observed release-level scope",
        "observed_revision": "..."
      }
    ]
  },
  "card": {},
  "configs": [],
  "files": [],
  "rows": [
    {
      "source_id": "dataset-local-id",
      "split": "test",
      "duration_s": 2400,
      "canonical_url": "https://...",
      "has_video": null,
      "has_audio": null,
      "has_speech": null,
      "has_ambient_audio": null,
      "upstream_namespace": null,
      "upstream_asset_id": null,
      "identity_resolution_status": "unresolved"
    }
  ]
}
```

Rows require a stable dataset-local source ID, split, positive duration,
canonical URL, and pinned row/repository revision. Media and upstream identity
may remain unknown during inspection. A direct media URL, size, checksum,
fingerprint, transcript/evidence indicators, retrieval metadata, and explicit
lineage are optional.

## Workflow

### Inspect

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
python scripts/inspect_dataset_release.py \
  --adapter lovr \
  --fixture tests_data/fixtures/hf_lovr_snapshot.json \
  --output /tmp/lovr-inspection.json
```

The LoVR fixture is schema-faithful reconnaissance with clearly marked
synthetic IDs. It intentionally preserves unknown streams, no direct media
URL, unresolved identity, no transcript claim, and conflicting release-level
license evidence.

### Select and draft

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
python scripts/select_rehearsal_candidates.py \
  /tmp/verified-inspection.json \
  --output /tmp/rehearsal-selection.json \
  --manifest-dir /tmp/draft-manifests \
  --created-by data_adapter
```

The default policy selects only resolved, verified audiovisual candidates in
the configured duration range. A schema-faithful reconnaissance snapshot may
produce no selection; that is the intended fail-closed result.

Selection artifacts are version `2.0`. When the selection CLI consumes an
inspection artifact, it copies the inspection's exact `snapshot_sha256` into
the selection's `source_snapshots` map before computing `selection_sha256`.
Each key identifies the exact `provider:repository@revision` source. Download
planning binds both the complete selection JSON and those source/hash pairs.
An executable plan requires at least one valid binding and complete coverage
for every selected candidate's provider, repository, and immutable revision.

If source snapshots are unavailable, callers must explicitly request
`metadata_preview` mode (CLI: `--mode metadata-preview`). That mode is useful
for reviewing URL, size, destination, and manifest metadata, but the resulting
plan has `executable: false` and cannot cross the authorization boundary.

Draft manifests remain metadata-only and non-approvable. Human review must
replace the placeholder rights evidence with asset-specific authority before a
gate transition.

### Plan and authorize

Download planning, approval validation, execution authorization, and transport
remain separate downstream controls. The shipped CLI performs no transfer.
Executable plans require explicit item and total byte caps, immutable
URL/revision binding, complete source snapshot coverage, a verified selection
artifact, reviewed manifests, an authorized signer/role mapping, and an
independently approved staging root.

Plan version `2.0` freezes the complete selected normalized records, policy and
summary hashes, source snapshot identities and hashes, manifest hashes,
canonical provider URLs, full 40/64-hex revisions, byte ranges/caps, and
normalized staging destinations. URL validation recursively rejects encoded
dot segments, encoded separators, encoded/literal control bytes, and ambiguous
provider paths such as `file.mp4/extra`.

The no-backend CLI command is named `validate` (`execute` remains a
compatibility alias). It checks the plan, manifests, signer/role allowlist,
approval contents, freshness, and staging-root allowlist, but the CLI has no
trusted signature verifier. An unsigned result is therefore
`validated_not_authorized`, never execution approval.

Any library call with a non-`None` `ByteTransferBackend` additionally requires:

- a trusted `ApprovalSignatureVerifier` and valid detached signature;
- an independently stored audit checkpoint containing the expected chain head
  and record count;
- complete redirect-count and per-hop peer-IP attestations;
- a full-object expected SHA-256 value; and
- independently observed filesystem effects after backend return.

The executor opens the destination itself and verifies that it is a regular
non-symlink file inside the staging root, then recomputes its exact byte count
and SHA-256 digest. A backend's self-attestation without the matching file is
rejected.

Audit JSONL is hash-chained and rejects credential-like fields. A chain file by
itself detects edits to retained records but cannot prove suffix completeness:
a valid final record can be removed while leaving a valid shorter chain.
`verify_audit_log` therefore accepts an external expected head and record count,
and future transfer execution requires that checkpoint to match.

No concrete `ByteTransferBackend` ships. The CLI always passes `backend=None`
and always reports `network_access_performed: false`; the abstract transport
boundary remains reserved for a separately reviewed implementation.

## Fixtures and tests

- `hf_lovr_snapshot.json`: schema-faithful, explicitly synthetic LoVR
  reconnaissance with unknown media and conflicting license evidence.
- `hf_missing_license.json`: zero license-evidence records with unresolved
  status.
- `hf_synthetic_av_snapshot.json`: clearly synthetic verified-AV behavior used
  for selection, manifest, CLI, and download-planning tests.
- `hf_synthetic_traceav_snapshot.json`: clearly synthetic mapped-upstream
  behavior.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
python -m pytest tests_data -q -o addopts=''
```

The suite covers corrected release IDs, explicit manual/protocol states,
tri-state preservation, unknown-audio holds, zero/conflicting license evidence,
no rights inheritance, namespaced identity, all requested lineage chains,
access-crosswalk rejection, safe legacy reading, schema-valid drafts, and the
existing download/provenance controls.
