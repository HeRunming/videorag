# Independent red-team review of dataset sourcing and download gates

**Review date:** 2026-09-07  
**Role:** adversarial dataset and reproducibility reviewer  
**Scope:** the files and implementation named in Task 28  
**Transfer constraint:** no media, archives, Parquet shards, embeddings,
thumbnails, or model weights were fetched.

The row-level findings are in
[`../../data/hf_recon/redteam_findings.csv`](../../data/hf_recon/redteam_findings.csv).
Finding IDs below refer to that file.

## Executive decision

| Decision | Verdict | Reason |
|---|---|---|
| Metadata-only candidate selection | **GO** (limited) | Small public annotation/metadata files can be inspected, but selection must exclude unresolved repositories and must not assert media or audio suitability. Canonical IDs, full immutable revisions, source-family deduplication, and selection-integrity checks are prerequisites for a frozen candidate list. |
| Requesting gated access | **GO** (conditional) | It is reasonable to request LongVideoBench, OmniVideoBench, and independently justified Ego4D access. Record the exact terms and acceptance event. Do **not** request broad Ego4D access for V-RAGBench until its UID list exists, and do not treat acceptance as redistribution permission. |
| Downloading 3–5 real videos | **NO-GO** | Media rights remain unresolved for the proposed first sources; per-file audio is unverified; several releases lack immutable pins; the adapter has URL, revision, binding, range, approval, and backend enforcement gaps; and the shipped CLI has no transfer backend. |
| Starting real annotation | **NO-GO** | No real candidate has a reconciled source ID, immutable revision, approved asset manifest, verified streams/audio class, duplicate clearance, and completed acquisition. The rehearsal modality matrix is aspirational. |

The narrow **metadata-only GO** does not authorize media access, model/API
execution, or annotation. It permits only reviewed small text/JSON metadata
from official sources.

## Method and evidence limits

I reviewed the specified Markdown/CSV files, `src/av_trace_data/`,
`scripts/plan_dataset_download.py`, the acquisition gate implementation and
schema on which it depends, the existing data-adapter tests, and
`data/rehearsal_plan/`.

The audit used the official project, GitHub, Hugging Face, data-portal, and
paper URLs recorded by the project. Direct shell requests to the official
GitHub and Hugging Face APIs were attempted on 2026-09-07, but the
launcher-supplied proxy hostname did not resolve. Therefore:

- a statement marked **verified fact** below is supported by a captured
  official release/paper record or by directly inspected local code;
- an **inference** is explicitly identified and is not treated as a release
  fact;
- an **unresolved item** requires a fresh official API response, gated-file
  inspection, author clarification, or authorized media probe;
- seven-character commit prefixes and a path displayed at `main` are evidence
  locators, not acceptable final immutable pins.

This limitation is itself a blocking finding, `RT-051`. Before any gate
transition, preserve fresh official API JSON, complete commit IDs, file
metadata, and terms snapshots.

## 1. Release payload, audio, and rights matrix

### FLARE / Video-MME

**Verified facts**

- FLARE reports 399 selected Video-MME source videos, 87,697 clips, generated
  vision/audio/unified captions, and generated retrieval queries. The HF tree
  exposes `datas/` and `videos/`; the demo describes two examples with one
  full video, three clips, and JSONL artifacts per example.
- Video-MME's HF release at the recorded full revision contains four video ZIP
  archives, a subtitle ZIP, and a small metadata/MCQ Parquet. It is a media
  release plus annotations, not an ID-only release.
- Video-MME's official README imposes academic/non-commercial and
  redistribution/modification restrictions and reserves source-video
  copyright. FLARE's card-level `cc-by-4.0` label does not erase those upstream
  restrictions.

**Unresolved**

- Whether FLARE's hosted “full” files are pristine source objects, transformed
  copies, or reconstructed derivatives.
- Exact FLARE clip start/end times and parent crosswalk completeness.
- Audio streams in every selected FLARE or Video-MME container.
- Whether audio content is speech, music, ambient/non-speech sound, mixed, or
  unintelligible.
