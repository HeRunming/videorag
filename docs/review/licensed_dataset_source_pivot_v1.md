# Licensed-dataset source pivot v1

**Task:** 152  
**Date:** 2026-09-23  
**Decision token:** `LICENSED_DATASET_SOURCE_PIVOT_REPAIR`  
**Authority created by this review:** none for media acquisition, annotation,
scientific execution, or public release.

## 1. Executive decision

Established, centrally managed research datasets are the preferred next source
pool for the event-centric AV-TRACE pilot. They are materially better than the
failed item-by-item web hunt on source identity, stable identifiers, temporal
metadata, annotation density, and reproducible access. They do **not** remove
the governing rights, privacy, source-group, audio, semantic-prescreen, or
release gates.

The pivot is `REPAIR`, not `READY`, because:

1. no exact six source-group IDs were enumerated before network work stopped;
2. no target dataset has local evidence of an accepted, current agreement for
   this project;
3. exact operative media terms are not locally archived for any proposed
   pilot source;
4. native audio has not been verified on any selected asset;
5. item-level untrimmed-duration distributions were not obtained from current
   official listings;
6. Assembly101, HD-EPIC, MECCANO, and CaptainCook4D do not have a locally
   pinned exact release plus license package in the collected evidence;
7. EPIC-KITCHENS' verified CC BY-NC 4.0 notice covers the annotation
   repository, not by itself the participant video/audio;
8. EgoLife has a locally recorded license conflict between Hugging Face
   metadata (`mit`) and the official repository's S-Lab License 1.0; and
9. the proposed six-source allocation is therefore a deterministic
   **selection contract**, not a frozen asset manifest.

The preferred conditional six-source pilot draws one leakage-safe source group
from each of:

1. Ego4D v2.1;
2. Ego-Exo4D V2, from a non-kitchen skilled-activity subset;
3. EPIC-KITCHENS-100 with EPIC-SOUNDS;
4. Assembly101;
5. HD-EPIC; and
6. EgoLife, conservatively grouped as the whole shared household-week lineage.

This gives four conservative lineage blocks: Meta/Ego, Oxford/EPIC,
Assembly101, and EgoLife. Ego4D and Ego-Exo4D do not count as two independent
publisher lineages; EPIC-KITCHENS and HD-EPIC do not count as two independent
publisher lineages. No more than two pilot groups come from either correlated
lineage.

MECCANO and CaptainCook4D remain named reserves. Network work stopped before
an official primary-source snapshot for either was collected in this task or
found locally, so their exact releases, terms, audio, and access routes are
`UNKNOWN_HOLD`; they cannot replace a pilot slot yet.

## 2. Governing constraints

This review applies Tasks 141, 144, and 149 and the project charter:

- the six-source pilot must contain 12 families, exactly two per source;
- source composition must be event-centric and capture-format-diverse rather
  than lecture/topic-diverse;
- at least two sources must pass human semantic non-speech-audio prescreens;
- at least two must pass human dynamic non-text-visual prescreens;
- source groups, not families, are split and resampled;
- selection and split assignment occur before question, support, or model
  outcomes are inspected;
- existing labels are leakage-prone seeds, not AV-TRACE H1/H2 truth;
- source-level reviewer blindness and the Task 149 role restrictions remain;
- no media or annotation work starts while an applicable rights field is
  `unknown_hold`; and
- no raw-media, annotation, transcript, feature, or public-benchmark release
  is inferred from dataset reputation, a downloader, an annotation license, or
  account login.

The newer Task 149 amendment permits a clearly labeled restricted internal
evaluation if later authorized. It does not make a licensed corpus a
release-ready public benchmark. Public-media and public-derived-artifact
rights remain separate decisions.

## 3. Evidence and network boundary

The user ordered all network work stopped and immediate finalization.

- Full media downloads: **0**.
- Media segments downloaded: **0**.
- Dataset asset listings successfully enumerated in Task 152: **0**.
- Successful official dataset-page responses collected in Task 152: **0**.
- One bounded EPIC page fetch failed before HTTP because the configured proxy
  hostname could not be resolved.
