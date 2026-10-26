# Upstream benchmark reproduction audit

**Cutoff:** 2026-09-06
**Inspection date:** 2026-09-07
**Scope:** metadata, small source files, repository trees, dataset cards, papers, and release pages only. No repository clone, dataset shard, archive, video, audio, or model weight was downloaded.

**Reconciliation note (2026-09-07):** live release reconnaissance supersedes
earlier access observations. LongShOTBench is currently recorded as public
ungated annotations; V-RAGBench is a public card with no usable payload.
FLARE's card claims CC BY 4.0, and TraceAV expressly applies CC BY 4.0 to
annotations and accompanying code. None of these statements clears upstream
media.

## Executive findings

1. **No target is a drop-in AV-TRACE corpus.** LoVR and LongVidSearch are mainly visual/caption retrieval; Video-MME and LongVideoBench are evaluation releases rather than provenance-complete construction pipelines; FLARE and TraceAV-Bench publish useful generation structure but not a turnkey, dependency-pinned build; TRACE still advertises method code as forthcoming; V-RAGBench exposes only a public card with no usable payload and depends on separately licensed Ego4D/EgoLife media.
2. **The safest reusable units are metadata parsers, timestamp normalization, evaluation logic, and construction ideas—not media acquisition.** In particular: LongVideoBench's subtitle/frame interleaver; LoVR's clip-boundary and retrieval-evaluation structure; LongVidSearch's standardized retrieval-tool boundary and exact necessary-evidence concept; FLARE's modality-specific query taxonomy and hard-bimodal filter; LongShOT's weighted rubric representation; TraceAV's trajectory representation; and VES-Bench's decoded-evidence coverage metrics.
3. **Repository licenses and source-media rights must remain separate.** An MIT or CC license attached to code/annotations does not establish a right to acquire, process, or redistribute YouTube, film, television, Ego4D/EgoLife, or other third-party media.
4. **Reproduction must pin immutable revisions before use.** Several official surfaces publish only a mutable `main`, have no GitHub release, or changed counts/assets after publication. The checklist therefore creates a text-only provenance snapshot first and stops before any media-bearing command.
5. **Do not transplant hard-coded paths, web-download recipes, hidden API assumptions, pickled caches, or model-server coupling.** Wrap upstream semantics behind source-family adapters and record every generated artifact's prompt, model, checkpoint, decoding parameters, and input hashes.

## Evidence and revision policy

A revision is recorded below only when the official surface exposed it during inspection. Otherwise the audit deliberately says **mutable `main`; resolve SHA before execution** rather than inventing a commit. Exact URLs are listed because source pages can change after the access date.

