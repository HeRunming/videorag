# AV-TRACE CVPR pivot decision and six-week critical path

**Frozen:** 2026-09-22  
**Decision:** `CVPR_PIVOT_FROZEN`  
**Decision owner:** Task 122  
**Scope:** paper positioning, six-week execution order, and gate authorization  
**Results policy:** this document records existing results and prospective gates; it does not create human, controller, benchmark, or paper results

## 1. Frozen decision

AV-TRACE will pivot to a **benchmark-and-diagnostic-protocol paper**, not a
controller-method paper.

The frozen paper thesis is:

> AV-TRACE tests long-video audiovisual reliability with human-adjudicated,
> source-disjoint matched episode families that hold the question, evidence
> graph, backend, and budget fixed while changing evidence-route
> availability. The benchmark diagnoses whether answer accuracy and retrieval
> recall conceal failures of evidence acquisition, claim support, citation,
> insufficiency diagnosis, stopping, and recovery across strong learned
> baselines.

The controller findings make this pivot necessary:

- the frozen 7B monolithic controller competence run was `NO_GO`: 11/16 valid
  structured outputs and 1/4 supported answers on oracle-evidence cases;
- controller v2 solved syntax but not semantics on its sealed unseen synthetic
  holdout: 28/28 action syntax, 28/28 state syntax, 15/28 correct actions,
  0/28 exact six-field states, 0/8 correct terminals, 0/4 supported answers,
  and 0/4 correct abstentions;
- controller v3 improved action behavior on consumed development data but
  remained `NO_GO`: 14/16 correct actions, 0/16 joint exact states, 1/8
  correct terminals, 1/5 supported answers, and 0/3 correct abstentions.

The v2 and v3 figures come from different suites and are descriptive, not a
paired improvement claim. In all three controller stages, unsupported required
claims remained zero; that safety property does not establish state estimation,
answering, abstention, or recovery competence.

Therefore:

1. the paper will not present controller v2 or v3 as the principal technical
   contribution;
2. controller v1/v2/v3 artifacts remain **diagnostic baselines and interface
   studies**;
3. the immediate scientific investment is the 12-family human construct pilot
   plus rights-first source diversification;
4. controller repair continues in parallel on synthetic/development data only;
5. no scientific evaluation family and no 60-H2 bulk production are authorized
   until the gates in this document pass.

## 2. Benchmark contribution versus diagnostic baselines

### 2.1 Intended benchmark contribution

The intended benchmark contribution is a rights-reviewed, source-disjoint
collection of matched `CLEAN`/`BLOCKED`/`RESTORED` families with:

- human-adjudicated questions, answers, and atomic claims;
- all accepted minimally sufficient evidence sets (SESs);
- necessity groups computed across every accepted SES;
- vision, speech, ambient-audio, and jointly cross-modal coverage;
- full-source alternative-evidence search and saturation audit;
- isolated blocking, exact restoration, derived-route closure, and no-trigger
  controls;
- full-timeline candidate universes;
- source-level split, provenance, rights, privacy, release, replacement, and
  takedown records.

This contribution is **intended, not achieved**. As of 2026-09-22 there are
zero human-reviewed families, zero H1 families, and zero H2 families. Existing
NOAA families remain machine-adjudicated provisional development material.

### 2.2 Diagnostic protocol contribution

The protocol contribution is the matched intervention and its trace-level
Acquire/Ground/Act measurements:

- evidence acquisition and all-SES coverage;
- claim-level support and citation;
- calibrated sufficiency and access-state diagnosis;
- final-point route certificates and premature stopping;
- common-endpoint restoration response;
- no-trigger false recovery;
- typed invalid runs, cost, and deterministic replay.

The engineering implementation is retained as a bounded contribution. Its
semantic construct remains gated on human validation.

### 2.3 Diagnostic baselines, not the paper's proposed method

The paper baseline matrix must contain:

1. a pinned direct/long-context learned audiovisual non-agent baseline;
2. single-shot learned RAG over the frozen retrieval backend;
3. learned ReAct;
4. learned evidence-sufficiency control;
5. oracle/H2-evidence-conditioned and partial-evidence generator diagnostics;
6. deterministic ReAct and deterministic sufficiency protocol controls;
7. `RESTORED` no-trigger controls.

