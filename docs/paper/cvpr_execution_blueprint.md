# AV-TRACE CVPR execution blueprint

**Version:** 1.0  
**Frozen for planning:** 2026-09-20  
**Scope:** scientific and paper planning only  
**Machine-readable companion:** `data/rehearsal_plan/cvpr_experiment_registry.json`

## 1. Executive decision

AV-TRACE is not yet a validated benchmark or a CVPR-main-ready empirical
paper. The repository currently supports:

- `INFRASTRUCTURE_PROVEN`;
- audited, full-timeline, matched `CLEAN`/`BLOCKED`/`RESTORED` execution;
- `LEARNED_RETRIEVAL_READY`;
- a five-family `MACHINE_ADJUDICATED_PROVISIONAL` Wave-R diagnostic;
- a deferred, executable human construct-validation protocol; and
- a pinned Qwen snapshot plus a frozen learned generation/agent experiment
  contract.

It does **not** currently contain:

- completed human review;
- any H1 or H2 family;
- a completed learned generation/agent pilot;
- an audited end-to-end learned-system result;
- a scaled, source-disjoint evaluation set; or
- a release-cleared public benchmark core.

The shortest credible route to a CVPR main paper is therefore gate-dependent:

```text
preserve audited infrastructure
  -> human construct-validity mini-pilot
  -> learned generation/agent technical audit
  -> H2-primary end-to-end mini diagnostic
  -> scale decision
  -> source-disjoint corpus production and freeze
  -> preregistered main evaluation
  -> claim, novelty, release and artifact audits
```

No later phase may start merely because code exists. In particular, the
current Task-110 implementation and 185-case machine-provisional contract are
**not results** and must not be represented as `LEARNED_GENERATION_READY`,
`LEARNED_AGENT_READY`, or `END_TO_END_DIAGNOSTIC_GO` until separately executed
and audited. This blueprint does not authorize or rerun that pilot.

## 2. Frozen paper thesis and contribution contract

### 2.1 One-sentence thesis

> Long-video agent reliability cannot be established by answer accuracy alone:
> under a fixed question, claim-evidence graph, backend, and budget, an agent
> must acquire a minimally sufficient multimodal evidence set, use and
> attribute that evidence claim by claim, diagnose insufficiency or access
> failure, recover when a blocked route is restored, and stop only when the
> evidence or a protocol-valid terminal declaration justifies stopping.

### 2.2 Unit of causal comparison

The causal unit is a **family**, not an episode and not a retrieval row. A
family fixes the source video, question, atomic claims, accepted
claim-hop-evidence derivations, all accepted minimal sufficient evidence sets
(SESs), necessity groups, backend, and budget. Only route availability changes:

- `CLEAN`: at least one accepted SES is reachable;
- `BLOCKED`: every accepted route through one human-validated necessity group
  or necessary channel is inaccessible;
- `RESTORED`: execution begins identically to `BLOCKED`, then a deterministic,
  policy-blind trigger restores exactly the registered route.

### 2.3 Three contributions that must remain separate

1. **Benchmark contribution:** a rights-reviewed, source-disjoint corpus of
   human-adjudicated C/B/R families with complete SES and necessity semantics.
2. **Diagnostic protocol contribution:** matched interventions and trace-level
   Acquire/Ground/Act measurements, including common-endpoint restoration and
   final-point route certificates.
3. **Empirical contribution:** learned-system separations on human-valid held-out
   families that ordinary answer accuracy or retrieval recall does not explain.

The paper is not viable as a component-stacking or “first agentic audiovisual
RAG benchmark” paper. Its differentiator must be the matched intervention and
the resulting causal, trace-grounded diagnosis.

## 3. Exact claim contract

The following are the intended main-paper claims. They are candidate claims,
not present results. Each may enter the abstract or conclusion only after its
named acceptance rule passes on frozen artifacts.