- A requested escalated retry was interrupted; no successful response or
  persisted body was observed.
- No network request was initiated after the stop instruction.
- No target dataset bytes or listings are present in the Hugging Face cache.

The review therefore uses only previously collected local records that
attribute their claims to official project pages, official documentation,
official repositories, or official Hugging Face metadata. Important local
inputs are:

- `docs/pilot/pilot_0_plan.md`, the original rights-first project execution
  plan;
- `docs/paper/cvpr_execution_blueprint.md`, the original CVPR execution
  blueprint;
- `docs/data/dataset_inventory.csv`, verified 2026-09-05;
- `docs/data/hf_dataset_recon.md`, official-source observations from
  2026-09-07;
- `docs/data/data_source_audit.md`;
- `docs/data/license_risk_register.md`;
- `docs/review/preflight_audit.md`;
- `docs/review/cross_document_conflicts.csv`;
- `data/hf_recon/dataset_releases.csv`;
- `data/hf_recon/redteam_findings.csv`;
- `data/hf_recon/snapshots/hf_api_DISLab_VRAG-Bench.json`; and
- `data/hf_recon/snapshots/hf_DISLab_VRAG-Bench_README_b491a12.md`.

No freshness later than those dated observations is claimed.

## 4. Current local credential and tooling readiness

| Capability | Observed status | Consequence |
|---|---|---|
| Hugging Face authentication | `hf auth whoami` succeeded. Account identity is intentionally omitted here. No token was printed. | Authentication exists in the current environment, but it proves neither dataset agreement acceptance nor access to any target repository. |
| Hugging Face target cache | No cached target repository was found for Ego4D, Ego-Exo4D, EPIC, Assembly101, MECCANO, CaptainCook4D, or HD-EPIC. | No offline asset listing can be claimed. |
| Proxy | Proxy variable names are present. The attempted official fetch failed because the proxy hostname could not be resolved. | Current general web route is not operational from the attempted command. |
| AWS credentials | No AWS credential environment variables or standard credentials file were found. | Ego4D's temporary-AWS-credential route is not ready. |
| Ego4D CLI | Not installed. | Ego4D selective listing/download is not ready. |
| AWS CLI | Not installed. | Direct AWS-backed inspection is not ready. |
| Dataset-specific agreement records | None found for the target datasets. | Access must be treated as absent even where an account is logged in. |

Secrets were neither read nor printed. The presence of a Hugging Face token
file was checked only as a boolean.

## 5. Candidate comparison

`YES—UNVERIFIED` below means the dataset-level evidence describes the
capability, but the selected source file still requires an authenticated
stream/container check. It does not mean local access.

