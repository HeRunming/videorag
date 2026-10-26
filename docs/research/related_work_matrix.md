# Long-video evidence and agent benchmark reverse engineering

**Audit date:** 2026-09-05.  
**Evidence policy:** factual statements below are tied to a primary-source BibTeX key in [`primary_sources.bib`](./primary_sources.bib). “Verified” means observed in an official paper page/PDF, CVF page, official repository, project page, or official dataset card. “Not verified” means the field was not recoverable from the accessible primary source and is intentionally not guessed.

## Executive comparison

Legend for overlap with the proposed hypothesis:

- **D** — directly operationalized or measured.
- **P** — partial/adjacent coverage, usually as a method feature or a static dataset property rather than a controlled benchmark intervention.
- **—** — not found in the verified source.

| Work | Unit / principal task | Missing evidence | Hard distractors | Modality or tool failure | Sufficiency calibration | Recovery / re-retrieval | Premature stopping | Counterfactual evidence use |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| LoVR | Long-video and clip text retrieval | — | P | — | — | — | — | — |
| LongVidSearch | Agentic, exact-\(k\)-hop evidence retrieval plus QA | **D** | **D** | — | P | P | P | — |
| FLARE | Vision/audio/audiovisual clip retrieval | P | **D** | P | — | — | — | — |
| V-RAGBench | Decoupled retrieval and generation on localized chunks | P | **D** | P | — | — | — | — |
| LongShOTBench | Open-ended omni-modal single/multi-turn QA with rubrics | — | P | P | P | P | P | — |
| HAVEN | Hierarchically aligned summarization, grounding, temporal reasoning, saliency | — | — | — | — | — | — | — |
| LongVT / VideoSIAH | Agentic crop-and-resample long-video QA | P | P | — | P | **D** | P | — |
| WorldMM | Memory agent evaluated on existing LVQA benchmarks | — | P | — | P | **D** | P | — |
| MOV-Bench | Multi-hop audio-visual MCQ; AOP-Agent | P | P | — | P | **D** | P | — |
| VideoGAIA | Multi-turn video inspection plus web tools | — | P | P | P | **D** | P | — |
| REVEAL | Sufficiency-verifying agent on existing benchmarks | P | P | — | **D** | **D** | **D** | — |
| TRACE / VES-Bench | Audit of actual decoded-frame coverage and evidence-convergent stopping | **D** | P | — | **D** | **D** | **D** | — |

The overlap labels are **our inference**, not claims made verbatim by the cited papers. They summarize the detailed records below. [@longvidsearch2026; @you2026flare; @lee2026vragbench; @kurpath2026longshot; @yang2026longvt; @yeo2026worldmmArxiv; @xu2026movbench; @zhang2026videogaia; @yan2026reveal; @liu2026trace]

---

## 1. LoVR

**Identity and date.** LoVR is a long-video/clip text-retrieval benchmark; the latest verified arXiv version is v3 dated **2025-11-13**. [@cai2025lovr]

| Requested field | Reverse-engineered record |
|---|---|
| Problem definition | Retrieve either an entire long video or a fine-grained clip from text, addressing duration, caption quality, and annotation granularity limitations in earlier video-text retrieval benchmarks. [@cai2025lovr] |
| Source videos | **Not verified.** The paper has a “Video Source” section, but the upstream collection/corpus was not recoverable from the accessible primary-source rendering. [@cai2025lovr] |
| Scale | **467 long videos** and **40,804+ fine-grained clips**. [@cai2025lovr] |
| Duration | Described as long video; exact range, mean, and total hours were **not verified**. [@cai2025lovr] |
| Modalities | Video/frames and text captions/queries. No verified audio evaluation track. [@cai2025lovr] |
| Query / QA construction | Clip captions are produced through VLM generation, caption-quality scoring, dynamic refinement, and final human quality assessment; full-video captions are generated through semantic fusion. [@cai2025lovr] |
| Evidence annotation | Temporal clip segmentation plus clip-level and full-video captions. These are relevance annotations, not jointly necessary evidence sets. [@cai2025lovr] |
| Tools / backend | Static retrieval benchmark; no standardized interactive agent tool loop was verified. [@cai2025lovr] |
| Metrics | Video retrieval and clip retrieval with Recall@K analyses. [@cai2025lovr] |
| Baseline systems | The paper evaluates multiple advanced video-text retrievers, but the exact roster was **not re-verified** from the accessible primary source. [@cai2025lovr] |
| License / release | Paper is CC BY 4.0; official code link is public. A separate dataset-content license was **not independently verified**. [@cai2025lovr; @lovrGithub] |
| Exact overlap with our hypothesis | **Partial:** large distractor space and fine-grained evidence localization. **Absent:** controlled evidence deletion, failed tools/modalities, calibrated sufficiency, recovery, stopping decisions, or counterfactual pairs. This is our inference. [@cai2025lovr] |

