# AV-TRACE CVPR evaluation preregistration after H2 construction

**Version:** 1.0  
**Preregistered:** 2026-09-23  
**Status:** planning-only; no evaluation authorized or executed  
**Readiness token:** `CVPR_EVALUATION_PREREGISTRATION_READY__EXECUTION_BLOCKED`  
**Machine-readable companion:** `data/rehearsal_plan/cvpr_evaluation_gate_registry.json`

## 1. Scope, authority, and non-result boundary

This document specifies the confirmatory evaluation that may be executed only
after AV-TRACE has constructed and frozen an eligible H2 corpus. It does not
authorize model inference, human annotation, source acquisition, family
acceptance, split access, or test execution. It contains no model result and no
invented human label.

No model runs were performed and no invented human labels were created.

This preregistration is subordinate to the frozen decisions in:

- `docs/paper/cvpr_pivot_decision_and_6week_plan.md`;
- `docs/paper/cvpr_thesis_and_evidence_gates.md`;
- `docs/paper/cvpr_execution_blueprint.md`;
- `docs/spec/metrics_protocol.md` version 0.3.0;
- `docs/annotation/construct_validity_protocol.md`;
- `docs/decisions.md`, especially D-023 through D-028; and
- `data/rehearsal_plan/cvpr_pivot_gate_registry.json`.

If this document conflicts with a frozen semantic decision, the frozen
decision controls and this preregistration must be versioned before execution.

The following boundaries are immutable:

1. The current NOAA families are `MACHINE_ADJUDICATED_PROVISIONAL`,
   development-only, and permanently excluded from the primary held-out test
   split.
2. The 12-family / 6-source human pilot is
   `LOW_N_MINI_PILOT_DESCRIPTIVE_ONLY`. It cannot support model rankings,
   population inference, final benchmark validity, or confirmatory hypothesis
   tests.
3. Only `H2_HUMAN_ADJUDICATED_GOLD` families may enter primary paper
   denominators.
4. Machine-provisional, H1, H2, public, restricted, and external-compatibility
   results are reported separately and never pooled.
5. The benchmark/protocol is the proposed contribution. Controllers, direct
   models, RAG systems, retrievers, and deterministic policies are baselines or
   diagnostics.
6. Null, adverse, invalid, and unavailable outcomes are retained. No baseline
   is assumed to win.

## 2. Research questions and candidate claims

The main study asks:

1. Does answer correctness diverge from supported-answer correctness and
   citation validity on held-out, human-adjudicated matched interventions?
2. Can complete traces distinguish acquisition, utilization, citation,
   access-diagnosis, stopping, and recovery failures that are not reducible to
   retrieval recall?
3. Does deterministic restoration change the common supported-answer endpoint
   relative to the matched blocked and no-trigger states?
4. Under a shared backbone, backend, candidate universe, finalizer, and budget,
   does explicit evidence-sufficiency control differ from ordinary learned
   ReAct?
5. Do conclusions persist under a second backbone family, a direct
   long-context baseline, retrieval-backend sensitivity, oracle evidence,
   partial evidence, and deterministic protocol controls?

The directional controller hypothesis is optional. A null or adverse
ReAct-versus-sufficiency result does not invalidate the benchmark if the
construct and broader diagnostic claims pass.

## 3. Units, notation, and analysis population

### 3.1 Nested units

| Level | Definition | Statistical role |
|---|---|---|
| Source group \(g\) | Earliest verified source lineage, including mirrors, excerpts, alternate encodings, transcript variants, near-duplicate edits, and all derivatives | Primary independent sampling/resampling unit |
| Family \(f\) | One source, question, atomic-claim graph, all accepted SESs, necessity groups, backend, and budget | Unit of matched causal comparison |
| Episode \(s\) | One state in `CLEAN`, `BLOCKED`, `RESTORED`, or the matched no-trigger control | Outcome observation; never treated as independent |
| Run \(m\) | One frozen system configuration on one episode | System-specific observation |
| Action \(t\) | One model decision or canonical tool/finalize action | Trace-level diagnostic unit only |

The inferential order is:

```text
episode outcome
  -> within-family state/system contrast
  -> mean over families within source group
  -> source-group uncertainty and paired tests
```

No episode-, action-, clip-, or family-level naive significance test may
replace source-group inference.

### 3.2 States

For each eligible family:

- \(C\): `CLEAN`, with at least one accepted SES reachable;
- \(B\): `BLOCKED`, with every route through the adjudicated necessity group or
  necessary channel inaccessible, including derived-route closure;
- \(R\): `RESTORED`, beginning identically to \(B\), with a deterministic,
  policy-blind trigger restoring exactly the registered route; and
- \(N\): `NO_TRIGGER`, beginning identically to \(R\), with the trigger
  disabled and no restoration.

The \(N\) condition is mandatory for every tool-using system exposed to a
restoration mechanism. It is also required for single-shot RAG if the fixed
retrieval pass can fire the same trigger. A direct model is eligible for
\(R\)/\(N\) recovery contrasts only if its adapter supports the same staged,
policy-blind trigger. Otherwise it is endpoint-only for \(C/B/R\), is marked
`NOT_ELIGIBLE_DIRECT_NONSTAGED`, and is excluded from trigger-conditioned
recovery denominators rather than assigned a synthetic value.

### 3.3 Analysis populations

1. **Primary test population:** every frozen H2 test family and every
   preregistered run assignment, with invalid runs retained under the
   intention-to-evaluate rules.
2. **Valid-run sensitivity:** runs with valid model identity, protocol,
   trajectory, budget, and final output.
