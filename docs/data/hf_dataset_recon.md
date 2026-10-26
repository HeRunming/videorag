# Hugging Face and official-release reconnaissance

**Evidence cutoff:** 2026-09-06  
**Live verification:** 2026-09-07, Asia/Shanghai  
**Scope:** FLARE / Video-MME; LoVR / LongVideoBench; LongVidSearch;
LongShOTBench; TraceAV-Bench; TRACE / VES-Bench; V-RAGBench / EgoLife /
Ego4D.  
**Acquisition constraint:** no video, audio, thumbnail, archive, LFS/Xet
object, feature shard, or complete dataset was downloaded.

**Date convention:** 2026-09-05 is the normative design freeze; 2026-09-06 is
the claims/evidence cutoff; 2026-09-07 is the live access-observation and
planning date.

This is a one-day retrospective verification. A revision with a dated release
before 2026-09-06 is reported as-of the requested cutoff. Where an official
site exposed only a live branch, relative timestamp, short hash, or file-level
revision, the full repository revision is marked
`UNRESOLVED_FULL_REVISION`. Short and file-level revisions remain useful
evidence leads but are not candidate-freeze revisions.

The inventory separates five concepts that must not be collapsed:

1. observed technical access route;
2. rights status;
3. artifact-license status and scope;
4. source-media rights;
5. episode publication class.

It also labels verified surface facts, upstream source claims, inferences, and
unresolved values. `observed_official_access_route` replaces the misleading
`authorized_acquisition_method`; actual authorization exists only in a
reviewed asset-level acquisition manifest.

## 1. Decision summary

1. **Highest-priority metadata lead for a possible later rehearsal: FLARE demo,
   conditional.** The official
   demo packages two source videos, three clips per source, and matching JSONL
   artifacts. It directly exercises visual, audio, and hard-bimodal retrieval.
   It must remain private/research-only until the conflict between FLARE's
   `cc-by-4.0` card field and Video-MME's stricter upstream terms is resolved.
   Official URL: `https://huggingface.co/datasets/AnonymousFLARE/FLARE_demo`;
   revision `a7e85c0`; accessed 2026-09-07. Evidence: the official card
   describes `sample_0` and `sample_1`, each with a full source video, three
   consecutive clips, and associated JSONL files.
2. **Highest-priority annotation-first metadata lead: TraceAV-Bench.** Its 8.81 MB public
   annotation release includes question IDs, answer choices, modality-labelled
   evidence trajectories, and timestamp-bearing trajectory serialization.
   Media are not hosted there and must be resolved through the official mapping
   and gated upstream source. Official URL:
   `https://huggingface.co/datasets/Heinz217/TraceAV-Bench`; revisions
   `cc96f31` and data commit `22ea02b`; accessed 2026-09-07.
3. **Best direct SES precedent: LongVidSearch, followed by VES-Bench.**
   LongVidSearch explicitly releases 2–4 necessary slice indices for each
   multi-hop item. VES-Bench pairs questions with jointly necessary temporal
   intervals. LongVidSearch lacks verified audiovisual media/timestamps in its
   own release; VES-Bench lacks a dataset license and documented upstream
   provenance.
4. **Best rubric and open-ended-answer compatibility source: LongShOTBench.**
   The 11.10 MB JSONL release has 3,401 questions, conversations, modality
   labels, difficulty, and weighted positive/penalty criteria, but no released
   gold evidence spans or transcripts.
5. **V-RAGBench is not executable from its current visible release.** The
   public HF repository is approximately 10.5 kB and exposes no supported
   benchmark data file. Its paper specifies 2,100 query–evidence–answer
   triplets over 216 Ego4D/EgoLife videos, but source IDs, serialized evidence
   boundaries, and splits remain `unverified`.
6. **No examined HF publication is sufficient evidence of raw-media
   redistribution rights.** Every raw-media decision remains separate from
   code, annotation, paper, and dataset-card licenses.

The row-level release inventory is in
[`../../data/hf_recon/dataset_releases.csv`](../../data/hf_recon/dataset_releases.csv).
The field-level mapping is in
[`../../data/hf_recon/artifact_field_mapping.csv`](../../data/hf_recon/artifact_field_mapping.csv).
No ranking or technical route in this document authorizes transfer, playback,
content review, annotation, or publication.