| Candidate | Exact release/version evidenced locally | Exact license status | Untrimmed duration evidence | Native synchronized audio | Existing speech / non-speech labels | Current access |
|---|---|---|---|---|---|---|
| Ego4D | v2.1; CLI release 1.5.2 | Named Ego4D License Agreement; operative text not archived | 3,670 corpus hours; exact item quantiles absent; V-RAGBench's distinct Ego4D subset reports source videos over 1 h and 86 min mean, but gives no usable UIDs | Nullable metadata; AAC when present; selected-file status unknown | Narrations; subset-dependent AV speech/corrected transcription and task annotations; no universal non-speech-event taxonomy established | `NO_ACCESS_EVIDENCE`: no accepted agreement, temporary AWS credentials, or CLI |
| Ego-Exo4D | V2; 5,035 takes; 1,286.30 summed video hours, including 221.26 ego-hours | Named Ego-Exo4D agreement; exact text not archived | Wall-clock take/session distribution absent; summed camera-hours must not be treated as elapsed duration | `YES—UNVERIFIED`; modality varies | Narrations, task/temporal labels, camera pose; universal transcript or non-speech taxonomy not established | `NO_ACCESS_EVIDENCE`: no accepted agreement or official downloader |
| EPIC-KITCHENS-100 + EPIC-SOUNDS | 2020-100; EPIC-SOUNDS revision not pinned | Annotation repository: CC BY-NC 4.0; raw media terms unarchived | 700 videos / 100 h, arithmetic mean 8.57 min; local evidence says many are tens of minutes, but no exact distribution | `YES—UNVERIFIED`; EPIC-SOUNDS requires source audio | Narrations and dense action/object intervals; EPIC-SOUNDS has 78,366 categorized and 39,187 uncategorized events | `NO_ACCESS_EVIDENCE`: no terms-acceptance record or downloader credentials |
| Assembly101 | Exact release/version unresolved locally | Exact package license unresolved | Exact distribution withdrawn as unverified; earlier combined 4,321-video/513-hour/15-view figures must not be used for planning | Dataset-level source videos described as having audio; channel consistency unknown | More than 1M fine/coarse action annotations and mistakes; speech transcript not guaranteed; non-speech taxonomy not established | `NO_ACCESS_EVIDENCE`: HF login exists, but no official repo/version/package authorization is pinned |
| HD-EPIC | Exact release/version unresolved locally | Official agreement/terms named only; exact text unarchived | 156 videos / 41.3 h, arithmetic mean 15.88 min; exact distribution absent | Rich audio described; released-channel status unknown | Corrected participant narrations, action/object labels, and 51K audio events reported | `NO_ACCESS_EVIDENCE`: no registration/agreement record or listing |
| EgoLife | HF visible revision `143fb31`; official repository license revision `c0545c1` | Conflict: HF metadata says MIT; official repository and V-RAGBench say S-Lab License 1.0; stricter terms control pending clarification | About 300 h across six participants/seven days; V-RAGBench's distinct EgoLife subset uses >1 h videos and reports 379 min mean; direct item distribution absent | `YES—UNVERIFIED`; per-file audio not established | Timestamped transcripts and dense captions; QA has `need_audio`; no complete source-world non-speech taxonomy established | `METADATA_AUTH_ONLY`: HF login works, but no listing was run and media use is blocked by license/privacy review |
| MECCANO | Not established from collected official evidence | Unknown | Unknown | Unknown | Unknown | `NO_ACCESS_EVIDENCE`; reserve only |
| CaptainCook4D | Not established from collected official evidence | Unknown | Unknown | Unknown | Unknown | `NO_ACCESS_EVIDENCE`; reserve only |

## 6. Rights and permitted-use findings

### 6.1 Ego4D v2.1

- **Agreement:** Ego4D License Agreement / data-usage workflow. Exact operative
  text and acceptance event are not archived locally.
- **Research use:** the official workflow is research-focused, but this
  project has no evidence that a named user/institution accepted the current
  agreement. Current use decision: `UNKNOWN_HOLD`.
- **Annotation:** not affirmatively established for AV-TRACE's new
  claim/evidence graph. `UNKNOWN_HOLD`.
- **Derived outputs:** publication of aggregate research findings may be
  expected in a research agreement, but no exact clause was captured.
  Embeddings, transcripts, clips, thumbnails, and new annotations are separate
  derivative classes and remain `UNKNOWN_HOLD`.
- **Publication/release:** no raw redistribution. Public release of derived
  annotations or identifiers requires clause-level review.
- **Route:** registration, agreement acceptance, temporary AWS credentials,
  official `ego4d` CLI, and an explicit UID allowlist.
- **Privacy:** critical: faces, homes, voices, bystanders, location/context,
  routines, and potentially sensitive activity.

### 6.2 Ego-Exo4D V2

- **Agreement:** Ego-Exo4D V2 license agreement. The local official-source
  audit says the access page describes research and commercial coverage with
  redistribution and other restrictions; the exact agreement is not archived.
- **Research, annotation, derivative, publication:** all `UNKNOWN_HOLD` for
  this project until the signed form and exact clauses are reviewed. The
  dataset's availability after signing is not a grant to republish media or
  unrestricted derivatives.
- **Route:** official registration/license workflow and official tooling.
- **Privacy:** critical: multiple synchronized views amplify face, voice,
  location, and third-party exposure.