- Separate license scope for FLARE generated captions/queries, extracted WAV,
  clips, full videos, and redistribution.

**Attack result**

FLARE is not presently the “best first real-media rehearsal” in an executable
sense. It may be a useful metadata-first target, but media transfer remains
blocked by `RT-001` through `RT-004`. FLARE and Video-MME must be one duplicate
family, keyed by the Video-MME/source identity.

### LoVR / LongVideoBench / LongVidSearch

**Verified facts**

- LoVR provides generated caption tables and multipart media containing
  segmented clips. Its documentation reconstructs “full videos” by
  concatenating clips; these are derivatives, not documented pristine
  LongVideoBench objects.
- LongVideoBench's full release is gated and includes processed MP4 and
  subtitle archives. Its separate public metadata release contains QA and
  paths, not the media or subtitle contents.
- LongVidSearch provides QA JSON, per-video JSON, caption data, embeddings,
  code, and an unsafe-to-load pickle/cache; no raw video release was observed.
  Its `evidence_slices` are ordinal clip identifiers rather than verified
  absolute source times.
- The source chain is shared:
  `LongVidSearch -> LoVR -> LongVideoBench`.

**Unresolved**

- LoVR's authoritative data license: official surfaces in the audit show
  conflicting CC BY and CC BY-NC-SA labels.
- Audio streams and speech/music/ambient classification for LoVR/LVB media.
- Subtitle provenance and completeness in LongVideoBench.
- LongVidSearch's exact clip/time join and the 447-paper-video versus
  444-visible-ID discrepancy.
- Exact model/checkpoint provenance for released embeddings and cached LLM
  artifacts.

**Attack result**

These releases must be treated as one source-media and leakage family.
LongVidSearch is suitable for a metadata-only SES-proposal parser after a full
pin, but not for real evidence annotation until every ordinal slice resolves
to an immutable LoVR clip and LongVideoBench source-time interval. See
`RT-005` through `RT-013`.

### LongShOTBench

**Verified facts**

- The recorded HF artifact is an annotation JSONL with questions,
  conversations, modality labels, difficulty, and weighted criteria. No source
  video, source URL, transcript, feature file, clip boundary, or gold evidence
  interval was confirmed in that payload.
- The official repository contains preprocessing/generation/evaluation
  workflows and documents a YouTube workflow involving user cookies.
- The paper and repository describe speech and non-speech/ambient processing,
  but those generated/runtime products are not a per-file source-audio
  guarantee.

**Contradiction**

`docs/data/hf_dataset_recon.md` and `dataset_releases.csv` call the current HF
release public/ungated. `upstream_reproduction_audit.md` and
`upstream_components.csv` call it gated and requiring login/acceptance. The
official API state must be refreshed before use.

**Attack result**

LongShOT metadata can support rubric and conversation parsing after the access
state and full revision are reconciled. It cannot support media, evidence-span,
speech, ambient, or cross-modal candidate selection now. Cookie-based
acquisition is not an authorized route. See `RT-014` through `RT-017`.

### TraceAV-Bench

**Verified facts**

- The public release is annotation-only: task JSONLs plus
  `video_name_mapping.jsonl`, with QA fields and serialized,
  timestamp-bearing evidence trajectories.
- The release statement is scoped to annotations and accompanying code. It
  does not license mapped upstream video.
- Some mapped retrieval is expected to use the separately gated
  OmniVideoBench release.

**Unresolved**

- Exact nested timestamp keys, units, interval inclusivity, and full modality
  vocabulary.
- Which source corpora and exact objects are represented by every mapping row.
- File-level audio and whether an `audio` trajectory step is speech,
  music, ambient sound, or a generated multimodal description.

**Attack result**

TraceAV is a strong annotation-first source, but the current repository records
do not justify a real-media or audio-modality selection. Parse and freeze the
mapping before requesting exact upstream files. See `RT-018` through
`RT-020`.

### TRACE / VES-Bench

**Verified facts**