The learned ReAct and learned sufficiency agents must use the same
backbone, backend, action space, grounded finalizer, budget, failure policy, and
candidate universe where practical. At least two backbone/model families must
appear in the final paper. Deterministic controls are never described as
learned systems. Controller v2/v3 may occupy learned-agent baseline rows only
after the strong-agent competence gate passes on a new unseen fictional suite.

## 3. Claim freeze

### 3.1 Claims retained now

| Claim | Frozen status and permitted wording |
|---|---|
| Audited execution infrastructure | **Retained, engineering-only.** “The infrastructure executes and replays matched C/B/R episodes under fixed budgets.” |
| Common supported-answer restoration endpoint | **Retained, engineering-only.** “Restoration response is defined with one supported-answer endpoint in BLOCKED and RESTORED.” |
| Final-point route certificates | **Retained, engineering-only.** “The protocol can distinguish protocol-valid stopping from a certified feasible route at the final decision point.” |
| Frozen learned modality retrieval | **Retained, engineering-only.** “The repository contains reproducible pinned visual/audio retrieval and fixed no-training fusion baselines.” |
| Human-adjudicated matched benchmark | **Retained as the primary candidate contribution, not a current result.** It requires the human and corpus gates below. |
| Answer versus supported-answer divergence | **Retained as a candidate empirical claim.** It requires H2 held-out evidence and may be dropped if the divergence is absent. |
| Failure-stage separation beyond retrieval | **Retained as the central candidate empirical claim.** It requires at least two non-retrieval categories on multiple sources. |
| Common-endpoint recovery measurement | **Retained as a candidate empirical claim.** It requires human-valid route isolation, no-trigger controls, and learned runs. |

### 3.2 Claims demoted to secondary or appendix status

| Claim | Frozen disposition |
|---|---|
| Generic learned retrieval is not automatically beneficial | Keep only as a five-family machine-provisional diagnostic until H2 revalidation and source-disjoint replication. |
| Full-timeline retrieval is harder than shortlisted retrieval | Keep as a provisional engineering observation until human-valid replication. |
| Explicit sufficiency control beats ReAct | Treat as a preregistered comparison, not a required thesis result. Report null or adverse results. |
| Modality-specific necessity | Report only for individually H2-validated families and sufficiently sourced strata. Otherwise use routing/corroboration language. |

### 3.3 Claims dropped

The following are removed from the main-paper claim set:

- controller v2 or v3 is a novel, competent, or superior proposed method;
- the current controller findings demonstrate learned-agent recovery;
- syntax validity implies semantic state competence;
- the current NOAA families form a validated benchmark or primary test set;
- current machine-provisional SESs, necessity groups, or modality labels are
  human gold;
- a broad “first,” SOTA, universal reliability, population-ranking, or
  out-of-domain generalization claim;
- a public-benchmark claim for assets without affirmative release authority;
- immediate commitment to 60-H2 production.

## 4. Immediate 12-family human pilot

### 4.1 Frozen sampling design

- **12 completed families from exactly 6 source groups**, targeting two
  families per source.
- At least **3 content domains**, with at least two source groups per domain.
- No more than **4 gate-defining families from 2 current NOAA source groups**.
- The other **8 families must come from 4 new source groups in at least 2
  non-NOAA domains**.
- Current NOAA source groups are permanently excluded from the future primary
  test split because they informed construction, retrieval, controller,
  metric, and repair work.
- Add **2 calibration families** that are excluded from every reported
  denominator.

Candidate-stratum targets are:

- 2 vision-dominant;
- 2 speech-dominant;
- 2 ambient-dominant;
- 2 V+S;
- 2 V+A or S+A, including at least one ambient combination;
- 2 V+S+A;
- 6 necessity-group-withholding and 6 modality-channel-outage families;
- 6 one-hop and 6 multi-hop families;
- 6 near/local and 6 far/separated families;
- at least 6 high alternative-support-risk cases;
- at least 2 deterministically selected low-risk controls.

