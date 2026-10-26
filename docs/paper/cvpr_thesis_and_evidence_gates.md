# AV-TRACE CVPR thesis and evidence gates

**Version:** 1.0  
**Frozen:** 2026-09-20  
**Status:** normative paper-claim contract  
**Authority:** this document, `docs/project_charter.md`, and the latest accepted
entries in `docs/decisions.md`

## 1. Canonical thesis

### One-sentence thesis

> Long-video agent reliability cannot be established by answer accuracy alone:
> under a fixed question, claim–evidence graph, backend, and budget, an agent
> must acquire a minimally sufficient multimodal evidence set, use and
> attribute that evidence claim by claim, diagnose insufficiency or access
> failure, recover when a blocked route is restored, and stop only when the
> evidence or a protocol-valid terminal declaration justifies stopping.

This is a falsifiable thesis. It is supported only if matched
`CLEAN`/`BLOCKED`/`RESTORED` episodes expose reliable differences that ordinary
answer accuracy or retrieval recall does not explain. It is weakened or
rejected if:

1. human reviewers cannot reproducibly establish the answer, accepted minimal
   sufficient evidence sets (SESs), necessity groups, and isolated
   interventions;
2. strong learned systems with similar `CLEAN` performance do not differ on
   insufficiency diagnosis, grounded evidence use, stopping, or recovery;
3. all apparent end-to-end differences are explained by retrieval recall
   alone;
4. answer correctness, claim support, and citation validity do not diverge on
   validated cases; or
5. intervention effects are driven by artifacts, leakage, one source video, or
   evaluator-private information.

### Unit of causal comparison

One family fixes:

- the source video and question;
- atomic required and forbidden claims;
- accepted claim–hop–evidence derivations;
- all accepted minimal SESs and necessity groups;
- the fixed backend and common budget.

Only evidence-route availability changes:

- `CLEAN`: an accepted SES is reachable;
- `BLOCKED`: all routes through one validated necessity group or necessary
  channel are inaccessible;
- `RESTORED`: execution begins identically to `BLOCKED`, then a deterministic,
  policy-blind trigger restores exactly the registered route.

The protocol asks not merely whether an endpoint answer is correct, but which
stage failed:

```text
Acquire evidence
    → Judge sufficiency and access state
    → Use evidence for atomic claims
    → Attribute claims to citable observations
    → Continue, recover, abstain, or stop
```

## 2. Contribution contract

The paper must keep three contribution types separate.

### 2.1 Benchmark contribution

A rights-reviewed, long-video audiovisual corpus of source-disjoint matched
episode families with:

- human-validated questions and atomic claims;
- enumerated accepted minimal SESs and necessity groups;
- vision, speech, ambient-audio, and cross-modal coverage;
- isolated `CLEAN`/`BLOCKED`/`RESTORED` states;
- full-timeline candidate universes rather than author-shortlisted windows;
- traceable provenance, versioning, and release boundaries.

This contribution is **not yet established**. Current NOAA families are
machine-adjudicated provisional cases, not benchmark gold.

### 2.2 Diagnostic protocol contribution

A matched interventional protocol that measures:

- minimally sufficient evidence acquisition;
- claim-level evidence utilization and citation;
- calibrated insufficiency and access-failure diagnosis;
- search-policy change and modality/tool routing;
- final-point premature stopping;
- restoration response and triggered recovery under a common budget;
- cost and replayability.

The engineering implementation of this contribution is substantially proven.
Its construct validity is not yet human validated.

### 2.3 Empirical findings contribution

Paper-level findings must concern learned systems on human-valid families, for
example:

- similar `CLEAN` answer accuracy but different false-sufficient,
  premature-stop, or restoration behavior;
- retrieval success without correct evidence use or citation;
- correct answers produced without a complete observed SES;
- agents that recognize insufficiency but fail to recover;
- recovery policies that differ despite a shared backbone and backend;
- generic learned retrievers that alter evidence localization without
  improving end-to-end grounded success.