3. **Complete-pair population:** families with both members required for a
   specific paired contrast. Missingness is reported; no pair is silently
   removed from the primary intention-to-evaluate analysis.
4. **Certificate-eligible population:** episodes whose final observed evidence
   is insufficient and whose final-point route certificate is valid.
5. **Trigger-eligible population:** families for which the registered
   restoration trigger fired in \(R\), remained disabled in \(N\), and passed
   independent replay.

## 4. Exact source-disjoint split policy

### 4.1 Source-group construction

Before split assignment, a provenance and near-duplicate audit must assign one
`source_group_id` to every source and all of its derivatives. Every media file,
clip, transcript chunk, OCR string, caption, embedding, query paraphrase,
candidate family, accepted/rejected SES, reviewer rationale, and model-derived
artifact inherits that source group and split.

A source group may appear in exactly one of:

- `DEVELOPMENT_TRAIN`;
- `VALIDATION`;
- `TEST`;
- `BLIND_RESERVE`; or
- `DEVELOPMENT_ONLY_QUARANTINE`.

Current NOAA source groups and every source used in family construction,
retrieval development, prompt work, controller work, metric repair, threshold
selection, mapper construction, or debugging are assigned
`DEVELOPMENT_ONLY_QUARANTINE` or `DEVELOPMENT_TRAIN`; they are never test
eligible.

### 4.2 Minimum corpus split

The minimum corpus-freeze design is:

| Split | Minimum source groups | Target H2 families | Permitted use |
|---|---:|---:|---|
| Development/train | 8 | 24 | Prompt/query development, learned fusion training, adapter development |
| Validation | 4 | 12 | Checkpoint selection, calibration, budget/threshold freeze, power simulation |
| Test | 8 | 24 | One locked primary evaluation; no tuning or replacement after outcomes |

This 8/4/8 whole-source split preserves the frozen 60-H2 / 20-source minimum.
If 30 sources are available, the preferred split is 12/6/12 plus a blind
reserve.

The 20-source corpus minimum is not equivalent to 20 independent test
clusters. With only eight test source groups, all between-system comparisons
retain the explicit label `LOW_TEST_SOURCE_COUNT_DESCRIPTIVE_COMPARISON`, even
when exact paired tests and cluster intervals are reported. A confirmatory
population-level comparative claim requires at least 20 untouched test source
groups or a separately approved, prospectively expanded test split before any
test outcome is viewed. Benchmark/protocol claims may proceed at the frozen
minimum if their non-ranking evidence gates pass.

### 4.3 Deterministic assignment

Before scaled H2 adjudication begins, after source lineage, rights eligibility,
and provisional source-level composition fields are frozen:

1. Exclude development-only and rights-ineligible groups.
2. Form source-level strata from content domain, intervention mechanisms
   available, and coarse modality-route coverage. No outcome from a learned
   system may enter stratification.
3. Enumerate assignments satisfying the source minima and target family
   counts.
4. Select one assignment using a public SHA-256-derived seed recorded before
   enumeration.
5. If no assignment covers a desired stratum in all splits, acquire additional
   sources or mark that stratum exploratory. Never duplicate a source across
   splits.
6. Every candidate and later H1/H2 record inherits the preassigned source
   split. Underfilled splits are filled only from source groups prospectively
   assigned to that split or its split-specific blind reserve.
7. At corpus freeze, verify the H2 counts and freeze the final source manifest
   and all descendant artifact hashes before validation-model selection.

No H2 test family may be replaced because a model fails, a result is
unfavorable, or a confidence interval is wide. A post-freeze source withdrawal
uses a predesignated blind-reserve source selected without viewing model
outcomes; otherwise the affected estimand is reported with the reduced
denominator.

### 4.4 Test firewall

The following are evaluator-private until all scored outputs are sealed:

- test questions and claim keys beyond the policy-visible public slots;
- accepted SESs, necessity groups, support mappings, and adjudication
  rationales;
- state identity, trigger definition, route certificates, and answer keys;
- test-source embeddings or queries containing evaluator labels; and
- aggregate or per-case test outcomes.

All prompt, retriever, fusion, mapper, budget, output-schema, and threshold
changes stop before test unlock. Any post-unlock change creates a new
configuration and cannot replace the preregistered primary analysis.

## 5. System and baseline matrix

### 5.1 Required learned classes

| ID | Class | Primary role | Required fairness contract |
|---|---|---|---|
| `DLC-B` | Direct long-context learned audiovisual/non-agent | Tests direct source conditioning without retrieval tools | One frozen backbone; deterministic source-uniform packing; same final schema; no H2-aware selection |
| `RAG-A` | Single-shot learned RAG | Non-agent retrieval-grounded baseline | Backbone A; frozen F-CTRL; one deterministic retrieval pass; same finalizer |
| `REACT-A` | Learned ReAct | Ordinary tool-using agent | Backbone A; same backend, tools, observations, context, and budget as `SUFF-A` |
| `SUFF-A` | Learned evidence-sufficiency controller | Tests explicit claim coverage, missingness, calibrated sufficiency, status, and recovery actions | Backbone A; differs from `REACT-A` only in preregistered controller interface/prompt |

At least two backbone/model families must appear in the final paper. The
minimum capacity-sensitivity row is one of:

- `RAG-B`, a single-shot RAG system using Backbone B under the same retrieval
  bundle and finalizer; or
- `DLC-B` if its backbone family is distinct from Backbone A.

Any claim that the ReAct-versus-sufficiency contrast generalizes across
backbones requires the complete paired `REACT-B` and `SUFF-B` rows. A second
direct or RAG backbone alone does not support a cross-backbone controller
claim.