These are candidate hypotheses, not labels to be forced. A failed modality or
necessity test changes the label, triggers repair, or rejects the family.

### 4.2 Human roles

Each family requires six distinct people:

1. question/claim author or independent verifier;
2. blind full-source alternative-evidence finder;
3. validator A;
4. validator B;
5. independent adjudicator;
6. blind post-adjudication saturation auditor.

No person may hold two roles on the same family. The blind finder must not see
the preferred SES, machine tier, machine confidence, model ranks, or validator
decisions. The saturation auditor receives the source and frozen question but
not the accepted SES ledger.

### 4.3 Required review operations

Every family must include:

- full-source chronological coverage with no unlogged gap beyond the frozen
  tolerance;
- independent enumeration of plausible answer routes;
- retrieval-assisted challenge after the blind pass;
- reconciliation of duplicate, derived, and genuinely distinct routes;
- leave-one-evidence-out minimality;
- necessity hitting sets over all accepted SESs;
- modality-drop and shortcut counterfactuals;
- derived-route closure across transcript, captions, OCR, labels,
  descriptions, metadata, and temporally bound substitutes;
- C/B/R pair isolation, exact restoration, feasible recovery, and no-trigger
  checks;
- blind saturation search and reopening if a new accepted route is found;
- rights, privacy, safety, attribution, retention, and release decisions;
- active and elapsed labor by role.

All statistics are labeled `LOW_N_MINI_PILOT_DESCRIPTIVE_ONLY`.

## 5. Candidate-source preparation

Candidate preparation is authorized now; bulk annotation is not.

Before a source can enter the 12-family pilot, prepare one source dossier that
contains:

1. canonical asset and `source_group_id`, including mirrors, excerpts,
   encodings, transcript variants, and near-duplicate lineage;
2. exact content hash, duration, streams, time base, decode result, and
   source-edit check;
3. an affirmative acquisition route and separate processing/annotation
   authority;
4. separate release decisions for media, clips, transcripts, annotations,
   features/embeddings, evaluator artifacts, and IDs;
5. dated license or grant evidence, rightsholder/licensor, attribution,
   share-alike, commercial-use, and component-level restrictions;
6. faces, voices, minors, bystanders, private spaces, precise locations,
   sensitive events, music, marks, and third-party component review;
7. retention, access control, takedown, withdrawal, quarantine, deletion, and
   replacement rules;
8. full-source technical readiness for video, speech, and non-speech audio;
9. candidate-family hypotheses and their intended strata, without claiming
   necessity before human review.

Source priority is:

1. low-privacy institutional or owner-controlled, public/reconstructable
   material with clear item-level authority;
2. NASA, NOAA, NARA, or Wikimedia material only after item- and
   component-level review;
3. restricted or ID-only sources only in separately governed, unpooled tracks.

An accessible URL, public-agency provenance, repository license, benchmark
card, or embedded player is not sufficient. Any applicable `unknown_hold`
blocks pilot use. LongVideoBench-derived candidates remain compatibility leads
unless their exact source, processing authority, and release boundary are
affirmatively resolved.

## 6. Strong-agent baseline readiness

The current status is `STRONG_AGENT_BASELINE_NO_GO`.

A candidate learned-agent stack may advance only on a new unseen,
non-evaluation-family fictional competence suite frozen before inference. It
must satisfy all of the following:

- action syntax and every required state-head syntax: **100%**;
- action correctness: **at least 80%**;
- every semantic state head: **at least 75%**;
- joint exact state: **at least 50%**;
- end-to-end terminal correctness: **at least 75%**;
- valid structured learned outputs after at most one permitted repair:
  **at least 90%**;
- supported-answer success on oracle-evidence cases: **at least 80%**;
- unsupported required claims: **0**;
- process, constraint-runtime, evaluator-leak, deterministic-substitution, and
  controller-state-to-answer mapping failures: **0**.

No tuning may use the Task-120 holdout, its restricted labels, future H2 test
sources, adjudication rationales, `r017`, NOAA evaluation families, or any
scientific evaluation family. Passing this gate authorizes an H2 mini
diagnostic; it does not establish a paper result.