## 2. LongVidSearch

**Identity and date.** LongVidSearch was submitted **2026-03-16** and explicitly frames long-video understanding as agentic multi-hop evidence retrieval under standardized access constraints. [@longvidsearch2026]

| Requested field | Reverse-engineered record |
|---|---|
| Problem definition | Separate retrieval planning from answer generation by requiring agents to locate exactly \(k\) necessary clips before answering. [@longvidsearch2026] |
| Source videos | **447 long videos**; exact upstream corpus attribution was not re-verified. [@longvidsearch2026] |
| Scale | **3,000 questions**, with 2-, 3-, and 4-hop requirements. [@longvidsearch2026] |
| Duration | Average video length **26 minutes**. [@longvidsearch2026] |
| Modalities | Verified focus is visual evidence plus text questions; an audio-specific track was not found. [@longvidsearch2026] |
| Query / QA construction | An agentic/adversarial construction funnel creates questions in State Mutation, Causal Inference, Global Summary, and Visual Tracking categories. Each Hop-\(k\) item is intended to require exactly \(k\) clips. [@longvidsearch2026] |
| Evidence annotation | Each question has an exact set of necessary evidence clips; removing any one is asserted to make the item unsolvable. [@longvidsearch2026] |
| Tools / backend | Standardized evidence-access interface for agentic retrieval; official repository is public. Exact API calls and backend indexes should be checked directly before implementation because they were not fully exposed in the accessible abstract. [@longvidsearch2026; @longvidsearchGithub] |
| Metrics | Final QA and evidence-retrieval behavior are evaluated; exact metric formulas were **not re-verified**. [@longvidsearch2026] |
| Baseline systems | Agentic and non-agentic long-video systems are compared; exact current roster was **not re-verified**. [@longvidsearch2026] |
| License / release | Official repository is public; repository/data license was **not verified** in this audit. [@longvidsearchGithub] |
| Exact overlap with our hypothesis | **Very high on necessary evidence and distractors.** It already supports a missing-one-clip necessity claim. It does **not** appear to run paired interventions at evaluation time, inject tool/modality failures, score recovery from failures, or test counterfactual evidence use. “First benchmark with necessary multi-hop evidence” is therefore unavailable to us. This is our inference. [@longvidsearch2026] |

## 3. FLARE

**Identity and date.** FLARE was submitted **2026-05-12** as a full-modality long-video audiovisual retrieval benchmark with user-simulated queries. [@you2026flare]

| Requested field | Reverse-engineered record |
|---|---|
| Problem definition | Retrieve short target clips from long videos using realistic short queries under visual-only, audio-only, and unified audiovisual settings. [@you2026flare] |
| Source videos | **399 screened Video-MME videos**. [@you2026flare; @videomme2024] |
| Scale | **87,697 clips**, **274,933 user-style queries**, **225.4 hours**. [@you2026flare] |
| Duration | **10–60 minutes** per source video. [@you2026flare] |
| Modalities | Vision, audio, and unified audiovisual evidence. [@you2026flare] |
| Query / QA construction | Vision, audio, and unified captions are converted to shorter user-simulated queries. Cross-modal queries undergo a hard bimodal filter: retrieval must fail with either modality alone and succeed with both. [@you2026flare] |
| Evidence annotation | Fine-grained clips annotated with vision, audio, and audiovisual captions; cross-modal items have empirical modality-necessity filtering. [@you2026flare] |
| Tools / backend | Static retrieval evaluation rather than a multi-turn agent protocol. [@you2026flare] |
| Metrics | Caption-based and query-based retrieval across three modality settings; the paper reports standard retrieval evaluation. Exact metric list/formulas were **not re-verified**. [@you2026flare] |
| Baseline systems | **15 representative retrievers**; exact roster was not re-verified. [@you2026flare] |
| License / release | Code and data are released through the official project page. Exact code/data license text was **not verified**. [@you2026flare; @flareProject] |
| Exact overlap with our hypothesis | **Direct precedent for modality necessity and hard audiovisual cases.** However, it does not test an agent that experiences a modality outage, notices it, reroutes, recovers, calibrates sufficiency, or decides whether to stop. Our novelty must be behavioral/interventional, not merely “both audio and vision are required.” This is our inference. [@you2026flare] |

