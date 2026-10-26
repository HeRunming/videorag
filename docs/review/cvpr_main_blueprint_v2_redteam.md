# Hostile independent red-team review of the AV-TRACE CVPR-main blueprint v2

**Review date:** 2026-09-23  
**Decision token:** `REDTEAM_REPAIR`  
**Review stance:** hostile but constructive independent CVPR benchmark-paper
review  
**Evidence boundary:** repository evidence only; no web browsing and no claim
of literature, model, API, license, or source freshness beyond the dated local
audits  
**Files under direct review:** the frozen pivot, owner report, Task 138
preregistration, Task 139 blueprint, construct-validity protocol and Task 140
audit, source/acquisition and rights audits, and local related-work/novelty
materials

## 1. Bottom-line decision

`REDTEAM_REPAIR`

The paper idea is not dead, but the current repository is not remotely a
submission-ready CVPR main paper. It is a strong engineering substrate and an
unusually careful prospective protocol surrounding a scientific result that
does not yet exist.

The narrow publishable idea is:

> an audited, matched evidence-access stress test that measures how a fixed
> long-video task changes when an adjudicated support route is made
> unavailable and later restored, with claim-level support, trace, stopping,
> and no-trigger measurements.

That idea is defensible only if AV-TRACE demonstrates a finding that the
closest static or agentic benchmarks cannot provide. Merely assembling
necessary evidence, audiovisual retrieval, tool use, sufficiency judgments,
and citations is incremental over the repository's own record of LoVR,
LongVidSearch, FLARE, V-RAGBench, LongShOTBench, HAVEN, LongVT/VideoSIAH,
REVEAL, and TRACE/VES-Bench.

The current package has seven submission-fatal gaps:

1. zero human-reviewed, H1, or H2 families;
2. no strong learned end-to-end baseline that has passed competence;
3. a source pool dominated by lectures and webinars, despite broad
   audiovisual and ambient claims;
4. a restoration design whose primary causal interpretation is still
   vulnerable when the trigger depends on the evaluated policy's action;
5. only eight proposed test source groups at the minimum split;
6. unresolved annotation/media/derivative release boundaries; and
7. no submission-date novelty audit.

These gaps are project-repairable. They are not wording problems.

## 2. Reviewer-style scores

Scores use a 1–5 scale. The first column scores the repository as a paper
package today, not the quality of its future plan.

| Dimension | Current likely score | Conditional ceiling after the minimum package below | Hostile reviewer rationale |
|---|---:|---:|---|
| Novelty | **2/5** | **3–4/5** | Nearly every component is occupied. Novelty survives only in the matched intervention, exogenous restoration/no-trigger design, and a demonstrated conclusion unavailable from static evaluation. |
| Technical quality | **3/5** | **4/5** | Engineering, auditability, hashes, replay, failure typing, and metric separation are strong. The actual causal estimand, direct-baseline contract, and learned-agent competence are not yet closed. |
| Dataset / construct validity | **1/5** | **3–4/5** | There are zero H2 families. “All SESs,” necessity, modality labels, and pair isolation are still hypotheses. The current source genre is a major threat to audiovisual validity. |
| Experiments | **1/5** | **3–4/5** | Existing scientific evidence is low-N, machine-provisional, and primarily retrieval or deterministic-policy evidence. No main learned C/B/R/N experiment exists. |
| Reproducibility | **4/5** | **4–5/5** | This is the strongest current dimension: pinned artifacts, fail-closed tooling, replay, and independent audits are unusually good. Public reproducibility remains limited by source rights and optional API drift. |
| Ethics / rights | **3/5** | **4/5** | The process is cautious and substantially better than typical benchmark work, but current assets remain restricted and public release of media, transcripts, annotations, and derivatives is not authorized. |
| Clarity | **3/5** | **4/5** | The claim firewall is commendable, but the project is overdocumented, contains stale status text and conflicting pilot/baseline thresholds, and risks presenting a planning bureaucracy instead of a scientific contribution. |

**Likely overall CVPR score if submitted from the current repository:** **3/10,
Reject**, confidence **5/5**.

**Plausible score after the minimum viable package:** **6/10, Weak Accept**.
A stronger and genuinely diverse source set, convincing learned baselines, and
a robust intervention-only finding could reach **7/10**. No such result is
claimed here.