| Target | Official surfaces inspected | Revision/release state on 2026-09-07 |
|---|---|---|
| LoVR | `https://github.com/TechNomad-ds/LoVR-benchmark`; `https://huggingface.co/datasets/debugger123/LoVR-benchmark`; `https://arxiv.org/abs/2505.13928` | Canonical HF release is `debugger123/LoVR-benchmark`. GitHub `main` and the HF files were observed only through short/file revisions. Pin full Git and HF revisions before use. |
| LongVidSearch | `https://github.com/yrywill/LongVidSearch`; `https://longvidsearch.github.io/`; `https://arxiv.org/abs/2603.14468` | GitHub `main`, 13 commits visible; branch page reports update 2026-04-01; no tagged release used. Repository identifies MIT. Pin full SHA. |
| FLARE | `https://github.com/YqjMartin/FLARE`; `https://huggingface.co/datasets/AnonymousFLARE/FLARE`; `https://flarebench.github.io/`; `https://arxiv.org/abs/2605.10228` | HF card field claims `cc-by-4.0`; scope over generated artifacts versus hosted Video-MME-derived media is unresolved. Pin full Git and HF revisions before use. |
| Video-MME | `https://github.com/MME-Benchmarks/Video-MME`; `https://video-mme.github.io/home_page.html`; official dataset link from README; `https://arxiv.org/abs/2405.21075` | Mutable `main`, 67 commits visible; README last visible commit `06c2315`; benchmark was refreshed on 2024-06-15 to replace broken/potentially broken videos and re-annotate them. No repository LICENSE file was visible. |
| LongVideoBench | `https://github.com/longvideobench/LongVideoBench`; `https://huggingface.co/datasets/longvideobench/LongVideoBench`; `https://longvideobench.github.io/`; `https://arxiv.org/abs/2407.15754` | No GitHub releases. Loader file shows commit `2aa4f91`; pin repository and HF revisions. README states dataset CC BY-NC-SA 4.0, non-commercial only. |
| LongShOTBench | `https://github.com/mbzuai-oryx/LongShOT`; `https://huggingface.co/datasets/MBZUAI/longshot-bench`; `https://arxiv.org/abs/2512.16978` | Current v2 annotations were observed public/ungated. The release claims CC BY-NC-SA 4.0, but source-media rights remain unresolved. Repository cookie/download instructions are not authority. Full Git/HF SHAs remain required. |
| TraceAV-Bench | `https://github.com/Heinz217/TraceAV-Bench`; `https://huggingface.co/datasets/Heinz217/TraceAV-Bench`; `https://arxiv.org/abs/2605.07593` | Public annotation release. Official README states CC BY 4.0 for annotations and accompanying code; upstream media are excluded and separately gated. Full Git/HF SHAs remain required. |
| TRACE / VES-Bench | `https://github.com/buaa-colalab/TRACE`; `https://buaa-colalab.github.io/TRACE/`; `https://huggingface.co/datasets/buaaplay/VES-Bench`; `https://arxiv.org/abs/2608.22516` | GitHub comparison surface exposes short revision `15e8c7e`; project repository says method code is coming soon. HF package includes a parquet and videos directory; no substantive data license was verified. |
| V-RAGBench | `https://huggingface.co/datasets/DISLab/VRAG-Bench`; `https://arxiv.org/abs/2606.13141` | Public card only; no usable row payload/source IDs were visible. The card points to Ego4D/EgoLife rights. Protocol-only until an immutable payload is released. |

## Cross-target acquisition and credentials

| Family | Official acquisition path | Credentials/cookies | Stop condition before transfer |
|---|---|---|---|
| GitHub code/metadata | GitHub repository HTML/API or a later shallow, blob-filtered checkout | Optional `GITHUB_TOKEN` only for rate limits; not needed for public HTML | Resolve commit SHA, enumerate files, fetch only README/LICENSE/config/source text. Do not run download scripts. |
| Hugging Face public release | `huggingface_hub` metadata APIs or `huggingface-cli download --dry-run` where supported | `HF_TOKEN` only if required; never print it | Capture dataset SHA, siblings, sizes/LFS markers, card/license, gated/private flags. Abort if any selected file is media/archive/parquet until reviewed. |
| Hugging Face gated release | Browser/API acceptance followed by authenticated metadata query | Named user account and `HF_TOKEN`; acceptance may bind additional terms | Record approver, accepted terms URL/date/hash and upstream agreements. Do not request media. |
| YouTube-origin workflows | Upstream repositories sometimes call `yt-dlp` or request `cookies.txt` | Browser-exported cookies or account session may be expected | **Do not execute for AV-TRACE.** A cookie recipe is not authorization. Require an approved acquisition route and per-asset rights record first. |
| Ego4D/EgoLife | Their official portals/agreements, independently of V-RAGBench metadata | Dataset registration, agreement acceptance, and possibly institutional identity | Keep metadata-only until both upstream agreements and privacy controls pass. |

## Target dossiers

### 1. LoVR

**Released structure.** The official repository contains `data_generation/` and `evaluate/`; the linked Hugging Face dataset is described as containing 467 long videos and 40,804 clips/captions. The release is derived from LongVideoBench videos, so LoVR packaging does not reset source-media rights.

**Processing reconstructed from code/paper.** `data_generation/clip_segmentation.py` is the central segmentation component; adjacent generation scripts implement VLM caption generation, caption scoring/dynamic refinement, semantic merging into video descriptions, and human quality assessment. The benchmark is visual-text retrieval; no reproducible audio/ASR pipeline is established. The evaluation directory supports CLIP, SigLIP, VideoCLIP-XL, and LanguageBind, with text-to-video/video-to-text retrieval and pass@k. Model weights are linked through ModelScope.

