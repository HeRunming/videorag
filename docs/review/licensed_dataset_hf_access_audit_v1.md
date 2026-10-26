# Licensed-dataset Hugging Face access audit v1

**Task:** 155  
**Date:** 2026-09-23  
**Decision token:** `LICENSED_DATASET_HF_ACCESS_REPAIR`  
**Authority created:** none for media acquisition, decoding, annotation,
evaluation, or release.

## 1. Decision

The authenticated Hugging Face access audit is **REPAIR**.

The current environment has an existing Hugging Face login, but Task 155 did
not obtain one successful provider response. Two completed search processes
made 18 metadata search attempts in total and failed at connection or proxy
name resolution. One separately escalated process was interrupted. After the
user ordered all network activity stopped, no further network request was
made.

Only **one exact official Hugging Face repository ID** is supported by the
retained local official-source evidence:

`lmms-lab/EgoLife`

Its live revision, current access state, and current-token tree listing could
not be refreshed. The retained evidence identifies only the short visible
revision `143fb31`, not a full immutable commit SHA. The repository was public
and ungated when inspected on 2026-09-07, but that historical observation is
not presented as a fresh access result.

No exact official Hugging Face repository ID is locally proven for the other
eight named subjects: Assembly101, HD-EPIC, Ego4D, Ego-Exo4D,
EPIC-KITCHENS, EPIC-SOUNDS, MECCANO, and CaptainCook4D. No third-party mirror
is treated as authoritative.

## 2. Exact counts

| Measure | Count |
|---|---:|
| Named dataset subjects | 9 |
| Exact official HF repo IDs confirmed from retained evidence | 1 |
| Exact official HF repo IDs newly confirmed live in Task 155 | 0 |
| Exact official repos with current-token tree/file listing proven | 0 |
| Exact official repos with historical public listing evidence | 1 |
| Historically public / gated / private exact official repos | 1 / 0 / 0 |
| Subjects without a proven exact official HF repo ID | 8 |
| Completed HF API search processes before stop | 2 |
| Completed term-search attempts | 18 |
| Successful HF API responses | 0 |
| Successful tree, file, README, or license fetches | 0 |
| Aborted escalated processes | 1 |
| Remote metadata payloads saved by Task 155 | 0 |
| Media files or bytes downloaded | 0 / 0 |
| Third-party mirrors accepted as authoritative | 0 |

The value “0 current-token listable repositories” means **zero proven
successes**, not a provider denial. The operative state is unknown because no
live provider response completed.

## 3. Authentication and network boundary

- The existing Hugging Face login is locally available.
- No token value or account identity was printed or written.
- Remote authentication was not confirmed in Task 155.
- The completed metadata searches failed before a successful HF response.
- The interrupted escalation produced no observable successful response or
  saved body.
- No process associated with the attempted searches remained running when
  finalization began.
- No network activity occurred after the explicit stop instruction.

This report therefore synthesizes the pinned local evidence already present
in the repository. It is not a claim about current Hugging Face state on
2026-09-23.

## 4. Exact repository audit

### 4.1 `lmms-lab/EgoLife`

| Required field | Finding |
|---|---|
| Genuine official repository | **Yes, based on retained official-source reconnaissance.** It is attributed to the EgoLife project laboratory and cross-referenced with the official `EvolvingLMMs-Lab/EgoLife` project repository. It is not treated as a third-party mirror. |
| Commit SHA | **Unresolved.** Retained evidence has visible short revision `143fb31`, observed 2026-09-07. A full immutable SHA was not captured. |
| Public/gated/private | Historically `PUBLIC_UNGATED_HIGH_RISK` as of 2026-09-07; gated `false`, private `false` in that dated observation. Current state was not refreshed. |
| Can the current token list the tree/files? | **Not verified.** Task 155 obtained zero successful provider responses and zero listings. This is not equivalent to access denial. |
| README/card metadata | Historical HF card license field: `mit`. Known layout describes six participant directories, `EgoLifeCap/DenseCaption`, `EgoLifeCap/Transcript`, `EgoLifeQA`, `EgoIT`, and Xet-backed media. Task 155 fetched no README body. |
| License metadata | Official project repository uses S-Lab License 1.0 at retained short revision `c0545c1`. This conflicts with the HF `mit` field. The stricter terms control pending written clarification. |
| File count | **Unknown.** The retained 32,001 viewer-row count is not treated as a repository file count. |
| Size | Historical estimate: about 512 GB total; `EgoLifeCap` about 49.6 MB. Exact total bytes were not captured. |
| Media packaging | Participant-oriented directory tree with Xet-backed video objects and separate caption, transcript, QA, and EgoIT trees. Exact archive/shard inventory is unknown. |
| Audio evidence | Project-level evidence says video/audio and environmental audio are captured. QA has a `need_audio` signal and timestamped transcript/dense-caption SRT is described. No selected file's audio stream was verified. |
| Access/use disposition | `UNKNOWN_HOLD`; do not acquire. The license conflict, missing full SHA, unverified live access, and very high participant privacy risk must be repaired first. |

`need_audio`, a transcript, or a dense caption does not establish that a
specific media object contains a usable audio stream, and it does not
characterize speech, music, or environmental sound for that object.

## 5. Named subjects without a proven exact official HF repo