## 3. Current-state correction to Task 139

Task 139 is already stale on one engineering blocker. At review time, all five
canonical four-source index artifacts are present under
`data/restricted/mini_pilot_index_v1/`, and the local verifier reports:

```text
verified=true
decision=MINI_PILOT_INDEX_VERIFIED
check_count=395
sources=4
temporal_segments=4004
failures=[]
```

This closes the substance of Task-139 blocker
`B01_CANONICAL_FOUR_SOURCE_FULL_TIMELINE_INDEX_INCOMPLETE`. The concurrently
completed Task-136 final audit independently records
`MINI_PILOT_FULL_TIMELINE_READY` with the same 395-check, zero-failure
verification boundary.

It does **not** close the paper:

- no real family-mining output exists;
- Gate A has not run;
- zero human reviews exist;
- no learned-agent gate has passed;
- no H2 scientific evaluation is authorized; and
- no public benchmark release exists.

The blueprint should not continue to lead with a blocker that the repository
has already resolved. Stale status text undermines trust in the otherwise
strong provenance story.

## 4. Major scientific objection: the interventions are not yet entitled to a broad causal claim

### 4.1 What is causally defensible

For a fixed family and frozen system, AV-TRACE can identify the effect of a
**benchmark-controlled access intervention** if:

- the question, answer contract, source, candidate universe, backend, budget,
  serializer, and unaffected tool results are identical;
- the only treatment is route/channel availability;
- each state is run in an isolated fresh session;
- run order is randomized or counterbalanced;
- state/private identifiers do not reach the model;
- no cross-state cache or conversation leaks;
- all assigned runs remain in the intention-to-evaluate denominator; and
- the intervention has passed human route-closure and artifact-leakage audits.

That supports a bounded statement such as:

> Under the frozen AV-TRACE interface, enabling or disabling an adjudicated
> evidence route causally changes the measured system outcome.

It does not support:

- a causal claim about real-world network, sensor, retrieval, or tool
  failures;
- proof that every possible semantic route was absent;
- proof that a modality is universally necessary;
- a general causal account of model reasoning; or
- population-wide causal claims over long-video systems.

### 4.2 The current restoration trigger creates a post-treatment problem

The repository permits a fixed-call trigger or a `get_channel_status` trigger.
If restoration occurs only after the evaluated policy chooses a particular
action, then treatment exposure is policy-dependent. Conditioning analysis on
“trigger fired” selects on post-treatment behavior and can make a stronger
policy look better merely because it was more likely to request the trigger.

The current `R-N` contrast is strongest when it is interpreted as an
**intention-to-treat effect of making restoration available**, not as the
effect of restoration among policies that happened to trigger it.

Required repair:

1. Make the primary restoration schedule exogenous and identical across
   systems, preferably at a frozen action index or budget point.
2. Give `RESTORED` and `NO_TRIGGER` the same pre-trigger transcript and the
   same-shaped trigger/sham event.
3. Analyze every assigned R/N run, including agents that terminate before the
   trigger.
4. Keep action-contingent `get_channel_status` restoration as a secondary
   ecological condition.
5. Label any trigger-conditioned estimate as per-protocol/descriptive, not the
   primary causal effect.

Without this change, “causal recovery” is an overclaim.

### 4.3 `CLEAN -> BLOCKED` and `BLOCKED -> RESTORED` answer different questions

- `CLEAN -> BLOCKED` estimates the impact of removing an access route.
- `BLOCKED -> RESTORED` under a common endpoint estimates the impact of an
  environment that can later restore access after a blocked prefix.
- `RESTORED -> NO_TRIGGER` estimates the effect of actual route restoration
  relative to a sham blocked continuation.

These must not be blended into one “robustness” scalar. The blueprint correctly
rejects subtracting BLOCKED diagnosis success from RESTORED answer success, but
the paper should go further: `R-N`, not `R-B`, is the primary evidence that a
restoration mechanism caused a supported answer.

### 4.4 Exhaustive SES language is too strong

Two full-source blind searches, retrieval-assisted challenge, adjudication,
and saturation are excellent quality controls. They are not a proof that “all
possible SESs” have been enumerated. The defensible term is:

> all accepted SESs discovered under the frozen human and retrieval-assisted
> saturation protocol.

This matters because the causal treatment is valid only relative to that
accepted route registry. A newly discovered route invalidates the intervention;
it does not merely lower annotation quality.