Exact model snapshots are frozen at `E-MAIN-00` after competence, license,
resource, and data-boundary checks. No current model candidate is presumed to
pass.

### 5.2 Mandatory diagnostics and controls

| ID | Condition | Purpose | Main-claim status |
|---|---|---|---|
| `ORACLE-A` | Backbone A generator receives one adjudicated complete H2 SES, with source-time observations and no evaluator labels | Ground ceiling conditional on complete evidence | Diagnostic only |
| `PARTIAL-A` | Same generator receives a preregistered proper subset that cannot support all required claims | Unsupported completion/refusal diagnostic | Diagnostic only |
| `DET-REACT` | Deterministic ReAct protocol control | Positive/control behavior and metric sensitivity | Never a learned baseline |
| `DET-SUFF` | Deterministic sufficiency protocol control | Protocol and intervention sensitivity | Never a learned baseline |
| `NO-TRIGGER` | Restoration-disabled matched condition | Detects trigger leakage and false recovery | Required for recovery claims |
| `F-VA` | Frozen learned visual/audio retrieval sensitivity | Tests retrieval dependence | Separate, unpooled sensitivity |

Oracle and partial bundles are selected by a frozen deterministic rule over H2
evidence before model runs. If several SESs exist, choose the canonical SES by
lexicographic order of its immutable evidence IDs. For partial evidence, remove
the lexicographically first member whose removal is adjudicated to break at
least one required claim; if that rule is inapplicable, use the next registered
member. The model never receives the reason for selection.

### 5.3 Eligibility by outcome family

| Outcome | Direct LC | Single-shot RAG | Learned agents | Deterministic controls |
|---|---:|---:|---:|---:|
| CLEAN/BLOCKED/RESTORED supported endpoint | Yes | Yes | Yes | Yes |
| Acquire metrics | Exposure-only | Yes | Yes | Yes |
| BLOCKED diagnosis/calibration | If schema emitted | Yes | Yes | Yes |
| Trigger-conditioned recovery | Only with staged adapter | Yes if trigger-capable | Yes | Yes |
| Search-policy metrics | No | Fixed-pass only | Yes | Yes |
| Premature stop | No unless a legal continuation interface exists | Fixed-pass certificate if defined | Yes | Yes |
| No-trigger false recovery | Only with staged adapter | Yes if trigger-capable | Yes | Yes |

Ineligible cells remain null with a reason code; they are never entered as zero.

## 6. Frozen resource and budget contract

### 6.1 Tool-using systems

The primary budget for `REACT-A`, `SUFF-A`, any corresponding Backbone-B
agents, and deterministic controls is:

- at most 10 canonical actions including `finalize`;
- total tool cost at most 12.0;
- one action per model turn;
- search `top_k=5`;
- context cap 32,768 processor tokens;
- at most 512 new output tokens per decision/finalization;
- greedy decoding where supported;
- at most one schema-only repair for one malformed decision;
- at most 12 model invocations including finalization and the allowed repair;
- no semantic repair, majority vote, best-of-N, answer substitution, or
  model-specific retry.

Tool costs are:

| Tool | Cost |
|---|---:|
| `search_visual` | 1.0 |
| `search_speech` | 1.0 |
| `search_ambient_audio` | 1.0 |
| `inspect_clip` | 2.0 |
| `read_transcript` | 1.0 |
| `get_channel_status` | 0.25 |
| `finalize` | 0.0 |

All systems share the same immutable candidate universe, decoder/ASR
derivatives, result shapes, intervention manifest, trigger, serializer, error
vocabulary, and context-compaction rule. Search pointers are not citable;
only returned inspect/read observations are citable.

A budget sensitivity may use 20 actions and cost 24.0. It is a separate,
unpooled run and cannot replace the primary result. Retrospective truncation is
prohibited.

### 6.2 Single-shot RAG

The primary single-shot retrieval pass is deterministic:

1. issue the frozen question-derived query to visual, speech, and ambient
   search once each with `top_k=5`;
2. fuse pointers with frozen F-CTRL;
3. traverse the fused order, executing the modality-appropriate inspect/read
   action while total tool cost remains at most 12.0;
4. call the learned finalizer once over the acquired observations.

The generator uses the same 32,768-token context cap, 512-token output cap,
decoding rule, final schema, and single schema-repair allowance as the learned
agents. It does not reformulate queries or retrieve after generation begins.
F-VA repeats this fixed procedure as a sensitivity.

### 6.3 Direct long-context

The direct baseline receives a deterministic, question-independent,
source-uniform representation of the state-accessible media. Packing proceeds
chronologically over a fixed source-time grid until the model's 32,768
processor-token cap is reached. The grid, frame/audio policy, transcript use,
processor, and tie-breaking are frozen on development/validation sources and
reported exactly. No H2 support interval, retrieval score, answer key, or
question-conditioned frame selection may influence packing.

The direct baseline receives one final generation call, at most 512 new
tokens, and one schema-only repair. Its decoded media seconds, frames, audio
seconds, input tokens, wall time, and peak memory are reported. Because its
access pattern differs from the tool budget, it is compared on task outcomes
and resource exposure, not on tool-cost equivalence.

### 6.4 Oracle and partial evidence

Oracle and partial diagnostics use one generation call, the same final schema,
32,768-token input cap, 512-token output cap, greedy decoding where supported,
and one schema-only repair. Their retrieval cost is structurally zero and is
reported as `NOT_APPLICABLE_DIAGNOSTIC`, not as a cost advantage.