## 4. V-RAGBench

**Identity and date.** V-RAGBench was submitted **2026-06-11** with CARVE, a chunk-adaptive VideoRAG method. [@lee2026vragbench]

| Requested field | Reverse-engineered record |
|---|---|
| Problem definition | Faithfully and separately evaluate video evidence retrieval and answer generation, avoiding questions answerable without the video. [@lee2026vragbench] |
| Source videos | Hour-scale egocentric video from **Ego4D and EgoLife**. [@vragbenchDataset] |
| Scale | **2,100** open-ended \(\langle\)query, evidence chunk, answer\(\rangle\) triplets from **216 videos**. [@vragbenchDataset] |
| Duration | Hour-scale source videos; evidence is localized to non-overlapping **2-minute chunks**. [@vragbenchDataset; @lee2026vragbench] |
| Modalities | Multiple video representations/modalities and temporal granularities are considered by retrieval configurations; exact representation menu should be taken from the paper implementation. [@lee2026vragbench] |
| Query / QA construction | Candidate triples are filtered for non-recurring evidence, visual grounding, evidence localization, shortcut resistance, answerability by a strong VLLM, and non-answerability from non-evidence chunks. [@lee2026vragbench; @vragbenchDataset] |
| Evidence annotation | One localized evidence chunk per open-ended QA triplet, enabling retrieval and generation to be scored separately and jointly. [@lee2026vragbench] |
| Tools / backend | CARVE runs parallel retrievers over modality/granularity configurations, reranks chunks, and passes each chunk to the generator in its winning representation. [@lee2026vragbench] |
| Metrics | Retrieval and generation are evaluated separately and end-to-end; the paper reports Recall@K-style retrieval and judged generation. Exact formulas were not copied in this audit. [@lee2026vragbench] |
| Baseline systems | CARVE is compared with **eight recent VideoRAG baselines**; exact roster not re-verified. [@lee2026vragbench] |
| License / release | Dataset card is public. Because data derive from EgoLife and Ego4D, use is governed by the S-Lab License 1.0 and Ego4D License Agreement rather than a simple permissive license. [@vragbenchDataset] |
| Exact overlap with our hypothesis | **Strong precedent for causal dependence on retrieved video and hard non-evidence chunks.** It does not create controlled missing-evidence episodes, perturb tools, evaluate recovery, or test stopping calibration. Its one-chunk localization also differs from a jointly sufficient multi-evidence set. This is our inference. [@lee2026vragbench] |

## 5. LongShOTBench

**Identity and version warning.** The current verified arXiv v2 is dated **2026-06-16**. The current release reports **3,401 questions over 274 videos**, whereas arXiv v1 reported 3,092 QA instances over 157 videos; all project claims should specify the version. [@kurpath2026longshot; @longshotDataset]

| Requested field | Reverse-engineered record |
|---|---|
| Problem definition | Diagnostic long-form omni-modal understanding with open-ended, intent-driven single- and multi-turn interaction and criterion-level rubrics. [@kurpath2026longshot] |
| Source videos | Long-form videos processed from YouTube; the preprocessing repository extracts visual descriptions, audio descriptions, speech transcripts, and metadata. [@longshotGithub] |
| Scale | Current release: **3,401 questions**, **274 videos**, approximately **188 hours**. [@longshotDataset] |
| Duration | Approximately **41 minutes average**. [@longshotDataset] |
| Modalities | Vision, speech, and ambient/non-speech audio. [@kurpath2026longshot] |
| Query / QA construction | Practical viewing scenarios are mapped to question types; single- and multi-turn open-ended questions, reference answers, and hierarchical weighted rubrics are generated and then manually verified/corrected. [@kurpath2026longshot; @longshotGithub] |
| Evidence annotation | Criterion-level rubrics identify required perceptual facts, temporal links, modality grounding, and reasoning steps. The release does not claim jointly necessary temporal intervals for every rubric item. [@kurpath2026longshot] |
| Tools / backend | LongShOTAgent performs full-video preprocessing, targeted retrieval, query-adaptive segment refinement, and claim verification over visual, speech, and non-speech audio evidence. [@kurpath2026longshot] |
| Metrics | Weighted rubric scoring with partial credit; verifier-human alignment is studied. [@kurpath2026longshot] |
| Baseline systems | The paper evaluates proprietary and open-source MLLMs and LongShOTAgent; reported examples include Gemini-2.5-Flash and open-source models. [@kurpath2026longshot] |
| License / release | Paper is CC BY-NC-SA 4.0. Code is public; the official dataset card requires acceptance of access conditions. A standalone permissive data license was not verified. [@kurpath2026longshot; @longshotGithub; @longshotDataset] |
| Exact overlap with our hypothesis | **High overlap on omni-modal routing, agentic retrieval, claim verification, and interpretable rubrics.** Missing are controlled tool failures, paired evidence removal/insertion, explicit abstention/sufficiency calibration targets, and counterfactual evidence-use tests. This is our inference. [@kurpath2026longshot] |

