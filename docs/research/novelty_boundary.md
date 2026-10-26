# Novelty boundary for an interventional long-video agent benchmark

**As-of date:** 2026-09-05.  
**Status vocabulary:** **Verified fact** is directly supported by a primary-source key. **Inference** is our synthesis or proposed positioning.

## Bottom-line reviewer verdict

**Inference:** A paper framed as “a long-video benchmark with sparse multi-hop evidence, audio-visual reasoning, tool use, evidence sufficiency, recovery, or stopping” would be rejected for weak novelty. Each component already exists in closely adjacent primary-source work: exact necessary clips in LongVidSearch, unavoidable multi-evidence integration in HERBench, hard bimodal retrieval in FLARE, omni-modal long-video QA in LongShOTBench and MOV-Bench, iterative native tool use in LongVT, adaptive sufficiency-oriented retrieval in WorldMM and REVEAL, decoded-frame evidence auditing and convergence-based stopping in TRACE/VES-Bench, and paired counterfactual audiovisual binding in OmniHalluc-L. [@longvidsearch2026; @herbench2025; @you2026flare; @kurpath2026longshot; @xu2026movbench; @yang2026longvt; @yeo2026worldmmArxiv; @yan2026reveal; @liu2026trace; @dong2026omnihallucl]

**Inference:** A defensible paper must make the **intervention itself the experimental unit** and measure causal behavioral changes across matched episodes. The benchmark should not merely contain hard items; it should replay the same latent question/evidence graph under controlled manipulations and score whether the agent detects insufficiency, avoids unsupported answers, changes its search policy, recovers when access returns, and uses newly supplied or counterfactual evidence.

## What is already occupied

### 1. Necessary and multi-hop evidence

- LongVidSearch defines Hop-\(k\) questions with exactly \(k\) necessary clips and claims that deleting any one makes the question unsolvable. [@longvidsearch2026]
- HERBench requires at least three non-overlapping cues from distinct segments. [@herbench2025]
- VES-Bench supplies a jointly necessary set of evidence intervals and audits whether the frames actually decoded cover every interval. [@liu2026trace]
- V-RAGBench makes generation causally depend on retrieval by filtering out questions recoverable from the query, parametric knowledge, or non-evidence chunks. [@lee2026vragbench; @vragbenchDataset]

**Inference:** “Our questions require multiple dispersed evidence pieces” is table stakes, not a thesis.

### 2. Evidence sufficiency, recovery, and stopping

- REVEAL explicitly distinguishes sufficiency from relevance, identifies missing clues after verification failure, and performs targeted re-retrieval. [@yan2026reveal]
- WorldMM iteratively selects memory sources/granularities until it determines that sufficient information has been gathered. [@yeo2026worldmmArxiv]
- TRACE grows a raw-clip evidence bundle and stops only after answer convergence and a same-evidence verification pass. [@liu2026trace]
- LongVT can correct an initially wrong localization by invoking additional crop/resampling calls. [@yang2026longvt]

**Inference:** “First sufficiency-aware/recovery-capable/stopping-aware long-video agent” is indefensible. The possible novelty is a **ground-truth benchmark of these behaviors under controlled perturbation**, not the concepts themselves.

### 3. Omni-modal routing and modality necessity

- FLARE separately evaluates visual, audio, and fused retrieval and filters cross-modal queries with a hard bimodal necessity test. [@you2026flare]
- LongShOTBench explicitly probes visual, speech, ambient-audio, temporal, and cross-modal reasoning, while LongShOTAgent verifies claims over those streams. [@kurpath2026longshot]
- MOV-Bench requires audio-visual evidence integration across temporal hops and accompanies AOP-Agent's active omni-modal perception. [@xu2026movbench]
- Video-MME evaluates video with subtitle/audio conditions. [@videomme2024]

**Inference:** “First long-video benchmark covering vision, speech, and ambient audio” and “first to require both audio and vision” are unavailable claims.

### 4. Counterfactual and perturbation evaluation

- OmniHalluc-L creates supported/counterfactual claims from the same audiovisual event evidence, scores strict pairs, and uses audio-negative modality probes for reliability calibration. [@dong2026omnihallucl]
- COVER systematically evaluates counterfactual video reasoning. [@cover2025]
- DualityVidQA-Test uses 600 manually curated real/counterfactual pairs created with controllable video editing. [@dualityvidqa2025]
- Video-MME-Logical is a controlled diagnostic benchmark with difficulty-controlled synthetic temporal-logical tasks. [@kwan2026videommelogical]