## 7. Exact Go / Repair / No-Go gates

### Gate A — `MINI_PILOT_INPUT_READY`

**GO**

- 12 eligible family candidates and 2 excluded calibration families;
- exactly 6 pilot source groups meeting the source/domain rules;
- complete source dossiers, hashes, media, and lineage;
- affirmative processing and annotation authority for every source;
- frozen forms, protocol version, sampling seed, and candidate registry;
- six or more trained reviewers with valid role assignment;
- no unresolved critical rights/privacy/safety hold.

**REPAIR**

- the six-source design remains feasible, but one or more candidate, role,
  technical, or non-critical rights records must be replaced or completed.

**NO-GO**

- fewer than six eligible source groups can be assembled without weakening
  source, rights, privacy, or technical rules; or
- a required pilot stratum cannot be sampled and no defensible narrower claim
  is accepted before review begins.

### Gate B — `CONSTRUCT_VALIDITY_MINI_PILOT_GO`

**GO**

- all 12 families complete across the 6 frozen source groups;
- every required role and adjudication complete;
- at least 9/12 reach H1;
- at least 8/12 reach H2;
- pair-isolation failures at most 1/12;
- no unresolved critical governance hold;
- no systematic minimality or modality failure affecting more than 3/12;
- at least two accepted source groups outside the current NOAA lineage;
- at least one ambient and one V+S+A family reach H2, or those strata are
  explicitly removed from the planned paper;
- the saturation auditor finds no unblocked accepted route, or every discovery
  is repaired and re-audited;
- observed labor and yield leave a credible unchanged-criteria route to 60 H2.

**REPAIR**

- at least 5/12 reach H1, or failures are localized to repairable wording,
  interval, route, role, form, or source defects;
- no evidence shows that the central SES/necessity/intervention construct is
  unreviewable.

Repair requires a versioned protocol or family revision and re-review of every
affected field. Pre- and post-repair records may not be pooled without a
compatibility audit.

**NO-GO**

- fewer than 5/12 reach H1;
- at least 6/12 are rejected;
- systematic alternative-support, minimality, necessity, intervention
  isolation, or governance failures undermine the construct; or
- the intended data cannot be used under the required rights/privacy rules.

### Gate C — `LEARNED_CONTROLLER_READY`

**GO**

- every threshold in Section 6 passes on one frozen unseen fictional suite;
- the run and independent audit are hash-bound and fail closed;
- no prohibited development or evaluator-private source was accessed.

**REPAIR**

- syntax and safety pass, but one or more semantic floors fail;
- failures are localized to controller/finalizer competence and can be repaired
  on consumed development data without changing evaluation labels, gates, or
  future test content.

**NO-GO**

- a second frozen unseen suite after repair still fails a semantic floor;
- evaluator leakage, post-output tuning, deterministic substitution, or
  controller-state-to-answer mapping occurs; or
- competence can be obtained only by exposing oracle or evaluation-private
  information.

Task-120 and Task-121 already establish that the current stack is in the
`REPAIR` branch and is not authorized for H2 scientific evaluation.

### Gate D — `END_TO_END_DIAGNOSTIC_GO`

Run only if Gates B and C are GO. Use every accepted H2 mini-pilot family with
no post-outcome replacement.

**GO**

- learned single-shot RAG, learned ReAct, and learned sufficiency control run
  under frozen common contracts;
- C/B/R and no-trigger accounting is complete and independently replayed;
- at least one intervention-aware diagnostic separation appears across at
  least 3 source groups and is not wholly attributable to one family;
- at least one H2 case separates answer correctness from supported-answer
  correctness or citation validity;
- at least two non-retrieval failure categories are observed, each on at least
  2 source groups;
- all effects are reported with source-level denominators and complete invalid
  run accounting;
- the CLEAN supported-answer difference for a directional ReAct-versus-
  sufficiency claim is within the frozen 0.10 absolute non-inferiority margin;
- any directional controller claim also reaches at least 0.15 absolute
  improvement in BLOCKED false sufficiency, premature stopping, or
  common-endpoint restoration.