## 6. HAVEN

**Name disambiguation.** This record refers to **“HAVEN: Hierarchically Aligned Multimodal Benchmark for Unified Video Understanding,” submitted 2026-05-19**, not the separate 2025 benchmark named HAVEN for hallucination in video understanding. [@shi2026haven]

| Requested field | Reverse-engineered record |
|---|---|
| Problem definition | Unified evaluation of faithful video summarization and reasoning through continuous, hierarchical video-text alignment at frame, shot, and whole-video levels. [@shi2026haven] |
| Source videos | Six released source collections: TVSum, SumMe, OVP, YouTube, VideoXum, and MR.HiSum. [@havenGithub] |
| Scale | **11,055 videos** in total: 50 TVSum + 25 SumMe + 50 OVP + 40 YouTube + 5,300 VideoXum + 5,590 MR.HiSum. [@havenGithub] |
| Duration | Mixed source-dataset durations; aggregate range/mean was **not verified**. [@havenGithub] |
| Modalities | Video and aligned text. An audio/speech track was not found. [@shi2026haven] |
| Query / QA construction | Not principally a QA-only benchmark. It evaluates summarization, temporal reasoning, multimodal grounding, and saliency ranking from unified annotations. [@shi2026haven] |
| Evidence annotation | Frame descriptions, clip/shot summaries and references, aligned full documents, aligned text summaries, saliency labels, and links from textual units to visual segments. [@havenGithub] |
| Tools / backend | Static benchmark/evaluation suite; no interactive agent tool protocol was verified. [@shi2026haven] |
| Metrics | Task-specific metrics for summarization, temporal reasoning, grounding, and saliency ranking. Exact metric formulas were **not re-verified** from the accessible primary source. [@shi2026haven] |
| Baseline systems | State-of-the-art MLLMs are benchmarked; exact roster was not re-verified. [@shi2026haven] |
| License / release | Dataset metadata and canonical files are released; repository includes a LICENSE file. Individual source datasets may impose their own terms. [@havenGithub] |
| Exact overlap with our hypothesis | **Useful annotation substrate** for evidence hierarchy and attribution, but not an intervention benchmark. It does not directly measure missing evidence, failure recovery, stopping, or counterfactual evidence utilization. This is our inference. [@shi2026haven] |

## 7. LongVT / VideoSIAH

**Identity and correction.** LongVT is a CVPR 2026 agentic method plus the VideoSIAH data suite. The latest paper/dataset release contains **652 unique evaluation QA pairs**, correcting an initial export of 1,280 duplicated rows; the paper states that metrics were unchanged because duplicates were exact copies. [@yang2026longvt; @videosiahDataset]

| Requested field | Reverse-engineered record |
|---|---|
| Problem definition | Train an LMM to interleave reasoning with native `crop_video(start_time,end_time)` calls, repeatedly moving from global preview to local inspection until it can answer from visual evidence. [@yang2026longvt] |
| Source videos | VideoSIAH-Eval contains **244 long-form videos**; exact upstream source composition was not re-verified. [@videosiahDataset] |
| Scale | Training: 247.9K SFT, 1.6K agentic RL, and 15.4K agentic RFT samples. Evaluation: **652 unique QA pairs**. [@yang2026longvt; @videosiahDataset] |
| Duration | Evaluation videos average approximately **1,688 seconds** (28.13 minutes). [@yang2026longvt] |
| Modalities | Visual video plus text QA and tool traces; no dedicated audio reasoning track was verified. [@yang2026longvt] |
| Query / QA construction | Semi-automatic evidence-sparse long-video QA pipeline with human-in-the-loop validation. [@yang2026longvt] |
| Evidence annotation | QA and tool-integrated trajectories encourage localization; the benchmark does not claim an exhaustive jointly necessary interval set for every answer. [@yang2026longvt] |
| Tools / backend | Native video cropping/resampling with an interleaved multimodal chain-of-tool-thought and self-reflection loop. [@yang2026longvt] |
| Metrics | QA accuracy on VideoSIAH-Eval and four external long-video benchmarks, plus ablations and efficiency analyses. [@yang2026longvt] |
| Baseline systems | Direct/textual-CoT LMMs, existing long-video methods, and LongVT 7B variants are compared. [@yang2026longvt] |
| License / release | CVF paper, code, data, and weights are public. Repository is Apache-2.0; arXiv v3 is CC BY 4.0. Dataset-media terms may depend on source videos. [@yang2026longvt; @longvtGithub; @videosiahDataset] |
| Exact overlap with our hypothesis | **Direct precedent for iterative recovery after an incorrect localization** and agentic zoom-in. It lacks benchmark-controlled tool failures, explicit sufficiency labels, calibrated abstention, and paired counterfactual evidence conditions. This is our inference. [@yang2026longvt] |