## 5. Major dataset objection: 60 H2 families, 20 sources, and eight test sources are not enough for the advertised claims

### 5.1 What the minimum design can support

Sixty high-cost H2 families from 20 source groups can support:

- a benchmark-construction paper with a narrow diagnostic scope;
- corpus/annotation statistics;
- within-family descriptive intervention effects;
- evidence that the protocol exposes specific failure cases; and
- source-cluster uncertainty with explicit low-source warnings.

It cannot credibly support:

- broad model rankings;
- stable controller-superiority claims;
- domain or modality generalization;
- a claim about long-video agents as a population;
- a claim that eight test sources establish robust cross-source behavior; or
- a multi-endpoint confirmatory story with four Holm-corrected controller
  hypotheses.

The preregistration itself acknowledges that eight test sources are
`LOW_TEST_SOURCE_COUNT_DESCRIPTIVE_COMPARISON`. That warning is scientifically
correct but rhetorically incompatible with a headline model-comparison result.

### 5.2 Why family count does not rescue source count

The source group is the independent unit. Twenty-four test families from eight
sources do not become 24 independent observations. Source bootstrap intervals
with eight clusters will be unstable, and leave-one-source-out analysis will
have enormous leverage. Exact sign-flip tests are valid but low-powered; the
four-way confirmatory family makes the problem worse.

### 5.3 Minimum repair

For a minimally credible main-conference package:

- keep at least **60 H2 families**;
- increase to at least **30 source groups**;
- use a whole-source **12 development / 6 validation / 12 test** split;
- target approximately **24 / 12 / 24 H2 families** across those splits;
- cap each source at three H2 families, with two preferred;
- treat all between-system conclusions as effect-size-first and descriptive
  unless a development/validation-only operating-characteristic simulation
  supports stronger inference; and
- require at least five untouched test source groups for any modality,
  mechanism, or domain-specific statement.

If the project retains only eight test source groups, drop confirmatory
controller superiority and position the work as a benchmark/protocol case
study.

## 6. Major external-validity objection: the current source composition is not genuinely audiovisual

The four newly acquired sources are:

- an Oxford quantum-mechanics lecture;
- an Oxford literary-studies lecture;
- an MIT fluid-dynamics lecture; and
- a Yale physics lecture.

The planned development additions are NOAA educational/webinar material. These
sources differ in topic, institution, and duration, but they are close in
capture format: lectures, presentations, slides/board work, and webinar-like
speech.

**Subject-domain diversity is not observation-process diversity.**

This composition creates predictable validity failures:

- speech and official transcripts may dominate answerability;
- visual “evidence” may be slide text, diagrams, or board writing that is a
  derived duplicate of speech;
- OCR/captions can collapse allegedly visual routes into text routes;
- applause, chalk, writing, room noise, or incidental impacts are unlikely to
  be semantically necessary ambient evidence;
- authored V+A or V+S+A questions may become contrived;
- a modality outage may test removal of a convenient channel, not a necessary
  signal; and
- results may describe lecture-navigation agents rather than long-video
  audiovisual agents.

The local mining fixture's ambient strings such as “applause,” “writing,”
“chalk,” and “impact” are machine search hypotheses, not evidence that ambient
audio can support an answer.

### Required source-composition repair before human annotation

The six-source gate-defining pilot must add a **capture-format** axis separate
from content domain:

- no more than **3 of 6** gate-defining source groups may be
  lecture/webinar/presentation style;
- at least **3 of 6** must be event-centric, such as field procedures,
  observational wildlife/environment, industrial or laboratory processes,
  maintenance/assembly, or demonstrations with temporally meaningful actions;
- at least **2 source groups** must contain a plausible semantically relevant
  non-speech event identified by a human pre-authoring scan;
- at least **2 source groups** must require dynamic visual evidence that is not
  recoverable from transcript, captions, OCR, slide text, or metadata;
- no ambient, V+A, S+A, or V+S+A quota may be satisfied by generic room noise,
  applause, music, writing, or model-predicted labels unless removing the
  sound changes human answerability; and
- at least one ambient-bearing H2 family and one V+S+A H2 family should come
  from different event-centric sources.

The current six-source concept is effectively presentation-heavy. At least
three gate-defining source groups should be replaced or demoted to
development/calibration before reviewer packets are released.