| Main claim | Exact admissible wording after gate | Required evidence and gate | Failure consequence |
|---|---|---|---|
| **MC1 — protocol validity** | “AV-TRACE provides human-adjudicated matched evidence-access interventions that preserve the question, evidence graph, backend, and budget while changing the reachability of a validated necessary route.” | H2 validation of SESs, necessity groups, pair isolation, derived-leak closure, exact restoration, and no-trigger controls; `CONSTRUCT_VALIDITY_MINI_PILOT_GO`, then final held-out audit. | If construct yield or isolation fails, do not scale the benchmark; revise the family construction protocol or stop. |
| **MC2 — answer accuracy is incomplete** | “On the held-out AV-TRACE core, answer correctness and supported-answer correctness diverge, and answer accuracy alone does not reveal all intervention-induced failures.” | On H2 test families from at least three source videos, a nonzero answer-correct/unsupported-or-invalid-citation set and at least one preregistered intervention-aware separation whose practical effect exceeds its frozen margin; `END_TO_END_DIAGNOSTIC_GO`. | If no divergence appears, narrow the paper to protocol/benchmark construction and do not claim answer accuracy is inadequate empirically. |
| **MC3 — failure-stage separation** | “AV-TRACE distinguishes failures of evidence acquisition, evidence use, citation, access diagnosis, and stopping from complete traces.” | At least two non-retrieval failure categories, each on H2 cases from at least two source videos, independently replayed and not wholly attributable to retrieval recall; `END_TO_END_DIAGNOSTIC_GO`. | If every failure is explained by acquisition, make retrieval the empirical focus and drop the broader stage-separation claim. |
| **MC4 — matched recovery is measurable** | “Restoration response can be estimated with a common supported-answer endpoint and separated from BLOCKED-state diagnosis, no-trigger behavior, and recovery cost.” | Human-valid C/B/R families, deterministic policy-blind triggers, no-trigger controls, common-endpoint paired restoration, trigger-conditioned latency/cost, and independent replay. | If restoration or no-trigger isolation fails, remove causal recovery language and report only state-specific behavior. |
| **MC5 — sufficiency-aware behavior differs from ordinary ReAct** | Preferred directional form, only if supported: “With a shared backbone, backend, retrieval, and budget, explicit evidence-sufficiency control reduces false sufficiency and/or premature stopping relative to ordinary ReAct without a practically unacceptable loss in CLEAN supported-answer success.” | H2-primary, same-backbone learned ReAct versus learned sufficiency controller; frozen non-inferiority margin for CLEAN and effect thresholds for BLOCKED FSR/premature stop; video-cluster uncertainty; `PAPER_CLAIM_READY`. | If direction is null or adverse, report the null/adverse result. The protocol paper can survive if MC2–MC4 hold across other systems. |
| **MC6 — retrieval is not the whole story** | “Matched retrieval coverage does not fully determine grounded success or recovery: systems with the same retrieved observations can differ in claim support, citation, stopping, or recovery.” | Evidence-conditioned generator and policy ablations with identical acquired observations; mediation/stratified analysis conditioned on all-evidence acquisition; at least one non-retrieval separation across multiple videos. | If conditioning on retrieval removes all differences, reject the central end-to-end thesis and reframe as a retrieval benchmark/negative result. |
| **MC7 — generic learned retrieval is not automatically beneficial** | “For the tested frozen encoders and AV-TRACE corpus, replacing task-aligned controls with generic learned modality encoders does not consistently improve evidence localization and may propagate degradation to grounded outcomes.” | Human-revalidated support registry; source-disjoint replication of F-CTRL versus F-VA; end-to-end propagation analysis; bounded wording to tested encoders/data. | If Wave-R degradation disappears after human alternative-SES review, report provisional-label incompleteness as the finding and drop the encoder claim. |

Engineering claims corresponding to ledger C001, C005, C006, and C007 may be
used now with their bounded wording. Claims MC1–MC7 remain gated.

## 4. Annotation-stage firewall

All new records must separate annotation status from experiment phase.

| Stage | Meaning | Permitted paper use |
|---|---|---|
| `MACHINE_ADJUDICATED_PROVISIONAL` | Canonical non-gold stage. Includes P0/P1/P2 machine tiers and all current NOAA families. `human_reviewed=false`, `gold_annotation=false`. | Engineering validation, candidate mining, dry runs, low-N descriptive diagnostics, appendix-labeled provisional analyses. Never a primary scientific denominator. |
| `H1_HUMAN_VALIDATED` | Four independent role forms are complete, full-source alternative search is complete, two validators agree on critical constructs, and critical checks pass. Not adjudicated gold. | Construct-yield and disagreement analysis; development/validation work. Excluded from primary test claims unless promoted to H2 before split freeze. |
| `H2_HUMAN_ADJUDICATED_GOLD` | Independent adjudication resolves all critical issues and accepts the family. Rights/release remains a separate gate. | Eligible for frozen evaluation after source-level split assignment. Only H2 families may enter primary paper metrics. |