## 8. WorldMM

**Type warning.** WorldMM is primarily a **method**, not a newly introduced benchmark. It is included because its adaptive retrieval and stopping behavior is close to the project hypothesis. [@yeo2026worldmm]

| Requested field | Reverse-engineered record |
|---|---|
| Problem definition | Build episodic, semantic, and visual memories over long video, then adaptively retrieve across memory types and temporal scales for long-video QA. [@yeo2026worldmmArxiv] |
| Source videos / scale / duration | No new benchmark corpus. Evaluated across five existing long-video QA benchmarks, spanning settings motivated by hours- to days-long video. Exact per-benchmark subsets should be taken from the paper. [@yeo2026worldmmArxiv] |
| Modalities | Textual and visual memory representations. [@yeo2026worldmmArxiv] |
| Query / QA construction | Inherited from the five evaluation benchmarks. [@yeo2026worldmmArxiv] |
| Evidence annotation | Inherited benchmark answers; no new gold sufficient-evidence intervention labels were verified. [@yeo2026worldmmArxiv] |
| Tools / backend | Adaptive retrieval agent chooses episodic, semantic, or visual memory and temporal granularity iteratively. [@yeo2026worldmmArxiv] |
| Metrics | Existing benchmark QA metrics; paper reports an average 8.4% gain over prior state of the art across five benchmarks. [@yeo2026worldmmArxiv] |
| Baseline systems | Existing long-video QA and memory-augmented systems; exact roster not re-verified. [@yeo2026worldmm] |
| License / release | CVPR paper and project page are public. Code/data license was not verified in this audit. [@yeo2026worldmm] |
| Exact overlap with our hypothesis | **Method-level overlap** on “continue until sufficient information has been gathered,” adaptive modality/memory selection, and iterative retrieval. It does not supply benchmark ground truth for whether the stop was premature, nor controlled failures or counterfactual evidence. This is our inference. [@yeo2026worldmmArxiv] |

## 9. MOV-Bench

**Identity and date.** MOV-Bench is introduced with AOP-Agent in a paper submitted **2026-05-27**. [@xu2026movbench]

| Requested field | Reverse-engineered record |
|---|---|
| Problem definition | Test multi-hop reasoning over sparse, temporally dispersed evidence distributed across audio and visual streams. [@xu2026movbench] |
| Source videos | **Not verified.** The accessible primary source did not expose the upstream video list. [@xu2026movbench] |
| Scale | **519** carefully curated multiple-choice questions. [@xu2026movbench] |
| Duration | Long/multi-segment video setting; exact range/mean was **not verified from a primary source**. [@xu2026movbench] |
| Modalities | Audio and vision, with cross-modal multi-hop reasoning. [@xu2026movbench] |
| Query / QA construction | Questions require integration across multiple temporal segments and modalities; they are curated as multi-hop MCQs. [@xu2026movbench] |
| Evidence annotation | Evidence is organized by multiple temporal segments/hops, but an exhaustive, released jointly necessary interval schema was not verified. [@xu2026movbench] |
| Tools / backend | AOP-Agent combines hierarchical omni-modal memory with an observe–reflect–replan loop and active perception. [@xu2026movbench] |
| Metrics | Multiple-choice accuracy and agent-vs-direct comparisons on MOV-Bench and OmniVideoBench. [@xu2026movbench] |
| Baseline systems | Current Omni-LLMs, including open-source models, and other agentic frameworks; exact roster not re-verified. [@xu2026movbench] |
| License / release | ArXiv paper is CC BY 4.0. An official code/data repository was not located in this audit and must be treated as **unverified release status**. [@xu2026movbench] |
| Exact overlap with our hypothesis | **High overlap on audio-visual multi-hop evidence and iterative replanning.** It does not explicitly benchmark modality outages, corrupted tool observations, recovery success after failure, or calibrated stopping. This is our inference. [@xu2026movbench] |