- The official release reports a Parquet file and a `videos/` directory and
  the paper reports jointly necessary evidence intervals.
- The inspected TRACE repository says method code is coming soon.

**Unresolved**

- Full immutable HF revision.
- Dataset and annotation license, source-media provenance, and redistribution
  authority.
- Parquet columns, interval units/endpoints, source IDs, splits, media
  duration, subtitles, and audio streams/content.

**Attack result**

Public hosting is not sufficient authority. VES-Bench cannot currently support
an ambient-audio slot, and official-method reproduction is unavailable. See
`RT-021` through `RT-023`.

### V-RAGBench / EgoLife / Ego4D

**Verified facts**

- The V-RAGBench paper defines 2,100 query/evidence/answer examples over 216
  EgoLife/Ego4D videos, but the visible HF release in the audit was only a
  small card-level payload without supported data records.
- EgoLife's official surfaces expose participant media plus QA and SRT
  artifacts. The official sources conflict between an HF `mit` label and the
  repository's S-Lab License 1.0.
- Ego4D uses registration/license acceptance, temporary AWS credentials, and
  the official CLI. It supplies stable UIDs, but its metadata permits missing
  audio fields.

**Unresolved**

- V-RAGBench's current HF gate state, immutable revision, actual payload,
  source UID list, split, and serialized evidence fields.
- Exact artifact-specific scope of EgoLife's license for code, QA,
  transcripts, generated captions/features, raw participant media, and onward
  redistribution.
- File-level audio and audio type for the V-RAGBench-selected sources.
- An official executable V-RAGBench implementation and fully pinned
  judge/retrieval services.

**Attack result**

V-RAGBench is protocol-only. Its missing UIDs block a minimal Ego4D request.
EgoLife media are additionally blocked by license conflict and privacy risk.
See `RT-024` through `RT-032`.

## 2. Shared corpora and likely duplicate sources

| Family | Relationship | Status | Required control |
|---|---|---|---|
| FLARE / Video-MME | FLARE selects Video-MME sources and derives clips/captions/queries from them. | **Verified** | Parent-source ID crosswalk; deduplicate before ranking; content/perceptual hash after authorized acquisition. |
| LongVidSearch / LoVR / LongVideoBench | LongVidSearch uses LoVR representations; LoVR derives from LongVideoBench. | **Verified** | Treat as one source family; resolve slice -> LoVR clip -> LVB parent/time; prevent cross-split leakage. |
| V-RAGBench / EgoLife / Ego4D | V-RAGBench is built over EgoLife and Ego4D. | **Verified** | Deduplicate by Ego4D UID and EgoLife participant/day/file identity. |
| TraceAV / OmniVideoBench | TraceAV includes a source mapping and uses OmniVideoBench where indicated. | **Conditional** | Parse every mapping row at a pinned revision; do not infer all rows share one source. |
| LongShOT versus other web benchmarks | Source overlap is plausible because of YouTube-oriented acquisition, but no complete source-ID list was verified. | **Inference only** | Do not claim overlap counts; reconcile source IDs before split construction. |
| VES-Bench versus other releases | Source provenance is not documented sufficiently for comparison. | **Unresolved** | Require a source manifest before treating VES videos as disjoint. |

Current selection logic deduplicates only on `upstream_id`. That works only if
all adapters normalize shared source identity consistently. The present
repository does not yet provide the required cross-family map.

## 3. License-scope audit

The reconnaissance correctly warns that repository licenses are not media
licenses, but the evidence model and implementation do not yet enforce the
needed separation.