## 2. Release matrix

| Source | Current official release | Access and payload | High-value artifacts | Principal blockers | Official URL / revision / access / evidence |
|---|---|---|---|---|---|
| FLARE | `AnonymousFLARE/FLARE`; about 71.2 GB | Public, ungated; `datas/` and `videos/`; exact media inventory below those directories `unverified` | 87,697 scene clips; vision/audio/unified captions; 274,933 queries; 399 Video-MME sources, 10–60 min, 225.4 h | Upstream Video-MME terms conflict with a broad reading of the HF `cc-by-4.0` field; clip timestamps and in-container audio are `unverified` | `https://huggingface.co/datasets/AnonymousFLARE/FLARE/tree/main`; `ed89d86`; accessed 2026-09-07. Official tree and paper `https://arxiv.org/abs/2605.10228v1`. |
| FLARE demo | `AnonymousFLARE/FLARE_demo` | Public, ungated; two small examples containing source video, three clips, and JSONL | Minimal end-to-end multimodal retrieval package and documented unimodal-failure examples | Same Video-MME rights issue; exact bytes and container audio `unverified` | `https://huggingface.co/datasets/AnonymousFLARE/FLARE_demo/blob/main/README.md`; `a7e85c0`; accessed 2026-09-07. |
| Video-MME | `lmms-lab/Video-MME`; about 101 GB | Public technical access; four video ZIPs, subtitle ZIP, one 405 kB Parquet | 900 video IDs/URLs, 2,700 MCQs, options/answers, duration/domain/task fields, subtitle archive | Academic-only; commercial use prohibited; redistribution/modification require prior approval; no evidence timestamps | `https://huggingface.co/datasets/lmms-lab/Video-MME/tree/3f70174ae54164dec63098b23704e2858d40169a`; accessed 2026-09-07. Terms at `https://github.com/MME-Benchmarks/Video-MME/blob/main/README.md`, `06c2315`. |
| LoVR | `debugger123/LoVR-benchmark`; about 95.9 GB | Public; four caption Parquets and three multipart media files | 467 parent videos; 40,804 scene clips; clip/video captions; `vid`, `path`, `slice_num`, `cap`, `theme_info` | Conflicting HF license displays; upstream LongVideoBench rights; absolute clip times and audio `unverified` | `https://huggingface.co/datasets/debugger123/LoVR-benchmark`; tree `5a46a68`, README `907eb91`; accessed 2026-09-07. |
| LongVideoBench | `longvideobench/LongVideoBench` plus public `LongVideoBench-Meta` | Full data gated; metadata public. Full tree has multipart MP4 tar, subtitle tar, JSON and Parquet; visible video parts alone exceed 62.8 GB | 3,763 videos, 6,678 MCQs, validation answers, timestamped subtitle cues, subtitle offset, duration and categories | Non-commercial gate; explicit upstream ownership disclaimer; complete size and audio streams `unverified`; test answers withheld | `https://huggingface.co/datasets/longvideobench/LongVideoBench`, README `60d1c89`; metadata files `cdf3444` and `99f42be`; accessed 2026-09-07. |
| LongVidSearch | `Fishiing/LongVidSearch`; about 328 MB | Public, ungated; QA JSON, per-video JSON, caption Parquet, embeddings, code; no raw video observed | 3,000 QA rows; 2–4 necessary `evidence_slices`; reasoning chains and visual proof | 447 reported videos versus 444 visible `vid` classes; slice-to-time join, audio, benchmark split, and media rights `unverified` | `https://huggingface.co/datasets/Fishiing/LongVidSearch`; `96cdf54`; accessed 2026-09-07. |
| LongShOTBench | `MBZUAI/longshot-bench`; 11,095,822 data bytes | Public, ungated; one `postvalid_v2_test.jsonl`; no raw media | 3,401 open-ended single/multi-turn items, reference answers, modality tags, difficulty, weighted criteria | No gold evidence spans, transcript, or clip boundaries; source acquisition is YouTube-oriented; source rights and per-file audio `unverified` | `https://huggingface.co/datasets/MBZUAI/longshot-bench/blob/main/README.md`; `b559813`; accessed 2026-09-07. |
| TraceAV-Bench | `Heinz217/TraceAV-Bench`; 8.81 MB | Public, ungated annotations only; 15 task JSONLs plus mapping | 2,200 MCQs; 578 videos / 339.5 h; modality-labelled `trajectory_with_timestamps`; explicit answer distractors | Media are upstream/gated; exact nested timestamp keys and transcripts `unverified` | `https://huggingface.co/datasets/Heinz217/TraceAV-Bench/tree/main`; `cc96f31`, data `22ea02b`; accessed 2026-09-07. |
| TRACE / VES-Bench | `buaaplay/VES-Bench`; 17.9 GB | Public, ungated; `VES-Bench.parquet` and `videos/` | 600 four-choice questions over 348 videos; jointly necessary evidence intervals | No dataset card/license; upstream provenance, durations, audio, exact Parquet schema, and benchmark splits `unverified` | `https://huggingface.co/datasets/buaaplay/VES-Bench`; HF `main`, immutable SHA `unverified`; accessed 2026-09-07. Repository `main@15e8c7e`. |
| V-RAGBench | `DISLab/VRAG-Bench`; about 10.5 kB | Public card, but no supported data file identifiable | Paper-defined 2,100 open-ended query/evidence/answer triplets over 216 1–9 h videos | Current payload incomplete; IDs, evidence boundaries, splits, features, audio, and code `unverified` | `https://huggingface.co/datasets/DISLab/VRAG-Bench`; `main`, immutable SHA `unverified`; accessed 2026-09-07. Paper `arXiv:2606.13141v1`. |
| EgoLife | `lmms-lab/EgoLife`; about 512 GB | Public, ungated UI; raw video and annotation trees, Xet-backed | Six participant directories; transcript and dense-caption SRT; Jake QA JSON with `need_audio`, `target_time`, choices and reason | HF says `mit`, GitHub says S-Lab License 1.0; complete 3K QA release and per-file audio `unverified`; high privacy risk | `https://huggingface.co/datasets/lmms-lab/EgoLife`; HF `main`, visible `143fb31`; accessed 2026-09-07. License `https://github.com/EvolvingLMMs-Lab/EgoLife/blob/main/LICENSE`, `c0545c1`. |
| Ego4D | Ego4D v2.1 via official portal/CLI | Request-only/licensed; official AWS distribution, not an official HF media release | Stable UIDs, clip boundaries, optional audio metadata, narrations/transcriptions, features, task splits | Exact V-RAGBench UID list unavailable; agreement text and redistribution permission must be reviewed; selected-file audio `unverified` | `https://ego4d-data.org/docs/start-here/` and `https://ego4d-data.org/docs/CLI/`; accessed 2026-09-07; CLI release `1.5.2`, 2023-12-15. |

