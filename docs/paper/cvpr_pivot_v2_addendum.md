# AV-TRACE CVPR Pivot v2 amendment

**Date:** 2026-09-23  
**Decision token:** `CVPR_PIVOT_V2_FROZEN`  
**Current Gate A decision:** `REPAIR`  
**Current event-source exact-acquisition decision:** `NOT_AUTHORIZED`

## 1. Authority and supersession

This is a prospective governance amendment to the frozen Task 122 CVPR pivot.
It does not rewrite or invalidate the evidence recorded by Task 122 or Tasks
138–148. Where a planning rule in those artifacts conflicts with this
amendment, this amendment controls future source selection, annotation,
intervention execution, baseline execution, scaling, analysis, and
paper-facing terminology.

This amendment creates no human result, H1/H2 family, model result, scientific
episode, acquisition approval, or release approval. Existing source data,
code, prior results, and frozen documents remain unchanged.

## 2. Executive decision

The paper remains a benchmark-and-diagnostic-protocol paper, not a controller
method paper. The stale lecture-heavy plan is replaced by the following
prospective design:

1. The four canonical lecture sources are development/calibration sources
   only. They cannot define the broad audiovisual pilot, enter its 12-family
   denominator, or enter a future primary test split.
2. The preferred Gate A pilot is exactly six source groups and 12 candidate
   families: conditional `cand-049` and `cand-052`, plus four newly cleared
   event-centric source groups with explicit capture-format quotas and
   semantic visual/audio prescreens.
3. The primary restoration effect is the Task 145 mechanism-specific,
   exogenous `RESTORED - NO_TRIGGER` intention-to-treat contrast. The two
   intervention mechanisms are not pooled.
4. The 12-family pilot requires source-group-level reviewer blindness, six
   distinct roles per family, and at least eight unique trained reviewers.
5. The paper-facing H2 term is
   `H2_HUMAN_ADJUDICATED_SATURATION_AUDITED`. “Gold,” “exhaustive,” and “all
   possible SESs” are not permitted.
6. The preferred final paper scale is at least 60 H2 families from at least 30
   source groups, including at least 12 untouched test source groups. A
   60-H2/20-source/8-test-source fallback is descriptive only and cannot
   support controller-superiority claims.
7. The exact Task 148 primary/fallback baseline matrix is adopted, but all
   acquisition, runtime, competence, H2, leakage, and scientific-execution
   gates remain controlling.
8. Gate A is `REPAIR`, not `GO` and not currently `NO_GO`. Event-source exact
   acquisition remains blocked for every proposed source.

## 3. Paper position and claim firewall

### 3.1 Retained prospective contribution

The intended contribution is a human-adjudicated, saturation-audited matched
evidence-access diagnostic with:

- whole-source construction and source-disjoint evaluation;
- matched `CLEAN`, `BLOCKED`, `RESTORED`, and `NO_TRIGGER` states;
- a common supported-answer endpoint;
- mechanism-specific exogenous restoration effects;
- answer-versus-support/citation diagnostics;
- trace-level Acquire/Ground/Act failure analysis; and
- rights-, privacy-, lineage-, and release-aware source governance.

### 3.2 Claims still prohibited

The following remain prohibited unless a later gate explicitly authorizes
them:

- controller novelty or superiority;
- SOTA, first, universal-reliability, broad population-ranking, or broad
  out-of-domain-generalization claims;
- claims that the canonical lecture sources establish broad audiovisual,
  ambient-audio, dynamic-visual, or event-centric validity;
- claims that machine retrieval labels, AST/CLIP labels, or placeholder
  questions establish semantic necessity;
- “human gold,” “exhaustive SES,” “all possible SES,” or equivalent
  completeness wording;
- claims that controlled evidence-access interventions estimate naturally
  occurring deployment-failure prevalence;
- public-benchmark or media-release claims beyond source-specific affirmative
  authority; and
- any result claim based on human reviews or model runs that have not
  occurred.

## 4. Source-composition amendment

### 4.1 Canonical four lecture sources

The following source groups are permanently classified
`DEVELOPMENT_OR_CALIBRATION_ONLY`:

| Source group | Allowed role | Prohibited role |
|---|---|---|
| `SG-OXFORD-QM-001` | author training, route-closure rehearsal, negative examples, development, excluded calibration | Gate A 12-family denominator; broad A/V pilot evidence; primary test |
| `SG-OXFORD-DHL-CONSCIOUSNESS` | development and repaired excluded calibration, including repaired `CAL02` if otherwise eligible | Gate A 12-family denominator; broad A/V pilot evidence; primary test |
| `SG-MIT-RES12-003-L01` | narrow lecture-navigation development/calibration | Gate A 12-family denominator; ambient or dynamic-visual evidence; primary test |
| `SG-YALE-PHYS200-L01` | board/OCR development/calibration | Gate A 12-family denominator; ambient or dynamic-visual evidence; primary test |

Their completed full-timeline index remains valuable engineering evidence. It
does not establish the source composition required for a broad audiovisual
pilot.

### 4.2 Preferred six-source Gate A pool

The only preferred broad-pilot composition is:

1. `cand-049`, conditionally retained for two repaired families;
2. `cand-052`, conditionally retained for two repaired families;
3. one newly cleared non-NOAA field-procedure or maintenance source;
4. one newly cleared non-NOAA observational-environment or wildlife source;
5. one newly cleared non-NOAA industrial or laboratory-process source; and
6. one newly cleared non-NOAA assembly, repair, mission-operation, or
   comparably action-rich source.

`cand-049` and `cand-052` remain development-touched and are permanently
ineligible for the future primary test split. Their inclusion in the pilot is
conditional on source-specific rights/privacy clearance and the semantic
prescreens below. Existing custody is not evidence of annotation or release
authority.

No Task 143/147 event-source lead is selected by this amendment. A source ID
may replace one of the four `NEW-EVENT-*` roles only after a separate
source-specific preflight records `GO`.

### 4.3 Exact source and capture-format quotas

Gate A `GO` requires all of the following:

- exactly six source groups and exactly two gate-defining candidates per
  source;
- exactly four newly cleared non-NOAA event-centric source groups;
- no more than two lecture/webinar/presentation-wrapped groups among the six;
- at least four distinct capture-format categories among the six;
- one new source satisfying each of the four event-centric roles in Section
  4.2;
- at least three independent publisher/production lineages among the four new
  event-centric sources;
- no single producer, series, or correlated production lineage satisfying
  more than two of the four event-centric slots;
- at least two source groups passing the semantic non-speech-audio source
  prescreen; and
- at least two source groups passing the dynamic non-text-visual source
  prescreen.

Topic diversity alone does not satisfy these quotas. Multiple NASA/JPL
documentaries, mirrors, excerpts, alternate encodes, or episodes from one
correlated production family cannot be counted as independent capture-format
diversity without an explicit lineage audit.

### 4.4 Exact 12-family target

The preferred authoring matrix is:

| Slot | Source role | Profile | Hop | Span | Intervention mechanism |
|---|---|---:|---:|---:|---|
| B01 | `cand-049` | A | one | near | silent route withholding |
| B02 | `cand-049` | V+S | multi | far | explicit channel outage |
| B03 | `cand-052` | S | one | near | explicit channel outage |
| B04 | `cand-052` | S | one | near | silent route withholding |
| B05 | field procedure/maintenance | V | one | near | silent route withholding |
| B06 | field procedure/maintenance | V+A | multi | far | explicit channel outage |
| B07 | observation/environment/wildlife | V | one | near | explicit channel outage |
| B08 | observation/environment/wildlife | V+S+A | multi | far | silent route withholding |
| B09 | industrial/laboratory process | A | one | near | explicit channel outage |
| B10 | industrial/laboratory process | S+A | multi | far | silent route withholding |
| B11 | assembly/repair/mission operation | V+S | multi | far | silent route withholding |
| B12 | assembly/repair/mission operation | V+S+A | multi | far | explicit channel outage |

The resulting targets are exactly two each of `V`, `S`, `A`, `V+S`,
`V+A/S+A`, and `V+S+A`; six one-hop and six multi-hop; six near/local and six
far/separated; and six families per intervention mechanism.

These are sampling and authoring targets, not labels to force. A failed
semantic, sufficiency, minimality, necessity, or shortcut test requires
repair, replacement, relabeling with a prospectively narrowed claim, or
rejection. It may not be overridden to preserve a quota.

### 4.5 Semantic visual/audio prescreens

Before substantive family authoring:

- every source proposed for an `A`, `V+A`, `S+A`, or `V+S+A` family must
  undergo a documented human semantic non-speech-audio prescreen;