**Inference:** “First counterfactual video benchmark,” “first modality-perturbation benchmark,” and “first controlled diagnostic video benchmark” are indefensible.

### 5. Evidence attribution and verifiability

- EG-VQA pairs open-ended answers with supporting temporal evidence over 2,067 videos and 11,838 QA pairs. [@egvqa2026]
- Evidence-Backed Video QA requires temporal segments and dense tracked masklets in addition to the answer. [@wang2026evqa]
- VideoZeroBench verifies precise spatio-temporal evidence rather than scoring answers alone. [@videozerobench2026]
- MAVIS provides fact-level citations to multimodal documents for long-form source attribution. [@mavis2025]
- VES-Bench goes further for long-video agents by auditing actual decoded frames, not only predicted intervals. [@liu2026trace]

**Inference:** “First evidence-grounded/verifiable/citation-aware video QA benchmark” is unavailable.

### 6. General tool-using long-video agents

- LongVT uses native temporal crop tools. [@yang2026longvt]
- LongShOTAgent uses preprocessing, targeted retrieval, segment refinement, and claim verification. [@kurpath2026longshot]
- WorldMM and REVEAL use iterative memory retrieval. [@yeo2026worldmmArxiv; @yan2026reveal]
- AOP-Agent uses active omni-modal perception. [@xu2026movbench]
- VideoGAIA standardizes video-window inspection, web search, and webpage extraction in a ReAct harness. [@videogaiaGithub]
- TRACE performs round-by-round visual retrieval with a stopping controller. [@liu2026trace]

**Inference:** “First agentic long-video benchmark” or “first video benchmark with tools” is clearly false by September 5, 2026.

## Defensible white space

### White space A — Paired causal interventions over the same evidence graph

**Inference:** None of the audited long-video agent benchmarks was verified to provide a full factorial set of matched episodes generated from one latent item:

1. complete sufficient evidence;
2. one necessary clue removed;
3. semantically similar but non-diagnostic distractor added;
4. relevant modality unavailable or corrupted;
5. a tool returns an error, empty result, stale result, or plausible wrong result;
6. access is restored after failure;
7. decisive evidence is replaced by a counterfactual;
8. evidence arrives incrementally in a known order.

LongVidSearch and VES-Bench provide necessary evidence structure; FLARE and OmniHalluc-L provide modality/counterfactual controls; VideoGAIA provides real tools; REVEAL and TRACE provide sufficiency/stopping methods. The unoccupied contribution is their **causally matched combination with trace-level evaluation**. [@longvidsearch2026; @liu2026trace; @you2026flare; @dong2026omnihallucl; @zhang2026videogaia; @yan2026reveal]

### White space B — Failure recognition and recovery as first-class outcomes

**Inference:** Existing work mostly asks whether iterative search eventually improves QA. A stronger diagnostic benchmark can label:

- whether the agent recognized the observation/tool result as unusable;
- whether it distinguished “no evidence exists” from “my access failed”;
- whether it selected a valid fallback modality/tool;
- how many actions and how much evidence were needed to recover;
- whether the final answer changed appropriately after recovery;
- whether unsupported confidence decreased before recovery and increased after decisive evidence arrived.

No audited source was verified to report a paired **failure-detection → fallback selection → recovery → answer revision** metric suite for long-video agents. [@yang2026longvt; @kurpath2026longshot; @xu2026movbench; @zhang2026videogaia; @yan2026reveal; @liu2026trace]

### White space C — Calibrated abstention under insufficient but plausible evidence

**Inference:** REVEAL calibrates sufficiency verdicts and TRACE audits coverage, but the benchmark side remains weak for explicitly unanswerable states. A defensible test would include minimally edited insufficient episodes whose visible content supports a tempting answer but does not logically determine it, then score abstention/selective risk and evidence-aware confidence. [@yan2026reveal; @liu2026trace; @absencBench2025]

The key distinction is:

- **relevance:** retrieved material is on-topic;
- **coverage:** all annotated evidence intervals were observed;
- **logical sufficiency:** observed evidence entails one answer rather than merely correlating with it;
- **access status:** missing evidence may be absent from the video or merely unavailable through the current tool;
- **calibration:** confidence tracks those states.