## 3. Detailed findings

### 3.1 FLARE and Video-MME

FLARE's official release hierarchy is:

```text
AnonymousFLARE/FLARE/
├── .gitattributes
├── FLARE.png
├── README.md
├── datas/
└── videos/
```

The indexed viewer exposed nine configurations:
`clip-caption-{audio,vision,unified}`,
`query-{audio,vision,unified}`, and
`video-caption-{audio,vision,unified}`. The directly inspected
`clip-caption-audio` configuration used a `test` split and exposed
`video_path` plus `audio_caption`; a sample path used the convention
`jWa2yrLGxCM/jWa2yrLGxCM-Scene-001.wav`. Exact schemas for the other
configurations are `unverified`. Official URL:
`https://huggingface.co/datasets/YqjMartin/FLARE`; live publication now
appears as `AnonymousFLARE/FLARE`; accessed 2026-09-07. Evidence: official HF
viewer and release tree.

FLARE reports 399 screened Video-MME sources, 87,697 clips, 225.4 hours, and
274,933 queries: 86,350 vision-only, 135,003 audio-only, and 53,580
cross-modal. Its hard-bimodal filter requires a cross-modal query to fail with
either modality alone and succeed with both. Official URL:
`https://arxiv.org/abs/2605.10228v1`; arXiv v1 dated 2026-05-11; accessed
2026-09-07.