The current Wave-R result supports only a low-N, machine-provisional,
retrieval-only finding. It is not yet the paper's end-to-end empirical
contribution.

## 3. Superseding semantic decisions

### 3.1 Restoration uses a common supported-answer endpoint

Let \(A_{f,s,m}\) be the **supported-answer endpoint** for family \(f\), state
\(s\), and system \(m\). It equals one only if:

1. the run and budget are valid;
2. the final verdict is `sufficient` and the mode is `answer`;
3. all required claims are correct;
4. no forbidden, contradictory, or unknown claim is asserted;
5. every required claim has valid citations; and
6. those citations instantiate an accepted support derivation from observations
   actually acquired by the system.

The primary paired restoration estimand is:

\[
\Delta_{\mathrm{restore}}^{\mathrm{supported}}
=
\frac{1}{|F_{\mathrm{eligible}}|}
\sum_{f\in F_{\mathrm{eligible}}}
\left(A_{f,R,m}-A_{f,B,m}\right).
\]

Both terms therefore ask the same question: did the system terminate with a
supported answer?

`BLOCKED` state-target success remains important, but it asks a different
question—whether the system correctly declared insufficiency/access failure
without unsupported claims. It must be reported separately. The following
subtraction is prohibited from being called restoration gain:

```text
RESTORED supported-answer success
minus
BLOCKED insufficiency-diagnosis success
```

If retained for historical parity, that heterogeneous quantity must be named
`state_target_success_difference` and labeled non-causal and diagnostic-only.

Additional restoration diagnostics remain separate:

- whether the restoration trigger fired;
- trigger-to-first-accepted-SES actions, cost, and decoded duration;
- trigger-to-supported-finalization actions, cost, and decoded duration;
- correction without grounding;
- retained error after restoration;
- common-failure-set recovery;
- own-failure recovery, with its behavior-dependent denominator disclosed.

### 3.2 Premature stopping and abstention

A final-point route-feasibility certificate is evaluated **after the last tool
response and before `finalize`**. It is evaluator-private and independent of
the policy's stated rationale.

A certified route is feasible only if it provides a legal action suffix that:

1. begins from the exact backend and channel state at the final decision point;
2. respects remaining step and cost budgets;
3. accounts for trigger state and whether each trigger can still legally fire;
4. reaches, retrieves, and exposes an accepted support derivation;
5. includes any required inspect/read action needed to make evidence citable;
6. leaves enough budget for a valid `finalize`; and
7. contains no evaluator-private shortcut unavailable to the policy.

The certificate stores at least:

- final action index and backend-state hash;
- remaining steps and cost;
- currently acquired evidence;
- reachable evidence/necessity routes;
- channel and restoration-trigger state;
- one executable legal action suffix per certified route;
- route steps and cost including finalization;
- validator/version identity.

For an episode whose final observed evidence is insufficient:

- if no route is certified feasible, a correctly typed and supported abstention
  or insufficiency declaration is not premature;
- if a route is certified feasible, termination is premature unless the episode
  contract explicitly permits a typed terminal declaration and the emitted
  declaration satisfies that type's oracle-checked conditions.

This rule applies equally to `answer`, `partial_answer`, and `abstain`.
Abstention is not automatically exempt.

A **protocol-valid typed terminal declaration** must:

- be enumerated before model runs in the episode/track contract;
- identify an allowed declaration class and the applicable missingness/access
  cause;
- contain no unsupported required claim;
- satisfy class-specific oracle conditions; and
- be independently validated.

The current boolean `diagnosis.recovery_route_declared` and free-text
description do not, by themselves, create an exemption. Unless a track
predeclares an allowed terminal declaration type, the exemption set is empty.
A `budget_guard` is valid only when the certificate shows that no complete
route fits the remaining budget; it cannot excuse stopping while a route is
certified feasible.