| Artifact class | Current evidence | Red-team disposition |
|---|---|---|
| Code | MIT/CC badges or repository statements exist for some targets; absent or unresolved for others. | Record at an immutable code revision only. Never reuse as media authority. |
| Benchmark annotations / QA | Card labels exist for FLARE, LongShOT, TraceAV and some other releases, but scope and conflicts remain. | Permit metadata inspection only where the official release is public and pinned; resolve contradictions before redistribution. |
| Generated captions / summaries | Present in FLARE, LoVR, EgoLife and upstream construction pipelines. | They are generated artifacts, not transcripts or source-media licenses; record generator and artifact-specific license. |
| Features / embeddings | LongVidSearch exposes embeddings; Ego4D/EgoLife may expose features. | Treat as separately licensed, potentially substitutive artifacts. Require model/checkpoint and hash metadata. |
| Transcripts / subtitles | Video-MME has a subtitle archive; LongVideoBench has subtitle JSON; EgoLife has transcript SRT. | Preserve provenance and coverage. Do not equate subtitle, ASR, transcript, dense caption, or audio caption. |
| Source media | Hosted for several releases, externally resolved for others. | Every target remains `unknown_hold` for the proposed real-media rehearsal unless an asset-level agreement or grant is reviewed. |
| Redistribution | No examined project-level label proves blanket onward redistribution of all underlying media. | Raw and derived media redistribution remains prohibited or unknown until separately approved. |

The most serious implementation defect is `RT-038`: repository/card license
metadata can be copied into the manifest's `license_or_grant` and
`authority_evidence` fields, while the acquisition gate validates status
values rather than the evidence's asset-level scope.

## 4. Immutable revisions and source identity

The documentation repeatedly requires immutable pins, but many audited records
retain:

- floating `main`;
- seven-character UI prefixes;
- separate file prefixes rather than one repository snapshot;
- paper version labels rather than data commits;
- mutable project pages or live viewers.

Only the recorded Video-MME HF revision and OmniVideoBench HF revision are full
40-character identifiers in the audited tables. Even those do not by
themselves pin separate GitHub code, terms, or upstream source objects.

The adapter's rejection is weaker than the documentation claims. It rejects
only four exact words. Values such as `refs/heads/main`, `main^`, `v1`,
`2026-09-07`, and short SHAs pass, while selection JSON can bypass adapter
inspection altogether (`RT-036`).

There are also canonical-ID conflicts (`RT-035`):

- configured `FLARE-Benchmark/FLARE` versus audited
  `AnonymousFLARE/FLARE`;
- configured `TechNomad-ds/LoVR` versus audited
  `debugger123/LoVR-benchmark`;
- configured `MBZUAI/LongShOTBench` versus audited
  `MBZUAI/longshot-bench`;
- configured `buaa-colalab/VES-Bench` versus audited
  `buaaplay/VES-Bench`.

These may represent old names, aliases, or mistakes. None was established as a
safe official redirect in the audited evidence. Metadata selection is limited
until they are reconciled.

## 5. Credentials, gates, private services, and unavailable components

- **LongVideoBench:** login/contact sharing and terms acceptance for full data.
- **TraceAV / OmniVideoBench:** upstream gated access for mapped media.
- **Ego4D:** registration, license acceptance, temporary AWS credentials, and
  official CLI.
- **LongShOT:** internally contradictory HF gate record; official repository
  also documents a browser-cookie YouTube workflow, which AV-TRACE must not
  execute as an acquisition authority.
- **V-RAGBench:** gate state is contradictory and no executable payload or
  official implementation repository was confirmed.
- **TRACE:** official method code was still marked “coming soon.”
- **Generated pipelines:** FLARE, LoVR, LongVidSearch, LongShOT, TraceAV, and
  V-RAGBench depend on model checkpoints or hosted model/judge services that
  are incompletely pinned. The audit cannot prove that a paid/private API is
  always required, but it also cannot prove that reproduction is independent
  of one.
- **Dead/mutable surfaces:** no specific official URL was proven dead in this
  run; however, stale namespace conflicts, floating branches, missing
  payloads, and web-video source attrition are unresolved reproducibility
  failures.

## 6. Adapter and download-gate attacks

### Controls that held

The local `tests_data` suite passed **20/20** on 2026-09-07. The implementation
does detect simple plan-body changes, detects manifest changes after planning,
rejects metadata-only draft manifests at execution, rejects unknown sizes when
a byte cap is requested, and ships no CLI transfer backend.