The final two conditions govern a directional controller claim; the benchmark
diagnostic gate may still pass without controller superiority if the other
conditions pass.

**REPAIR**

- construct and controller gates pass, but the low-N diagnostic is
  inconclusive, a typed execution defect is repairable, or source coverage is
  insufficient for the frozen separation;
- no causal-isolation, evaluator-leakage, or central construct failure occurs.

Repair means a new preregistered run on untouched source groups where needed;
it does not permit family replacement based on outcomes.

**NO-GO**

- human-valid intervention isolation or leakage closure fails;
- all apparent differences are explained by retrieval recall or metric
  artifacts;
- no answer-versus-support/citation divergence appears;
- no non-retrieval failure-stage separation survives audit; or
- a valid strong learned baseline cannot execute the protocol without
  evaluator-private help.

### Gate E — `60_H2_PRODUCTION_AUTHORIZED`

There are two authorization tranches.

**Tranche 1 GO — authorize the first 40 scaled human reviews**

- Gates B, C, and D are GO;
- a frozen pool of 120–160 P-tier candidates from 30–40 source groups exists;
- at least 25 rights-eligible source groups are available for the 20-source
  target plus a 25% reserve;
- source-disjoint development/validation/test assignment rules are frozen;
- staffing, labor budget, compute/storage budget, and rights-review capacity
  are approved;
- no construct threshold is relaxed.

**Tranche 1 REPAIR**

- the scientific gates pass but candidate, rights, reserve, staffing, or
  budget capacity is incomplete and can be completed without changing the
  construct.

**Tranche 1 NO-GO**

- any of Gates B–D is NO-GO, or reaching the pool/reserve requires weaker
  construct, rights, privacy, or split rules.

**Tranche 2 GO — continue from 40 reviews to a 60-H2 freeze**

- observed H2 yield after the first 40 completed reviews is at least 60%;
- no evidence shows that acceptance requires weakened SES, necessity,
  modality, or pair-isolation rules;
- every high-risk stratum has at least 5 completed reviews;
- measured source preparation, annotation labor, rights throughput, compute,
  and storage fit the remaining schedule and budget;
- the rights-eligible reserve remains at least 25%;
- the frozen route still reaches 60 H2 from at least 20 source groups.

**Tranche 2 REPAIR**

- yield or throughput misses a floor for a localized, versionable reason that
  can be rerun without using test outcomes or weakening acceptance.

**Tranche 2 NO-GO**

- H2 yield is below 60% without a localized repair;
- rights, labor, source diversity, or reviewer capacity makes 60 H2
  infeasible;
- a required stratum cannot be filled under unchanged H2 rules; or
- the principal diagnostic conclusion no longer supports the benchmark thesis.

### Gate F — `60_H2_CORPUS_FREEZE`

**GO**

- 60 H2 families from at least 20 source groups;
- whole-source split of at least 8 development, 4 validation, and 8 untouched
  test source groups, targeting 24/12/24 families;
- all current NOAA and other development-touched sources excluded from the
  primary test split;
- complete rights decisions with no applicable `unknown_hold`;
- a 25% source/family reserve for rights failure, withdrawal, or late
  construct defects;
- frozen prompts, models, retrieval, budgets, metrics, practical thresholds,
  invalid-run reserve, and release scope;
- no weakened construct criterion and no test-source tuning.

**REPAIR**

- the authorized production wave is scientifically valid but has fewer than
  60 H2 families, fewer than 20 eligible source groups, an underfilled
  composition stratum, or an incomplete non-critical rights/release record;
- the deficit can be filled from the frozen reserve or a new rights-first
  source wave without changing test outcomes, construct thresholds, or split
  rules.

**NO-GO**

- 60 H2 or 20 source groups cannot be reached without weaker construct or
  governance rules;
- test privacy or source disjointness has been broken;
- a critical rights, leakage, pair-isolation, or construct defect affects the
  frozen core and cannot be repaired from the reserve; or
- the required source/domain composition remains infeasible.

### Gate G — `PAPER_CLAIM_READY`

**GO**

- Gate F and every prior scientific gate are GO;
- at least four preregistered learned system classes and at least two
  backbone/model families are complete;