## 10. VideoGAIA

**Identity and date.** VideoGAIA was submitted **2026-08-12** as an agentic benchmark for general AI assistants working with video. [@zhang2026videogaia]

| Requested field | Reverse-engineered record |
|---|---|
| Problem definition | Replace one-shot QA with multi-turn, tool-augmented interaction in which models inspect video, invoke external tools, gather complementary information, and integrate evidence. [@zhang2026videogaia] |
| Source videos | Official release packages **271 MP4 videos**, one per task. [@videogaiaDataset] |
| Scale | **271 open-ended tasks**, each verified independently by three human experts; six categories. [@zhang2026videogaia; @videogaiaDataset] |
| Duration | Per-video duration is included in the released JSONL; aggregate range/mean was not verified. [@videogaiaDataset] |
| Modalities | Video frames, text questions, and external web text. The primary sources do not establish a dedicated audio/speech evaluation track. [@videogaiaGithub; @videogaiaDataset] |
| Query / QA construction | Model-human co-designed, evidence-grounded task generation with rubric-based quality control, cross-modal filtering, tool-necessity assessment, safety screening, and human annotation. [@zhang2026videogaia] |
| Evidence annotation | Human-verified reference answers and construction-time evidence grounding; released dataset schema does not expose exhaustive gold temporal evidence intervals. [@zhang2026videogaia; @videogaiaDataset] |
| Tools / backend | Unified ReAct harness with arbitrary-window video resampling, web search through Serper, and page extraction through Jina Reader. Tool results are inserted as genuine observations and model-authored fake observation tags are rejected. [@videogaiaGithub] |
| Metrics | LLM-judged overall, category-level, and difficulty-level accuracy, with primary/fallback judges. [@videogaiaGithub] |
| Baseline systems | Frontier and open MLLMs under a unified harness; the paper explicitly reports GPT-5.5 and Kimi-K3 among evaluated frontier systems. [@zhang2026videogaia] |
| License / release | Paper is CC BY 4.0; code and data are public. No explicit dataset-card license metadata was present in the verified card, so reuse terms require confirmation. [@zhang2026videogaia; @videogaiaGithub; @videogaiaDataset] |
| Exact overlap with our hypothesis | **Strong agent/tool overlap** and some tool-necessity filtering. It does not systematically inject tool failures or missing modalities, score recovery trajectories, or pair factual and counterfactual evidence conditions. This is our inference. [@zhang2026videogaia] |

## 11. REVEAL

**Type warning and date.** REVEAL, submitted **2026-08-09**, is a method for explicit evidence-sufficiency verification, not a newly released benchmark. [@yan2026reveal]

| Requested field | Reverse-engineered record |
|---|---|
| Problem definition | Separate evidence sufficiency from semantic relevance; verify whether retrieved evidence satisfies a question-specific rubric before answering. [@yan2026reveal] |
| Source videos / scale / duration | Uses existing Video-MME-L, LVBench, LongVideoBench, EgoLifeQA, and Ego-R1 Bench subsets; no new source-video corpus. [@yan2026reveal] |
| Modalities | Primarily visual long-video memory and text QA; no dedicated audio track was verified. [@yan2026reveal] |
| Query / QA construction | Inherited from existing benchmarks. An automatically constructed contrastive rubric library supplies sufficiency criteria. [@yan2026reveal] |
| Evidence annotation | The method samples and labels evidence to build/refine rubrics, but the evaluated public benchmarks do not become a new per-item gold missing-evidence intervention dataset. [@yan2026reveal] |
| Tools / backend | Visual-similarity event segmentation; offline global memory plus dynamic online question-conditioned memory; planner, verifier, answerer, and targeted re-retrieval. [@yan2026reveal] |
| Metrics | Existing benchmark accuracy plus analyses of evidence volume, sufficiency-verdict calibration, retrieval rounds, runtime, token use, and cost. [@yan2026reveal] |
| Baseline systems | Closed- and open-source long-video methods on five benchmarks; exact roster not re-verified. [@yan2026reveal] |
| License / release | ArXiv page uses its perpetual non-exclusive license. No official code/data release was found in this audit. [@yan2026reveal] |
| Exact overlap with our hypothesis | **Directly occupies “evidence sufficiency verification,” missing-clue identification, targeted recovery, and premature-stopping prevention at the method level.** We cannot claim those concepts as new. White space remains in *benchmarking them through controlled paired interventions with ground-truth failure/recovery states*. This is our inference. [@yan2026reveal] |