For the scaled corpus, cap lecture/webinar/presentation material at **25% of
H2 families** and require at least four capture-format categories. If this
cannot be achieved, remove “ambient” and broad “audiovisual” claims from the
title and abstract.

## 7. Major ecological-validity objection: BLOCKED and RESTORED may be artificial state machines

The intervention is intentionally synthetic. That is acceptable for a
controlled stress test, but not if the paper implies that it samples the
natural distribution of deployed failures.

Two mechanisms should be separated:

1. **Silent route withholding:** the backend omits a registered route while
   maintaining result schema, count, timing bucket, and public metadata.
   This tests insufficiency and search adaptation without an explicit error.
2. **Explicit channel outage:** the tool returns a standardized, typed
   unavailable response. This tests whether a policy responds correctly to a
   known access failure.

Do not pool these mechanisms into one causal number. An explicit outage does
not test whether the agent inferred hidden missingness; the interface told it.

Before annotation, freeze:

- a state-surface manifest of every policy-visible field;
- independent fresh sessions and counterbalanced state order;
- identical result shape and latency policy where the mechanism permits;
- a source-group-cross-validated classifier test using only non-semantic
  metadata, which must not outperform the majority-class baseline;
- a sham event for no-trigger;
- a no-cross-state cache rule; and
- mechanism-specific estimands and tables.

The paper should call these **controlled evidence-access interventions** or
**stress-test states**, not realistic failure prevalence.

## 8. Major annotation objection: six roles are scientifically defensible but operationally fragile

Six distinct identities per H2 family are not inherently excessive. The two
blind searches are the strongest defense against the paper's most serious
construct threat. The problem is practicality and genuine independence.

### 8.1 The current independence rule is too weak

“No person may hold two roles on the same family” is insufficient when two
families come from one source. A reviewer who saw a preferred route for family
A is not blind when searching the same full source for family B.

Required repair:

- maintain a source-level exposure ledger;
- prohibit anyone who has seen preferred evidence, machine ranks, validator
  decisions, or adjudication for any family in source group \(g\) from serving
  as a blind finder or saturation auditor for another family in \(g\);
- prohibit adjudicators from authoring any family from the same source group;
- freeze assignments before packets are distributed; and
- use at least eight trained reviewers for the 12-family pilot so source-level
  blindness is feasible.

### 8.2 `H2_HUMAN_ADJUDICATED_GOLD` overstates epistemic certainty

The process produces high-confidence adjudicated labels, not metaphysical
gold. Rename the release-facing tier to something like:

```text
H2_HUMAN_ADJUDICATED_SATURATION_AUDITED
```

The implementation may keep a backward-compatible internal enum, but the
paper should avoid implying exhaustive proof.

### 8.3 Scale only after measured labor

The current 6.0–10.5 hour estimate per reviewed family may be optimistic for
45–75 minute repetitive sources because two roles must search the full
timeline. Before scaling:

- run the two excluded calibration families end to end;
- require reviewer qualification on route classification, minimality, and
  modality-derived leaks;
- record active and elapsed minutes per role;
- stage the workflow so adjudication and saturation occur only after a
  four-role candidate remains H1-eligible;
- freeze repair limits and do not repeatedly coach a family into H2; and
- use observed median and 90th-percentile labor, not the planning envelope, for
  the production authorization.

If source-level independence or staffing cannot be maintained, reduce claims
or stop; do not quietly collapse roles.

## 9. Major experimental objection: the strong-baseline plan is not credible yet

The blueprint lists many systems, but current readiness is:

- Qwen2.5-1.5B and Qwen2.5-7B controller variants failed competence;
- the selected GPT-OSS-20B acquisition/runtime preflight is `NO_GO`;
- the closed API row is planning-only and requires re-verification and
  governance approval;
- no native audiovisual direct baseline is frozen;
- no H2 learned RAG, ReAct, or sufficiency-agent run exists.

This is not strong baseline coverage. It is a shopping list.

### 9.1 Minimum credible baseline matrix

The main paper needs:

1. one genuinely native audiovisual direct/long-context model with a
   deterministic, question-independent source packing policy;
2. one single-shot RAG baseline;
3. one ordinary learned ReAct agent;
4. one explicit sufficiency-aware agent using the same backbone, backend,
   finalizer, observations, and budget as ReAct;