Primary premature-stop denominator:

```text
episodes with insufficient observed evidence at finalization
and at least one certified feasible route
```

Episodes without a valid certificate receive `null`, not zero. Correct
abstention/diagnosis is reported separately from premature stopping.

### 3.3 Learned retrieval readiness

`LEARNED_RETRIEVAL_READY` is an engineering/readiness gate, not a superiority
claim.

It may be reached when all preregistered learned **modality retrievers** for the
wave:

- use pinned, integrity-checked model snapshots;
- load and infer offline;
- cover the frozen candidate universe;
- produce finite deterministic embeddings and rankings;
- exclude answer/evidence labels and evaluator-private fields;
- pass matched control, leakage, resource, and replay audits.

A trained learned fusion model is **not required** when no disjoint training
split exists. In that setting:

- learned fusion is disabled and must not be simulated or fit on evaluation
  families;
- fixed, preregistered equal-weight reciprocal-rank fusion is the official
  no-training fusion baseline;
- its parameters, input depth, missing-modality handling, and temporal-binding
  adapter are frozen before evaluation.

For Wave R, both declared modality gates—learned visual and learned audio—plus
the fixed speech control and preregistered RRF comparisons are required.

`WAVE_R_DIAGNOSTIC_GO` means only that preregistered, reproducible descriptive
differences were observed. Improvement is not required. It must never be
expanded into “learned retrieval is better,” “the model is generally worse,”
or a population-level ranking claim.

### 3.4 Canonical non-gold stage vocabulary

The canonical non-gold annotation stage is:

```text
MACHINE_ADJUDICATED_PROVISIONAL
```

It is intentionally independent of experiment scale. Experiment phase is stored
separately, for example:

```text
experiment_phase = REAL_AV_MVP | SCALE1A | SCALE1B_WAVE_R | ...
```

Required boundary flags remain:

```text
human_reviewed = false
gold_annotation = false
final_benchmark_status = FINAL_BENCHMARK_NOT_YET_VALIDATED
```

Historical aliases map as follows and need not be rewritten in frozen results:

| Historical value | Canonical interpretation |
|---|---|
| `MACHINE_ADJUDICATED_PROVISIONAL_MVP` | `MACHINE_ADJUDICATED_PROVISIONAL` with the artifact's recorded experiment phase |
| `MACHINE_ADJUDICATED_PROVISIONAL_SCALE1A` | `MACHINE_ADJUDICATED_PROVISIONAL` with `experiment_phase=SCALE1A` |
| prose `machine-provisional` | shorthand only; serialize the canonical value in new machine-readable artifacts |

No machine-only review, model agreement, counterfactual check, or audit promotes
an item beyond this stage. Promotion requires the human workflow and gate
defined below.

## 4. CVPR evidence ladder

Gates are monotonic claim permissions, not marketing labels. A later gate
inherits all earlier applicable requirements. An engineering milestone can be
proven while a scientific gate remains closed.

### 4.1 `INFRASTRUCTURE_PROVEN`

**Required evidence**

- exact source/media/model identity and integrity;
- full-timeline multimodal indexing and deterministic replay;
- opaque tool protocol with complete action/response trajectories;
- executable `CLEAN`/`BLOCKED`/`RESTORED` and no-trigger controls;
- strict claim/citation, budget, restoration, and route-feasibility metrics;
- independent artifact/metric audit with fail-closed verifiers;
- explicit restricted/release boundaries.

**Forbidden claims**

- human construct validity;
- gold SES, necessity, or modality labels;
- learned-agent behavior;
- benchmark-level model ranking or generalization.

**Current status:** achieved for the bounded research infrastructure, as
documented by the Task-100 and Task-105 final audits.

### 4.2 `CONSTRUCT_VALIDITY_MINI_PILOT_GO`

**Required evidence**

- 8–12 accepted families across at least five source-disjoint videos, with a
  target of 12;