## 12. TRACE / VES-Bench

**Identity and date.** TRACE/VES-Bench was submitted **2026-08-23** and is accepted to EMNLP 2026 Main Conference. [@liu2026trace]

| Requested field | Reverse-engineered record |
|---|---|
| Problem definition | Audit whether the frames a method actually decoded before answering cover every event required by the answer, rather than scoring only the final answer or predicted interval. [@liu2026trace] |
| Source videos | **348 public long videos**. [@liu2026trace] |
| Scale | **600 four-choice questions**. [@liu2026trace] |
| Duration | Long-horizon videos; aggregate duration statistics were not verified. [@liu2026trace] |
| Modalities | Raw visual clips and text QA; no audio track was verified. [@liu2026trace] |
| Query / QA construction | Temporal Ordering and Event Counting items designed around multiple events. [@liu2026trace] |
| Evidence annotation | Every item has a **jointly necessary set of evidence intervals**. Evaluation audits whether actual decoded frames cover every interval at three strictness levels. [@liu2026trace] |
| Tools / backend | TRACE is training-free, retrieves raw visual clips round by round, grows an evidence bundle, and stops only when the answer stabilizes as evidence grows and a final pass over the same clips agrees. [@liu2026trace] |
| Metrics | Final answer accuracy, frame cost, and evidence-supported correctness under three interval-coverage strictness levels. The abstract reports 50.7% correct with at least two decoded frames in every evidence interval at 98.7 frames/question, and 63.5% overall answer accuracy in the audit. [@liu2026trace] |
| Baseline systems | Same-backbone uniform decoding at 128/256 frames and agentic retrieval baselines; TRACE is also evaluated on Video-MME, LVBench, and LongVideoBench. [@liu2026trace] |
| License / release | Official repository, project page, and VES-Bench dataset card are public; method code is marked “coming soon” in the repository snapshot. The dataset card has no substantive license card, so reuse terms are unresolved. [@traceGithub; @traceProject; @vesbenchDataset] |
| Exact overlap with our hypothesis | **Closest direct benchmark precedent** for jointly necessary evidence, evidence coverage, and premature stopping. It still does not inject controlled tool/modality failures, test recovery after an observed failure, include insufficient/unanswerable states as first-class targets, or test counterfactual evidence utilization. Any “first evidence coverage audit” or “first stopping-aware long-video benchmark” claim is unavailable. This is our inference. [@liu2026trace] |

---

## Additional primary-source work, 2024–2026