5. one materially different second backbone/model family on at least the
   direct or RAG row, and on both ReAct/Suff rows if cross-backbone controller
   claims are made;
6. oracle-complete and adjudicated-partial evidence diagnostics;
7. deterministic protocol controls; and
8. at least one faithful published-style comparison or ablation corresponding
   to a close precedent, such as TRACE-style convergence/evidence stopping,
   REVEAL-style verification/re-retrieval, or a LongVT-style crop policy on
   its eligible visual subset.

An API model is optional. No primary claim should depend on it.

### 9.2 The direct baseline contract is underspecified

For `BLOCKED`, a native direct model cannot receive the unmodified full source
if the agent is supposedly denied a route; that would leave the evidence
accessible. If the direct input is edited, muted, masked, or truncated, those
operations can introduce visible artifacts and make the comparison different
from tool-access blocking.

Before evaluation, specify for each intervention:

- whether the direct model is eligible;
- the exact state-consistent media transformation;
- artifact masking and validation;
- whether the row is endpoint-only or recovery-eligible; and
- why its treatment is comparable to the agent treatment.

If this cannot be done cleanly, report the direct model on CLEAN and
state-specific endpoints only. Do not force it into trigger-conditioned
recovery.

### 9.3 “Audiovisual agent” may be an interface over text proxies

The planned strong controllers consume textualized observations rather than
raw video/audio. That is a legitimate systems setup, but it tests policy over
an audiovisual retrieval backend, not native audiovisual reasoning by the
controller.

Either:

- include a native A/V path and a perception audit; or
- narrow the paper to “agents over long-video audiovisual evidence” and report
  perception-proxy failures separately.

## 10. Novelty: distinct only if the experiment earns the distinction

The local related-work audit supports the following bounded comparison:

| Work | Occupied territory | What AV-TRACE must add to remain distinct |
|---|---|---|
| LoVR | Long-video and clip retrieval at much larger scale | Interactive, matched evidence-access states and supported-answer traces; AV-TRACE cannot compete on scale. |
| LongVidSearch | Agentic search with exact necessary multi-hop clips | Human accepted alternative-SES registry, evaluation-time route manipulation, BLOCKED/RESTORED/no-trigger behavior, and support-aware endpoints. |
| FLARE | Visual/audio/audiovisual retrieval and hard bimodal filtering | Online channel failure, policy response, calibrated insufficiency, exogenous restoration, and reacquisition. |
| V-RAGBench | Retrieval/generation decomposition with shortcut-resistant evidence chunks | Within-family access interventions and trace-level Acquire/Ground/Act failure attribution. |
| LongShOTBench | Omni-modal long-form QA, rubrics, retrieval, refinement, and verification | Matched state intervention, common endpoint, no-trigger control, and route-isolation audit. |
| HAVEN | Hierarchical video-text alignment and broad unified understanding | Causal access manipulation and interactive recovery rather than another aligned annotation hierarchy. |
| LongVT / VideoSIAH | Native crop/search agent and iterative correction | Benchmark-grounded insufficiency/failure states, controlled restoration, and policy-blind negative controls. |

This is a **combination-level distinction**, not a broad first. The novelty
collapses if the final result is only:

- retrieval is hard;
- multimodal questions are hard;
- agents use tools;
- evidence sufficiency matters;
- a stronger model scores higher; or
- the system performs differently after an obvious error message.

The final paper needs at least one held-out result showing that the matched
intervention changes a conclusion that CLEAN answer accuracy, retrieval recall,
or existing static evidence metrics would not reveal. Examples of acceptable
result forms, without assuming that any will occur, include:

- similar CLEAN supported-answer rates but different BLOCKED false
  sufficiency or RESTORED/no-trigger behavior;
- correct answer rankings that reverse under supported-answer scoring;
- complete evidence acquisition followed by distinct Ground or Act failures;
  or
- restoration-enabled success that disappears under the sham no-trigger
  control.

If no such result appears across multiple untouched source groups and at least
two learned system classes, the paper is a careful benchmark implementation,
not a compelling CVPR contribution.

**Mandatory submission-time action:** repeat the primary-source literature
audit immediately before submission. The local novelty materials are dated
2026-09-05/07 and explicitly describe a fast-moving field. This review did not
browse and does not certify current priority or completeness.