- independent author, blind alternative-evidence finder, validator A,
  validator B, and adjudicator roles;
- human-validated question, answer, atomic claims, evidence intervals, accepted
  alternative SESs, leave-one-out minimality, and necessity-group coverage;
- full-source alternative-support search using both human review and the frozen
  retrieval stack;
- isolated `CLEAN`/`BLOCKED`/`RESTORED`, exact restoration, no-trigger controls,
  and two successful validator trajectories;
- at least one accepted family in each declared vision, speech, ambient, and
  cross-modal stratum, or an explicit no-go for a stratum rather than imputation;
- both approved intervention mechanisms represented;
- shortcut, derived-leak, metadata, transcript-only, silent-video, temporal,
  and intervention-artifact audits as applicable;
- candidate-to-accepted funnel, disagreement counts, adjudication reasons,
  active labor, rejection labor, and replay rate.

**Forbidden claims**

- population-level system ranking;
- CVPR-scale benchmark validity;
- modality necessity outside validated families;
- extrapolation from accepted families to rejected candidates or all long
  videos.

**Current status:** not achieved. Existing families remain
`MACHINE_ADJUDICATED_PROVISIONAL`.

### 4.3 `LEARNED_GENERATION_READY`

**Required evidence**

- a pinned learned generator with offline/reproducible inference;
- model-authored structured claims, citations, sufficiency verdict, diagnosis,
  and abstention rather than evaluator-filled outputs;
- oracle-evidence, complete retrieved evidence, partial evidence, blocked
  evidence, distractor, and malformed-output smoke tests;
- strict final-output validation, bounded repair policy, timeout/OOM handling,
  and fail-closed invalid runs;
- independent recomputation of Answer Score, Citation F1,
  Supported-Claim Rate, false-sufficient rate, and state-target outcomes;
- no evaluator-private leakage.

**Forbidden claims**

- learned planning or recovery;
- benefit of agentic search;
- end-to-end diagnostic separation.

**Current status:** not achieved.

### 4.4 `LEARNED_AGENT_READY`

**Required evidence**

- at least two learned controllers, including ordinary ReAct-style and explicit
  evidence-sufficiency control, using the same frozen backbone where practical;
- identical fixed backend, candidate universe, tool schema, budget, generator
  contract, and failure handling;
- genuinely model-selected actions; deterministic policies may appear only as
  protocol controls;
- independently hashed prompts/configurations and demonstrably distinct state
  transitions;
- complete action traces for all three states plus no-trigger controls;
- validated timeout, malformed action, unavailable channel, OOM, and
  over-budget behavior;
- strict final-point feasibility and premature-stop scoring.

**Forbidden claims**

- one learned controller is scientifically better before human-valid matched
  evaluation;
- recovery from retrieval-only top-\(K\) projection probes;
- general agent reliability.

**Current status:** not achieved.

### 4.5 `END_TO_END_DIAGNOSTIC_GO`

**Required evidence**

- `CONSTRUCT_VALIDITY_MINI_PILOT_GO`,
  `LEARNED_GENERATION_READY`, and `LEARNED_AGENT_READY`;
- preregistered matched comparisons with a common supported-answer restoration
  endpoint;
- at least two learned agents and a non-agent/single-shot control;
- intervention effects visible across at least three source-disjoint videos and
  not wholly attributable to one family;
- at least one validated separation not explained by retrieval recall alone,
  such as acquired evidence but failed utilization/citation, correct
  insufficiency diagnosis but failed recovery, or feasible route with premature
  stopping;
- a nonzero set of validated cases where answer correctness differs from
  supported-answer correctness or citation validity;
- video-cluster uncertainty and complete invalid/missing-run accounting;
- independent leakage, metric, and replay audit.

Before model runs, the experiment must freeze practical-effect thresholds or an
equivalence margin for any “similar CLEAN performance but different
intervention behavior” claim.

**Forbidden claims**