- **Long-form caution:** 1,286.30 hours is a sum across video streams. It
  cannot establish the elapsed duration of one synchronized take or session.

### 6.3 EPIC-KITCHENS-100 plus EPIC-SOUNDS

- **Exact covered license:** CC BY-NC 4.0 is verified only for the annotation
  repository in the local audit.
- **Raw video/audio:** media agreement/package terms are not archived.
  Acquisition, processing, annotation against media, derived media output, and
  raw release are `UNKNOWN_HOLD`.
- **Annotation reuse:** covered annotation files may be used only within the
  exact CC BY-NC 4.0 scope and attribution/non-commercial obligations. This
  does not resolve access to participant footage/audio.
- **Route:** accept the official terms and use the official downloader.
- **Privacy:** identifiable hands, kitchens/homes, voices, routines, and
  possible bystanders.
- **Scientific strength:** EPIC-SOUNDS is the strongest collected
  non-speech-event annotation source, but using its labels to choose or write
  AV-TRACE audio questions creates severe label leakage.

### 6.4 Assembly101

- **Release and license:** unresolved. The prior inventory's combined counts
  were explicitly withdrawn because the release/unit interpretation was not
  reproducible.
- **Research, annotation, derivative, publication:** all `UNKNOWN_HOLD`.
- **Route:** official project scripts and hosted packages are described, but
  no exact package, revision, license, or local authorization is frozen.
- **Privacy:** controlled capture reduces contextual risk relative to homes,
  but faces, voices, and participant identity remain.
- **Scientific strength:** synchronized multi-view assembly and mistake labels
  are excellent for dynamic non-text visual reasoning and repeated procedural
  stages. Exact native-audio coverage and coherent elapsed duration remain
  blockers.

### 6.5 HD-EPIC

- **Release and agreement:** official project/download path is recorded, but
  exact release and terms are not locally pinned.
- **Research, annotation, derivative, publication:** all `UNKNOWN_HOLD`.
- **Route:** apply/register through the official release.
- **Privacy:** critical because of high-resolution home/kitchen imagery,
  voices, identities, routines, and sensor-rich records.
- **Scientific strength:** reported corrected narrations and 51K audio events
  make it attractive for speech plus non-speech evidence. Existing labels must
  remain sealed during source selection and independent authoring.

### 6.6 EgoLife

- **Exact conflict:** official HF metadata was observed as `mit`; the official
  repository and V-RAGBench identify S-Lab License 1.0. The stricter custom
  license controls until maintainers clarify artifact-by-artifact scope in
  writing.
- **Research, annotation, derivative, publication:** all media-dependent uses
  are `UNKNOWN_HOLD`.
- **Route:** official HF release and repository instructions. Current HF login
  does not settle the license conflict or participant-data authority.
- **Privacy:** extreme: six identifiable people living together over a week,
  conversations, routines, shared residence, possible health and bystander
  information.
- **Source-count caution:** for leakage control the entire synchronized
  household-week is one source group. It cannot be split into seemingly
  independent participant-days for development and test.

### 6.7 MECCANO and CaptainCook4D

No official primary-source snapshot for either candidate was available in the
collected local evidence before the stop. No exact version, license,
download/auth route, duration distribution, audio guarantee, annotations, or
privacy terms may be claimed. Both remain `RESERVE_UNKNOWN_HOLD`, not pilot
sources.

## 7. Source-group definitions and leakage policy

The source group is deliberately broader than one file when participant,
scene, recording session, or synchronized-view overlap could leak content.