| Work | Verified contribution | Relevance to proposed benchmark |
|---|---|---|
| HERBench (2025) | 26,806 five-way MCQs across 12 compositional tasks; every question requires at least three non-overlapping cues from distinct video segments. [@herbench2025] | Blocks broad claims about first unavoidable multi-evidence integration. It is static and does not test failures/recovery. |
| OmniHalluc-L (2026-06-02) | 3,600 single-claim items from 638 videos averaging 24.16 minutes (256.87 h); paired supported/counterfactual audio-visual event-binding claims; strict-pair accuracy; structured audio-negative probes for reliability calibration. [@dong2026omnihallucl] | Direct precedent for counterfactual audiovisual grounding and modality perturbation. Our work must target *agent evidence acquisition/utilization under interventions*, not generic first counterfactual AV benchmark. |
| EG-VQA (2026) | 2,067 videos and 11,838 open-ended QA pairs with fine-grained supporting temporal evidence. [@egvqa2026] | Blocks “first open-ended video QA with temporal evidence” and “first answer + evidence evaluation.” |
| Evidence-Backed Video QA (2026-07-13) | Requires a semantic answer plus temporal segments and dense tracked segmentation masklets; official code/data release. [@wang2026evqa; @evqaGithub] | Blocks broad claims about first verifiable or spatiotemporally grounded VideoQA. |
| VideoZeroBench (2026) | Hierarchical long-video QA that verifies precise spatio-temporal evidence rather than answer correctness alone. [@videozerobench2026] | Further narrows evidence-verification novelty; our distinctive unit must be *interventional trajectories*. |
| Video-MME-Logical (2026-06-26) | Controlled benchmark with 25 tasks across state tracking, sequential counting, temporal ordering, dynamic spatiality, and structural composition, with difficulty control and intermediate-state diagnostics. [@kwan2026videommelogical] | Blocks “first controlled diagnostic video benchmark.” It does not focus on agent tools or evidence failure/recovery. |
| COVER (2025) | Counterfactual video-reasoning benchmark spanning abstract/concrete and perception/cognition axes with decomposed subquestions. [@cover2025] | Blocks first counterfactual video reasoning claims. |
| DualityVidQA-Test (2025) | 600 manually curated real/counterfactual paired samples across four classes, generated through controllable video editing. [@dualityvidqa2025] | Strong precedent for strict paired counterfactual evaluation. |
| MAVIS (2025) | 157K visual QA instances with fact-level citations to multimodal documents for long-form source attribution. [@mavis2025] | Blocks “first multimodal citation/evidence attribution benchmark,” though it is not specifically long-video agent interaction. |
| SIEVE (2026) | Separates sparse multimodal evidence acquisition from verification for video misinformation; an agent constructs a compact evidence package for a verifier. [@sieve2026] | Strong adjacent evidence-seeking/retrieval-verification precedent outside generic VideoQA. |
| AbsenceBench (2025) | Tests whether language models can identify omitted information rather than merely retrieve present information. [@absencBench2025] | Conceptual precedent for missingness diagnosis, but text-only and not an agent/tool benchmark. |
| LongVideoBench (2024) | 3,763 web videos with subtitles, up to one hour, and 6,678 human-annotated MCQs in 17 referring-reasoning categories. [@longvideobench2024] | Establishes long-context interleaved video-language QA and retrieval/reasoning framing. |
| Video-MME (2024) | 900 videos, 254 hours, 2,700 human QA pairs; evaluates video, subtitles, and audio conditions. [@videomme2024] | Early direct evidence that audio/subtitles materially affect video understanding; blocks “first multimodal long-video benchmark.” |
| MLVU (2024) | Videos from 3 minutes to 2 hours and nine long-video evaluation tasks. [@mlvu2024] | Background precedent for multi-task long-video evaluation. |
| MomentSeeker (2025) | Long-video moment-retrieval benchmark varying task types, query modalities, video lengths, and moment distributions. [@momentseeker2025] | Blocks broad novelty claims around long-video retrieval difficulty/efficiency. |
| ScaleLong (2025) | Within-video questions at Clip, Shot, Event, and Story temporal scales. [@scalelong2025] | Precedent for controlled multi-timescale diagnosis, but not interventions or tool recovery. |

## Consolidated takeaways

1. **Necessary evidence is no longer open territory.** LongVidSearch, HERBench, and VES-Bench explicitly enforce or annotate multi-piece necessity. [@longvidsearch2026; @herbench2025; @liu2026trace]
2. **Evidence sufficiency and re-retrieval are no longer open method concepts.** REVEAL verifies sufficiency and directs targeted re-retrieval; WorldMM adaptively continues retrieval; TRACE uses evidence-growth convergence to stop. [@yan2026reveal; @yeo2026worldmmArxiv; @liu2026trace]
3. **Audio/vision necessity and counterfactual modality binding are occupied.** FLARE has a hard bimodal retrieval constraint, MOV-Bench and LongShOTBench cover audio-visual multi-hop reasoning, and OmniHalluc-L uses paired counterfactual event binding and modality perturbation. [@you2026flare; @xu2026movbench; @kurpath2026longshot; @dong2026omnihallucl]
4. **Tool-using video agents are established.** LongVT, LongShOTAgent, AOP-Agent, WorldMM, REVEAL, TRACE, and VideoGAIA all use iterative retrieval, memory, inspection, verification, or external tools. [@yang2026longvt; @kurpath2026longshot; @xu2026movbench; @yeo2026worldmmArxiv; @yan2026reveal; @liu2026trace; @zhang2026videogaia]
5. **The defensible gap is not another static long-video QA set.** The strongest remaining opportunity is a paired, factorial, intervention-based evaluation in which the *same underlying task* is replayed under controlled evidence removal, distractor insertion, modality/tool degradation, restoration, and counterfactual substitution, with the full action/evidence trace audited. This is our inference from the cited boundary. [@longvidsearch2026; @you2026flare; @dong2026omnihallucl; @yan2026reveal; @liu2026trace]