- population-wide superiority;
- final benchmark validity;
- scale-up before construct yield, labor, and rights throughput are acceptable.

**Current status:** not achieved.

### 4.6 `DATA_SCALE_UP_GO`

**Required evidence**

- `CONSTRUCT_VALIDITY_MINI_PILOT_GO` and
  `END_TO_END_DIAGNOSTIC_GO`;
- measured candidate yield, rejection causes, annotation/adjudication labor,
  compute/storage cost, and rights-review throughput;
- a frozen sampling plan, source-disjoint split policy, modality/mechanism
  strata, reserve policy, and power/precision target;
- a credible route to 20–30 rights-cleared videos and 60 accepted families
  without weakening SES, necessity, intervention, or release rules;
- demonstrated reviewer capacity and quality-control throughput.

**Forbidden claims**

- filling quotas by lowering construct thresholds;
- treating candidate videos as accepted sources;
- fitting learned fusion or prompts on evaluation families;
- starting a broad crawl merely to increase item count.

**Current status:** not achieved.

### 4.7 `PAPER_CLAIM_READY`

**Required evidence**

- the scaled, frozen evaluation set and all prior scientific gates;
- at least four preregistered system classes, including strong learned
  long-context/non-agent and learned-agent baselines;
- primary dashboard with video-cluster uncertainty, sensitivity analyses,
  invalid-run accounting, cost, and complete denominator disclosure;
- evidence that the principal intervention-aware finding is not reducible to
  ordinary answer accuracy, one retriever, one model family, one modality, or
  one source;
- ablations for evidence acquisition, generation, sufficiency control,
  restoration trigger, and stopping semantics;
- updated dated related-work/novelty audit;
- a claim-by-claim internal audit showing that every abstract/conclusion claim
  is supported by a frozen result.

**Forbidden claims**

- “first” or “unique” without a new dated and defensible priority audit;
- SOTA or general superiority outside the tested systems and corpus;
- calling machine-provisional evidence human gold;
- hiding negative, null, excluded, or failed strata.

**Current status:** not achieved.

### 4.8 `FINAL_BENCHMARK_VALIDATED`

**Required evidence**

- all scored test families are human adjudicated and frozen;
- alternative SES, minimality, necessity, modality, pair isolation, and
  restoration checks pass under the final schema;
- rights, privacy, attribution, takedown, replacement, and release decisions
  are approved for every public artifact;
- public evaluator, schemas, manifests, checksums, baseline recipes, and
  replay instructions reproduce the released scores within declared tolerance;
- a held-out blind audit and versioned maintenance policy pass;
- no unresolved critical leakage, construct, or reproducibility finding.

**Forbidden claims**

- that restricted internal media or model weights are redistributable;
- that future benchmark versions inherit validation without re-audit;
- that validation implies universal coverage of long-video reasoning.

**Current status:** not achieved.

## 5. Current evidence position

| Item | Current evidence | Gate interpretation |
|---|---|---|
| Real long A/V assets | Five NOAA videos, exact hashes, full-timeline decoding/indexing | Supports `INFRASTRUCTURE_PROVEN` only |
| Action-level C/B/R protocol | Replayed trajectories, no-trigger controls, strict metrics | Supports protocol engineering, not construct validity |
| Learned retrieval | Pinned SigLIP and CLAP, matched controls, deterministic rankings | `LEARNED_RETRIEVAL_READY`; supporting milestone outside the eight-rung ladder |
| Wave-R differences | Five retained machine-provisional families; low-N degradation/differences | Descriptive retrieval finding only |
| Human SES/necessity | None | Blocks `CONSTRUCT_VALIDITY_MINI_PILOT_GO` |
| Learned generation | None | Blocks `LEARNED_GENERATION_READY` |
| Learned agents | None | Blocks `LEARNED_AGENT_READY` |
| End-to-end thesis | Not tested on human-valid families | Blocks all later scientific gates |

The current paper posture is therefore:

```text
INFRASTRUCTURE_PROVEN
LEARNED_RETRIEVAL_READY
CONSTRUCT_VALIDITY_MINI_PILOT_GO = false
LEARNED_GENERATION_READY = false
LEARNED_AGENT_READY = false
END_TO_END_DIAGNOSTIC_GO = false
DATA_SCALE_UP_GO = false
PAPER_CLAIM_READY = false
FINAL_BENCHMARK_VALIDATED = false
```

## 6. Paper claim ledger policy

The machine-readable ledger is:

```text
data/rehearsal_plan/cvpr_claim_evidence_ledger.json
```

The canonical reader-facing ledger is:

| ID | Claim candidate | Current evidence | Status | Minimum missing experiment | Allowed wording now | Forbidden wording now |
|---|---|---|---|---|---|---|
| C001 | Audited matched C/B/R real-A/V protocol | Task-100 and strict real-A/V metric/replay audits | `SUPPORTED_ENGINEERING` | None for bounded engineering; human construct validation for benchmark semantics | “The infrastructure executes and replays matched C/B/R episodes.” | “The benchmark already validates real-agent recovery.” |
| C002 | Answer accuracy alone is inadequate | Metrics separate answer, support, citation, and stopping; no human-valid learned comparison | `HYPOTHESIS_ONLY` | Human-valid learned runs showing endpoint divergence not explained by recall | “The protocol is designed to test hidden failures beyond answer accuracy.” | “We have shown answer accuracy is inadequate for learned agents.” |
| C003 | Human-valid minimal SESs and necessity groups | Current labels are machine-provisional and non-gold | `BLOCKED_BY_HUMAN_VALIDATION` | Independent 8–12-family construct mini-pilot | “Current SESs are provisional protocol hypotheses.” | “Current evidence sets are human gold or proven minimal.” |
| C004 | Blocking/restoration causally isolates semantic insufficiency | Mechanics, closures, and controls pass; semantic routes are not human validated | `BLOCKED_BY_HUMAN_VALIDATION` | Human SES/necessity, pair-isolation, leak, and restoration validation | “The protocol mechanically isolates registered provisional routes.” | “All semantically sufficient evidence is causally removed.” |
| C005 | Common-endpoint restoration gain is interpretable | Independent reviews identified the conflict; D-024 and metrics v0.3.0 freeze the repair | `SUPPORTED_ENGINEERING` | Learned runs on human-valid families for an empirical recovery claim | “Restoration gain uses one supported-answer endpoint.” | “Current results prove learned-agent recovery.” |
| C006 | Route certificates distinguish premature stop from justified abstention | Action-level certificates exist; D-025 freezes abstention semantics | `SUPPORTED_ENGINEERING` | Human-valid certificate audit and learned-controller comparison | “The protocol can score final-point premature stopping.” | “Learned agents are shown to abstain correctly.” |
| C007 | Learned modality retrieval is ready without trained fusion | Pinned SigLIP/CLAP, full coverage, fixed RRF, Task-105 audit | `SUPPORTED_ENGINEERING` | A disjoint split only if learned fusion is later claimed | “Wave R uses audited learned modality retrievers and no-training RRF.” | “Wave R includes learned multimodal fusion.” |
| C008 | Generic learned encoders did not automatically beat controls | Five machine-provisional Wave-R families; descriptive paired differences | `SUPPORTED_LOW_N_DESCRIPTIVE` | Human support audit and larger source-disjoint replication | “On these five provisional families, ranks often degraded.” | “SigLIP/CLAP is generally inferior for long-video retrieval.” |
| C009 | Full-timeline search exposes bounded-to-full degradation | Scale-1A provisional migration and one top-20 exclusion | `SUPPORTED_LOW_N_DESCRIPTIVE` | Human-valid matched replication on more videos | “The provisional migration exposed full-timeline degradation.” | “Full-timeline retrieval is universally harder by this amount.” |
| C010 | Learned sufficiency control improves over learned ReAct | Only deterministic controls exist | `BLOCKED_BY_LEARNED_SYSTEMS` | Same-backbone learned ReAct and sufficiency agents on human-valid C/B/R | “This is a preregisterable learned-agent hypothesis.” | “The sufficiency agent outperforms ReAct.” |
| C011 | Learned agents diagnose access failure and recover | Current recovery is deterministic; Wave-R probes are retrieval-only | `BLOCKED_BY_LEARNED_SYSTEMS` | Learned action-generating agents plus no-trigger controls and common endpoint | “The infrastructure is ready to test learned recovery.” | “Wave R demonstrates learned-agent recovery.” |
| C012 | The protocol empirically separates acquisition, utilization, citation, diagnosis, and stopping failures | The outcomes are operationalized, but no human-valid learned failure population exists | `HYPOTHESIS_ONLY` | Independently adjudicated non-retrieval failure categories in learned traces | “AV-TRACE measures these stages separately.” | “We empirically disentangle all long-video agent failures.” |
| C013 | A modality is necessary in current retained families | Verified necessary V/S/A counts are all zero | `BLOCKED_BY_HUMAN_VALIDATION` | Human answerability and modality-drop tests over all accepted SESs | “Current modality roles are routing hypotheses.” | “Current visual, speech, or ambient labels prove necessity.” |
| C014 | Population-level ranking or SOTA | Low-N provisional retrieval-only study | `PROHIBITED` | Powered human-valid preregistered evaluation, still bounded in wording | “No population-level ranking is made.” | Any SOTA, general superiority, or general inferiority claim |
| C015 | First/unique long-video agentic benchmark | Novelty audit finds substantial prior overlap | `PROHIBITED` | Experiments cannot establish priority; only a new dated literature audit can support narrow wording | “AV-TRACE combines matched interventions with trace-level diagnosis.” | Broad “first,” “unique,” or “only” wording |
| C016 | Current assets are a release-ready public core | Internal integrity and restricted-use evidence only | `PROHIBITED` | Final asset-level rights, privacy, takedown, and release approval | “Current NOAA assets support restricted internal research.” | “Current media/annotations/vectors/weights may be redistributed.” |
| C017 | The project is already a complete CVPR-main work | Infrastructure and learned retrieval are ready; core scientific gates are closed | `PROHIBITED` | Pass all human, learned end-to-end, scale, and paper gates | “This is audited infrastructure plus a low-N retrieval diagnostic.” | “The final CVPR benchmark and claims are complete.” |