## 7. Outcomes and estimands

Let \(A_{fsm}\) be the common supported-answer endpoint, equal to one only when
the run and budget are valid, the system answers with `sufficient`, all
required claims are correct, no forbidden/contradictory/unknown claim is
asserted, and every required claim is supported by valid citations to
observations the system acquired.

Let \(D_{fBm}\) be BLOCKED diagnostic success under metrics protocol 0.3.0,
\(F_{fBm}\) false-sufficient behavior, \(P_{fsm}\) premature stop when
certificate-eligible, and \(I_{fsm}\) a typed invalid-run indicator.

### 7.1 Primary benchmark estimands

All means first average eligible families within source group and then average
source groups equally.

1. **CLEAN supported-answer rate**

   \[
   \mu^A_{C,m}=E_g\{E_f(A_{fCm}\mid g)\}.
   \]

2. **BLOCKED diagnostic-success rate**

   \[
   \mu^D_{B,m}=E_g\{E_f(D_{fBm}\mid g)\}.
   \]

3. **BLOCKED false-sufficient rate**

   \[
   \mu^F_{B,m}=E_g\{E_f(F_{fBm}\mid g)\}.
   \]

   Pure FSR and the conservative `false_sufficient_or_invalid` rate are both
   reported.

4. **RESTORED supported-answer rate**

   \[
   \mu^A_{R,m}=E_g\{E_f(A_{fRm}\mid g)\}.
   \]

5. **Common-endpoint restoration gain**

   \[
   \Delta^{A}_{R-B,m}
   =E_g\{E_f(A_{fRm}-A_{fBm}\mid g)\}.
   \]

   Subtracting BLOCKED diagnostic success from RESTORED answer success is
   prohibited from being called restoration gain.

6. **Trigger-specific restoration effect**

   \[
   \Delta^{A}_{R-N,m}
   =E_g\{E_f(A_{fRm}-A_{fNm}\mid g)\}.
   \]

7. **No-trigger false-recovery rate**

   \[
   \mu^A_{N,m}=E_g\{E_f(A_{fNm}\mid g)\}.
   \]

   Any supported answer in \(N\) is audited for alternative-route leakage,
   memorized/unsupported completion, intervention failure, or scoring error.

8. **Premature-stop rate**

   \[
   \mu^P_m
   =E_g\{E_f(P_{fsm}\mid \text{valid feasible-route certificate},g)\}.
   \]

   Missing or invalid certificates produce null, never zero. A confirmatory
   premature-stop claim is blocked unless certificate coverage is 100% for its
   preregistered eligible denominator.

### 7.2 Primary system contrast

The sole confirmatory between-policy contrast is same-backbone
`SUFF-A - REACT-A`.

| ID | Estimand | Direction and claim rule |
|---|---|---|
| `H-C1` | \(\mu^A_{C,\mathrm{SUFF}}-\mu^A_{C,\mathrm{REACT}}\) | CLEAN non-inferiority margin \(-0.10\) |
| `H-C2` | \(\mu^F_{B,\mathrm{SUFF}}-\mu^F_{B,\mathrm{REACT}}\) | Lower favors sufficiency; practical threshold at most \(-0.15\) |
| `H-C3` | \(\mu^P_{\mathrm{SUFF}}-\mu^P_{\mathrm{REACT}}\) | Lower favors sufficiency; practical threshold at most \(-0.15\) |
| `H-C4` | \(\Delta^A_{R-B,\mathrm{SUFF}}-\Delta^A_{R-B,\mathrm{REACT}}\) | Higher favors sufficiency; practical threshold at least \(+0.15\) |

A directional controller claim requires:

1. `H-C1` non-inferiority;
2. at least one of `H-C2`–`H-C4` passing its multiplicity-adjusted test;
3. the corresponding point estimate meeting the 0.15 practical threshold;
4. no reversal under leave-one-source-out analysis;
5. complete invalid-run and certificate accounting; and
6. wording restricted to the tested backbone unless `REACT-B/SUFF-B` also
   replicate the result.

Failure of any item yields a null, adverse, or inconclusive comparison, not a
changed endpoint.

### 7.3 Secondary metrics

**Acquire**

- alternative-SES-aware Evidence Recall at depths 5 and 20;
- All-Evidence Success at 5 and 20;
- all-SES coverage and necessity-route coverage;
- first accepted evidence rank, MRR, and nDCG;
- inspected/decoded fraction, useful-call rank, and retrieval burden;
- modality/tool calls, query reformulation, fallback, repeated-call, and
  post-block valid-route allocation.

**Ground**

- Answer Score;
- Citation precision, recall, and F1;
- Supported-Claim Rate and unsupported-claim rate;
- correct-answer/wrong-citation rate;
- answer-correct but unsupported rate;
- correction-without-grounding and retained-error rates;
- oracle-evidence grounding ceiling;
- partial-evidence unsupported-completion and calibrated non-answer rates.

**Act**

- high-confidence FSR at \(p_\text{sufficient}\ge0.8\);
- final and stepwise sufficiency Brier scores;
- access-state accuracy and multiclass Brier;
- missing-modality and missing-hop F1/Brier;
- trigger firing, post-trigger reacquisition, and no-trigger status checks;
- trigger-to-first-accepted-SES and trigger-to-supported-finalization actions,
  tool cost, and decoded duration;
- changed-claim sensitivity and unchanged-claim invariance.

**Cost/reliability**

- model calls, tool calls, tokens, tool cost, decoded video/audio seconds,
  wall time, peak memory, and monetary cost where applicable;