- every source proposed for a `V`, `V+S`, `V+A`, or `V+S+A` family must
  undergo a documented human dynamic non-text-visual prescreen; and
- the prescreener must not later serve as a blind alternative finder or blind
  saturation auditor for that source group.

The audio prescreen passes only when a temporally localizable, source-world
non-speech event plausibly changes answerability and is not merely speech,
music/score, applause, generic room noise, a coarse AST label, or a
spoken/visible substitute.

The visual prescreen passes only when dynamic non-text evidence plausibly
changes answerability and is not recoverable from transcript, captions, OCR,
slides, title cards, talking heads, metadata, or a static diagram alone.

The prescreens establish authoring eligibility only. They are not H1/H2
necessity findings. Full-source search, derived-route closure, modality drops,
minimality, necessity hitting sets, and saturation audit remain mandatory.

## 5. Gate A decision

### 5.1 Decision: `REPAIR`

Gate A is `REPAIR`.

It is not `GO` because:

- Task 147 found zero `EXACT_PREFLIGHT_READY` event sources, five held
  candidates, and one no-go candidate;
- no event source has affirmative acquisition, internal-processing, and
  restricted-annotation authority;
- the preferred four-source event-centric replacement wave is not selected or
  frozen;
- Task 144 found that all 14 existing registry questions and answers are
  placeholders and none is ready for human review as written;
- only repaired `F09`–`F12` may be conditionally carried from the current
  gate-defining candidates;
- `cand-049` and `cand-052` still require their specified rights/privacy and
  semantic/shortcut repairs;
- the 12 candidates, two excluded calibrations, source dossiers, capture
  fields, intervention-v2 manifests, and packet hashes are not frozen;
- the Task 145 metadata-only leakage gate is not run;
- no roster of at least eight trained reviewers has been assigned and frozen;
  and
- the two excluded calibration families have not been completed.

It is not currently `NO_GO` because repository evidence still contains
plausible event-centric leads and an unchanged-construct replacement path.
That is feasibility evidence only, not acquisition or annotation authority.
Gate A becomes `NO_GO` if six eligible sources and the required strata cannot
be assembled without weakening source, rights, privacy, semantic, technical,
construct, or blindness rules.

### 5.2 Gate A `GO`

Gate A may be reconsidered as `GO` only when:

1. the exact six-source composition and 12-slot matrix in Section 4 are
   frozen;
2. all four event-centric sources have source-specific exact-route,
   identity/duration/stream, lineage, component, rights, privacy, processing,
   restricted-annotation, and custody decisions that are affirmative for the
   intended pilot use;
3. `cand-049` and `cand-052` have no applicable unresolved hold;
4. all required source-level and family-level semantic V/A prescreens pass;
5. all placeholder questions, answers, claims, intervals, SES hypotheses, and
   shortcut ledgers are replaced with substantive authored records;
6. all 12 families use the Task 145 intervention-v2 contract and have
   mechanism-specific route-closure/restoration feasibility;
7. the state-surface and R/N fork manifests are frozen and the metadata-only
   leakage preflight passes;
8. exactly two excluded calibration families are frozen and completed, and
   resulting protocol/training defects are repaired before pilot packet
   distribution;
9. at least eight unique trained reviewers are available and all six
   family-level roles can be assigned under the source-blindness rules;
10. reviewer assignments and the pre-distribution source-exposure snapshot
    are hash-frozen;
11. forms, protocol version, candidate registry, sampling seed, packet
    manifests, and hashes are frozen; and
12. no critical rights, privacy, safety, lineage, construct, or technical hold
    remains.

Gate A `GO` authorizes distribution of the 12-family pilot packets. It does
not authorize scientific model episodes or scaled production.

## 6. Human construct and terminology amendment

### 6.1 Roles and reviewer count

Each family retains six distinct human roles:

1. question/claim author or independent verifier;
2. blind full-source alternative-evidence finder;
3. validator A;
4. validator B;
5. independent adjudicator; and
6. blind post-adjudication saturation auditor.

The complete 12-family pilot must use at least eight unique trained reviewers.
Assignments are frozen before packet distribution.

### 6.2 Source-level blindness

Family-level role separation is necessary but insufficient. For every source
group `g`:

- a person exposed to preferred evidence, machine ranks, validator decisions,
  adjudication, or the accepted SES ledger for any family in `g` may not be a
  blind alternative finder or saturation auditor for another family in `g`;