Those are useful controls, but they do not establish safe transfer.

### Controls that failed

1. **Mutable revision rejection is superficial** (`RT-036`). Provider-specific
   immutable formats are not enforced at every entry point.
2. **Revision and URL are not bound** (`RT-037`). A candidate may claim a SHA
   while using a `/resolve/main/` or unrelated URL.
3. **Repository license can leak into asset approval** (`RT-038`).
   `source.rightsholder_or_status=unknown_hold` is not independently rejected
   by the acquisition gate once other fields are manually flipped.
4. **Manifest and candidate are incompletely bound** (`RT-039`). Planning does
   not compare approved canonical URL, dataset, publisher, acquisition method,
   manifest byte size, or manifest content hash to the planned object.
5. **URL handling is unsafe for a future backend** (`RT-040`). Any HTTP(S)
   netloc is accepted; host allowlists, HTTPS-only rules, userinfo rejection,
   private-address rejection, port policy, DNS rebinding protection, and
   redirect validation are absent.
6. **A backend can ignore the plan** (`RT-041`). The abstract backend's result
   is not checked against range, size, checksum, URL, destination, or revision.
7. **Range accounting and stored request disagree** (`RT-042`). The cap is
   calculated from a clamped end, but the unclamped end is stored.
8. **Selection tampering is not detected** (`RT-043`). The download CLI ignores
   `selection_sha256`, policy, summary, and source snapshot hash.
9. **Approval is not authenticated** (`RT-044`). Nonempty strings pass for
   identity and timestamp; there is no signature or authorized-role lookup.
10. **Destination containment/collision checks are absent** (`RT-045`).
11. **Future resolver headers can leak credentials** (`RT-046`).
12. **The append-only audit log is not tamper-evident** (`RT-047`).
13. **There is no transfer backend** (`RT-048`). This is safe for the current
    CLI, but means the requested real-video step is not implemented; the
    abstract extension point is not safe enough to enable.

## 7. Rehearsal-plan attack

The rehearsal plan is a design target, not an evidenced sample plan.

Every row in `candidate_funnel.csv` still has:

- `release_item_id = TBD`;
- `release_revision = TBD`;
- `asset_locator_status = metadata_row_not_reconciled`;
- `current_stage = dataset_recon_pending`;
- `approval_status = PROVISIONAL_NOT_APPROVED`;
- a reason that says HF reconnaissance is absent, despite a separate
  reconnaissance document.

The modality slots are particularly unsupported:

- speech slots use LoVR/LongVidSearch or LongShOT candidates without verified
  original speech streams;
- ambient slots use LongVidSearch/LoVR, VES, TraceAV, or FLARE labels without
  verified non-speech audio;
- cross-modal slots infer audiovisual suitability from benchmark labels or
  generated captions rather than source stream/content evidence;
- no selected source has a pinned item, source-time map, completed audio probe,
  or duplicate-family clearance.

The plan correctly says technical audio and rights review are required, but its
preferred-candidate assignments must not be reported as achieved coverage.
Findings `RT-033` and `RT-034` require the funnel to be regenerated from the
reconciled release inventory before use.

## 8. Factual claims not confirmed from an official source

The following audited claims must remain explicitly unresolved rather than
being repeated as facts:

- FLARE “full” files are raw/pristine source videos.
- Every FLARE or Video-MME video contains usable audio.
- Audio captions identify speech, music, or ambient/non-speech categories.
- LoVR's effective dataset/media license is one specific CC license.
- LoVR reconstructed full videos are equivalent to pristine LongVideoBench
  files.
- LoVR or LongVidSearch supplies audio-bearing media or speech/ambient labels.
- LongVideoBench subtitles are complete, original, or independent speech
  transcripts for every source.
- LongVidSearch's 447 reported videos exactly match the 444 visible `vid`
  classes, or its evidence indices already map to absolute source time.
- LongShOT's current HF release is definitely gated or definitely ungated.
- LongShOT modality labels prove source audio or distinguish speech from
  ambient sound.