Human validation is currently `DEFERRED_NOT_EXECUTED`: zero H1 and zero H2
records exist. Machine agreement, counterfactual machine checks, model
agreement, or an audit cannot promote a family to H1/H2.

## 5. Gate-dependent execution program

### Phase 0 — preserve and register the current state

**Purpose.** Prevent scientific drift while human and learned-system evidence is
still missing.

**Inputs.**

- Task-100 Scale-1A final audit;
- Task-105 Wave-R final audit;
- `cvpr_thesis_and_evidence_gates.md`;
- metrics protocol v0.3.0;
- Task-108 deferred protocol and schemas;
- Task-109 Qwen snapshot;
- current Task-110 code, prompts, and frozen 185-case contract.

**Actions.**

1. Hash every normative input before a future experiment.
2. Preserve the canonical stage `MACHINE_ADJUDICATED_PROVISIONAL`.
3. Treat Task-110 artifacts as implementation/contract evidence only until an
   independent run and audit exists.
4. Freeze the primary metrics, practical-effect thresholds, invalid-run rules,
   and source-level split policy before viewing any new aggregate outcome.

**Exit.** Documentation and registries are internally consistent; no scientific
gate is promoted.

### Phase 1 — deferred human construct-validity mini-pilot

**Experiment IDs:** `E-CV-01`, `E-CV-02`.

**Minimum scale.**