- cost per supported answer;
- completion, typed-invalid, exact replay, and semantic replay rates.

No weighted leaderboard scalar is primary or required.

## 8. Failure taxonomy and attribution rules

### 8.1 Behavioral failures on valid runs

These remain scientific outcomes and are never reclassified as infrastructure
invalidity:

- `ACQUIRE_NOT_FOUND`: no accepted SES acquired;
- `ACQUIRE_PARTIAL`: some accepted evidence acquired but no complete SES;
- `GROUND_UTILIZATION`: complete accepted evidence acquired but required claim
  wrong or omitted;
- `GROUND_UNSUPPORTED_CLAIM`: unsupported required/unknown claim asserted;
- `GROUND_CITATION`: claim correct but citation absent, invalid, or
  non-supporting;
- `DIAGNOSIS_FALSE_SUFFICIENT`;
- `DIAGNOSIS_WRONG_ACCESS_CAUSE`;
- `ACT_PREMATURE_STOP`;
- `ACT_NO_RECOVERY_AFTER_TRIGGER`;
- `ACT_FALSE_RECOVERY_NO_TRIGGER`;
- `ACT_OVERSEARCH_REDUNDANT`;
- `FINAL_VALID_WRONG_ANSWER`;
- `FINAL_VALID_SUPPORTED_ABSTENTION`.

A run may receive several leaf tags, but the stage-failure table also reports
one deterministic first-failure stage:

```text
protocol validity
  -> Acquire
  -> sufficiency/access diagnosis
  -> Ground/utilize
  -> cite
  -> continue/recover/stop
  -> supported endpoint
```

### 8.2 Typed invalid runs

Every invalid run receives exactly one primary invalid code and any secondary
diagnostic codes:

- `INVALID_MODEL_IDENTITY`;
- `INVALID_CONFIG_OR_HASH`;
- `INVALID_PRIVATE_FIELD_EXPOSURE`;
- `INVALID_RIGHTS_OR_DATA_BOUNDARY`;
- `INVALID_INPUT_SERIALIZATION`;
- `INVALID_CONTEXT_OVERFLOW`;
- `INVALID_MODEL_TIMEOUT`;
- `INVALID_PROVIDER_ERROR_OR_REFUSAL`;
- `INVALID_MALFORMED_AFTER_REPAIR`;
- `INVALID_ILLEGAL_ACTION`;
- `INVALID_TOOL_TIMEOUT_OR_ERROR`;
- `INVALID_BACKEND_OR_INDEX_MISMATCH`;
- `INVALID_OOM`;
- `INVALID_PROCESS_CRASH`;
- `INVALID_OVER_BUDGET`;
- `INVALID_FINALIZER_SCHEMA`;
- `INVALID_UNKNOWN_CITATION`;
- `INVALID_TRIGGER_OR_INTERVENTION`;
- `INVALID_REPLAY_MISMATCH`;
- `INVALID_OTHER_PREDECLARED`.

`INVALID_OTHER_PREDECLARED` requires a frozen subtype before test unlock. New
post-outcome catch-all categories cannot be used to remove unfavorable runs.

### 8.3 Failure attribution audit

MC3 failure-stage counts require two independent trace auditors or one auditor
plus exact deterministic recomputation. Disagreement is resolved without
access to system identity where feasible. If a failure could be explained by
both acquisition and a later stage, it is counted in multi-label diagnostics
but assigned to the earliest deterministic stage for mutually exclusive
tables.

## 9. Missing, invalid, retry, and exclusion handling

1. **No silent retry selection.** The only routine retry is one schema-only
   repair, retained in the trajectory and charged in model calls/tokens.
2. **Positive success endpoints:** every assigned invalid run contributes zero
   in the intention-to-evaluate analysis.
3. **Lower-is-better safety endpoints:** report:
   - the semantic rate with invalid count shown separately;
   - a conservative `event_or_invalid` rate assigning invalid runs to the
     adverse outcome; and
   - a valid-run-only sensitivity.
   A favorable claim must survive the conservative analysis.
4. **Premature stop:** absent/invalid route certification is null. If any
   required certificate is absent, no confirmatory premature-stop claim is
   permitted; the remaining valid certificates may be shown descriptively.
5. **Paired system contrast:** if one system is invalid and the other valid,
   the intention-to-evaluate endpoint uses the fail-closed assignment above.
   Complete-valid-pair analysis is secondary.
6. **Source withdrawal:** no outcome-based replacement. Use a previously
   frozen blind reserve or report the reduced source count and gate failure.
7. **Structural ineligibility:** direct-model recovery or search metrics that
   the adapter cannot express are null with an eligibility reason, not
   failures.
8. **Mapper failure:** if a frozen claim mapper is required, mapper failure is
   reported separately and is invalid for claim-level scoring. Native
   structured-claim systems remain the primary analysis where available.
9. **Unknown gold/evaluator defect:** quarantine the affected family across all
   systems and states before unblinding aggregate system labels where possible.
   Report the defect and both original-assignment and corrected-denominator
   accounting. A defect discovered because of one model's output does not
   permit selective removal.

## 10. Statistical analysis

### 10.1 Point estimates

For every system/state metric:

1. compute the episode outcome;
2. form required within-family contrasts;
3. average family values within each source group with equal family weight;
4. average source-group values with equal source weight.

The equal-source estimand prevents a source with many families from dominating
the result. A family-weighted estimate is reported only as sensitivity.

### 10.2 Confidence intervals

Primary uncertainty uses a paired source-cluster bootstrap with at least
10,000 resamples:

1. resample test source groups with replacement;
2. carry all systems, states, and paired family records from each selected
   group together;