- source-cluster uncertainty, source/domain leave-out sensitivity, required
  ablations, costs, invalid runs, denominators, and negative/null strata are
  complete;
- the principal finding survives retrieval, capacity, modality, prompt,
  trigger, metric, and source sensitivity;
- independent metric, replay, leakage, rights/release, novelty, and
  sentence-level claim audits pass;
- every abstract and conclusion statement maps to a frozen result and uses the
  approved release boundary.

**REPAIR**

- the benchmark and main evaluation remain valid, but a non-critical missing
  baseline, ablation, audit, uncertainty analysis, or wording defect prevents
  a complete claim package;
- repair does not permit rerunning the locked test set to select a favorable
  result.

**NO-GO**

- the core matched-intervention construct or causal isolation fails;
- the principal result is explained by one source, one domain, retrieval
  alone, evaluator leakage, or an invalid metric;
- strong baselines or source-level inference are absent;
- release wording exceeds actual rights; or
- an unsupported headline claim remains after audit.

The current authorization is:

```text
CANDIDATE_SOURCE_PREPARATION = AUTHORIZED
12_FAMILY_HUMAN_MINI_PILOT = AUTHORIZED_AFTER_GATE_A
SCIENTIFIC_EVALUATION_FAMILIES = NOT_AUTHORIZED
FIRST_40_SCALED_REVIEWS = NOT_AUTHORIZED
FULL_60_H2_PRODUCTION = NOT_AUTHORIZED
```

## 8. Six-week critical path

The schedule is gate-driven. A missed gate moves subsequent work to
`REPAIR/HOLD`; it does not compress review, reuse held-out data, or weaken a
threshold.

| Week | Critical-path work | Required exit |
|---|---|---|
| **1 — freeze and mobilize** | Freeze this decision and registry; assign annotation, adjudication, rights/privacy, engineering, and audit owners; train at least six reviewers; select two excluded calibration families; open source dossiers for at least 10 candidate source groups to yield 6 pilot sources; freeze strong-baseline fairness and competence contracts. | Staffing and candidate pipeline active; no human denominator started. |
| **2 — source and input gate** | Complete exact asset, lineage, media, rights, privacy, and release review; select exactly 6 pilot source groups and 12 candidates; verify modality streams without asserting necessity; freeze sampling seed, packets, role assignments, and calibration outcomes. | Gate A GO, REPAIR, or NO-GO. |
| **3 — independent human passes** | Execute author/verifier, blind alternative search, validators A/B, full-source logs, retrieval-assisted challenge, leave-one-out, modality drops, and pair-isolation checks. Continue rights-first preparation of the 120–160-candidate reserve without bulk annotation. | All independent forms complete or explicit repair queue. |
| **4 — adjudication and saturation** | Adjudicate every family; run the blind saturation audit; reopen and revalidate any newly discovered route; import immutable records; report funnel, agreement, alternative-SES discovery, failures, governance holds, and labor. | Gate B GO, REPAIR, or NO-GO. |
| **5 — strong-agent competence** | Repair controller/finalizer only on consumed synthetic/development data; freeze a new unseen fictional suite; run once; independently audit syntax, semantics, terminals, oracle evidence, abstention, unsupported claims, failures, leakage, and hashes. | Gate C GO, REPAIR, or NO-GO. |
| **6 — H2 mini diagnostic and scale decision** | Only if Gates B and C are GO, freeze and execute the H2 mini diagnostic with single-shot RAG, learned ReAct, learned sufficiency control, oracle/partial evidence diagnostics, and no-trigger controls. Audit all denominators and decide Gate D. Then decide only the first-40-review authorization under Gate E. | `END_TO_END_DIAGNOSTIC_GO/REPAIR/NO_GO` and `60_H2_PRODUCTION_AUTHORIZED/HOLD/NO_GO`. |

If Gate B or C is not GO by Week 6, the week is used for the authorized repair
branch and no scientific family run occurs.

## 9. Compute, labor, rights, and schedule dependencies

### 9.1 Labor