## 11. Reproducibility, ethics, and rights

### Strengths

- content-addressed source/model artifacts;
- exact hashes and revisions;
- deterministic replay and independent metric recomputation;
- typed invalid-run policy;
- clear separation of machine-provisional and human tiers;
- strong prohibition on cookie-based or unauthorized acquisition;
- artifact-level release boundaries; and
- explicit privacy, component, attribution, withdrawal, and takedown planning.

### Submission blockers

- current source media and transcripts are restricted;
- public release of the acquired lecture assets, annotations, embeddings, and
  derived observations remains unapproved;
- a stable public/reconstructable primary test set does not exist;
- the strong open baseline is not acquired or runtime-validated;
- the API baseline would be date-, account-, retention-, and provider-state
  dependent; and
- external reproduction may be impossible if the evaluator depends on
  restricted source-derived observations.

Minimum release standard:

1. Every primary H2 source permits release of annotations, source/split
   identifiers, provenance, evaluator records, and required attribution.
2. Every test source is either redistributable or lawfully reconstructable
   from a stable, first-party route with exact identity checks.
3. A public evaluator, schemas, metrics, prompts, baseline recipes, split
   manifest, checksums, and typed failure examples are released.
4. Restricted media and source-derived artifacts are absent from the public
   package unless specifically authorized.
5. A release bill of materials and tested withdrawal/versioning procedure are
   complete before the paper calls AV-TRACE a public benchmark.

If these conditions fail, the title, abstract, and artifact statement must say
“restricted evaluation corpus” or “public protocol with restricted
evaluation,” not “released benchmark.”

Submission-time web re-verification is required for source routes and terms,
model licenses and exact revisions, API availability/pricing/data controls,
and every related benchmark's current release/version. No freshness claim is
made in this review.

## 12. Clarity and internal consistency defects

These are repairable before annotation:

1. **Pilot size conflict.** The construct protocol allows 8–12 families over
   5–6 sources and calls 10 preferred; the frozen pivot and Tasks 138/139
   require exactly 12 over exactly 6 sources with stricter 9-H1/8-H2 gates.
2. **Baseline competence conflict.** The pivot, preregistration, and strong
   baseline plan use related but non-identical action, state, terminal,
   abstention, and recovery thresholds.
3. **Source-plan drift.** The human source-pool plan names USGS/NASA/Commons,
   while the acquired/indexed replacement pool is Oxford/MIT/Yale lectures.
4. **Stale blueprint status.** Task 139 still says the canonical full build is
   incomplete, while the current local artifacts verify.
5. **Domain vocabulary drift.** Some documents require three domains; the
   construct review's scaled target requires four domains and five source
   groups per domain. Capture format is not represented.
6. **Gold terminology.** `H2_HUMAN_ADJUDICATED_GOLD` implies stronger
   exhaustiveness than the protocol can establish.
7. **Excessive endpoint surface.** The main tables expose many metrics while
   only one same-backbone controller contrast is nominally confirmatory. The
   paper risks looking designed to find some positive result.

Issue one versioned pre-annotation contract that supersedes these conflicts.
Do not ask annotators to work under a precedence chain spread across several
documents.

## 13. Fatal versus repairable reviewer objections

### 13.1 Submission-fatal now, but project-repairable

| Objection | Why fatal at submission | Required repair |
|---|---|---|
| No human-valid construct | Zero H1/H2 means the benchmark's central labels do not exist. | Pass the revised 12-family pilot, then scaled H2 production without weakened criteria. |
| Causal restoration is policy-contingent | Trigger exposure can depend on the policy and induce selection bias. | Exogenous primary trigger, sham no-trigger, intention-to-treat analysis, action-contingent secondary analysis. |
| Source genre invalidates broad A/V claims | Lecture/webinar-heavy data can reduce vision to slides and ambient to incidental noise. | Replace/demote at least three pilot sources; enforce capture-format and semantic ambient/dynamic-visual gates. |
| Eight test sources are too few | Model comparison and four confirmatory hypotheses would be unstable and source-driven. | Use at least 12 untouched test source groups or make comparisons explicitly descriptive. |
| Strong baselines are hypothetical | Existing controllers failed; proposed strong rows are not ready. | Freeze and pass competence for the minimum learned matrix and one close published-style comparator. |
| Rights/release mismatch | A benchmark claim is not credible if core evaluation cannot be reconstructed or released. | Finish artifact-level release decisions and public/reconstructable test routing. |
| Novelty audit is stale by submission | The field is moving and the local audit is dated. | Repeat a submission-date primary-source audit and remove unsupported priority wording. |