The FLARE card field is exactly `license: cc-by-4.0`, located in the HF
README YAML. No separate release-wide legal text or clear statement that this
license sublicenses Video-MME media was verified. Video-MME's official README
instead states, in relevant part, that Video-MME is for academic research only,
commercial use is prohibited, source-video copyright remains with video
owners, and distribution/publication/copying/dissemination/modification
requires prior approval. Official URL:
`https://github.com/MME-Benchmarks/Video-MME/blob/main/README.md`; revision
`06c2315`; accessed 2026-09-07. **Disposition:** FLARE annotations can be
inspected under the published card; media reuse and redistribution remain on
hold.

Video-MME's HF tree at
`3f70174ae54164dec63098b23704e2858d40169a` contains:

```text
subtitle.zip                            7.49 MB
videos_chunked_01.zip                  26.7 GB
videos_chunked_02.zip                  26.7 GB
videos_chunked_03.zip                  26.7 GB
videos_chunked_04.zip                  21 GB
videomme/test-00000-of-00001.parquet    405 kB
```

Its sole `test` split has 2,700 rows and fields `video_id`, `duration`,
`domain`, `sub_category`, `url`, `videoID`, `question_id`, `task_type`,
`question`, `options`, and `answer`. Subtitle internals, gold evidence
timestamps, and audio streams inside the hosted archives are `unverified`.
Official URL:
`https://huggingface.co/datasets/lmms-lab/Video-MME/tree/3f70174ae54164dec63098b23704e2858d40169a`;
accessed 2026-09-07.

### 3.2 LoVR and LongVideoBench

LoVR is derived from LongVideoBench and reports 467 long videos and 40,804
fine-grained clips, with averages of about 25.3 minutes per source and 17.9
seconds per clip. Official URLs: `https://arxiv.org/abs/2505.13928` and
`https://github.com/TechNomad-ds/LoVR-benchmark`; paper v4 dated 2026-02-04,
GitHub visible `main@d7ee1f5`; accessed 2026-09-07.

Its official HF layout is:

```text
caption_data/
  clip_train.parquet
  clip_test.parquet
  video_train.parquet
  video_test.parquet
scripts/
  merge_clips.py
video_data/
  part_aa
  part_ab
  part_ac
```

The three parts reconstruct a gzip tar of segmented clips. Full videos are
reconstructed by concatenating clip folders, so they are not documented as
pristine upstream files. The observed clip viewer fields are `path`, `vid`,
`slice_num`, `cap`, and `theme_info`. Although the GitHub README illustrates
`start_time` and `end_time`, those fields were not present in the inspected
viewer; absolute boundaries are therefore `unverified`. Official URL:
`https://huggingface.co/datasets/debugger123/LoVR-benchmark`; tree
`5a46a68`, README `907eb91`; accessed 2026-09-07.

LoVR's dataset license is unresolved: the HF header displayed
`cc-by-nc-sa-4.0`, while an indexed README revision displayed
`license: cc-by-4.0`; the GitHub code repository is MIT. None establishes a
media sublicense from LongVideoBench. Treat the effective data/media license
as `unverified`.

LongVideoBench's full HF dataset is gated. The gate requires non-commercial
use and acceptance of `CC-BY-NC-SA 4-0`, while acknowledging that the
benchmark did not create or own the linked videos and may remove material at
source owners' request. The public metadata repository exposes validation and
test Parquets totaling about 2.04 MB, with fields:

```text
video_id, id, video_path, subtitle_path, correct_choice, question,
option0..option4, duration, duration_group, question_category,
topic_category, starting_timestamp_for_subtitles
```

Validation has 1,337 questions; test has 5,341 and withholds ground truth.
The official loader accepts subtitle entries as either
`{"timestamp":[start,end],"text":"..."}` or
`{"start":"...","end":"...","line":"..."}` and applies
`starting_timestamp_for_subtitles` when aligning them to the video segment.
Official URLs:
`https://huggingface.co/datasets/longvideobench/LongVideoBench` and
`https://huggingface.co/datasets/longvideobench/LongVideoBench-Meta`;
README `60d1c89`, metadata file revisions `cdf3444` and `99f42be`; accessed
2026-09-07.

### 3.3 LongVidSearch