This decomposition is an inference motivated by REVEAL, VES-Bench, LongVidSearch, and AbsenceBench. [@yan2026reveal; @liu2026trace; @longvidsearch2026; @absencBench2025]

### White space D — Counterfactual evidence *utilization* by an interactive agent

**Inference:** Counterfactual benchmarks usually score whether a model answers the altered example correctly. A stronger agent benchmark can measure whether a policy:

- notices that newly observed evidence invalidates its current hypothesis;
- revisits previously accepted evidence;
- changes which tool/modality it queries;
- retracts or revises its answer;
- avoids “belief inertia” when the counterfactual is decisive.

This is narrower than first counterfactual reasoning and complementary to OmniHalluc-L, COVER, and DualityVidQA. [@dong2026omnihallucl; @cover2025; @dualityvidqa2025]

### White space E — Trace-grounded diagnosis across modalities and tools

**Inference:** VES-Bench audits decoded visual frames, while LongShOTBench provides multimodal rubrics and VideoGAIA logs heterogeneous tool calls. A plausible new contribution is a common evidence ledger that records, for every action, the requested source, returned observation, provenance, modality, temporal span, availability/error state, and which answer claim it supports. [@liu2026trace; @kurpath2026longshot; @videogaiaGithub]

The benchmark can then distinguish:

- retrieval miss;
- tool/access failure;
- perception failure on retrieved evidence;
- cross-modal binding failure;
- evidence integration failure;
- sufficiency miscalibration;
- premature stop;
- correct recovery;
- correct answer obtained without sufficient observed evidence.

This taxonomy is our inference; it is not claimed verbatim by the cited papers.

## Claims we must **not** make

| Prohibited or unsafe claim | Why it fails |
|---|---|
| “First long-video retrieval benchmark.” | LoVR and MomentSeeker predate the proposed work. [@cai2025lovr; @momentseeker2025] |
| “First agentic long-video benchmark.” | LongVidSearch, LongShOTBench, VideoGAIA, and VES-Bench already evaluate agentic behavior. [@longvidsearch2026; @kurpath2026longshot; @zhang2026videogaia; @liu2026trace] |
| “First benchmark with multi-hop/necessary evidence.” | LongVidSearch, HERBench, MOV-Bench, and VES-Bench. [@longvidsearch2026; @herbench2025; @xu2026movbench; @liu2026trace] |
| “First evidence-sufficiency method/benchmark.” | REVEAL directly centers explicit sufficiency verification; VES-Bench audits complete evidence coverage. [@yan2026reveal; @liu2026trace] |
| “First to study premature stopping.” | REVEAL criticizes stopping at relevance; TRACE provides evidence-convergence stopping. [@yan2026reveal; @liu2026trace] |
| “First recovery/re-retrieval agent.” | LongVT, WorldMM, AOP-Agent, and REVEAL already retrieve iteratively and can refine or replan. [@yang2026longvt; @yeo2026worldmmArxiv; @xu2026movbench; @yan2026reveal] |
| “First audio-visual long-video benchmark.” | Video-MME, FLARE, LongShOTBench, and MOV-Bench. [@videomme2024; @you2026flare; @kurpath2026longshot; @xu2026movbench] |
| “First benchmark where both audio and vision are necessary.” | FLARE applies a hard bimodal necessity constraint; MOV-Bench targets cross-modal hops. [@you2026flare; @xu2026movbench] |
| “First counterfactual video benchmark.” | COVER, DualityVidQA-Test, and OmniHalluc-L. [@cover2025; @dualityvidqa2025; @dong2026omnihallucl] |
| “First modality perturbation/calibration benchmark.” | OmniHalluc-L includes modality perturbation and reliability calibration. [@dong2026omnihallucl] |
| “First verifiable/evidence-grounded VideoQA benchmark.” | EG-VQA, E-VQA, VideoZeroBench, and VES-Bench. [@egvqa2026; @wang2026evqa; @videozerobench2026; @liu2026trace] |
| “First multimodal source-attribution/citation benchmark.” | MAVIS provides fact-level citations to multimodal documents. [@mavis2025] |
| “First controlled diagnostic video benchmark.” | Video-MME-Logical explicitly uses controlled difficulty and intermediate-state diagnostics. [@kwan2026videommelogical] |
| “First rubric-based long-video evaluation.” | LongShOTBench uses weighted criterion-level rubrics; REVEAL uses a rubric library. [@kurpath2026longshot; @yan2026reveal] |
| “First benchmark to audit evidence actually seen by the model.” | VES-Bench audits actual decoded frames. [@liu2026trace] |