- LongShOT has been confirmed as Video-MME-derived; the stronger verified
  description is YouTube-oriented with unresolved overlap.
- Every TraceAV mapping resolves to OmniVideoBench, every mapped file has
  audio, or the `audio` label identifies a particular sound class.
- VES-Bench's hosted videos are licensed for acquisition or redistribution.
- VES-Bench has usable audio, known timestamp units, or a released official
  TRACE implementation.
- V-RAGBench currently contains selectable records, stable source IDs,
  serialized evidence boundaries, or an official executable implementation.
- V-RAGBench's current HF gate state is settled.
- EgoLife's HF MIT label and S-Lab license have a reconciled,
  artifact-specific scope.
- EgoLife `need_audio`, transcript SRT, or dense captions prove ambient/music
  coverage or file-level audio.
- Every Ego4D canonical video has an audio stream.
- Any short hash or `main` locator in the audited tables is a valid final
  immutable revision.
- The configured alternative HF namespaces are official aliases for the
  audited releases.

## Required remediation before gate changes

### Before freezing metadata selection

1. Refresh official HF/GitHub metadata with working network access and save the
   complete API responses and hashes.
2. Resolve all canonical repository IDs and full immutable revisions.
3. Reconcile LongShOT and V-RAGBench gate-status contradictions.
4. Parse the TraceAV source mapping and LongVidSearch/LoVR/LVB parent joins.
5. Build the three duplicate-family maps listed above.
6. Regenerate `candidate_funnel.csv` with real release item IDs/revisions.
7. Validate selection hashes and bind candidates to inspection snapshot hashes.

### Before requesting gated access

1. Define a named purpose and minimum file/UID list.
2. Record terms URL, exact text/hash, acceptance date, accepting identity, and
   downstream restrictions.
3. Request LongVideoBench or mapped OmniVideoBench access only for a
   metadata-selected subset.
4. Request Ego4D for V-RAGBench only after exact UIDs are available.
5. Do not use cookies, private browser sessions, or generic video downloaders
   as authority.

### Before any media transfer

1. Close `RT-001`, `RT-005`, `RT-009`, `RT-020`, `RT-021`, `RT-028`, and
   other applicable rights findings for each exact asset.
2. Close implementation findings `RT-036` through `RT-048`.
3. Add an approved provider-specific transfer backend and adversarial
   integration tests.
4. Enforce official-host allowlists, pinned object IDs, redirects, exact byte
   counts, ranges, destination containment, and hashes in trusted code.
5. Use authenticated approvals and tamper-evident audit records.

### Before real annotation

1. Complete acquisition and immutable content hashing.
2. Run a pinned `ffprobe` and human audio review.
3. Record speech, music, ambient/non-speech, mixed, silent, and unknown
   independently.
4. Verify source time bases and all evidence joins.
5. Complete privacy/safety and embedded-component review.
6. Confirm source disjointness and remove duplicates.
7. Populate the annotation template and reviewer assignments with real,
   independently approved records.

## Final conclusions

### Metadata-only candidate selection: **GO**

Proceed only with small official annotation/metadata artifacts that have a
verified canonical repository and full immutable revision. Do not select
V-RAGBench records that are not released, VES records whose schema is not
known, or any candidate on the basis of inferred audio.

### Requesting gated access: **GO**

Request narrowly scoped access to LongVideoBench, mapped OmniVideoBench, or
another independently justified official source after terms are captured.
Do not request V-RAGBench-related Ego4D media without exact UIDs. Access is not
media or redistribution approval.

### Downloading 3–5 real videos: **NO-GO**

No proposed source presently combines resolved rights, immutable object
identity, verified audio suitability, duplicate clearance, and a safe,
implemented transfer path.

### Starting real annotation: **NO-GO**

The rehearsal plan has no resolved assets and its modality coverage is
aspirational. Annotation must wait for completed acquisition, stream/content
verification, rights/privacy approval, timestamp validation, and source
disjointness.