LongVidSearch's public HF release is approximately 328 MB and includes
`full-QA(3000).json` (5.16 MB), per-video QA JSON files,
`video-caption.parquet`, `video_embeddings/`, code, and small supporting
artifacts. No raw video directory or MP4 was observed. Official URL:
`https://huggingface.co/datasets/Fishiing/LongVidSearch`; visible revision
`96cdf54`; accessed 2026-09-07.

The viewer exposes:

```text
question
answer
category
hop_level
evidence_slices
reasoning_chain
logic_check_reasoning
visual_proof
vid
original_text_answer
verdict_meta
```

All 3,000 rows are under HF's `default/train`. `evidence_slices` has length
2–4. A visible example used `vid=-7wwfGJXEZg` and evidence slices `[1,48]`.
The benchmark defines each Hop-\(k\) question to require exactly \(k\)
clips, becoming unsolvable when any is removed. This is the closest released
artifact to an AV-TRACE SES seed. Official URLs:
`https://longvidsearch.github.io/` and
`https://arxiv.org/abs/2603.14468`; arXiv v1 submitted 2026-03-15; accessed
2026-09-07.

The paper/README reports 447 source videos, but the HF viewer reported 444
distinct `vid` classes. The difference is `unverified`. The release gives
slice indices rather than absolute times; an exact join to LoVR boundaries is
also `unverified`. Both GitHub and HF display MIT, but the license cannot be
propagated to upstream LoVR/LongVideoBench media.

### 3.4 LongShOTBench

The current HF release has one config, `postvalid_v2`, one `test` split, and
one file, `postvalid_v2_test.jsonl`, containing 3,401 examples and
11,095,822 bytes. It declares:

```text
video_id, duration, categories, sample_id, sample_type, scenario, task,
conversations[{content, conversation_role}],
criteria[{category, description, is_penalty, name, score, weight}],
difficulty, modalities, role
```

Official URL:
`https://huggingface.co/datasets/MBZUAI/longshot-bench/blob/main/README.md`;
revision `b559813`; accessed 2026-09-07.

The current paper reports 274 videos, about 188 hours, 41.3-minute mean,
40.9-minute median, and a 7.8–89.7-minute range. No raw video, URL field,
gold evidence timestamps, clip boundaries, released transcript, audio
caption, visual description, or explicit distractor field appears in the HF
schema. LongShOTAgent can locally produce Whisper transcripts, SigLIP/text
embeddings, refined clips, and claim-verification outputs, but these are
runtime products rather than released benchmark annotations. Official URL:
`https://arxiv.org/abs/2512.16978`; v2 dated 2026-06-16; accessed
2026-09-07.

The exact HF field is `license: cc-by-nc-sa-4.0`. The source repository's
README badge says `License: CC BY-NC-SA 4.0`, but license scope across code,
annotations, and upstream YouTube media is `unverified`. The repository
provides a YouTube downloader using user-supplied authentication/cookies;
this is a technical workflow, not proof of rightsholder authorization.

### 3.5 TraceAV-Bench

TraceAV-Bench and TRACE/VES-Bench are separate projects. TraceAV-Bench is the
audio-visual trajectory benchmark at arXiv `2605.07593`; TRACE/VES-Bench is
the evidence-coverage work at arXiv `2608.22516`.

TraceAV's 8.81 MB HF release contains 15 task JSONLs plus
`video_name_mapping.jsonl`. Observed task fields are:

```text
task_type, question_id, video_id, question, options, question_type,
correct_options, answer_text, minute_hop_count, hop_length_label,
trajectory_with_timestamps, difficulty
```

A visible trajectory object contained `event_id`, `evidence`, `label`, and
`reason`, with `audio` observed as a modality label. Exact nested timestamp
keys and interval semantics remain `unverified`. All configurations appear
under a packaging split named `train`; no authored train/dev/test partition
was found. Official URL:
`https://huggingface.co/datasets/Heinz217/TraceAV-Bench`; root `cc96f31`,
data `22ea02b`; accessed 2026-09-07.

The benchmark reports 578 unique videos, 2,200 questions, 339.5 hours,
606–8,394 seconds per video, about 35 minutes mean, 3.68 hops per trajectory,
and a 15.1-minute mean trajectory span. Official URL:
`https://arxiv.org/abs/2605.07593`; v2 dated 2026-08-29; accessed
2026-09-07.