## Claims that may be defensible if the implementation fully supports them

The following are **candidate claims, not verified facts**:

1. **“First paired interventional benchmark for long-video agents that holds the latent question/evidence graph fixed while manipulating evidence availability, distractors, modality access, and tool reliability.”**
2. **“First long-video benchmark to jointly score failure recognition, calibrated insufficiency, fallback selection, recovery efficiency, answer revision, and evidence-supported correctness.”**
3. **“First trace-level causal evaluation of whether an agent uses restored or counterfactual evidence, rather than merely producing the right final answer.”**
4. **“First benchmark to separate evidence absence from access failure in long-video reasoning.”**

Before using “first,” the camera-ready literature check must be repeated because the field is moving rapidly; REVEAL, VideoGAIA, and TRACE appeared between **2026-08-09 and 2026-08-23**. [@yan2026reveal; @zhang2026videogaia; @liu2026trace]

## Three candidate paper theses

Scores use a 1–5 scale and are **our reviewer-style judgment**.

### Rank 1 — Causal resilience under evidence-access interventions

**Thesis.** Long-video agent reliability cannot be inferred from static QA accuracy; it must be measured through matched interventions on evidence and access. Build a benchmark in which each base item yields a causal episode family covering sufficient evidence, clue deletion, distractor insertion, modality outage, tool failure, restoration, and counterfactual substitution. Score the change in policy and answer, not only endpoint correctness.

| Criterion | Score | Reviewer rationale |
|---|---:|---|
| Novelty | **5/5** | The ingredients exist separately, but their paired factorial combination and causal trace analysis were not verified in prior work. [@longvidsearch2026; @you2026flare; @dong2026omnihallucl; @zhang2026videogaia; @yan2026reveal; @liu2026trace] |
| Scientific value | **5/5** | Supports causal attribution of failure to retrieval, access, perception, integration, calibration, or stopping. |
| Feasibility | **3/5** | Requires high-integrity evidence graphs, intervention validity checks, and an instrumented tool harness; annotation cost and leakage control are substantial. |

**Required experiment design.**

- Use matched episode IDs and identical questions across conditions.
- Have at least one verified necessary clue and one verified hard distractor per base item.
- Include both silent failures (plausible empty/wrong output) and explicit errors.
- Log all requests, returned evidence, failures, confidence/sufficiency judgments, and revisions.
- Report average treatment effects and paired confidence intervals, not only aggregate accuracy.
- Include human validation that deleting a clue truly destroys answer identifiability.

**Likely reviewer attack.** “This is just LongVidSearch + FLARE + OmniHalluc-L + TRACE glued together.”  
**Necessary rebuttal.** Demonstrate that static scores cannot predict intervention responses; show rank reversals and distinct failure signatures under matched causal perturbations.

### Rank 2 — Calibrated evidence sufficiency and recovery curves

**Thesis.** The central long-video agent capability is knowing when observed evidence is insufficient and allocating additional search accordingly. Reveal evidence incrementally or restore failed access at controlled steps, requiring an explicit `continue / answer / abstain` decision and confidence after each step.

| Criterion | Score | Reviewer rationale |
|---|---:|---|
| Novelty | **3/5** | REVEAL and TRACE directly occupy sufficiency and stopping; novelty survives only as a benchmark with gold staged evidence states and calibrated decisions. [@yan2026reveal; @liu2026trace] |
| Scientific value | **5/5** | Produces interpretable search-vs-risk curves and directly tests premature stopping. |
| Feasibility | **4/5** | Can be built from items with necessary evidence sets, though sufficiency labels require careful human validation. |

**Core metrics proposed by us.**

- **Sufficiency AUROC / AUPRC:** predict whether currently observed evidence is sufficient.
- **Selective risk:** answer error as a function of coverage/abstention.
- **Premature-stop rate:** agent answers before all necessary evidence is available/observed.
- **Over-search rate:** agent continues after sufficiency is reached.
- **Recovery latency:** actions, frames, seconds, and token cost from restoration to justified answer.
- **Evidence-conditioned calibration error:** confidence error stratified by complete, incomplete, failed-access, and counterfactual conditions.