| Dataset | Conservative `source_group_id` root | Files that must remain together |
|---|---|---|
| Ego4D | participant/wearer plus continuous recording lineage; at minimum `origin_video_id` with all `video_component_uid` derivatives | all components, clips, narrations, features, encodes, and benchmark derivatives of that recording; participant-level split grouping if participant identity is available |
| Ego-Exo4D | participant/team × capture session/task/scene lineage; selected `take_uid` is nested inside the group | every synchronized ego/exo view, take derivative, pose stream, narration, and task annotation; repeated participants/scenes stay in one split |
| EPIC-KITCHENS-100 | participant/kitchen lineage | every recording, clip, narration, action/object annotation, and EPIC-SOUNDS event for that participant/kitchen |
| Assembly101 | participant × assembly-session lineage, with a stricter participant-level split block if participants repeat | all synchronized static/ego views, clips, action/mistake labels, and derivatives |
| HD-EPIC | participant/kitchen recording lineage | all high-resolution video, audio, sensor streams, narrations, and temporal labels from that participant/kitchen |
| EgoLife | entire shared household-week | all six participants, all ego/third-person synchronized media, transcripts, dense captions, QA, and derivatives |

Before final split freeze, a cross-dataset duplicate/participant/location
audit must also test EPIC-KITCHENS versus HD-EPIC and Ego4D versus Ego-Exo4D.
If identity or scene overlap cannot be ruled out, the affected groups form one
super-group and cannot occupy different splits.

### Existing-annotation leakage risk

| Candidate | Leakage risk | Required control |
|---|---|---|
| Ego4D | High: narrations and temporal task labels can reveal events and evidence intervals | selection team sees only rights, stream, duration, and nonsemantic capture fields; seal narrations/features until after source freeze; independently author from raw A/V |
| Ego-Exo4D | High: task labels, narrations, poses, and synchronized views can expose answer structure | seal semantic labels and nonselected views during initial authoring; treat alternate views as derived leaks in intervention closure |
| EPIC/EPIC-SOUNDS | Critical: action and sound-event timestamps directly nominate evidence | do not select groups or questions by label names/timestamps; independent raw-A/V authoring first; labels may be opened only for a declared post-authoring audit |
| Assembly101 | High: action and mistake labels expose procedural transitions and failures | selection uses nonsemantic metadata only; labels are evaluator-private during authoring and model runs |
| HD-EPIC | Critical: corrected narrations plus dense action/audio labels can answer candidate questions | seal all semantic annotations; use them only for blinded alternative-evidence and coverage audit after independent authoring |
| EgoLife | Critical: transcripts, dense captions, QA answers, target times, and `need_audio` can reveal both question and support | exclude all existing QA items and paraphrases; hash-based near-duplicate screen; source selection without text; seal transcripts/captions until post-authoring audit |

Existing annotations may improve auditing, but they never establish AV-TRACE
minimality, necessity, saturation, or H2.

## 8. Conditional exact six-source / 12-family pilot

### 8.1 Exact allocation

This is the exact allocation to be filled. It is **not** an exact asset list:
each `TBD_AFTER_LICENSED_LISTING` must be replaced by a canonical official ID
before Gate A can be reconsidered.

| Pilot source | Dataset-origin slot | Required source-group type | Families |
|---|---|---|---:|
| `LDS-P01` | Ego4D v2.1 | non-kitchen, continuous naturalistic recording lineage, native audio present, 20–90 min eligible untrimmed timeline | 2 |
| `LDS-P02` | Ego-Exo4D V2 | non-kitchen skilled-activity capture session with synchronized ego/exo views, native audio present, 20–90 min wall-clock timeline | 2 |
| `LDS-P03` | EPIC-KITCHENS-100 + EPIC-SOUNDS | one participant/kitchen lineage containing an eligible 20–90 min untrimmed recording with audio | 2 |
| `LDS-P04` | Assembly101 | one coherent assembly-session lineage with all views grouped, native audio, and a 20–90 min wall-clock timeline without concatenating unrelated takes | 2 |
| `LDS-P05` | HD-EPIC | one participant/kitchen lineage containing an eligible 20–90 min continuous sequence with released native audio | 2 |
| `LDS-P06` | EgoLife | one eligible native continuous file/session of 20–90 min from the household-week, while the entire household-week remains the leakage/source group; no arbitrary semantic trimming | 2 |

If a dataset has no qualifying coherent untrimmed group, the slot is not
filled by concatenation. It is replaced prospectively by a separately cleared
dataset lineage, with MECCANO and CaptainCook4D considered only after their
official evidence is captured.