The exact release statement applies CC BY 4.0 to **annotations and
accompanying code**. It does not license upstream videos. The README includes
a takedown contact. Media are obtained by resolving the mapping and using the
official gated `NJU-LINK/OmniVideoBench` release where indicated.

### 3.6 TRACE / VES-Bench

The separate VES-Bench release is public, approximately 17.9 GB, and documents
`VES-Bench.parquet` plus `videos/`. It reports 600 four-choice Temporal
Ordering/Event Counting questions over 348 public long videos. Each item has a
jointly necessary set of temporal evidence intervals, evaluated at three
coverage strictness levels. Official URLs:
`https://github.com/buaa-colalab/TRACE` and
`https://huggingface.co/datasets/buaaplay/VES-Bench`; repository
`main@15e8c7e`, HF immutable SHA `unverified`; accessed 2026-09-07.

The repository contains only `assets/` and `README.md` and says method code is
coming soon. The HF dataset has no dataset card and no visible license field.
Exact Parquet columns, IDs, timestamp units, video formats, durations, audio,
subtitle/transcript fields, and benchmark split definitions are `unverified`.
Public hosting is not a redistribution grant.

### 3.7 V-RAGBench, EgoLife, and Ego4D

V-RAGBench's current visible HF repository is only about 10.5 kB and the viewer
detects no supported data file. The paper specifies 2,100 open-ended
query–evidence-chunk–answer triplets over 216 Ego4D/EgoLife videos spanning
1–9 hours. The card's license token is
`egolife-slab-1.0-and-ego4d` and is displayed as `other`. Exact source IDs,
serialized evidence intervals, splits, features, and code remain
`unverified`. Official URLs:
`https://huggingface.co/datasets/DISLab/VRAG-Bench` and
`https://arxiv.org/abs/2606.13141`; HF `main`, arXiv v1 dated 2026-06-11;
accessed 2026-09-07.

EgoLife's visible release is approximately 512 GB with 32,001 HF viewer rows.
The root includes six participant directories plus `EgoLifeCap`,
`EgoLifeQA`, and `EgoIT`. Timestamped `.srt` files are available for
transcripts and dense captions; one visible 591 kB QA file is
`EgoLifeQA_A1_JAKE.json`. The QA schema shown in the official EgoRAG README
includes `ID`, `query_time`, `type`, `need_audio`, `need_name`, `last_time`,
`trigger`, `question`, `choice_a`–`choice_d`, `answer`, `target_time`,
`keywords`, and `reason`. Official URLs:
`https://huggingface.co/datasets/lmms-lab/EgoLife` and
`https://github.com/EvolvingLMMs-Lab/EgoLife/blob/main/EgoRAG/README.md`;
visible revisions `143fb31` and `b39c8f6`; accessed 2026-09-07.

EgoLife's HF metadata says `mit`, while the official repository has
**S-Lab License 1.0** and V-RAGBench also characterizes EgoLife that way.
The exact scope conflict is unresolved. Treat the stricter S-Lab conditions
as operative pending written clarification.

Ego4D is request-only/licensed. The current formal data release is v2.1; the
CLI release is 1.5.2. Official documentation reports approximately 3,670
hours, about 7.1 TB for the primary dataset and more than 30 TB for the whole
distribution. Canonical videos are normalized to 30 FPS VP9 with AAC audio,
but metadata permits null audio fields. The authorized route is license
acceptance, temporary AWS credentials, and the official `ego4d` CLI; use
`--video_uid_file` once V-RAGBench publishes its source IDs. Official URLs:
`https://ego4d-data.org/docs/start-here/`,
`https://ego4d-data.org/docs/CLI/`, and
`https://ego4d-data.org/docs/data/metadata/`; accessed 2026-09-07.

## 4. Cross-source AV-TRACE mapping

The authoritative row-level mapping is in
`data/hf_recon/artifact_field_mapping.csv`. The main conclusions are:

- **Source asset:** directly represented by IDs in every usable release, but
  media resolution is conditional for LongVidSearch, LongShOT, TraceAV, and
  V-RAGBench.