**Likely reviewer attack.** “REVEAL already verifies sufficiency and TRACE already stops on convergence.”  
**Necessary rebuttal.** Emphasize that those are methods evaluated largely on ordinary QA; the proposed contribution is controlled ground truth for sufficiency states, failure states, and optimal stopping decisions.

### Rank 3 — Omni-modal graceful degradation and routing under failures

**Thesis.** A robust long-video agent should identify which signal carries the decisive evidence, degrade gracefully when that signal or its tool fails, and switch among visual inspection, ASR/speech, ambient-audio retrieval, OCR, and external search.

| Criterion | Score | Reviewer rationale |
|---|---:|---|
| Novelty | **3/5** | FLARE, LongShOTBench, MOV-Bench, and OmniHalluc-L already cover modality necessity/perturbation. Novelty depends on interactive failure/recovery and explicit routing metrics. [@you2026flare; @kurpath2026longshot; @xu2026movbench; @dong2026omnihallucl] |
| Scientific value | **4/5** | Highly relevant to deployed agents and reveals modality-specific brittleness. |
| Feasibility | **3/5** | Requires reliable audio, speech, and ambient-event annotation plus realistic tool-failure simulation. |

**Minimum viable condition set.**

- visual-only sufficient;
- speech-only sufficient;
- ambient-audio-only sufficient;
- vision+speech jointly necessary;
- vision+ambient jointly necessary;
- one modality unavailable;
- one modality returns plausible but wrong evidence;
- modality restored;
- cross-modal counterfactual binding.

**Likely reviewer attack.** “This is an agentic wrapper around FLARE/LongShOT/MOV-Bench.”  
**Necessary rebuttal.** Show paired routing changes, detection of the failed source, fallback quality, recovery after restoration, and calibration—none of which static modality ablations measure.

## Recommended primary thesis and paper framing

**Inference:** Choose **Rank 1** and treat Ranks 2 and 3 as two orthogonal diagnostic axes inside it.

Recommended one-sentence framing:

> We introduce a paired interventional benchmark for long-video agents that causally audits how evidence removal, hard distractors, modality/tool failures, restoration, and counterfactual substitution change evidence acquisition, sufficiency judgments, stopping, recovery, and final answers.

Recommended paper contribution structure:

1. **Intervention model:** a formal latent evidence graph and matched episode family.
2. **Benchmark:** long-video, audiovisual, tool-instrumented episodes with validated necessary evidence and distractors.
3. **Metrics:** endpoint accuracy plus sufficiency calibration, evidence coverage, failure recognition, recovery latency, stopping error, revision correctness, and counterfactual sensitivity.
4. **Findings:** static benchmark leaders need not be interventionally robust; answer accuracy can remain high despite unsupported observation, as VES-Bench motivates. [@liu2026trace]
5. **Baselines:** direct long-context models; uniform sampling; retrieval-only RAG; LongVT-style crop agent; LongShOT-style omni-modal agent; REVEAL-style verifier; TRACE-style convergence controller; VideoGAIA-style heterogeneous-tool agent. [@yang2026longvt; @kurpath2026longshot; @yan2026reveal; @liu2026trace; @videogaiaGithub]

## Go/no-go criteria

**Inference:** Do not submit the benchmark paper unless the pilot demonstrates all of the following:

1. Removing a labeled necessary clue drives human answerability to chance or abstention.
2. Added distractors are semantically competitive but do not change the correct answer.
3. Tool failures are realistic and distinguishable from true negative retrieval only through further action.
4. At least two strong agents show materially different recovery policies under the same failures.
5. Final-answer accuracy and evidence-supported correctness diverge, reproducing the kind of hidden unsupported success highlighted by VES-Bench. [@liu2026trace]
6. Intervention-aware metrics reveal model rankings or failure modes not explained by ordinary QA accuracy.
7. Counterfactual episodes measure answer revision based on changed evidence rather than linguistic artifacts, addressing the paired-evaluation concerns motivating OmniHalluc-L and DualityVidQA. [@dong2026omnihallucl; @dualityvidqa2025]

If these conditions fail, the project risks reading as a broad but incremental aggregation of recent benchmarks rather than a new scientific evaluation paradigm.