### 13.2 Repairable without new scientific results

- close the stale index blocker;
- reconcile the source registry with the acquired replacement sources;
- align the pilot and baseline gates;
- narrow “causal,” “gold,” “audiovisual,” and “public benchmark” wording;
- reduce main-paper metrics to a small primary set;
- move machine-provisional NOAA/Scale-1A/Wave-R results to motivation or
  appendix;
- define state order, session isolation, cache isolation, and direct-baseline
  eligibility; and
- collapse the planning narrative into one readable benchmark contract.

### 13.3 True no-go outcomes

These are not fixable by prose:

- systematic alternative-route discoveries invalidate necessity groups;
- pair isolation repeatedly fails;
- ambient or V+S+A families cannot survive human counterfactual review;
- a non-semantic classifier detects state from artifacts;
- strong learned systems cannot pass basic competence;
- apparent effects disappear after controlling for acquired evidence;
- no answer/support or non-retrieval failure separation appears;
- the result reverses when one source is removed;
- required annotations/evaluator artifacts cannot be released or lawfully
  reconstructed; or
- a submission-time audit finds direct prior art for the claimed matched
  intervention and recovery contribution.

The correct response to these outcomes is to narrow to a protocol/artifact
paper, change venue, or stop. Do not manufacture a benchmark story.

## 14. Minimum viable CVPR submission package

### A. Claim

Use one bounded headline:

> AV-TRACE is an audited matched evidence-access stress test for agents over
> long-video audiovisual evidence, with adjudicated support routes,
> exogenous restoration and sham controls, and trace-level
> Acquire/Ground/Act outcomes.

Do not claim firstness, broad model ranking, universal reliability, or
real-world failure prevalence.

### B. Data

- at least **60 H2 adjudicated/saturation-audited families**;
- at least **30 source groups**;
- **12/6/12** development/validation/test source groups;
- approximately **24/12/24** H2 families;
- no more than three H2 families per source;
- at least four content domains and four capture-format categories;
- presentation-style material at most 25% of H2;
- event-centric material from at least half of source groups;
- modality/mechanism claims only when at least five untouched test sources
  contribute; and
- full rejected/repair/quarantine funnel and labor accounting.

### C. Construct

- all accepted SESs discovered under the frozen saturation protocol;
- source-level blind-role independence;
- leave-one-out minimality;
- necessity-group recomputation;
- modality and derived-representation counterfactuals;
- C/B/R/N isolation;
- exogenous primary restoration;
- pair-isolation and non-semantic artifact audits; and
- no unresolved critical rights/privacy/safety hold.

### D. Systems

- native A/V direct baseline;
- single-shot RAG;
- same-backbone ReAct and sufficiency agent;
- a second materially different backbone/model family;
- oracle and partial evidence;
- deterministic controls;
- one close published-style stopping/retrieval-agent comparator or a clearly
  documented faithful reimplementation;
- all required systems passing a frozen source-free competence suite; and
- no primary dependence on a closed API row.

### E. Experiments

The submission needs, on untouched H2 test sources:

- the Acquire/Ground/Act dashboard;
- C-to-B access-removal effects;
- R-to-N exogenous restoration effects;
- no-trigger false recovery;
- answer versus supported-answer/citation divergence;
- observed-evidence-lock and oracle/partial diagnostics;
- at least two non-retrieval failure categories on multiple source groups;
- source and domain leave-out analysis;
- invalid-run and cost accounting; and
- all null/adverse results.

Controller superiority is optional and should be dropped unless it clears the
power, competence, practical-effect, multiplicity, and leave-one-source rules.

### F. Artifact and rights package

- public evaluator and schemas;
- frozen split/source manifests and checksums;
- prompts/configs/model identities and acquisition recipes;
- complete allowed traces or privacy-preserving trace records;
- source-cluster analysis code and seeds;
- release bill of materials;
- attribution and takedown/versioning process; and
- explicit public/reconstructable/restricted partition labels.

## 15. Exact changes required before the first human annotation packet