- **Evidence unit:** strongest in LongVidSearch (`evidence_slices`),
  TraceAV (`trajectory_with_timestamps`), VES-Bench (jointly necessary
  intervals), FLARE (scene clip), and timestamped EgoLife/LongVideoBench SRT.
- **Modality:** strongest explicit labels are FLARE's
  audio/vision/unified configurations, TraceAV's trajectory labels and task
  prefixes, LongShOT's `modalities`, and EgoLife's `need_audio`.
- **Claim:** no source provides AV-TRACE-normalized atomic claims. LongShOT
  criteria, LongVidSearch reasoning chains, and question-plus-answer pairs are
  candidate inputs requiring controlled transformation and review.
- **SES proposal:** LongVidSearch's necessary slice set and VES-Bench's jointly
  necessary interval set are the strongest direct seeds. They are not
  automatically accepted AV-TRACE SESs: AV-TRACE still requires exhaustive
  alternative search and independent minimality/satisfiability validation.
- **Distractor:** explicit answer distractors exist in multiple-choice sources;
  temporal/retrieval distractors usually must be derived and must not be
  mislabeled as source annotations.
- **Transcript:** direct timestamped text is strongest in EgoLife SRT and
  LongVideoBench subtitle JSON. Generated captions from FLARE/LoVR and
  evidence descriptions from TraceAV are not transcripts.
- **Clip boundary:** direct or near-direct in VES-Bench, TraceAV, EgoLife SRT,
  LongVideoBench subtitle cues, and possibly LoVR after schema reconciliation.
- **Question/answer:** direct in LongVidSearch, LongShOT, TraceAV, VES-Bench,
  Video-MME, LongVideoBench, V-RAGBench conceptually, and EgoLife QA.

## 5. Ranked uses

### 5.1 Conditional rehearsal discovery order

| Rank | Source | Use | Conditions | Official URL / revision / access / evidence |
|---:|---|---|---|---|
| 1 | FLARE demo | Two-source end-to-end audiovisual retrieval rehearsal | Private research workspace; resolve Video-MME terms; inspect JSONL before media; no redistribution | `https://huggingface.co/datasets/AnonymousFLARE/FLARE_demo`; `a7e85c0`; accessed 2026-09-07. Card states source videos, clips, and JSONL are bundled. |
| 2 | TraceAV-Bench small mapped subset | Multi-hop AV QA and trajectory rehearsal | Pin annotation revision; inspect mapping; obtain only mapped upstream files through official gate; verify audio | `https://huggingface.co/datasets/Heinz217/TraceAV-Bench`; `cc96f31`/`22ea02b`; accessed 2026-09-07. |
| 3 | LongVideoBench validation subset | Subtitle-grounded QA rehearsal | Use public metadata first; accept the full-data gate; select a small validation subset; no raw redistribution | `https://huggingface.co/datasets/longvideobench/LongVideoBench-Meta`; `cdf3444`; accessed 2026-09-07. |
| 4 | EgoLife Jake text/SRT subset | Transcript, target-time, audio-required, and distractor adapter rehearsal | Text only initially; resolve S-Lab/MIT conflict before broader copying; no participant media | `https://huggingface.co/datasets/lmms-lab/EgoLife/tree/main/EgoLifeQA`; `a305851`; accessed 2026-09-07. |

### 5.2 Full benchmark candidates