3. recompute source means and the target estimand;
4. report percentile 95% intervals and the bootstrap seed.

A two-stage hierarchical sensitivity resamples source groups and then families
within selected groups, preserving all system/state pairings. Source-only and
two-stage intervals are both shown if they materially differ.

For medians and cost distributions, use the same source-cluster resampling,
not a run-level bootstrap.

### 10.3 Paired tests

Confirmatory p-values use source-level paired differences. With 12 or fewer
test source groups, enumerate every sign flip; with more than 12, use at least
100,000 seeded sign flips. Non-inferiority uses the source-level difference
shifted by the \(-0.10\) margin. Superiority tests use the preregistered
direction.

The paired test supplements effect sizes and intervals; it does not authorize
a broad population claim at low source count.

### 10.4 Multiplicity

The confirmatory family contains only `H-C1` through `H-C4`. Apply Holm's
step-down correction at family-wise \(\alpha=0.05\) to their four
preregistered one-sided p-values. A controller superiority claim also requires
the practical thresholds in Section 7.2, regardless of p-value.

All other between-system, retrieval, modality, mechanism, domain, budget,
backbone, and component-ablation tests are secondary or exploratory:

- report unadjusted effect estimates and 95% intervals;
- if p-values are shown for a declared exploratory family, apply
  Benjamini-Hochberg at \(q=0.10\) within that named family;
- do not mix hypotheses across exploratory families to obtain a favorable
  correction set; and
- label analyses with fewer than five contributing source groups as
  `SPARSE_STRATUM_DESCRIPTIVE_ONLY`.

No post-hoc threshold, weighted score, favorable budget, or selected stratum
may replace a failed primary endpoint.

### 10.5 Influence and robustness

Required sensitivity analyses are:

- leave-one-source-out point estimates for every headline effect;
- leave-one-domain-out when at least three domains and at least two sources per
  retained domain are present;
- family-weighted versus equal-source weighting;
- intention-to-evaluate versus valid-run-only;
- semantic adverse rate versus `event_or_invalid`;
- all accepted SESs versus the canonical preferred SES only;
- F-CTRL versus F-VA;
- Backbone A versus available Backbone B rows;
- direct-input packing/exposure disclosure;
- observed-evidence-lock analysis using identical acquired observations;
- oracle and partial evidence;
- route-certificate and typed-terminal semantics;
- primary versus doubled budget as separate runs.

If a headline direction reverses after removing one source, the corresponding
general claim fails.

## 11. Power, precision, and scope

No numerical power claim is made now because AV-TRACE has zero H2 families and
no H2 source-level variance estimate. The 12-family pilot is too small for
power estimation and remains descriptive.

Before test unlock, use development/validation outcomes only to run a frozen
simulation-based operating-characteristic analysis:

- preserve observed families-per-source and missing/invalid rates;
- vary source-level effect sizes from 0.05 to 0.30 absolute in 0.05 steps;
- vary intra-source correlation over a prespecified plausible grid;
- evaluate Holm-adjusted power for `H-C1`–`H-C4`;
- estimate interval width and probability of a one-source sign reversal; and
- archive the simulation code, seed, assumptions, and decision.

The simulation cannot change endpoint definitions or test outcomes. It may
cause one of three prospective decisions before test access:

1. add untouched source groups to the test split;
2. retain the minimum split but downgrade comparisons to descriptive; or
3. abandon the directional controller claim.

The frozen 60-H2 / 20-source design is a lower bound for a benchmark/protocol
paper, not evidence of domain representativeness. Expected limitations include:

- few independent test source groups at the minimum split;
- non-random, rights-constrained source sampling;
- limited model/backbone coverage;
- possible foundation-model pretraining overlap;
- sparse modality/mechanism strata;
- direct-versus-retrieval systems having different access interfaces;
- evaluator dependence on complete alternative-SES enumeration;
- API drift or unavailability for any closed row; and
- restricted assets that may prevent a fully public benchmark claim.

No SOTA, universal reliability, broad population ranking, or out-of-domain
generalization claim is permitted.

## 12. Minimum evidence for retained paper claims

| Claim | Minimum retained evidence | If unmet |
|---|---|---|
| **EC1 — audited execution infrastructure** | Existing audited C/B/R execution, exact hashes, replay, budgets, and typed failures; no new empirical claim | Engineering-only wording |
| **EC2 — common supported-answer restoration endpoint** | Metrics protocol 0.3.0 implemented and independently recomputed | Definition-only wording |
| **EC3 — final-point route certificates** | Valid certificate implementation and independent audit; empirical stopping claim additionally requires 100% certificate coverage in its denominator | Definition-only wording or drop stopping result |
| **EC4 — frozen learned retrieval exists** | Exact retriever snapshots and audited deterministic F-CTRL/F-VA execution | Engineering-only wording |
| **MC1 — human-adjudicated matched benchmark/protocol validity** | At least 60 H2 families from at least 20 source groups; frozen source split; all test families H2; pair isolation, derived-leak closure, exact restoration, no-trigger, rights, and held-out construct audit pass | Do not call the corpus benchmark-valid; repair or stop |
| **MC2 — answer accuracy is incomplete** | On H2 test data, answer-correct but unsupported or wrong-citation cases occur on at least three test source groups and across at least two learned system classes; exact denominators and cluster intervals reported | Narrow to “the protocol measures both”; no empirical inadequacy claim |
| **MC3 — failure-stage separation** | At least two non-retrieval failure categories, each occurring on at least two test source groups, independently trace-audited, and not eliminated by conditioning on complete evidence acquisition | Reframe as retrieval-focused or report no stage separation |
| **MC4 — matched recovery is measurable** | Human-valid C/B/R/N isolation; policy-blind trigger; complete trigger/replay audit; common-endpoint \(R-B\), trigger-specific \(R-N\), no-trigger false recovery, and recovery cost reported on at least three test source groups | Remove causal recovery wording; report state endpoints only |
| **MC5 — sufficiency control improves behavior** | All six controller-claim rules in Section 7.2; same-backbone comparison; Holm control; 0.10 CLEAN margin; 0.15 practical improvement; no one-source reversal | Report null/adverse/inconclusive result |
| **MC6 — retrieval is not the whole story** | At least one Ground/Act separation on at least two test source groups under identical acquired observations or conditional on All-Evidence Success; replicated in at least two learned classes | State that observed differences are explained by acquisition |
| **MC7 — generic learned retrieval is not automatically beneficial** | H2 alternative-SES-aware F-CTRL/F-VA replication on source-disjoint test data; at least five source groups per claimed modality stratum; end-to-end propagation; wording bounded to tested encoders/corpus | Drop encoder claim or report provisional registry error |
| **Release claim** | Asset-level release authority, privacy/component review, attribution, takedown/replacement, public evaluator, and reproduction package | Describe restricted/internal evaluation only |