- an adjudicator may not have authored any family in `g`;
- the saturation auditor begins only after adjudication is frozen, receives
  the source provenance/duration and frozen question, and remains blind to the
  accepted SES ledger, preferred SES, machine ranks/confidence/tier evidence,
  validator decisions, and adjudication decision;
- every exposure and assignment is recorded in the source-exposure and
  reviewer-assignment ledgers; and
- assignment or exposure-ledger mutation after freeze invalidates the
  affected packet.

### 6.3 Paper-facing H2 term

The only paper-facing H2 name is:

`H2_HUMAN_ADJUDICATED_SATURATION_AUDITED`

It means that all required roles, adjudication, source-level independence,
rights/privacy/safety checks, full-source route search, minimality, necessity,
pair isolation, restoration feasibility, derived-route closure, and blind
saturation audit passed under the frozen protocol.

It does not mean exhaustive truth. The permitted SES wording is:

> all accepted SESs discovered under the frozen saturation protocol

If the saturation audit finds a new sufficient route, the family reopens and
loses H1/H2 promotion until the route is reconciled and all affected checks
are repeated.

### 6.4 Pilot outcome gate

The Task 122 numerical Gate B floors remain:

- 12/12 completed;
- at least 9/12 H1;
- at least 8/12 H2;
- pair-isolation failures at most 1/12;
- systematic minimality/modality failure at most 3/12;
- no unresolved critical governance hold;
- at least two accepted non-NOAA source groups;
- at least three accepted event-centric source groups, unless broad
  audiovisual/event-centric claims are prospectively removed before
  scientific execution;
- ambient and `V+S+A` H2 coverage, or prospective removal of those paper
  strata;
- all saturation discoveries repaired and re-audited; and
- measured labor and yield supporting an unchanged-criteria route to scale.

All pilot statistics remain `LOW_N_MINI_PILOT_DESCRIPTIVE_ONLY`.

## 7. Causal amendment

Task 145 controls primary restoration scheduling and analysis.

### 7.1 Primary intervention

- The restoration checkpoint is fixed at zero-based action index 4: after four
  completed action/response cycles and before the next model decision.
- One blocked prefix is replayed into fresh, isolated `RESTORED` and
  `NO_TRIGGER` continuations.
- Both arms receive a byte-identical neutral public checkpoint event.
- Only evaluator-private route availability changes in `RESTORED`.
- Public transcript hashes must match through the checkpoint.
- Early terminators and typed invalid runs remain in both assigned arms and in
  the fail-closed intention-to-treat denominator.

### 7.2 Co-primary estimands

The two co-primary causal estimands are:

1. `P1_RN_SILENT_ROUTE_WITHHOLDING_ITT`: mechanism-specific
   `RESTORED - NO_TRIGGER` on the common supported-answer endpoint; and
2. `P2_RN_EXPLICIT_CHANNEL_OUTAGE_ITT`: mechanism-specific
   `RESTORED - NO_TRIGGER` on the common supported-answer endpoint.

Family outcomes are aggregated within source and then equally across sources.
The two mechanisms must have separate tables and wording. A pooled primary
restoration estimand is prohibited.

`RESTORED - BLOCKED` is a secondary mechanism-specific state contrast.
Action-contingent `get_channel_status` restoration is
`SECONDARY_PER_PROTOCOL_ACTION_CONTINGENT`, is separately assigned and
reported, and is never pooled with the exogenous primary condition.

### 7.3 Causal execution prerequisites

Scientific intervention execution remains blocked until all Task 145
requirements pass, including H2 eligibility, frozen mechanism manifests,
state-surface classification, exact R/N prefix replay, fresh-session and
no-cross-state-cache attestations, Williams counterbalancing, route
restoration feasibility, complete ITT assignments, and the source-group-held
metadata-only leakage gate.

## 8. Final scale and inference amendment

### 8.1 Preferred paper scale

The preferred main-paper corpus freeze requires:

- at least 60 `H2_HUMAN_ADJUDICATED_SATURATION_AUDITED` families;
- at least 30 source groups;
- at least 12 untouched test source groups;
- a minimum whole-source split of 12 development, 6 validation, and 12 test
  source groups, targeting approximately 24/12/24 H2 families;
- no more than three H2 families from one source group;
- at least four capture-format categories;
- lecture/webinar/presentation material at no more than 25% of H2 families;
- all development-touched sources, including current NOAA and the canonical
  four lecture sources, excluded from primary test;