**Schema.** The usable semantic unit is `(video_id, clip_id, start_s, end_s, clip_caption)` plus an aggregated video caption. Preserve original video identity separately from reconstructed/segmented files. Exact column names must be discovered from the pinned HF revision before coding.

**Reuse.** Adapt clip-boundary records and retrieval metric logic; use the evaluation scripts as a behavioral oracle. Avoid copying model-specific loaders or assuming fixed local directories. Reimplement segmentation in an AV-TRACE transformation stage with explicit time-base and ffmpeg/PySceneDetect versions.

**Risks.** No tagged release, mutable HF artifacts, generated-caption provenance, ModelScope checkpoint dependency, likely unpinned Python/CUDA stack, and inherited LongVideoBench/web-media rights. Code license: MIT as displayed by GitHub. Dataset/media rights: unresolved and upstream-specific.

### 2. LongVidSearch

**Released structure.** The repository contains per-video `dataset/*_qa.json`, `full-QA(3000).json`, `video-caption.parquet`, `video_embeddings/`, `cache_llm.pkl`, `main.py`, `tools.py`, `utils_general.py`, `requirements.txt`, and `data_generation/run_pipeline.sh`. It reports 3,000 QA pairs over 447 videos, averaging about 26 minutes.

**Processing.** LongVidSearch builds on clip/caption representations rather than exposing a media-ingestion pipeline. Construction covers State Mutation, Causal Inference, Global Summary, and Visual Tracking. Hop-2/3/4 items are intended to have exactly k necessary clips; the paper describes deletion-based necessity checking. Runtime fixes the retrieval backend through a standardized tool interface so agent query planning can be compared independently of the retriever.

**Schema.** Normalize each QA into `question_id`, `video_id`, `question`, `answer`, `reasoning_category`, `hop_count`, ordered evidence clip identifiers/intervals, and construction/validation provenance. Treat the repository's per-video JSON files as authoritative only after schema fingerprinting; do not deserialize `cache_llm.pkl` from upstream.

**Reuse.** Reuse/adapt `tools.py` interface semantics, per-video JSON aggregation, evidence-set cardinality checks, and retrieval/answer score separation. Avoid the committed pickle, opaque precomputed embeddings, and any prompt/API cache lacking model and prompt hashes.

**Risks.** No media downloader is supplied; media provenance flows through LoVR/LongVideoBench. Precomputed embeddings couple results to an undocumented checkpoint/environment unless metadata is added. The construction pipeline is useful but not fully dependency/model pinned. Code license: MIT. Media rights: unresolved inherited web media.

### 3. FLARE

**Released structure.** The official GitHub tree contains a small `flare/` package and README; an official HF dataset is linked. The paper reports 399 screened Video-MME videos, 87,697 clips, 274,933 user-simulated queries, and 225.4 hours.

**Processing.** Videos are segmented into fine-grained clips. Each clip receives visual, audio, and unified audiovisual captions; long-video descriptions aggregate clip information. Query generation rewrites captions into shorter user-style text. Hard-bimodal examples are retained only when retrieval fails with either modality alone and succeeds with both. This is the most reusable modality-necessity construction pattern among the targets.

**Schema.** Expected normalized entities are video, clip interval, modality-specific caption, query, query modality class (`visual`, `audio`, `audiovisual`), and validation outcomes for visual-only/audio-only/fused retrieval. Exact released fields and media references require the pinned HF schema.

**Reuse.** Adapt the query taxonomy, validation matrix, and retrieval metrics. Rebuild caption generation and retrieval checks behind provider-neutral interfaces. Avoid direct coupling to a particular inference server, proprietary API, or Video-MME path layout.

**Risks.** Very young repository with four visible commits, no verified license, sparse environment documentation, generated data dependent on model/prompt versions, and inherited Video-MME media rights. Do not treat the public dataset as permission to redistribute source videos.

### 4. Video-MME

**Released structure and acquisition.** The official repository contains `evaluation/`, a JSON output template, and documentation linking official dataset storage. It has 900 videos, 2,700 human QA pairs, 254 hours, three duration bands, six broad domains, and 30 subfields. The project evaluates video-only, video+subtitle, and video+audio conditions. The 2024-06-15 refresh replaced broken or potentially broken links and re-annotated affected items, demonstrating revision sensitivity.