MC2–MC4 do not require any named system to win. They require the specified
diagnostic evidence. MC5 is explicitly contingent and dispensable.

## 13. Go / Repair / No-Go progression

### Gate A — `MINI_PILOT_INPUT_READY`

**GO**

- 12 eligible family candidates and two excluded calibration families;
- exactly six source groups and at least three declared domains;
- at most four gate-defining families from two current NOAA source groups;
- eight candidates from four new non-NOAA source groups;
- complete source dossiers, exact media/hash/lineage records, technical checks,
  and affirmative processing/annotation authority;
- frozen reviewer forms, protocol, seed, and assignments;
- at least six trained reviewers with valid role separation; and
- no unresolved critical rights/privacy/safety hold.

**REPAIR**

- the six-source design remains feasible but candidate, role, technical, or
  non-critical governance records are incomplete.

**NO-GO**

- six eligible groups cannot be assembled without weakening source,
  governance, technical, or stratum rules.

### Gate B — `CONSTRUCT_VALIDITY_MINI_PILOT_GO`

**GO**

- 12/12 families complete across six frozen source groups;
- all six roles complete;
- at least 9/12 reach H1 and at least 8/12 reach H2;
- pair-isolation failures at most 1/12;
- systematic minimality/modality failure at most 3/12;
- no unresolved critical governance hold;
- at least two accepted non-NOAA source groups;
- ambient and V+S+A H2 coverage or prospective removal of those strata;
- all accepted saturation discoveries repaired and re-audited; and
- observed labor/yield supports an unchanged-criteria route to 60 H2.

**REPAIR**

- at least 5/12 reach H1 or failures are localized and versionably repairable,
  with no evidence that the central construct is unreviewable.

**NO-GO**

- fewer than 5/12 reach H1;
- at least 6/12 are rejected; or
- systematic alternative-support, minimality, necessity, isolation, rights, or
  privacy failures undermine the construct.

This gate remains descriptive and cannot promote a paper result.

### Gate C — `STRONG_BASELINE_TECHNICAL_READY`

**GO**

- each required learned system passes its frozen source-free competence suite;
- direct LC, single-shot RAG, learned ReAct, and learned sufficiency adapters
  are hash-frozen;
- at least two backbone/model families are feasible;
- shared schemas, finalizer, budgets, failure policy, and data boundaries pass;
- zero evaluator-private exposure or deterministic answer substitution; and
- independent replay/metric audit passes.

**REPAIR**

- failures are technical or competence-localized and repair uses only synthetic
  or development data under a new version.

**NO-GO**

- a required strong learned class cannot pass competence without evaluator
  assistance, silent fallback, changed scientific labels, or test access.

### Gate D — `H2_MINI_DIAGNOSTIC_GO`

Run only on accepted H2 mini-pilot families after Gates B and C.

**GO**

- learned RAG, ReAct, and sufficiency systems complete under frozen common
  contracts with C/B/R and no-trigger accounting;
- at least one intervention-aware separation occurs across at least three
  source groups and is not one-family driven;
- at least one answer/support or citation divergence occurs;
- at least two non-retrieval failure categories occur, each on at least two
  source groups; and
- invalid runs and source-level denominators are complete.

**REPAIR**

- construct and technical gates pass but the descriptive H2 diagnostic is
  inconclusive or a typed execution defect is repairable without
  outcome-selected replacement.

**NO-GO**

- intervention isolation fails; all differences are retrieval-only/metric
  artifacts; no answer/support divergence exists; no non-retrieval separation
  survives; or strong learned execution requires private assistance.

### Gate E — `FIRST_40_SCALED_REVIEWS_AUTHORIZED`

**GO**

- Gates B–D are GO;
- 120–160 frozen P-tier candidates from 30–40 source groups;
- at least 25 rights-eligible groups for a 20-source target plus 25% reserve;
- source-disjoint split and selection rules frozen; and
- staffing, labor, compute, storage, and rights-review capacity approved.

**REPAIR**

- science gates pass but candidate pool, reserve, staffing, or governance
  capacity is incomplete without requiring weaker construct rules.

**NO-GO**

- a prerequisite is NO-GO or the pool is reachable only through weaker
  construct/governance rules.

### Gate F — `FULL_60_H2_PRODUCTION_AUTHORIZED`