### 8.2 Exact family matrix

| Family | Source | Profile target | Hop | Span | Intervention |
|---|---|---|---|---|---|
| `LDF01` | `LDS-P01` Ego4D | A | one | near | silent route withholding |
| `LDF02` | `LDS-P01` Ego4D | V+S+A | multi | far | explicit channel outage |
| `LDF03` | `LDS-P02` Ego-Exo4D | V | one | near | explicit channel outage |
| `LDF04` | `LDS-P02` Ego-Exo4D | V+S | multi | far | silent route withholding |
| `LDF05` | `LDS-P03` EPIC | A | one | near | silent route withholding |
| `LDF06` | `LDS-P03` EPIC | V+A | multi | far | explicit channel outage |
| `LDF07` | `LDS-P04` Assembly101 | V | one | near | explicit channel outage |
| `LDF08` | `LDS-P04` Assembly101 | V+S | multi | far | silent route withholding |
| `LDF09` | `LDS-P05` HD-EPIC | S+A | multi | far | silent route withholding |
| `LDF10` | `LDS-P05` HD-EPIC | V+S+A | multi | far | explicit channel outage |
| `LDF11` | `LDS-P06` EgoLife | S | one | near | silent route withholding |
| `LDF12` | `LDS-P06` EgoLife | S | one | near | explicit channel outage |

The matrix has:

- two each of `V`, `S`, `A`, `V+S`, `V+A/S+A`, and `V+S+A`;
- six one-hop and six multi-hop targets;
- six near/local and six far/separated targets; and
- six silent-route-withholding and six explicit-channel-outage targets.

These are authoring targets, not labels to force. Failure of speech presence,
semantic non-speech audio, dynamic non-text vision, sufficiency, minimality,
necessity, alternative-route closure, or shortcut checks rejects or replaces
the family/source. Quotas never override evidence.

### 8.3 Realistic sample sizes

- **Immediate pilot:** 6 source groups, 12 candidate families, 2 families per
  group, plus the two excluded calibrations required by Task 149.
- **Media listing request:** enumerate metadata only for the minimum candidate
  pool needed to choose one group per slot. Target 8–12 eligible groups per
  dataset before deterministic selection where the dataset permits; do not
  request broad media merely to discover candidates.
- **Pilot acquisition after GO:** one selected group plus one predeclared
  replacement group per dataset; acquire only the selected group initially.
- **Scale implication:** EgoLife contributes at most one independent
  household-week source group. EPIC/HD-EPIC and Ego4D/Ego-Exo4D are correlated
  lineages. These six datasets therefore cannot alone satisfy the final
  30-source/12-test-source diversity target; additional independent dataset
  lineages are mandatory.

## 9. Pre-outcome source selection protocol

The following procedure must be executed before questions, answers, evidence
intervals, human judgments, or model outcomes are inspected.

1. **Archive authority.** Save the exact release name, dataset manifest
   revision, agreement/terms text and hash, acceptance identity/date,
   institution/project scope, and artifact-specific decisions for
   acquisition, processing, annotation, derived outputs, publication,
   transcript release, annotation release, feature release, and raw-media
   release.
2. **Metadata-only enumerate.** Use the official authenticated listing route.
   Request identifiers, group/participant/session fields, wall-clock duration,
   stream metadata, capture format, task/domain category, and byte estimates.
   Do not download media.
3. **Build leakage blocks.** Apply Section 7 group definitions and cross-dataset
   overlap checks before sampling.
4. **Apply nonsemantic eligibility filters.**
   - exact official ID and release;
   - affirmative project access/processing/annotation authority;
   - 20–90 min coherent untrimmed wall-clock timeline;
   - native audio stream declared;
   - dynamic captured activity rather than lecture/slides;
   - no unresolved participant withdrawal or special restriction;
   - no known source overlap with current development material;
   - at most two kitchen groups across the six slots; and
   - required storage within the approved bounded acquisition budget.