Every candidate claim has:

- current authoritative evidence;
- a status;
- its minimum missing experiment;
- wording allowed now;
- wording forbidden now;
- the evidence-ladder gate that may promote it.

Allowed status values are:

```text
SUPPORTED_ENGINEERING
SUPPORTED_LOW_N_DESCRIPTIVE
HYPOTHESIS_ONLY
BLOCKED_BY_HUMAN_VALIDATION
BLOCKED_BY_LEARNED_SYSTEMS
PROHIBITED
```

Before any abstract, introduction, result, or conclusion freeze, every sentence
that asserts novelty, capability, comparison, validity, scale, or release
status must map to a ledger entry and a frozen artifact.

## 7. Next experiment implied by this freeze

This semantic freeze does not authorize broad scale-up. The shortest path to a
CVPR-level paper is:

1. run the human-valid 8–12-family mini-pilot;
2. freeze accepted human-valid families and rejected-case reasons;
3. make a learned evidence-conditioned generator ready;
4. make learned ReAct and learned evidence-sufficiency controllers ready;
5. run the preregistered end-to-end matched diagnostic;
6. scale only if the protocol reveals a non-retrieval diagnostic separation.

The project should stop or revise the thesis if the construct mini-pilot cannot
produce valid families, or if learned end-to-end behavior is fully explained by
ordinary retrieval and answer accuracy.