- 8–12 completed families, with a paper-gate target of 12 (the Task-108
  sampler's preferred operational default is 10);
- at least five and at most six source-disjoint videos;
- current five retained NOAA families may be sampled but are not presumed
  valid and cover only three source videos;
- add two to three source videos before execution;
- at least one candidate in each vision, speech, ambient, and cross-modal
  stratum, or declare that stratum no-go rather than imputing validity;
- both intervention mechanisms represented;
- at least one deterministic random low-risk control.

**Required human roles.**

1. question/claim author or verifier;
2. blind full-source alternative-evidence finder;
3. validator A;
4. validator B;
5. independent adjudicator.

All five identities are distinct within a family. The blind finder must not see
the preferred SES, machine tier/confidence, model rankings, validator decisions,
or adjudication.

**Required checks.**

- answerability, ambiguity, answer and atomic-claim correctness;
- precise interval support;
- complete full-source alternative evidence and alternative SES search;
- leave-one-evidence-out minimality;
- necessity-group hitting-set validation over every accepted SES;
- `drop_vision`, `drop_speech`, `drop_ambient`, question-only, and metadata-only
  counterfactuals;
- C/B/R pair isolation, derived-leak closure, exact restoration, no-trigger
  behavior, and feasible recovery route;
- rights, release, privacy, safety, attribution, and takedown flags;
- two successful validator trajectories per accepted family;
- active labor and rejection/repair reasons.

**Decision.**

- `GO`: 8–12 complete, at least five source videos, all roles complete, H1
  yield at least 75%, H2 yield at least 60%, pair-isolation failure at most
  10%, no unresolved critical hold, and no systematic
  minimality/modality failure over 25%.
- `REPAIR`: at least 40% reach H1 or failures are localized and repairable.
- `NO_GO`: fewer than 40% reach H1, at least half are rejected, or systematic
  alternative-support/minimality/necessity/isolation/rights failures undermine
  the construct.

The mini-pilot is always `LOW_N_MINI_PILOT_DESCRIPTIVE_ONLY`. It cannot support
population model rankings or final benchmark validation.

### Phase 2 — learned generation and learned-agent technical readiness

**Experiment IDs:** `E-GA-01`, `E-GA-02`.

This phase must be performed by the owner of the learned-agent work, not by
this planning task. The existing Qwen snapshot and Task-110 code/contract may
be used, but their presence is not a passed gate.

**Required systems.**

- evidence-conditioned learned generator;
- learned ReAct;
- learned evidence-sufficiency controller using the same backbone;
- deterministic ReAct and deterministic sufficiency controls;
- single-shot learned generation over F-CTRL and F-VA;
- complete/provisional-evidence and partial-evidence generator diagnostics.

**Required readiness checks.**

- actual pinned Qwen inference through the isolated JSONL process boundary;
- no evaluator-private IDs, state role, answer key, support sets, or trigger
  definition exposed to the model;
- strict structured finalization and at most one bounded repair;
- no deterministic answer substitution on model failure;
- complete C/B/R and no-trigger trajectories for both learned policies;
- timeout, malformed output/action, OOM, over-budget, and process-crash
  failures typed and fail-closed;
- independent recomputation of Answer Score, Citation F1,
  Supported-Claim Rate, FSR, state outcomes, route certificates, and replay.

Machine-provisional runs may establish technical readiness, but they remain
low-N engineering evidence. They do not satisfy the human-valid end-to-end
gate and must not be pooled with H1/H2 primary results.

### Phase 3 — H2-primary end-to-end mini diagnostic

**Experiment ID:** `E-E2E-01`.

Run only after `CONSTRUCT_VALIDITY_MINI_PILOT_GO`,
`LEARNED_GENERATION_READY`, and `LEARNED_AGENT_READY`.

**Primary family set.** Every accepted H2 mini-pilot family, with no
post-outcome family replacement. H1-only families may appear in a sensitivity
table but not in the primary denominator.

**Primary systems.**

1. single-shot learned generator over F-CTRL;
2. learned ReAct over F-CTRL;
3. learned evidence-sufficiency controller over F-CTRL.

**Mandatory secondary retrieval factorial.**

- repeat the three learned systems over F-VA;
- report retrieval-by-policy interactions;
- do not tune F-VA, prompts, or fusion on these families.

**Protocol controls.**

- deterministic ReAct;
- deterministic evidence-sufficiency;
- oracle/H2-evidence-conditioned learned generator;
- partial-evidence learned generator;
- RESTORED no-trigger controls.

**Gate-defining separations.**

At least one of the following must occur on H2 families from at least three
source videos and not be wholly attributable to one family:

- acquired accepted evidence but failed utilization or citation;
- correct insufficiency diagnosis but failed recovery;
- a certified feasible route but premature stopping;
- answer correctness without supported-answer correctness;
- similar CLEAN performance but practically different BLOCKED FSR,
  premature-stop, or RESTORED recovery.

Before execution, freeze:

- a CLEAN supported-answer equivalence/non-inferiority margin of **0.10
  absolute** for the primary learned ReAct versus learned-sufficiency contrast;
- a minimum practically meaningful paired improvement of **0.15 absolute** in
  BLOCKED FSR, premature-stop rate, or common-endpoint restoration gain for a
  directional controller claim;
- a minimum non-retrieval diagnostic count of **two failure categories**, each
  represented on **at least two source videos**;
- complete invalid/missing-run accounting.

These are practical-effect gates, not low-N significance thresholds. The
mini-diagnostic may return `INCONCLUSIVE` even when the technical systems pass.

### Phase 4 — scale-up decision and data production

**Experiment IDs:** `E-SCALE-01`, `E-SPLIT-01`, `E-CV-03`.

Scale only if Phase 3 yields a non-retrieval diagnostic separation and Phase 1
shows acceptable construct and rights throughput.

**Minimum viable paper scale.**

- 20 rights-cleared, source-disjoint videos;
- 60 H2 families;
- 180 C/B/R episodes per system;
- at least four primary learned system classes;
- at least 720 core runs before diagnostics, retries, and reserves.

The 20-video minimum is the lower bound for video-cluster uncertainty, not a
claim of domain representativeness. The preferred acquisition envelope remains
20–30 videos. If 60 H2 families cannot be obtained without weakening
construct rules, the project must reduce its claim scope rather than fill a
quota with lower-quality items.

**Production funnel.**

1. Build 100–200 P-tier candidates.
2. Stratify by modality, intervention, source/domain, machine disagreement,
   learned/control ranking disagreement, correct-answer/wrong-citation,
   uncertain minimality, alternative-support risk, rights risk, and random
   low-risk controls.
3. Human-review 30–50 candidates first to estimate yield and labor.
4. Continue production only under unchanged H2 rules until 60 frozen families
   and the source/stratum minima are met.
5. Preserve every rejection and repair reason.

### Phase 5 — frozen main evaluation

**Experiment IDs:** `E-MAIN-01` through `E-MAIN-06`.

The main evaluation begins only after source-level splits, H2 annotations,
rights decisions, prompts, model snapshots, retrieval, budgets, metrics,
practical thresholds, and an invalid-run reserve are frozen.

#### Primary system classes

At least four learned classes are required:

1. **Direct/long-context learned non-agent baseline.** A pinned video-capable
   model or other defensible learned long-context baseline, evaluated with the
   same final-output validator and with derived transcript/audio inputs
   disclosed.
2. **Single-shot learned RAG.** The frozen learned generator over a fixed
   retrieval backend.
3. **Learned ReAct.** Same generator/backbone/backend/budget as the
   sufficiency-aware agent where practical.
4. **Learned evidence-sufficiency agent.** Explicit public claim-slot coverage,
   missing modality/hop/cause hypotheses, calibrated sufficiency, and
   status/recovery actions.

Protocol-only deterministic controls are reported separately and never called
learned baselines. F-CTRL is primary unless the disjoint development split
supports a separately frozen learned fusion model. F-VA remains a mandatory
retrieval sensitivity condition.

#### Primary comparisons

1. learned sufficiency versus learned ReAct, paired by family/state;
2. agentic policies versus single-shot learned RAG;
3. direct/long-context versus retrieval-grounded systems;
4. F-CTRL versus F-VA within each compatible learned system;
5. `CLEAN` versus `BLOCKED` and `BLOCKED` versus `RESTORED` within family;
6. answer correctness versus supported-answer correctness and citation
   validity.

No weighted leaderboard scalar is primary.

## 6. Source-disjoint split logic

### 6.1 Grouping unit

All derivatives of the same source program or media lineage form one
`source_group_id`. This includes mirrored uploads, excerpts, alternate
encodings, transcript variants, near-duplicate edits, and all families from
that source. A source group may appear in exactly one split.

### 6.2 Split assignment

Assign source groups, not families, before any prompt, retriever, fusion, or
threshold tuning on H2 outcomes.

For the minimum 20-video / 60-family corpus:

| Split | Minimum source videos | Target H2 families | Allowed use |
|---|---:|---:|---|
| Development/train | 8 | 24 | Prompt development, query decomposition, and learned fusion training if used. |
| Validation | 4 | 12 | Model/checkpoint selection, calibration, practical-threshold checks, and one-time design freeze. |
| Test | 8 | 24 | Locked primary evaluation only. No tuning or family replacement after outcomes. |

If 30 videos are available, prefer a 12/6/12 source split and retain additional
blind reserve sources for audit/replacement. If a stratum has too few source
groups to occur in all splits, do not duplicate a source across splits; merge
the stratum into an explicitly exploratory analysis or acquire more sources.

### 6.3 Leakage controls

- Near-duplicate detection and provenance review occur before split freeze.
- Every family, clip, transcript chunk, feature vector, query paraphrase, and
  alternative SES inherits its source split.
- Test questions, claims, support intervals, model rankings, and adjudication
  rationales are evaluator-private.
- Prompt/fusion tuning uses development and validation only.
- Foundation-model pretraining overlap is not claimed absent; known exact
  public-source overlap is recorded as a limitation and analyzed where
  possible.
- Rejected candidates from test sources remain test-private and cannot be used
  as training negatives.
- Public compatibility suites are separate and unpooled.

## 7. Metrics, estimands, and statistical unit

### 7.1 Primary experimental unit

The primary causal unit is the matched family. The primary independent
resampling unit is the **source video/source group**.

Required aggregation:

1. compute episode outcomes;
2. compute state contrasts within family;
3. average family outcomes within source video;
4. estimate uncertainty by resampling source videos.

Episodes and families from one source are not treated as independent samples.

### 7.2 Primary dashboard

**Acquire**

- Evidence Recall and All-Evidence Success at preregistered depths;
- first accepted evidence rank, MRR, nDCG;
- inspected/decoded fraction and retrieval burden;
- modality-route coverage and all-SES coverage.

**Ground**

- Answer Score;
- Citation F1;
- Supported-Claim Rate;
- unsupported-claim rate;
- correct-answer/wrong-citation rate;
- supported-answer endpoint;
- partial-evidence hallucination rate.

**Act**

- `BLOCKED` false-sufficient rate and high-confidence FSR;
- final and stepwise sufficiency Brier score;
- access-failure diagnosis accuracy and multiclass Brier score;
- final-point premature-stop rate;
- common-endpoint paired restoration gain;
- trigger-conditioned recovery, no-trigger false recovery;
- actions/cost/decoded duration from trigger to first accepted SES and
  supported finalization;
- query reformulation, modality switch, status checks, redundant search;
- completion, invalid-run, and deterministic replay rates.

**Cost**

- calls, tool cost, decoded video/audio seconds;
- tokens, latency, peak memory where available;
- cost per supported answer.

### 7.3 Confirmatory contrasts and uncertainty

For the frozen test split:

- report paired absolute risk differences first;
- report video-cluster bootstrap 95% confidence intervals with at least 10,000
  resamples;
- report a source-level randomization/permutation test for the small, frozen
  confirmatory comparison family when feasible;
- use Holm correction across the preregistered primary learned-controller
  contrasts only;
- use BH only for labeled exploratory secondary analyses;
- report exact denominators, invalid/null counts, and source leave-one-out
  sensitivity;
- show modality and intervention-mechanism strata without claiming effects for
  strata with fewer than five source videos.

At fewer than 20 source videos, all model comparisons remain descriptive and
must carry a low-source warning. No family-level bootstrap substitutes for
video clustering.

### 7.4 Missing and invalid runs

- No silent retry selection.
- Predeclare one repair attempt where allowed.
- A timeout, malformed output/action, OOM, over-budget event, process crash, or
  failed route certificate is reported under its typed outcome.
- Primary analysis is fail-closed: invalid runs do not become successes or
  deterministic fallback answers.
- Report both intention-to-evaluate results, where invalid runs count as
  failures for endpoint success, and valid-run-only sensitivity.
- Premature stop is `null`, not zero, without a valid final-point certificate.

## 8. Required baselines

| Baseline | Role | Required controls |
|---|---|---|
| Deterministic ReAct probe | Protocol positive/control behavior, not a learned baseline | Same backend, tools, state machine, and budget. |
| Deterministic evidence-sufficiency probe | Checks metric and intervention sensitivity | Same as above; never used for learned capability claims. |
| Direct/long-context learned model | Tests whether retrieval/agent scaffolding is necessary | Same question set and final validator; exact media sampling and derived inputs disclosed. |
| Single-shot learned RAG over F-CTRL | Non-agent learned grounding baseline | Same generator and final schema as learned agents. |
| Single-shot learned RAG over F-VA | Retrieval sensitivity | No evaluation-family tuning. |
| Learned ReAct | Ordinary learned agent comparator | Same backbone/backend/budget/generator as sufficiency agent where practical. |
| Learned evidence-sufficiency | Main controller hypothesis | Only public claim slots and observations; no evaluator-private graph. |
| Oracle/H2-evidence-conditioned generator | Upper-bound utilization diagnostic, not a deployable system | Receives accepted evidence only; tests Ground independent of Acquire. |
| Partial-evidence generator | Hallucination/refusal diagnostic | Receives preregistered incomplete support. |
| RESTORED no-trigger control | Tests trigger leakage and false recovery | Identical initial blocked state with restoration disabled. |

At least two model/backbone families must appear somewhere in the final paper
evaluation to support a claim that a finding is not one-model-specific. The
same-backbone ReAct/sufficiency pair remains the clean controller comparison;
the second backbone may be a direct or single-shot learned baseline if compute
prevents duplicating both agents. The currently inventoried direct candidate is
`HuggingFaceTB/SmolVLM2-2.2B-Instruct` at revision
`482adb537c021c86670beed01cd58990d01e72e4`; it remains optional until its
resource, exact-snapshot, input-sampling, and output-validation gates pass.

## 9. Required ablations

1. **Answer-only scoring:** compare model conclusions under Answer Score versus
   supported-answer and citation-aware scoring.
2. **Observed-evidence lock:** feed identical acquired observations to the same
   generator across controller outputs to isolate evidence utilization.
3. **Oracle/H2 evidence versus retrieved evidence:** separates retrieval from
   generation/grounding.
4. **Partial evidence:** measures unsupported completion and calibrated refusal.
5. **F-CTRL versus F-VA:** tests whether learned retrieval changes propagate to
   Ground/Act outcomes.
6. **Single-modality controls:** V-CLIP/V-SigLIP2, A-AST/A-CLAP, and S-BM25
   where the H2 family is eligible.
7. **Explicit sufficiency fields removed:** same learned-agent backbone and
   budget, but remove claim-slot coverage, missingness, or calibrated
   sufficiency structure one component at a time.
8. **Status tool removed:** tests whether `get_channel_status` enables diagnosis
   or merely leaks restoration.
9. **No-trigger restoration control:** estimates false recovery and trigger
   artifacts.
10. **Route-certificate semantics:** compare final-point scoring with and
    without typed terminal exceptions; the normative result uses the frozen
    certificate semantics.
11. **Budget caps:** only separate frozen runs at preregistered caps; no
    retrospective truncation.
12. **Alternative-SES sensitivity:** score against all H2 accepted SESs versus a
    single preferred route to quantify registry incompleteness effects.
13. **Source leave-one-out:** tests whether any headline effect is driven by one
    video.
14. **Mapper sensitivity:** for systems that cannot emit public claim handles,
    report frozen-mapper errors separately.

## 10. Paper tables and figures

### Main-paper tables

| ID | Content | Gate |
|---|---|---|
| **Table 1** | Corpus and construct statistics: videos, families, duration, modality/intervention strata, SES count, alternative SESs, H1/H2 funnel, pair-isolation pass, rights/release status, labor. | H2 corpus freeze |
| **Table 2** | System matrix: model/backbone, direct/RAG/agent class, retrieval variant, tool access, budget, prompt hash, train/development use, parameters, completion. | Main experiment freeze |
| **Table 3** | Primary Acquire/Ground/Act dashboard by system and state, with source-cluster 95% intervals and invalid counts. | `PAPER_CLAIM_READY` |
| **Table 4** | Paired treatment effects: C→B degradation, B→R common-endpoint restoration, BLOCKED FSR, premature stop, no-trigger false recovery, and cost. | `END_TO_END_DIAGNOSTIC_GO` |
| **Table 5** | Failure taxonomy and answer-versus-supported-answer divergence, with number of families and source videos per category. | MC2/MC3 |
| **Table 6** | Ablations: retrieval backend, oracle/partial evidence, sufficiency components, status tool, budget, and alternative-SES scoring. | Main evaluation |

### Main-paper figures

1. **Figure 1 — family intervention schematic.** One fixed claim-evidence graph
   replayed as CLEAN/BLOCKED/RESTORED, with the common supported-answer endpoint.
2. **Figure 2 — trace and metric decomposition.** Acquire → judge → Ground →
   Act/Stop, with examples of retrieval, utilization, citation, diagnosis, and
   stopping failure.
3. **Figure 3 — answer accuracy versus supported reliability.** Per-system
   scatter or paired bars showing Answer Score, supported-answer success,
   Citation F1, and FSR.
4. **Figure 4 — restoration trajectories.** Trigger-aligned probability,
   actions, modality allocation, evidence acquisition, and supported
   finalization.
5. **Figure 5 — source-level effects.** Video-level paired effect forest plot
   and leave-one-source-out sensitivity.
6. **Figure 6 — construct funnel.** P-tier candidate to H1/H2 acceptance,
   rejection causes, alternative-SES discovery, and annotation labor.

### Appendix requirements

- complete metric definitions and denominator rules;
- all prompt/config/model/source hashes;
- family and source split manifests without private gold leakage;
- full negative/null strata;
- rights/release boundary;
- invalid-run and replay audit;
- per-family qualitative traces selected by a frozen rule, not cherry-picked.

## 11. Negative-result branches

| Observed branch | Required decision and paper posture |
|---|---|
| **Construct mini-pilot NO_GO** | Stop benchmark scale-up. Publish no benchmark-valid or modality-necessity claim. Repair the construct or abandon C/B/R as the main thesis. |
| **Construct REPAIR** | Version the protocol, rerun affected families, and keep all learned results provisional. Do not aggregate pre- and post-repair families without a compatibility audit. |
| **Alternative SES discovery is high** | Rebuild support graphs before interpreting retriever misses. A valuable negative result may be that machine-provisional support registries systematically undercount valid evidence. |
| **Modality necessity rarely survives** | Drop modality-necessity claims and reframe modalities as routing/corroboration strata. Do not force single-modality labels. |
| **Learned generator fails readiness** | No end-to-end paper claim. Diagnose schema/grounding limits or use a separately preregistered stronger model; never substitute deterministic answers. |
| **Learned agents fail readiness** | Keep a generator/retrieval paper only if scientifically sufficient; do not call scripted probes learned agents. |
| **No end-to-end separation beyond retrieval** | Reject MC2/MC3/MC6 in their strong form. Reframe around retrieval localization, benchmark construction, or a negative result that agent policies add no measurable robustness under the tested protocol. |
| **Sufficiency controller is null or worse** | Report the null/adverse result. Retain protocol claims if other systems exhibit diagnostic separations. |
| **Wave-R degradation disappears after H2 audit** | Attribute the provisional result to incomplete/incorrect support registration; drop generic-encoder degradation as a main claim. |
| **Only one source drives an effect** | Remove the headline generalization, report source sensitivity, and acquire additional sources before submission. |
| **Rights throughput fails** | Keep internal scientific results separate from public release; do not call the corpus a public core. Consider a protocol paper only if release requirements can still be met. |
| **Minimum scale is not reached** | Do not claim population rankings or a validated benchmark. Submit only if the venue/story can honestly support a smaller diagnostic study. |

## 12. Explicit prohibited claims

The following are prohibited unless a future normative decision explicitly
supersedes this list:

- “AV-TRACE is already a validated benchmark.”
- “Current NOAA families contain human-gold minimal SESs or necessity groups.”
- “Machine agreement, machine counterfactual checks, or model agreement equals
  H1/H2.”
- “Vision, speech, or ambient audio is necessary” without H2 alternative-SES
  and modality-drop validation for the named family.
- “Wave R proves learned-agent recovery.”
- “The current benchmark distinguishes source evidence absence from access
  failure.” Pilot-0 has no source-absence partition; adding one requires a
  separate decision, schema, validation, and experiment.
- “The existing Task-110 code or frozen contract proves learned generation or
  learned-agent readiness.”
- “SigLIP2 or CLAP is generally superior or inferior for long-video
  retrieval.”
- “F-VA is learned multimodal fusion.” It is fixed no-training RRF.
- “RESTORED supported-answer success minus BLOCKED diagnostic success is
  restoration gain.”
- “Abstention is never premature.”
- Any SOTA, population-wide model ranking, universal reliability, or
  out-of-domain generalization claim.
- “First,” “unique,” “only,” or equivalent broad priority wording.
- “Current NOAA media, transcripts, vectors, annotations, or model weights are
  authorized for redistribution.”
- Pooling machine-provisional, H1, and H2 outcomes in one primary score.
- Treating episodes or families from one video as statistically independent.
- Training or tuning prompts, retrievers, fusion, thresholds, or mappers on
  held-out test families.
- Hiding rejected families, failed strata, invalid runs, null results,
  no-trigger failures, or source-level sensitivity.

## 13. Submission readiness checklist

`PAPER_CLAIM_READY` requires all of the following:

- 60 H2 families from at least 20 rights-cleared source videos;
- frozen source-disjoint development/validation/test manifests;
- at least four learned system classes and two model/backbone families in the
  paper;
- complete C/B/R and no-trigger runs under common budgets;
- primary dashboard and source-cluster uncertainty;
- at least one non-retrieval diagnostic separation across at least three test
  source videos;
- nonzero answer-versus-supported-answer or citation divergence;
- all required ablations and invalid-run accounting;
- independent metric, leakage, route-certificate, replay, and claim audits;
- dated related-work audit immediately before submission;
- every abstract/conclusion sentence mapped to a frozen claim and result;
- explicit limitations on source diversity, model coverage, rights, and
  generalization.

`FINAL_BENCHMARK_VALIDATED` additionally requires all scored test families to
be H2, a held-out blind construct audit, complete release governance, and a
public evaluator/artifact package that reproduces released scores. A credible
CVPR paper may report a restricted internal evaluation if the release boundary
is explicit, but it may not call restricted assets a release-ready public
benchmark.

## 14. Authoritative inputs

This blueprint is subordinate to newer accepted decisions and was derived from:

- `docs/overview/av_trace_project_status_for_owner.md`;
- `docs/paper/cvpr_thesis_and_evidence_gates.md`;
- `data/rehearsal_plan/cvpr_claim_evidence_ledger.json`;
- `docs/spec/metrics_protocol.md`;
- `docs/review/scale1b_wave_r_final_audit.md`;
- `docs/project_charter.md`;
- `docs/decisions.md`;
- `docs/annotation/construct_validity_protocol.md`;
- `data/rehearsal_plan/construct_validity_mini_pilot_plan.json`;
- `docs/review/scale1b_ga_model_acquisition.md`; and
- the current Task-110 implementation and frozen experiment contract, inspected
  only to record their present technical/planning status.