**Processing.** The repository does not expose a full source-collection/segmentation/ASR construction pipeline. The release supplies benchmark media/metadata and an answer-template/evaluation path. Subtitles exist for a subset; audio is an input condition rather than a released ASR normalization standard.

**Schema/evaluation.** Preserve video identity, duration group, domain, subcategory, task type, three multiple-choice questions per video, answer key where licensed, subtitle availability, and prediction. `eval_your_results.py` reports accuracy sliced by duration, domain, subcategory, and task type.

**Reuse.** Adapt schema mapping and grouped accuracy reporting. Use the template as a conformance fixture. Avoid reconstructing source media from historical links and avoid assuming current files match pre-refresh paper results without revision fingerprints.

**Risks.** Mutable release, link replacement history, no verified code/data license in the repository root, heterogeneous copyrighted media, and no end-to-end preprocessing recipe. Video-MME-v2 is a distinct benchmark and must not be mixed into this adapter.

### 5. LongVideoBench

**Released structure and acquisition.** The README documents `huggingface-cli download longvideobench/LongVideoBench --repo-type dataset --local-dir LongVideoBench --local-dir-use-symlinks False`, followed by concatenating `videos.tar.part.*` and extracting `videos.tar` and `subtitles.tar`. Those are media-transfer commands and are intentionally excluded from the runnable checklist. Metadata files include `lvb_val.json` and `lvb_test_wo_gt.json`.

**Frame/subtitle handling.** `longvideobench/longvideobench_dataset.py` uses Decord, calculates average FPS, selects at most `max_num_frames` approximately uniformly over `duration`, converts frames to PIL RGB, and interleaves subtitle strings by midpoint. It supports two subtitle shapes: `{timestamp:[start,end], text}` and `{start,end,line}`, offsets subtitle times by `starting_timestamp_for_subtitles`, and handles malformed/non-float ends by substituting duration.

**Schema/evaluation.** Normalize video path/id, duration, subtitle path/list, subtitle start offset, question, candidate options, correct choice (validation only), and question category. Evaluation is multiple-choice accuracy; official integration also exists in LMMS-Eval.

**Reuse.** The timestamp parser and subtitle/frame merge behavior are directly useful as a compatibility adapter and test oracle. Do not reuse its frame sampler unchanged: integer stepping can duplicate/bias indices, assumes CFR-like behavior, ignores packet timestamps, and can divide by zero for sub-second durations. AV-TRACE should sample by presentation timestamps and record actual decoded times.

**Risks.** Large multipart archives, no checksums documented in README, no tagged GitHub release, Decord/FFmpeg compatibility risk, hidden reliance on local tar layout, and CC BY-NC-SA 4.0 non-commercial dataset terms that do not independently clear embedded media.

### 6. LongShOTBench

**Released structure and access.** `preprocess/`, `datagen/`, and `eval/` are
exposed. The current v2 release reports 274 videos, about 188 hours, and 3,401
questions; v1 used materially different counts. The HF annotation release was
observed as public/ungated on 2026-09-07. Source media are not hosted there and
remain separately unresolved. Upstream preprocessing documentation includes a
YouTube `cookies.txt` workflow, which is not an authorized AV-TRACE route.

**Processing.** The repository describes full-video preprocessing into visual descriptions, speech transcripts, non-speech/audio descriptions, and metadata; data generation creates practical, intent-driven single- and multi-turn questions, reference answers, and hierarchical weighted rubrics; manual verification/correction follows. LongShOTAgent performs targeted retrieval, query-adaptive segment refinement, and claim verification over vision, speech, and ambient audio.

**Schema/evaluation.** Normalize conversation turns, reference answer, rubric criteria, criterion weights, modality tags, and any referenced evidence. Evaluation is weighted partial-credit rubric scoring and includes verifier/human alignment analysis.

**Reuse.** Adapt the rubric schema, weighted scorer, modality routing, and claim-verification interfaces. Do not reuse the cookie downloader, absolute path assumptions, or model/API wrappers without isolation and revision pinning.