1. **Issue construct protocol v1.2.** Make the gate-defining pilot exactly
   12 families from exactly six sources, with the frozen 9-H1/8-H2 thresholds.
   Keep generic 8–12 sampling only as non-gate exploratory mode.
2. **Reconcile the source registry.** Replace the obsolete
   USGS/NASA/Commons plan with the exact acquired Oxford/MIT/Yale identities
   and the final retained NOAA development sources.
3. **Change the pilot source composition.** Demote or replace at least three
   presentation-style groups so the six-source pilot has at least three
   event-centric groups and no more than three lecture/webinar groups.
4. **Add source-format fields.** Freeze `capture_format`,
   `scene_dynamics`, `speech_dominance`, `text_on_screen_density`,
   `semantic_non_speech_candidate`, and `dynamic_visual_candidate`.
5. **Add a semantic modality pre-screen.** No family authoring for A, V+A,
   S+A, or V+S+A until a human verifies that the candidate non-speech event is
   meaningful and separable from speech/music, and that the visual claim is
   not recoverable from text derivatives.
6. **Rename the paper-facing H2 tier.** Use
   `H2_HUMAN_ADJUDICATED_SATURATION_AUDITED`; describe SES completeness as
   protocol-bounded.
7. **Enforce source-level blindness.** Add an exposure ledger and prevent
   blind roles or adjudicators from being contaminated by another family from
   the same source.
8. **Freeze an exogenous restoration primary condition.** Use a common
   action/budget trigger, a same-shaped no-trigger sham, and intention-to-
   evaluate analysis. Keep `get_channel_status`-contingent restoration
   secondary.
9. **Freeze session/order controls.** Fresh process/session per state,
   counterbalanced state order, no shared conversation, and no cross-state
   response cache.
10. **Separate intervention mechanisms.** Silent route withholding and
    explicit channel outage receive separate estimands, tables, and wording.
11. **Narrow missingness claims.** Until a separate source-absence control set
    exists, say “diagnoses registered access failure” rather than “distinguishes
    absence from access failure.”
12. **Freeze a non-semantic leakage test.** Use source-group cross-validation
    and require state prediction from non-treatment metadata not to beat the
    majority-class baseline.
13. **Raise the source minimum before scaled selection.** Make 30 source
    groups and 12 untouched test groups the minimum for the main submission.
    If retained at 20/8, remove confirmatory model-comparison language.
14. **Unify competence gates.** Select one threshold set across the pivot,
    preregistration, and strong-baseline plan before any baseline sees a
    scientific family.
15. **Freeze baseline identities and eligibility.** Identify the native A/V
    direct model, shared-backbone RAG/ReAct/Suff rows, second backbone, and
    published-style comparator; document which states each can validly enter.
16. **Reduce primary endpoints.** Make CLEAN supported answer, BLOCKED false
    sufficiency/diagnosis, and R-N supported-answer effect the small primary
    set. Keep the remaining dashboard diagnostic.
17. **Freeze scaled source assignment before H2 review.** Rejected candidates
    from test sources remain test-private; all derivatives inherit source
    split.
18. **Require affirmative annotation/evaluator release before expensive
    review.** Raw-media release can differ, but annotation and evaluator
    rights may not remain `unknown_hold`.
19. **Freeze stop rules for failed strata.** If ambient or V+S+A does not
    survive, remove the stratum rather than replacing labels after outcomes.
20. **Schedule the submission-time audits now.** Novelty, source/license,
    baseline/model/API identity, and release audits must be rerun at paper
    freeze using then-current primary sources.

## 16. Final reviewer statement

AV-TRACE's strongest asset is not its current dataset or its controller. It is
the discipline with which the project has allowed audits to invalidate prior
engineering and scientific claims.

That discipline now has to be applied to the paper's most attractive words:
“causal,” “audiovisual,” “gold,” “benchmark,” and “recovery.” The current
lecture-heavy, zero-H2, no-strong-baseline repository does not earn those words
as empirical claims.

The project should proceed only after the pre-annotation repairs above. If the
revised pilot demonstrates that diverse event-centric sources can yield
stable, saturation-audited interventions and the learned systems then exhibit
multi-source differences that static accuracy cannot explain, the paper has a
credible CVPR path. If not, the correct outcome is a narrower protocol or
artifact paper, not a forced benchmark.

**Decision token: `REDTEAM_REPAIR`**