- Pilot direct review: **72–126 person-hours**.
- Training/calibration: **15–25 person-hours**.
- Pilot source rights/technical preparation: **24–60 person-hours**.
- Coordination/reporting: **10–20 person-hours**.
- Total pilot planning envelope: **approximately 100–220 person-hours**.
- Required staffing: at least six trained reviewers with role rotation, an
  annotation lead, at least two adjudication-capable reviewers, a
  rights/privacy lead, and data/QA support.
- A 60-H2 program is not a six-week annotation task: its current planning
  envelope is approximately **680–1,480 person-hours** for 80–100 completed
  reviews, excluding counsel delay, model experiments, and storage.

### 9.2 Compute

- The exact Qwen2.5-7B snapshot is available and has demonstrated roughly
  15–16 GB peak resident memory in existing CPU runs.
- The v3 development run required 122 model calls for 16 cases and recorded
  355.437090 seconds of summed generation latency. This is planning evidence,
  not a forecast for the H2 experiment.
- Before Gate C, reserve capacity for a one-shot unseen synthetic run,
  independent verification, and immutable output storage.
- Before Gate D, budget all C/B/R episodes, no-trigger controls,
  oracle/partial-evidence diagnostics, replay, and failure reserves. There is
  no silent retry selection.
- At the minimum 60-H2 scale, 60 families produce 180 C/B/R episodes per
  system; four core learned classes imply at least 720 core trajectories before
  secondary retrieval conditions, diagnostics, and reserves.
- A direct video-capable baseline may require GPU capacity and a separately
  pinned snapshot. It cannot be replaced by a text-only controller while still
  being described as a direct audiovisual baseline.

### 9.3 Rights and release

- Rights review precedes expensive annotation.
- Scientific acceptance, processing authority, and public release authority
  are separate decisions.
- Every primary family must permit release of annotations, schemas, split
  metadata, evaluation code, and required attribution.
- Raw media may remain non-redistributable only if lawful reconstruction or a
  clearly labeled restricted evaluation remains possible.
- Public and restricted build pipelines must remain physically and logically
  separate.
- Any `unknown_hold` blocks H2 freeze for the intended use.

### 9.4 Critical external dependencies

- reviewer availability and independence;
- source owner/licensor response time;
- component-level music, image, speaker, and third-party rights;
- stable authorized acquisition routes;
- sufficient non-NOAA source diversity;
- strong model snapshot availability and license;
- CPU/GPU queue time, local storage, and artifact retention;
- independent metric, leakage, replay, and claim auditors.

## 10. Freeze boundary

This decision supersedes any implication that the shortest CVPR route is to
keep iterating a controller until it becomes the paper's proposed method. It
does not supersede the canonical metric semantics, annotation tiers, source
firewall, or rights rules.

No later artifact may:

- promote machine-provisional families to H1/H2 without completed human roles;
- tune on Task-120 labels, future test sources, or adjudication rationales;
- call v2/v3 a strong agent before Gate C;
- start scaled human production before Gate E;
- replace a failed family or model run after seeing outcomes;
- convert a failed modality stratum into a positive claim;
- describe restricted assets as a public benchmark.

The decision remains `CVPR_PIVOT_FROZEN` because the thesis, contribution
boundary, six-week path, resource dependencies, and stop conditions are
coherent with the available evidence.

## 11. Authoritative evidence read for this freeze

- `docs/paper/cvpr_thesis_and_evidence_gates.md`
- `docs/paper/cvpr_execution_blueprint.md`
- `docs/review/cvpr_pre_submission_risk_register.md`
- `docs/review/cvpr_pivot_review_data_construct.md`
- `docs/review/controller_capacity_sensitivity_qwen7b.md`
- `docs/review/controller_capacity_sensitivity_qwen7b_audit.md`
- `docs/design/controller_v3_factorized_state.md`
- `data/restricted/scale1b/controller_v2_holdout_evaluation/safe_aggregate.json`
- `orchestration/results/108_construct_validity_mini_pilot.txt` through
  `orchestration/results/121_controller_v3_development.txt`, including the
  Task-113/114/119 continuation and audit reports

The restricted controller-v2 evaluator key and restricted per-case labels were
not read for this decision.