- at least five untouched test source groups supporting any claimed
  modality-, mechanism-, or domain-specific conclusion;
- complete source-level rights/release decisions, a 25% source/family reserve,
  frozen contracts, and no test-source tuning.

This scale supports a narrow diagnostic benchmark claim. It does not by
itself authorize broad population ranking, SOTA, universal reliability, or
out-of-domain generalization.

### 8.2 Constrained 20-source/8-test fallback

If production reaches at least 60 H2 families but only 20 eligible source
groups with an 8/4/8 whole-source split and eight untouched test sources:

- the benchmark may be reported only as a narrow, source-bounded diagnostic;
- all model comparisons are descriptive, with source-level estimates,
  uncertainty, leave-one-source-out sensitivity, invalid-run accounting, and
  no confirmatory superiority language;
- the four-hypothesis controller-comparison family is not used to claim
  success;
- controller-superiority, population-ranking, and broad modality/mechanism
  generalization claims are dropped; and
- the paper must state that the test split is low-source.

Fewer than 60 H2 families, fewer than 20 eligible source groups, or fewer than
eight untouched test source groups cannot use this fallback and requires
`REPAIR` or `NO_GO`.

## 9. Strong-baseline matrix

### 9.1 Primary matrix adopted from Task 148

| Role | Frozen choice | Current status |
|---|---|---|
| Native direct A/V, `DLC-B` | `Qwen/Qwen2.5-Omni-7B` at `ae9e1690543ffd5c0221dc27f79834d0294cba00` | metadata reachable; not acquired, load-tested, licensed for project use, or competent |
| RAG-A / REACT-A / SUFF-A controller | `ibm-granite/granite-3.3-8b-instruct` at `51dd4bc2ade4059a6bd87649d68aa11e4fb2529b` | metadata reachable; not acquired, load-tested, or competent |
| Grounded finalizer and ORACLE/PARTIAL diagnostics | the same exact Granite snapshot and tokenizer | pending the same gates |
| Close published-style comparator | `TRACE-STYLE-A-GRANITE33-8B` on its eligible visual subset | AV-TRACE-authored adaptation; never an official TRACE reproduction |
| Controls | `DET-REACT`, `DET-SUFF`, and restoration `NO-TRIGGER` | protocol controls, not learned systems |

No primary claim may depend on a closed API.

### 9.2 Fallback matrix

| Role | Frozen fallback | Limitation |
|---|---|---|
| Direct packed A/V | `microsoft/Phi-4-multimodal-instruct` at `93f923e1a7727d1c4f446756212d9d3e8fcc5d81` | deterministic sampled frames plus audio; not a cleared strict native-video substitute; remote code must be archived and reviewed |
| RAG/ReAct/Suff/finalizer | `Qwen/Qwen3-8B` at `b968826d9c46dd6066d109eabc6255188de91218` | not acquired, load-tested, or competent |
| Published-style comparator | `LONGVT-STYLE-A-QWEN3-8B` on eligible visual cases | adaptation only; no official-reproduction claim |

Fallback activation requires a versioned registry amendment before sealed
competence outputs. Primary and fallback rows may not be mixed based on
outcomes.

### 9.3 Baseline gates

The Task 148 competence floors supersede older inconsistent threshold sets.
The controller/finalizer suite has at least 48 sealed fictional cases and
requires:

- 100% deterministic parser/schema failure-fixture handling;
- at least 90% valid structured model calls;
- at least 85% correct first actions overall and 75% in every stratum;
- at least 75% exact six-field state and 80% on every state component;
- at least 80% oracle-evidence supported answers;
- at least 80% correct abstention on blocked/partial cases;
- at least 80% restoration/reacquisition success;
- zero unsupported required claims, private-field exposures, or deterministic
  answer substitutions; and
- 100% fail-closed behavior on identity mismatch and injected failure.

The direct A/V suite has at least 24 sealed fictional cases and requires:

- 100% processor-manifest failure-fixture handling;
- at least 90% valid final outputs;
- at least 80% complete-evidence supported answers;
- at least 75% supported answers in every modality stratum;
- at least 80% correct abstention on partial/masked cases;
- zero unsupported required claims and zero out-of-exposure citations; and
- 100% observed-evidence lock, required modality-drop counterfactuals, and
  deterministic local replay.