**Credentials/services.** HF acceptance/token is required for gated artifacts. The documented browser-cookie path may be required by upstream YouTube processing, but it is forbidden in AV-TRACE preflight absent independent authorization. Generation/evaluation may depend on hosted proprietary or large local models; exact model identifiers and endpoints must be extracted from the pinned source before execution.

**Risks.** Version drift, gated terms, credential handling, YouTube availability, generated-rubric judge drift, and no blanket source-media rights. Keep v1/v2 namespaces separate.

### 7. TraceAV-Bench

**Released structure.** The repository exposes staged source folders for video captioning, event segmentation, agentic question generation, and quality assurance, plus evaluation/examples. The release reports 578 videos, 339.5 hours, and 2,200 trajectory-grounded multiple-choice questions, with average 3.68 hops over a 15.1-minute evidence span.

**Processing.** The described pipeline creates per-minute visual captions, fuses audio-visual descriptions, segments events, generates multi-hop trajectories/questions, and applies automated followed by human quality assurance. It explicitly targets cross-modal trajectory reasoning and hallucination robustness.

**Schema.** Preserve `video_id`, question/options/answer, dimension/category, ordered trajectory steps, per-step timestamps, modality for each step, and QA/validation provenance. If the HF schema differs, store raw fields losslessly under `source_payload`.

**Reuse.** The staged directory boundary and ordered trajectory representation are strong templates. Adapt quality gates but replace hard-coded model clients with injected providers and immutable prompt/model manifests.

**Risks.** Full data availability and exact repository license were not verified; model and API dependencies are underdocumented at the release surface; captions/segments are generated and may not reproduce without exact prompts/checkpoints; upstream media rights remain heterogeneous.

### 8. TRACE / VES-Bench

**Released structure.** The HF repository includes `VES-Bench.parquet` and a `videos/` directory (about 17.9 GB reported by the official surface). The benchmark has 600 four-choice questions over 348 public long videos. GitHub revision `15e8c7e` was exposed during inspection.

**Evidence/evaluation.** Each item has a jointly necessary set of evidence intervals. The central contribution is to audit frames actually decoded by a system, with three interval-coverage strictness levels, and combine evidence-supported correctness with final answer accuracy and frame cost. TRACE retrieves raw visual clips iteratively and stops based on answer convergence/evidence growth.

**Schema.** Normalize question/options/answer, evidence interval set, strictness rules, and decoded observation log `(frame_pts_s, frame_index, source_hash, request_id)`. Keep predicted intervals distinct from actually decoded evidence.

**Reuse.** Reimplement interval-coverage and evidence-supported-correctness metrics from the formal definitions; treat the released parquet as a test vector. The concept is highly reusable, but code reuse is presently blocked because the repository still labels method code as coming soon.

**Risks.** No substantive dataset license verified, no released method implementation at the audited revision, media provenance not sufficient for onward redistribution, and results are sensitive to decoder timestamps/frame rounding.

### 9. V-RAGBench

**Released structure/access.** The official HF card describes 2,100 `<query, evidence, answer>` triplets over 216 Ego4D/EgoLife videos spanning roughly 1–9 hours. Evidence is localized to non-overlapping two-minute chunks. Access is governed by the dataset card plus Ego4D and EgoLife/S-Lab terms.

**Construction.** Candidate triplets are filtered for non-recurring evidence, visual grounding, localized answerability, shortcut resistance, answerability by a strong VLM, and failure on non-evidence chunks. CARVE evaluates retrieval and generation separately, using multiple modality/granularity retrievers and reranking before generation.

**Schema/evaluation.** Normalize query, answer/reference, source video/session, evidence chunk index/start/end, split, source family (`ego4d` or `egolife`), and filter/judge outcomes. Evaluate retrieval with Recall@K-style metrics and generation with the official judged metric; record the judge model/prompt/version.

**Reuse.** The decoupled retrieval/generation protocol and negative/non-evidence filtering are valuable. Implement from the paper/card rather than importing an unavailable official codebase.

**Risks.** Gated upstream media, substantial privacy exposure, no official code repository found, evaluation-judge dependency, and non-commercial/restricted agreement constraints. This should remain a restricted compatibility adapter, never a public-core source.