| Subject | Exact official HF repo IDs proven | Fail-closed result | Authoritative route retained locally |
|---|---:|---|---|
| Assembly101 | 0 | Do not infer an ID from search-name matches. | Official project site and maintained download scripts. |
| HD-EPIC | 0 | No HF listing or repo status can be claimed. | Official HD-EPIC project site. |
| Ego4D | 0 | No official HF media mirror is proven; third-party loaders or mirrors are non-authoritative. | Official portal, license agreement, temporary AWS credentials, and Ego4D CLI. |
| Ego-Exo4D | 0 | No official HF media mirror is proven. | Official V2 portal, agreement, and official tooling. |
| EPIC-KITCHENS | 0 | Annotation or similarly named mirrors do not establish an official raw-media HF repository. | Official EPIC portal and downloader. |
| EPIC-SOUNDS | 0 | No exact official HF repository is proven. | Official EPIC project distribution route. |
| MECCANO | 0 | No retained primary-source HF evidence. | Unresolved. |
| CaptainCook4D | 0 | No retained primary-source HF evidence. | Unresolved. |

The absence of a proven exact repo ID is not evidence that no repository
exists. It means the audit cannot responsibly identify or authorize one from
the evidence available after network activity was stopped.

## 6. Strongest actionable next steps

These four datasets have the clearest bounded path to **metadata listing and
terms completion next**. They are not approved for media transfer.

### Priority 1 — Assembly101

**Why next:** retained official-source records say the project maintains
download scripts and may expose a Hugging Face route. The bounded missing
facts are the exact project-linked repo ID and package terms.

**Authorized user actions**

1. Open the official Assembly101 download page.
2. Record the exact HF repository ID only if the official project itself
   links it.
3. Archive the package-level license/terms and any gate form or acceptance
   record.
4. If no official link confirms an HF repo, use only the official project or
   cloud route and reject similarly named mirrors.

**Administrator actions**

1. Review research use, derivative annotations, privacy, retention, and
   redistribution for the exact package.
2. Approve a metadata-only listing of names, sizes, immutable revisions, and
   checksums.
3. Restrict any later plan to a selected view and exact files; do not approve
   the multi-view corpus.

### Priority 2 — EPIC-KITCHENS-100 plus EPIC-SOUNDS

**Why next:** the official portal/downloader route and annotation-license
evidence already exist. The raw video/audio terms remain the bounded gap.

**Authorized user actions**

1. Register or sign in through the official EPIC route.
2. Archive the current raw-media terms separately from the annotation
   repository's CC BY-NC notice.
3. Accept only after institutional review; retain the accepted release,
   timestamp, confirmation, and purpose.

**Administrator actions**

1. Confirm non-commercial compatibility and whether internal audio extraction
   and new annotations are permitted.
2. Approve only an official metadata or participant/kitchen listing first.
3. Record EPIC-KITCHENS and EPIC-SOUNDS artifact scopes separately. Do not
   propagate annotation licensing to raw media.

### Priority 3 — Ego4D v2.1

**Why next:** no official HF mirror is required. The official external
agreement, temporary AWS credential, and CLI route are known.

**Authorized user actions**

1. Apply through the official Ego4D portal for v2.1.
2. Have an institutionally authorized person review and accept the exact
   current Ego4D License Agreement.
3. Preserve the agreement text, submitted purpose, acceptance date, approval,
   and release scope.
4. Obtain temporary AWS credentials through the official process without
   storing secrets in the repository.

**Administrator actions**

1. Approve internal research, processing, new annotation, deletion, and
   publication obligations separately.
2. Install and pin the official CLI in a controlled environment.
3. Run a metadata-only list for `video_uid`, `origin_video_id`, component IDs,
   sizes, and audio metadata before approving any object.

### Priority 4 — Ego-Exo4D V2

**Why next:** the external V2 agreement and official route are known, although
no current acceptance or local official tooling is recorded.

**Authorized user actions**

1. Register at the official V2 portal and submit the exact intended use.
2. Have an authorized person execute and retain the current V2 agreement,
   approval, date, and release coverage.
3. Ask first for metadata sufficient to identify non-kitchen source groups.

**Administrator actions**

1. Classify the project under the agreement's applicable research/commercial
   provisions and review redistribution restrictions.
2. Approve official tooling for metadata-only enumeration.
3. Require grouping across participant/team, capture session, take,
   synchronized views, poses, and derivatives before any file request.

## 7. Held candidates

- **EgoLife:** hold for written MIT/S-Lab scope reconciliation, a full HF
  revision, current listing proof, and privacy review.
- **HD-EPIC:** hold until the exact release, agreement, official access route,
  and any official HF repository are pinned.
- **MECCANO:** hold because no official primary-source or exact HF repository
  evidence is retained.
- **CaptainCook4D:** same hold as MECCANO.

## 8. Conditions for `READY`

A future `READY` decision requires all of the following for at least the
selected next-source set:

1. exact official repo ID or official non-HF route verified from a
   project-maintained source;
2. full immutable provider SHA/release revision;
3. successful authenticated metadata/tree listing with no media transfer;
4. exact file count and total size from provider metadata;
5. archived README plus operative package license/agreement;
6. explicit separation of media, annotations, transcripts, derived outputs,
   and release rights;
7. media packaging and per-file audio declaration recorded;
8. accepted external gate evidence where applicable; and
9. a separate exact-file allowlist and internal approval before acquisition.

None of those requirements may be satisfied by a third-party mirror,
repository popularity, a permissive code license, or public technical access.

## 9. Saved evidence

Small, non-provider snapshots were written under:

- `data/hf_recon/licensed_source_access_v1/run_summary.json`
- `data/hf_recon/licensed_source_access_v1/repo_lmms-lab__EgoLife.json`
- `data/hf_recon/licensed_source_access_v1/subject_resolution.json`

They are explicitly local evidence syntheses, not live Hugging Face response
bodies. No media shard, archive, thumbnail, sample, or large data file was
downloaded.

## 10. Final

`LICENSED_DATASET_HF_ACCESS_REPAIR`