Model acquisition, loadability, and competence are all currently unpassed.
No usable dedicated GPU, frozen runtime, complete license/security archive,
or cleared strict native-A/V fallback exists. `STRONG_BASELINE_REFRESH_REPAIR`
therefore remains controlling.

## 10. Authorization and prohibition map

### 10.1 Authorized now

- Read-only audit and planning using existing artifacts.
- Replacement-source discovery and dossier repair.
- Dated item/policy/rights metadata capture that does not acquire media.
- Requests for source-specific acquisition, processing, restricted-annotation,
  privacy, component, attribution, retention, and takedown authority.
- Development/calibration-only use of the canonical four lecture sources,
  within their existing custody and rights restrictions.
- Repair planning for `cand-049`, `cand-052`, `F09`–`F12`, `CAL01`, and
  `CAL02`; no H-tier promotion is implied.
- Reviewer recruitment, qualification design, blank roster preparation,
  source-exposure planning, and non-distributable packet generation.
- Baseline metadata/license/security archiving, runtime design, synthetic
  adapter work, and source-free test-fixture preparation.

### 10.2 Conditional on a separate written authorization

- Tiny no-retention media/decode probes for a held event source, only after
  governance approval for that probe and with immediate deletion of media
  bytes.
- Exact event-source acquisition, source by source, only after exact route,
  identity, duration/streams, lineage, component rights, privacy, internal
  processing, restricted annotation, custody, and use authority all pass.
- Large-model weight acquisition and load tests, only after exact
  license/security archive, named compute approval, isolated runtime, storage
  approval, and a usable dedicated device path.
- Distribution of calibration packets, only after source-specific
  annotation authority, reviewer training, assignments, and exposure-ledger
  freeze.
- Distribution of the 12-family pilot packets, only after Gate A `GO`.
- H2 mini-diagnostic execution, only after construct Gate B, baseline Gate C,
  and causal/leakage prerequisites pass.

### 10.3 Prohibited now

- Exact acquisition of any Task 143/147 event-source candidate.
- Full media download, indexing, family mining, or human annotation for any
  held/no-go event source.
- Counting a Task 143/147 metadata hypothesis as semantic audio, dynamic
  visual evidence, modality necessity, or source eligibility.
- Using the canonical four lecture sources in the Gate A 12-family
  denominator or any primary test split.
- Distributing the current placeholder candidate registry for human review.
- Assigning H1/H2, calling any family human gold, or claiming exhaustive SES
  coverage.
- Scientific C/B/R/N model episodes, H2 evaluation, first-40 scaled reviews,
  full production, or test unlock.
- Outcome-conditioned fallback selection, silent deterministic answer
  substitution, evaluator-private assistance, or test-source tuning.
- Public release of media, clips, frames, audio, transcripts, annotations,
  embeddings, evaluator artifacts, or IDs without the applicable affirmative
  release decision.

## 11. Updated gates and critical path

### 11.1 Current gate state

| Gate | Current state | Controlling reason |
|---|---|---|
| A — `MINI_PILOT_INPUT_READY` | `REPAIR` | preferred source pool, rights, semantic screens, authored candidates, leakage preflight, calibrations, and reviewer roster incomplete |
| B — `CONSTRUCT_VALIDITY_MINI_PILOT_GO` | `NOT_RUN` | Gate A has not authorized packet distribution; H1=0 and H2=0 |
| C — `STRONG_BASELINE_TECHNICAL_READY` | `REPAIR` | Task 148 matrix identified but acquisition, runtime, compute, load, and competence gates are unpassed |
| Causal execution interlock | `BLOCKED` | Task 145 protocol is ready, but manifests and leakage gate are not run |
| D — `H2_MINI_DIAGNOSTIC_GO` | `NOT_AUTHORIZED` | requires B and C `GO` plus causal interlock pass |
| E — first 40 scaled reviews | `NOT_AUTHORIZED` | requires B–D `GO`, measured calibrations, and a rights-eligible scaled pool |
| F — continuation to final H2 scale | `NOT_AUTHORIZED` | requires first-40 yield/capacity evidence under unchanged rules |
| G — corpus freeze | `NOT_RUN` | preferred target is now 60 H2/30 sources/12 untouched test; fallback restrictions apply at 20/8 |
| H — main evaluation freeze | `NOT_RUN` | corpus, baseline, causal, run-matrix, and test-firewall prerequisites absent |
| I — `PAPER_CLAIM_READY` | `NOT_RUN` | no H2 corpus or scientific results |