## Reusable, adaptable, and avoid list

| Disposition | Components |
|---|---|
| **Reuse with attribution/license verification** | LoVR retrieval metric behavior; LongVidSearch tool API semantics and evidence cardinality; LongVideoBench subtitle parsing/interleaving; Video-MME result-template grouping; LongShOT rubric weighting; TraceAV ordered trajectory representation; VES-Bench evidence-coverage definitions. |
| **Adapt/reimplement** | All segmentation, frame sampling, ASR, captioning, multimodal fusion, query generation, LLM judging, embedding, and retrieval backends. Reimplementation should use AV-TRACE manifests, PTS timestamps, provider interfaces, deterministic seeds, and content-addressed artifacts. |
| **Avoid** | Cookie-based web acquisition; automatic execution of upstream download scripts; untrusted pickle loading; mutable `main` references; tar concatenation before sizes/checksums are approved; absolute paths; secrets in source/config; silently calling proprietary APIs; unversioned prompts/models; treating generated captions as ground truth; mixing benchmark versions; treating repo license as media license. |

## Gaps and stale/dead-link flags

- **Video-MME:** official history confirms link attrition and a 2024-06-15 replacement/re-annotation event. Any reproduction must name the exact post-refresh revision.
- **TRACE:** method code is still marked **coming soon** at the audited repository; only data/paper-level compatibility can be planned.
- **LongVideoBench:** no GitHub releases; multipart media archives are documented without README checksums.
- **LongShOTBench:** public annotation access does not provide source media;
  cookie-based YouTube preprocessing is not an authorized route, so durable
  source reproduction remains impossible without asset-level resolution and
  approval.
- **V-RAGBench:** no official implementation repository or usable row payload
  was found; the public card is accessible, while source media remain governed
  by separate Ego4D/EgoLife terms.
- **FLARE:** public code/data surfaces exist but license and complete dependency/model specifications were not verified.
- **LoVR/LongVidSearch/TraceAV-Bench:** construction stages are visible, but exact environment locks, prompts, checkpoints, and all service credentials are not fully documented.
- **All web-derived sets:** public hosting is not evidence of transferable source-media rights. Maintain asset-level rights decisions and a compatibility-only storage boundary.

## Primary-source URL register

All URLs below were accessed 2026-09-07; paper claims are considered current through 2026-09-06.

- LoVR: `https://github.com/TechNomad-ds/LoVR-benchmark`; `https://huggingface.co/datasets/TechNomad-ds/LoVR`; `https://arxiv.org/abs/2505.13928`
- LongVidSearch: `https://github.com/yrywill/LongVidSearch`; `https://longvidsearch.github.io/`; `https://arxiv.org/abs/2603.14468`
- FLARE: `https://github.com/YqjMartin/FLARE`; `https://huggingface.co/datasets/AnonymousFLARE/FLARE`; `https://flarebench.github.io/`; `https://arxiv.org/abs/2605.10228`
- Video-MME: `https://github.com/MME-Benchmarks/Video-MME`; `https://video-mme.github.io/home_page.html`; `https://arxiv.org/abs/2405.21075`
- LongVideoBench: `https://github.com/longvideobench/LongVideoBench`; `https://huggingface.co/datasets/longvideobench/LongVideoBench`; `https://longvideobench.github.io/`; `https://arxiv.org/abs/2407.15754`
- LongShOTBench: `https://github.com/mbzuai-oryx/LongShOT`; `https://huggingface.co/datasets/MBZUAI/longshot-bench`; `https://arxiv.org/abs/2512.16978`
- TraceAV-Bench: `https://github.com/Heinz217/TraceAV-Bench`; `https://huggingface.co/datasets/Heinz217/TraceAV-Bench`; `https://arxiv.org/abs/2605.07593`
- TRACE/VES-Bench: `https://github.com/buaa-colalab/TRACE`; `https://buaa-colalab.github.io/TRACE/`; `https://huggingface.co/datasets/buaaplay/VES-Bench`; `https://arxiv.org/abs/2608.22516`
- V-RAGBench: `https://huggingface.co/datasets/DISLab/VRAG-Bench`; `https://arxiv.org/abs/2606.13141`