| Rank | Source | Rationale | Blocking conditions | Official URL / revision / access / evidence |
|---:|---|---|---|---|
| 1 | TraceAV-Bench | Best combined QA, audio/visual task coverage, multi-hop trajectory, timestamps, and distractors | Upstream gate and mapping; rights review; timestamp-schema check; audio-stream verification | `https://huggingface.co/datasets/Heinz217/TraceAV-Bench`; `cc96f31`/`22ea02b`; accessed 2026-09-07. |
| 2 | FLARE | Strongest modality-specific retrieval and hard-bimodal filtering at scale | Written resolution of Video-MME rights; explicit scene-time map; source/clip hashes; audio probe | `https://huggingface.co/datasets/AnonymousFLARE/FLARE`; `ed89d86`; accessed 2026-09-07. |
| 3 | VES-Bench | Strongest compact jointly-necessary interval benchmark | Dataset license and upstream provenance; Parquet schema; duration/audio verification | `https://huggingface.co/datasets/buaaplay/VES-Bench`; HF `main`, SHA `unverified`; accessed 2026-09-07. |
| 4 | LongShOTBench | Best open-ended multimodal QA and rubric coverage | Source acquisition/rights; author or AV-TRACE evidence spans; transcripts; audio probe | `https://huggingface.co/datasets/MBZUAI/longshot-bench`; `b559813`; accessed 2026-09-07. |
| 5 | LongVidSearch | Best released exact-\(k\) necessary-slice labels and retrieval-agent protocol | Resolve 447/444 discrepancy, timestamps, audiovisual status, media license, and split | `https://huggingface.co/datasets/Fishiing/LongVidSearch`; `96cdf54`; accessed 2026-09-07. |
| 6 | V-RAGBench | Excellent conceptual query/evidence/answer design over very long egocentric video | Actual payload, IDs, splits, evidence schema, and dual-source authorization are absent/unverified | `https://huggingface.co/datasets/DISLab/VRAG-Bench`; `main`, SHA `unverified`; accessed 2026-09-07. |

These are compatibility-track candidates, not replacements for the
rights-cleared AV-TRACE public core.

### 5.3 Compatibility-only evaluation

1. **LongVidSearch:** evidence-set selection, hop compliance, retrieval cost,
   and answer compatibility without raw media.
2. **LongShOTBench:** conversations, open-ended answers, modality tags, and
   weighted criterion scoring.
3. **Video-MME and LongVideoBench:** established MCQ adapters, IDs, duration
   strata, subtitles, and held-out test conventions.
4. **TRACE/VES-Bench:** decoded-frame coverage and evidence convergence;
   method code was not released in the inspected repository.
5. **Ego4D/EgoLife:** restricted schema compatibility for temporal metadata,
   audio-presence fields, transcripts, and long-horizon QA.
6. **V-RAGBench:** protocol-level compatibility only until a benchmark payload
   is released.

## 6. Release and rights controls

- A repository software license does not automatically cover annotations,
  features, transcripts, clips, or source media.
- An annotation license does not automatically cover third-party media.
- A public/ungated HF repository is a technical-access fact, not a
  redistribution grant.
- Keep immutable source revision, access date, source ID, acquisition method,
  rights evidence, and derived-artifact release decision separately.
- For every media candidate, verify container streams locally after authorized
  acquisition. Until then, audio-stream presence is `unverified`, even when a
  benchmark evaluates audio.
- Treat generated audio captions, visual captions, evidence descriptions, and
  subtitles as distinct artifact types. None should silently become a
  verbatim transcript.
- An upstream “necessary evidence” label is an **SES proposal**, not an
  accepted AV-TRACE SES, until independent validators establish sufficiency,
  leave-one-out minimality, and exhaustion of alternatives.

## 7. Unresolved items requiring author or gated-file access

- FLARE: exact contents and sizes below `datas/` and `videos/`; explicit scene
  start/end times; media-license scope; parent-ID crosswalk to Video-MME.
- Video-MME: subtitle archive structure/coverage; file-level audio streams;
  permission channel for derived clips and annotations.
- LoVR: effective dataset license; exact Parquet timestamp fields; part
  sizes/hashes beyond `part_aa`; audio streams.
- LongVideoBench: complete gated repository size/shard list; file-level audio;
  explicit answer-evidence spans.
- LongVidSearch: 447-versus-444 video discrepancy; stable QA IDs; exact
  embedding specification; slice-to-time join.
- LongShOTBench: source ID resolution, exact conversation enums, source
  availability, evidence spans, transcripts, and media-license scope.
- TraceAV-Bench: full mapping-source distribution and exact nested trajectory
  timestamp schema.
- VES-Bench: immutable HF SHA, Parquet columns, durations, audio, license,
  source provenance, and benchmark splits.
- V-RAGBench: actual data payload, source IDs, serialized evidence chunks,
  splits, code/config/checkpoints, and Ego4D/EgoLife allocation.
- EgoLife: complete 3K QA publication, media license scope, and per-file audio.
- Ego4D: V-RAGBench-selected UIDs, selected release version, agreement terms
  applicable to AV-TRACE-derived annotations, and selected-file audio.