### 11.2 Dependency-ordered critical path

The former calendar-first six-week plan is superseded by this
dependency-first path. No elapsed-time promise is made while source authority
and dedicated compute are unresolved.

1. **Freeze this amendment.** Adopt the new source, causal, terminology,
   baseline, scale, and authorization rules.
2. **Repair the event-source pool.** Resolve exact identity, route/runtime,
   component rights, privacy, processing/annotation authority, and production
   lineage; replace the USGS no-go and correlated/unsuitable holds as needed.
3. **Obtain source-specific acquisition decisions.** Gate each source
   independently. Current decision for all event-source exact acquisition is
   blocked.
4. **Acquire and technically verify only cleared sources.** Use restricted
   custody, hashes, stream/timestamp checks, and no implied release right.
5. **Run semantic source prescreens.** Establish authoring eligibility for
   non-speech audio and dynamic non-text visual evidence; replace failures.
6. **Freeze the six-source/12-family input.** Repair `cand-049`/`cand-052`,
   author eight new event-source families, close derivatives/shortcuts, bind
   Task 145 intervention manifests, and freeze two excluded calibrations.
7. **Train and freeze the human workflow.** Recruit at least eight reviewers,
   complete both calibration families, record role-level labor, repair
   training/protocol defects, and freeze source-blind assignments and
   exposure ledgers.
8. **Re-audit Gate A.** Only `GO` authorizes pilot packet distribution.
9. **Run the 12-family construct pilot.** Complete six roles per family,
   adjudication, and saturation audit; decide Gate B without inventing or
   forcing strata.
10. **In parallel, repair the baseline stack.** Complete exact archives,
    approvals, acquisition, isolated load/smoke tests, and the sealed Task 148
    competence suites; decide Gate C.
11. **Pass the causal execution interlock.** Freeze state surfaces, exact R/N
    prefixes, sessions/caches, counterbalancing, ITT assignments, and pass the
    metadata-only leakage gate.
12. **Run the low-N H2 diagnostic only if authorized.** If B and C are `GO`
    and the causal interlock passes, execute the fixed matrix and decide D.
13. **Authorize scale in tranches.** Only after D `GO`, freeze the candidate
    and rights reserve, authorize the first 40 reviews, audit yield/labor, and
    decide continuation without weakening the construct.
14. **Freeze the final corpus.** Prefer 60 H2/30 sources/12 untouched test.
    If only 60/20/8 is achieved, activate the descriptive-only fallback and
    delete controller-superiority claims before test unlock.
15. **Freeze and execute the main evaluation.** Lock source splits, systems,
    prompts, budgets, adapters, estimands, multiplicity, invalid handling,
    environment, and release scope before untouched test execution.
16. **Run final independent audits.** Metric/replay, leakage, construct,
    source/disjointness, rights/release, novelty/freshness, and sentence-level
    claim audits precede `PAPER_CLAIM_READY`.

## 12. Authoritative inputs

This amendment was reconciled from:

- `docs/paper/cvpr_pivot_decision_and_6week_plan.md`;
- `data/rehearsal_plan/cvpr_pivot_gate_registry.json`;
- Tasks 138–148 result reports;
- `docs/review/cvpr_main_blueprint_v2_redteam.md`;
- `docs/review/mini_pilot_family_candidates_scientific_audit.md`;
- `data/rehearsal_plan/mini_pilot_candidate_disposition_v1.json`;
- `docs/design/exogenous_restoration_protocol_v2.md`;
- `data/rehearsal_plan/exogenous_restoration_protocol_v2.json`;
- `docs/review/construct_validity_source_blindness_audit.md`;
- `docs/review/event_centric_source_discovery_v1.md`;
- `data/rehearsal_plan/event_centric_source_dossiers_v1.json`;
- `docs/review/event_centric_live_preflight_v1.md`;
- `data/rehearsal_plan/event_centric_live_preflight_v1.json`;
- `docs/review/strong_baseline_refresh_v2.md`; and
- `data/rehearsal_plan/strong_baseline_registry_v2.json`.

## 13. Freeze boundary

This amendment is governance only. It authorizes no source acquisition, human
review result, model execution on scientific families, scale production,
test-set unlock, or public release. No rights or construct gate is weakened.

`CVPR_PIVOT_V2_FROZEN`