**GO**

- first 40 reviews have H2 yield at least 60%;
- every high-risk stratum has at least five completed reviews;
- no construct threshold is weakened;
- measured labor, rights, compute, and storage fit the plan;
- rights-eligible reserve remains at least 25%; and
- an unchanged-criteria path remains to 60 H2 from at least 20 groups.

**REPAIR**

- a localized, versionable throughput/yield issue can be corrected without
  using test outcomes.

**NO-GO**

- yield is below 60% without localized repair; source/rights/reviewer capacity
  is infeasible; a required stratum cannot be filled; or the principal
  diagnostic premise no longer survives.

### Gate G — `60_H2_CORPUS_FREEZE`

**GO**

- at least 60 H2 families from at least 20 source groups;
- minimum 8/4/8 source-disjoint development/validation/test split with target
  24/12/24 families;
- complete rights decisions and no applicable `unknown_hold`;
- 25% source/family reserve;
- no test-source tuning; and
- prompts, models, retrieval, metrics, budgets, thresholds, invalid reserve,
  and release scope ready to freeze.

**REPAIR**

- scientifically valid production has a fillable count/stratum/governance
  deficit that can be repaired from blind reserve without changing outcomes.

**NO-GO**

- count/source minima require weaker rules; source disjointness or test privacy
  was broken; or an irreparable critical rights/construct/isolation defect
  affects the core.

### Gate H — `MAIN_EVALUATION_FREEZE`

**GO**

- exact source manifests, system snapshots, prompts, adapters, processors,
  retrieval indexes, budgets, seeds, metric code, hypothesis families,
  correction rules, power simulation, and analysis environment are hashed;
- all required competence and data-boundary audits pass;
- no test outcome has been viewed; and
- run matrix includes all primary C/B/R assignments, eligible no-trigger
  assignments, invalid reserve, diagnostics, and deterministic controls.

**REPAIR**

- a missing non-outcome technical artifact can be frozen before test unlock.

**NO-GO**

- any test leakage occurred, an exact system identity cannot be frozen, or the
  run matrix/budget differs by system in an unapproved way.

### Gate I — `PAPER_CLAIM_READY`

**GO**

- Gates A–H are GO;
- four required learned classes and two backbone/model families complete;
- all primary dashboard, paired effects, uncertainty, multiplicity, invalid
  accounting, ablations, and source/domain sensitivities complete;
- at least one non-retrieval diagnostic separation occurs across at least
  three test source groups;
- answer/support or citation divergence is nonzero across at least three test
  source groups;
- no headline conclusion is one-source driven;
- independent metric, replay, leakage, construct, rights/release, novelty, and
  sentence-level claim audits pass; and
- every claim uses only the evidence permission in Section 12.

**REPAIR**

- the corpus/evaluation remains valid but a non-critical baseline, audit,
  uncertainty analysis, or wording defect is missing and can be repaired
  without rerunning the locked test set for result selection.

**NO-GO**

- matched intervention validity fails; the principal result is explained by
  one source/domain, retrieval alone, evaluator leakage, or invalid scoring;
  strong baselines/source-level analysis are absent; or release/headline
  wording exceeds evidence.

`FINAL_BENCHMARK_VALIDATED` remains a later release-and-blind-audit gate. A
restricted internal H2 evaluation can support a bounded scientific paper but
cannot be called a release-ready public benchmark.

## 14. Required paper reporting

The main paper and supplement must report:

- source and H2 construct funnel, alternative SESs, pair isolation, labor, and
  rights/release boundary;
- exact system/backbone/retrieval/budget/prompt/snapshot matrix;
- state-specific Acquire/Ground/Act dashboard with source-cluster intervals;
- C→B, R−B, and R−N matched effects;
- BLOCKED FSR, diagnostic success, premature stop, and no-trigger false
  recovery;
- answer versus supported-answer/citation divergence;
- typed failure counts by run, family, and source;
- all null, adverse, invalid, excluded, and sparse-stratum outcomes;
- source and domain influence plots;
- oracle/partial evidence, observed-evidence lock, F-CTRL/F-VA, budget, and
  sufficiency-component sensitivities; and
- a claim-to-artifact map for every abstract and conclusion sentence.

Qualitative examples must be selected by a frozen rule, such as the first
lexicographic family in each preregistered failure category, not by visual
appeal or result favorability.

## 15. Current readiness and blockers

**Readiness token:** `CVPR_EVALUATION_PREREGISTRATION_READY__EXECUTION_BLOCKED`

The token means that the evaluation design is sufficiently specified for
future freeze/version review. It does not authorize execution.

Current blockers as of 2026-09-23:

1. zero completed human reviews, zero H1 families, and zero H2 families;
2. the 12-family construct pilot has not run and remains descriptive-only;
3. current NOAA families remain development-only and test-ineligible;
4. the canonical new-source full-timeline index is incomplete, so real
   mini-pilot family mining has not run;
5. no accepted real 12-family candidate set exists;
6. strong learned-agent competence remains unpassed;
7. the direct long-context baseline and final two-backbone matrix are not
   frozen or execution-ready;
8. no 60-H2 / 20-source corpus or source-disjoint split exists;
9. no development/validation operating-characteristic simulation exists;
10. rights/release boundaries remain incomplete for a public benchmark claim;
11. no main run matrix, prompt/config freeze, or test firewall has been
    activated; and
12. no model run, human label, or scientific result is authorized by this
    preregistration.

**Current decision:** `PLANNING_GO__SCIENTIFIC_EXECUTION_NO_GO`