5. **Keep semantic labels sealed.** Do not expose narration text, transcripts,
   action names, sound-event labels, QA, evidence intervals, mistake labels, or
   benchmark split outcomes to the selector.
6. **Deterministic rank.** Canonicalize each eligible official group ID and
   compute `SHA256("AVTRACE-LICENSED-PILOT-V1|" + dataset_release + "|" +
   source_group_id)`. Choose the lexicographically lowest hash in each slot.
   Freeze the next-lowest eligible group as the replacement. This selection
   must run once and be logged before content inspection.
7. **Freeze lineage/split.** Pilot groups are development-touched forever and
   ineligible for the future primary test split. All derivatives inherit the
   source group's split.
8. **Verify streams without semantic review.** After acquisition is separately
   authorized, check container, duration, time base, video motion, audio codec,
   sample rate, channels, synchronization drift, dropouts, and hashes.
9. **Run human source prescreens.** Only then run Task 149's semantic
   non-speech-audio and dynamic non-text-visual prescreens. Prescreeners cannot
   later serve as blind alternative finders or saturation auditors for the
   same group.
10. **Author independently.** Author from raw A/V without existing semantic
    labels. Open legacy annotations only in a later, logged leakage/coverage
    audit.

This procedure prevents favorable question/model outcomes from affecting
source inclusion and prevents dense upstream labels from silently becoming
the benchmark answer key.

## 10. Dataset-specific readiness and replacement order

### Conditional pilot order

1. **EPIC-KITCHENS-100 + EPIC-SOUNDS** — strongest structural match for
   non-speech audio, but blocked on raw-media terms and exact asset audio.
2. **Assembly101** — strongest distinct multi-view assembly lineage, but
   blocked on exact release/license/counts/duration/audio.
3. **Ego4D v2.1** — strongest long naturalistic pool, but blocked on agreement,
   CLI/AWS credentials, privacy, and selected-file audio.
4. **Ego-Exo4D V2** — strongest synchronized skilled-activity pool, but
   blocked on exact agreement and elapsed-duration/audio listing.
5. **HD-EPIC** — strong audio/narration source, but blocked on exact release,
   terms, privacy, and duration distribution.
6. **EgoLife** — strongest day-scale source, but highest privacy and leakage
   burden plus an unresolved license conflict.

This order is for rights/listing work, not outcome-conditioned scientific
preference.

### Reserve order

1. MECCANO;
2. CaptainCook4D.

Neither reserve may enter the deterministic draw until its official exact
release, license, permitted uses, listing route, duration distribution, audio
status, privacy terms, and source-group keys are captured.

## 11. Conditions for `LICENSED_DATASET_SOURCE_PIVOT_READY`

The decision may become `READY` only when all of the following are true:

1. exact current terms and release manifests are archived for all six selected
   dataset slots;
2. named project/institution access is actually accepted where required;
3. acquisition, internal processing, new annotation, restricted derived
   output, and aggregate publication are affirmatively allowed;
4. public-release decisions are separately recorded and never inferred;
5. official metadata-only listings produce canonical candidate IDs without
   media download;
6. source groups and correlated lineage blocks are frozen;
7. the deterministic pre-outcome draw yields six exact IDs plus replacements;
8. each selected group has a 20–90 min coherent untrimmed timeline;
9. each selected asset has verified synchronized native audio;
10. at least two selected sources pass semantic non-speech-audio prescreens;
11. at least two pass dynamic non-text-visual prescreens;
12. existing annotations are sealed and leakage controls pass;
13. privacy/withdrawal/storage/deletion controls are approved;
14. the exact 12 candidate records and Task 145 intervention manifests are
    frozen; and
15. Task 149's calibrations, reviewer roster, blindness, and Gate A conditions
    pass independently.

## 12. Final

Licensed datasets are the correct source-pool pivot, but the repository has
only dataset-level feasibility evidence, not exact item authority or exact
source readiness. No access, audio, annotation, derived-output, publication,
or release permission is claimed where the necessary credential/agreement or
clause evidence is absent.

`LICENSED_DATASET_SOURCE_PIVOT_REPAIR`
