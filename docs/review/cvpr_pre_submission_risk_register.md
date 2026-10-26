# CVPR pre-submission risk register and red-team plan

**Review date:** 2026-09-20  
**Role:** independent benchmark reviewer / red-team planner  
**Status:** `PLANNED_NOT_EXECUTED`  
**Machine-readable companion:** `data/rehearsal_plan/end_to_end_redteam_checklist.json`

## 1. Scope and non-interference boundary

This review reads the current scientific contract, metrics contract, project
status, construct-validity plan, and learned generation/agent framework. It
does **not** modify or reinterpret Task-108 or Task-110 implementation or
results. It does not promote any evidence-ladder gate.

The authoritative inputs used for this plan are:

- `docs/project_charter.md`
- `docs/decisions.md`
- `docs/paper/cvpr_thesis_and_evidence_gates.md`
- `docs/spec/metrics_protocol.md`
- `docs/overview/av_trace_project_status_for_owner.md`
- `docs/research/novelty_boundary.md`
- `data/rehearsal_plan/cvpr_claim_evidence_ledger.json`
- `data/rehearsal_plan/construct_validity_mini_pilot_plan.json`
- `data/rehearsal_plan/scale1b_learned_baseline_plan.json`
- `orchestration/prompts/108_construct_validity_mini_pilot.md`
- `orchestration/prompts/110_learned_generation_agent_implementation.md`
- `src/av_trace_scale1b_agent/`
- `tests_scale1b_agent/`
- the frozen Task-110 experiment contract/manifest and existing excluded smoke
  artifact under `data/restricted/scale1b/ga_pilot/`

Observed context is used only to prioritize audits:

- the canonical evidence ladder currently marks construct validity, learned
  generation, learned agents, end-to-end diagnosis, scale-up, and paper claims
  as not achieved;
- the human mini-pilot protocol is prepared but recorded as deferred and not
  executed;
- the Task-110 contract is explicitly low-N and
  `MACHINE_ADJUDICATED_PROVISIONAL`;
- the local learned stack uses a pinned Qwen2.5-1.5B-Instruct text model,
  isolated JSONL execution, frozen prompts, opaque public handles, fixed
  budgets, F-CTRL/F-VA retrieval, typed failures, and no deterministic answer
  substitution;
- the existing Qwen smoke record is explicitly excluded from scientific
  evaluation because that family was used for prompt development;
- complete Task-110 result and go/no-go artifacts were not present when this
  plan was written.

These are not new scientific outcomes. Every check below starts as `NOT_RUN`.

## 2. Reviewer stance

The strongest defensible paper is not “another long-video QA benchmark.” It is
a matched intervention study in which a fixed question, support graph, backend,
and budget are replayed while evidence-route availability changes. A CVPR
reviewer is likely to reject the work if any of the following remain true:

1. the novelty claim reduces to combining already occupied components;
2. SES, necessity, or modality labels are machine-provisional;
3. the intervention can be detected through artifacts rather than evidence;
4. prompts or policies were tuned on evaluation families;
5. a weak controller creates artificial failures;
6. results are driven by one source, one domain, one model, or one modality;
7. metric selection, dependence, or missing runs exaggerate separation; or
8. assets, models, or API systems cannot be legally released or reproduced.

The red-team therefore treats any unresolved critical check as a gate blocker,
not as a limitation paragraph that can be deferred to the paper.

## 3. Severity and status vocabulary

| Field | Meaning |
|---|---|
| `CRITICAL` | Failure invalidates the causal construct, evaluation boundary, or principal paper claim. |
| `HIGH` | Failure makes the central result unconvincing or non-generalizable. |
| `MEDIUM` | Failure is survivable only with narrower claims and prominent disclosure. |
| `NOT_RUN` | Required audit has not produced its signed artifact. It cannot count as a pass. |
| `PASS` | Every listed pass criterion is met by a frozen artifact. |
| `FAIL` | At least one pass criterion is violated. |
| `INCONCLUSIVE` | Evidence exists but cannot decide the criterion; this remains blocking unless the rubric explicitly permits otherwise. |
| `NOT_APPLICABLE` | Permitted only with a signed rationale proving the feature/system is absent from every affected claim and result. |

## 4. Risk register

### R01 — Novelty overlap and priority overclaim

- **Likely objection:** Necessary evidence, audiovisual retrieval, sufficiency
  verification, stopping, recovery, tool-using video agents, and
  counterfactual evaluation all have close prior art. A component-stacking or
  broad “first” claim will look incremental.
- **Severity:** `HIGH`
- **Blocks:** `PAPER_CLAIM_READY`
- **Executable audit:** Update the related-work search to the submission date;
  build a claim-by-claim comparison matrix covering task unit, intervention,
  evidence semantics, agent observability, recovery endpoint, and trace
  metrics; have two independent readers map every novelty sentence to that
  matrix.
- **Required artifact:** dated literature-search log, primary-source matrix,
  signed novelty-language audit, and revised claim ledger.
- **Pass criterion:** no unsupported “first/unique/only” wording; every novelty
  sentence names the narrow matched-intervention/trace-level distinction and
  survives both independent audits; negative or overlapping prior work is not
  omitted.

### R02 — Construct validity remains machine-provisional

- **Likely objection:** The benchmark may only encode machine-generated
  questions, answers, support, and intervention hypotheses rather than a
  reproducible human construct.
- **Severity:** `CRITICAL`
- **Blocks:** all three decision gates in this document.
- **Executable audit:** Execute the Task-108 protocol with independent author,
  blind alternative finder, validators A/B, and adjudicator; validate
  answerability, atomic claims, exact intervals, shortcuts, pair isolation,
  recovery feasibility, and rights/privacy flags.
- **Required artifact:** completed portable reviewer packets, validated imports,
  adjudication report, candidate funnel, disagreement report, labor report, and
  immutable accepted/rejected registry.
- **Pass criterion:** the canonical
  `CONSTRUCT_VALIDITY_MINI_PILOT_GO` rule is met: 8–12 completed families,
  at least five source-disjoint videos, all roles complete, at least 75% H1,
  at least 60% H2, pair-isolation failure at most 10%, no unresolved critical
  hold, and no systematic modality/minimality failure above 25%.

### R03 — Minimal evidence is non-unique or incompletely enumerated

- **Likely objection:** Removing the authors' preferred clip does not establish
  insufficiency when paraphrases, repeated statements, cross-modal substitutes,
  or wider temporal context provide another sufficient route.
- **Severity:** `CRITICAL`
- **Blocks:** `END_TO_END_DIAGNOSTIC_GO` and later gates.
- **Executable audit:** For every proposed family, perform blind full-source
  search before revealing the preferred SES, retrieval-assisted alternative
  search, leave-one-evidence-out testing, and a final holdout search by a new
  reviewer. Recompute necessity groups as hitting sets over all accepted SESs.
- **Required artifact:** alternative-search logs with inspected intervals,
  accepted/rejected SES ledger, leave-one-out decisions, hitting-set
  computation, saturation declaration, and adjudicator signature.
- **Pass criterion:** every accepted SES is sufficient and leave-one-out
  minimal; every necessity group intersects every accepted SES; the final
  blind holdout search adds no unblocked accepted route; unresolved alternatives
  quarantine the family rather than being called absent.

### R04 — Modality necessity is confused with modality routing

- **Likely objection:** A controller's use of vision, speech, or ambient audio
  does not prove that the modality is necessary for the item.
- **Severity:** `HIGH`
- **Blocks:** modality claims at every gate and blocks scale-up if planned
  strata cannot be validated.
- **Executable audit:** Run human answerability review under leave-one-modality
  counterfactuals, including transcript-only, silent-video, visual-description,
  audio-event-label, and cross-modal substitute conditions. Close derived
  leaks from ASR, captions, metadata, OCR, and machine descriptions.
- **Required artifact:** per-family modality-counterfactual matrix, leak-closure
  manifest, adjudicated valid missing-modality sets, and stratum summary.
- **Pass criterion:** a modality is labeled necessary only if removing it and
  its derived representations breaks every accepted SES while controls remain
  answerable; otherwise the label is routing/corroboration only and modality
  metrics remain null. Every claimed V/S/A/cross-modal stratum has at least one
  accepted family or is explicitly no-go.

### R05 — Intervention leakage or non-isolated blocking/restoration

- **Likely objection:** Agents may infer `BLOCKED` or `RESTORED` from IDs,
  response formatting, timing, result counts, prompt text, trigger artifacts,
  or collateral changes rather than diagnose evidence access.
- **Severity:** `CRITICAL`
- **Blocks:** `END_TO_END_DIAGNOSTIC_GO` and later gates.
- **Executable audit:** Compare policy-visible pre-intervention and pre-trigger
  transcripts field by field; scan all model inputs/outputs for private IDs;
  verify unaffected tool results and budgets; run no-trigger controls; use an
  adversarial classifier on non-semantic metadata; independently replay exact
  restoration and derived-leak closure.
- **Required artifact:** visibility-diff report, private-field taint scan,
  timing/shape analysis, classifier report, no-trigger matrix, and restoration
  replay hashes.
- **Pass criterion:** no state/family/intervention/support identifier reaches
  the policy; non-semantic pre-causal fields are identical or classifier
  performance is statistically indistinguishable from chance; only the
  registered route changes; no-trigger runs never restore; restored evidence
  must be searched and observed again.

### R06 — Prompt tuning or policy development leaks evaluation families

- **Likely objection:** Prompt wording, action-menu heuristics, repair rules, or
  thresholds may have been optimized after inspecting the same families used
  for evaluation.
- **Severity:** `CRITICAL`
- **Blocks:** end-to-end and paper claims.
- **Executable audit:** Build a chronological development ledger for every
  family/source seen during prompt, controller, schema, metric, and threshold
  development. Freeze hashes before evaluation and rerun only on source-disjoint
  untouched families. Quarantine any touched family from primary evaluation.
- **Required artifact:** prompt-development ledger, family/source quarantine
  list, immutable prompt/config hashes, pre-run timestamped registration, and
  evaluation split manifest.
- **Pass criterion:** zero primary evaluation family or source was used to
  author, repair, select, or compare prompts/policies/thresholds; every change
  after freeze creates a new version and fresh untouched evaluation split.
  Development families may appear only in a separately labeled diagnostic
  table.

### R07 — The 1.5B controller is too weak to test the thesis

- **Likely objection:** Differences may be artifacts of basic instruction
  following, JSON production, or reasoning failure in Qwen2.5-1.5B rather than
  evidence-sufficiency control.
- **Severity:** `HIGH`
- **Blocks:** `END_TO_END_DIAGNOSTIC_GO` if competence floors fail; blocks
  `PAPER_CLAIM_READY` without model-capacity sensitivity.
- **Executable audit:** Before outcome analysis, freeze competence thresholds
  and test schema compliance, oracle/provisional-evidence finalization,
  partial/blocked refusal, simple tool selection, and recovery. Add at least
  one materially stronger controller/backbone sensitivity run on the same
  human-valid families for paper claims.
- **Required artifact:** preregistered competence-threshold file, per-family
  smoke matrix, structured-failure report, stronger-model sensitivity table,
  and compute/cost disclosure.
- **Pass criterion:** 100% deterministic schema/failure fixtures pass; at
  least 90% learned calls end in valid structured output after the single
  allowed repair; at least 80% of human-valid oracle-evidence cases reach the
  supported-answer endpoint with zero unsupported required claims; and the
  principal diagnostic conclusion is not reversed solely by replacing the
  1.5B backbone. Failure of the last condition requires narrowing the claim to
  the tested small model.

### R08 — Source and domain bias

- **Likely objection:** NOAA webinars, three family-bearing videos, and a small
  number of templates may make results source-specific.
- **Severity:** `HIGH`
- **Blocks:** `DATA_SCALE_UP_GO` and `PAPER_CLAIM_READY`; end-to-end claims must
  remain explicitly mini-pilot scoped.
- **Executable audit:** Report source/domain/template/modality/mechanism
  composition; enforce source-disjoint splits; run leave-one-source-out and
  leave-one-domain-out sensitivity; inspect whether one source or template
  determines the sign of the principal finding.
- **Required artifact:** frozen sampling/split manifest, composition table,
  source-cluster estimates, leave-one-group-out report, and source-family
  influence plot.
- **Pass criterion:** scale plan credibly reaches 20–30 rights-cleared videos
  and 60 accepted families; the final evaluation covers at least three content
  domains and both intervention mechanisms; no single video contributes more
  than 10% of scored families; the principal conclusion retains its direction
  after removing each source and is not supported by one domain alone.

### R09 — Licensing, privacy, attribution, and release are unresolved

- **Likely objection:** Public availability or government provenance does not
  automatically authorize redistribution of media, transcripts, annotations,
  embeddings, model weights, or derived clips.
- **Severity:** `HIGH`
- **Blocks:** `DATA_SCALE_UP_GO`, any public benchmark claim, and
  `PAPER_CLAIM_READY` if release language is used.
- **Executable audit:** Conduct item-level review of acquisition, processing,
  annotation, transcript, derivative, raw-media, and public-release decisions;
  separately audit model/data licenses, attribution, privacy, takedown,
  quarantine, and replacement.
- **Required artifact:** final asset rights manifests and evidence snapshots,
  model-license inventory, release bill of materials, attribution file,
  privacy review, and approved takedown/replacement policy.
- **Pass criterion:** no relevant decision is `unknown_hold`; every public
  artifact has affirmative authority and required attribution; restricted
  artifacts are excluded from release packages and claims; no model weight is
  redistributed without authorization.

### R10 — Metrics multiplicity and selective endpoint reporting

- **Likely objection:** A large Acquire/Ground/Act dashboard creates many
  opportunities to select favorable metrics, strata, budgets, or denominators
  after seeing results.
- **Severity:** `HIGH`
- **Blocks:** end-to-end comparative claims and `PAPER_CLAIM_READY`.
- **Executable audit:** Freeze primary hypotheses, practical-effect thresholds,
  denominators, metric directions, strata, equivalence margins, and correction
  families before learned evaluation. Reconstruct every paper table from a
  claim-to-result ledger.
- **Required artifact:** timestamped statistical analysis plan, metric registry,
  hypothesis-family/correction table, denominator audit, and paper claim-result
  map.
- **Pass criterion:** the primary output remains the full dashboard with no
  post-hoc weighted scalar; confirmatory families use Holm correction;
  exploratory BH analyses are labeled; all null, negative, invalid, excluded,
  and failed strata are reported; no headline claim depends on an unregistered
  endpoint or threshold.

### R11 — Statistical dependence and pseudo-replication

- **Likely objection:** Treating states, families, clips, or repeated runs as
  independent inflates precision because the true sampling unit is the source
  video.
- **Severity:** `CRITICAL`
- **Blocks:** population/comparative claims at end-to-end and paper gates.
- **Executable audit:** Verify family-first pairing and video-level aggregation;
  compute video-cluster bootstrap/permutation intervals, source-family
  sensitivity, intracluster dependence, and influence diagnostics. Keep
  low-source pilots descriptive.
- **Required artifact:** analysis code and frozen environment, cluster membership
  manifest, resampling seeds, interval tables, influence report, and independent
  recomputation.
- **Pass criterion:** no family/episode-level naive significance is used;
  estimates pair within family, average within video, and resample videos;
  mini-pilot claims are descriptive; paper-level inference uses the frozen
  20–30-video design or a separately justified power/precision analysis.

### R12 — API-model reproducibility and silent model drift

- **Likely objection:** API baselines cannot be pinned, may change after
  submission, and may silently substitute models or tools.
- **Severity:** `HIGH`
- **Blocks:** any claim relying on an API system; `NOT_APPLICABLE` is allowed
  only if no API row supports the claim.
- **Executable audit:** Prefer pinned offline models for primary results. For
  every API row, archive provider/model string, request date, endpoint,
  parameters, region where relevant, prompts, request/response hashes, retries,
  tool definitions, and repeated-run variance. Test that API failure produces a
  typed invalid run rather than local fallback.
- **Required artifact:** API provenance manifest, restricted raw response
  archive, replay/variance report, cost log, and fallback-injection report.
- **Pass criterion:** all primary claims reproduce without API-only systems, or
  the exact API configuration is documented and a repeated audit shows the
  conclusion is stable; no silent substitution occurs; unavailable historical
  API versions are labeled non-reproducible and excluded from decisive claims.

### R13 — Benchmark contamination or answer memorization

- **Likely objection:** Public NOAA content, transcripts, titles, or repeated
  web text may have appeared in model pretraining, allowing correct answers
  without video evidence.
- **Severity:** `HIGH`
- **Blocks:** claims that answer correctness demonstrates evidence use.
- **Executable audit:** Run question-only, title/metadata-only,
  transcript-only, silent-video, shuffled-evidence, and decoy-citation controls;
  search for exact and near-duplicate question/answer phrases; add source-disjoint
  newly collected or post-training-cutoff material where feasible.
- **Required artifact:** contamination search log, control-run matrix,
  memorization-risk labels, source-date/model-cutoff table, and exclusion or
  sensitivity analysis.
- **Pass criterion:** primary conclusions use supported-answer and citation
  endpoints, not answer accuracy alone; no item is admitted when metadata alone
  reveals the answer; high-risk items are excluded or separately reported; the
  principal intervention finding remains after removing all high-risk items.

### R14 — Evaluator-private information leaks through mapping or scoring

- **Likely objection:** Public claim slots, action menus, observations, repair
  prompts, or post-validation mapping may encode answer/support structure or
  permit an evaluator shortcut.
- **Severity:** `CRITICAL`
- **Blocks:** learned generation/agent readiness and later gates.
- **Executable audit:** Taint evaluator-private IDs/labels and trace every
  serialized model request; fuzz public handles; inspect process environment;
  attempt unknown claim/citation/state-role injection; independently verify
  that mapping occurs only after strict public-schema validation.
- **Required artifact:** taint-flow log, captured request corpus, fuzz results,
  environment audit, and independent mapping-order review.
- **Pass criterion:** zero evaluator-private marker or gold value is present in
  model-visible requests; unknown/private handles fail closed; changing opaque
  handle strings does not change semantic access; post-mapping cannot modify
  model-authored text, claims, citations, or verdict.

### R15 — “Audiovisual agent” claims rely on textualized perception proxies

- **Likely objection:** A text-only controller receiving machine descriptions,
  ASR, or labels is not equivalent to native long-video/audio understanding.
- **Severity:** `HIGH`
- **Blocks:** broad audiovisual capability claims and `PAPER_CLAIM_READY`.
- **Executable audit:** Separate retrieval, perception, and policy errors;
  human-audit every citable observation in the mini-pilot; compare proxy
  observations with at least one raw-frame/raw-audio-capable baseline or
  modality-native tool path; rerun the principal policy comparison on the
  human-audited observation subset.
- **Required artifact:** perception provenance table, human observation audit,
  native-modality baseline manifest, error decomposition, and sensitivity
  result.
- **Pass criterion:** the paper either demonstrates the principal conclusion
  under a raw-modality-capable path, or explicitly limits the claim to agents
  operating over audited multimodal retrieval observations; proxy errors and
  derived modalities are not counted as native modality understanding.

### R16 — Baseline fairness and action-menu/prompt confounding

- **Likely objection:** ReAct and sufficiency controllers may differ in prompt
  length, allowed actions, action ordering, context truncation, retry behavior,
  or hidden heuristics rather than the intended sufficiency state.
- **Severity:** `HIGH`
- **Blocks:** comparative learned-controller claims.
- **Executable audit:** Diff every non-policy configuration; replay with
  counterbalanced action-menu order; report prompt tokens and truncation; verify
  identical backend, retrieval, tool schema, budget, generator, repair, timeout,
  and failure handling. Add a prompt-matched ablation that removes only the
  explicit sufficiency fields.
- **Required artifact:** paired configuration diff, menu-order randomization
  manifest, token/context report, transition-distance report, and policy
  ablation table.
- **Pass criterion:** the intended policy/prompt fields are the only systematic
  differences; results are invariant to menu order within the preregistered
  tolerance; neither system receives more usable context or retries; distinct
  state transitions are demonstrated without evaluator-private information.

### R17 — Metric implementation does not match the claimed constructs

- **Likely objection:** Automated semantic matching, support linkage,
  premature-stop certificates, or restoration arithmetic may be internally
  reproducible yet not valid measures of correctness, support, or recovery.
- **Severity:** `CRITICAL`
- **Blocks:** all scientific gates using those metrics.
- **Executable audit:** Independently recompute every gate-driving metric from
  raw trajectories; blind-human audit answer correctness and claim/citation
  support; execute every route certificate; verify common-endpoint restoration,
  final-decision timing, and null eligibility rules.
- **Required artifact:** independent metric implementation, row-level diff,
  human-vs-automatic agreement report, executable certificate logs, and metric
  version/hash manifest.
- **Pass criterion:** zero arithmetic mismatches; zero unresolved disagreement
  on the binary supported-answer endpoint in the mini-pilot; at least 0.90 raw
  agreement on claim-support/citation labels with all disagreements adjudicated;
  every non-null premature-stop score has an executable final-point route; the
  prohibited heterogeneous restoration subtraction is absent from claims.

### R18 — Missing runs, retries, and failure exclusions create survivorship bias

- **Likely objection:** Completion thresholds or checkpoint reuse may allow
  difficult model failures to disappear from the analyzed denominator.
- **Severity:** `HIGH`
- **Blocks:** learned readiness and all comparative claims.
- **Executable audit:** Reconcile the frozen matrix, checkpoints, trajectories,
  metrics, reports, and paper tables; enumerate every retry and typed failure;
  rerun semantic replay; compare complete-case and all-assigned analyses.
- **Required artifact:** case-accounting ledger, retry chronology, checkpoint
  integrity report, failure taxonomy, all-assigned sensitivity table, and
  manifest hash audit.
- **Pass criterion:** every preregistered case appears exactly once in the
  all-assigned denominator; retries are retained and policy-compliant; no model
  failure receives a deterministic answer; exclusions are predeclared and
  visible; the principal conclusion is unchanged under all-assigned accounting
  or is reported as inconclusive.

## 5. Recommended execution order

1. **Freeze boundaries:** R06, R10, R12, R14, R16, R18.
2. **Validate the construct:** R02, R03, R04, R05, R09, R13, R15, R17.
3. **Establish model competence and fair comparison:** R07 and R16.
4. **Run the matched end-to-end experiment:** R05, R10, R11, R17, R18.
5. **Decide whether scale is justified:** R08 and R09 plus measured
   construct yield/labor/cost.
6. **Only after frozen scaled results:** R01 and the final paper claim audit.

No step should be marked passed from prose alone. The required artifact must
exist, be immutable or hash-bound, name its auditor, and state the exact inputs
and exclusions.

## 6. Final decision rubric

### `END_TO_END_DIAGNOSTIC_GO`

Issue this decision only when:

1. canonical `CONSTRUCT_VALIDITY_MINI_PILOT_GO`,
   `LEARNED_GENERATION_READY`, and `LEARNED_AGENT_READY` are all true;
2. R02–R08, R10–R11, R13–R14, and R16–R18 are `PASS`;
3. R12 is `PASS` or has a valid gate-scoped `NOT_APPLICABLE`
   determination proving that no API system supports the decision;
4. the matched study includes two learned agents and a learned non-agent
   control under common backend/budget/generator contracts;
5. intervention-aware effects appear across at least three source-disjoint
   videos and are not wholly attributable to one family;
6. at least one human-valid diagnostic separation is not explained by
   retrieval recall alone;
7. at least one validated case separates answer correctness from
   supported-answer correctness or citation validity;
8. practical-effect/equivalence thresholds were frozen before model outcomes;
9. video-cluster uncertainty, invalid runs, no-trigger controls, negative
   results, and all denominators are reported.

Return `END_TO_END_DIAGNOSTIC_HOLD` when any required check is `NOT_RUN` or
`INCONCLUSIVE`, or when a repairable failure remains. Return
`END_TO_END_NO_GO` when human construct validation fails centrally, the
intervention cannot be isolated, leakage cannot be closed, or all apparent
separation is explained by retrieval/metric artifacts.

### `DATA_SCALE_UP_GO`

Issue this decision only when:

1. `END_TO_END_DIAGNOSTIC_GO` and
   `CONSTRUCT_VALIDITY_MINI_PILOT_GO` are true;
2. R02–R11 and R13–R18 are `PASS`, with no unresolved critical finding;
3. measured candidate yield, alternative-SES failure, rejection causes,
   reviewer time, adjudication time, compute/storage cost, and rights-review
   throughput are available;
4. a frozen plan credibly reaches 20–30 rights-cleared videos and 60 accepted
   families without lowering construct thresholds;
5. source-disjoint splits, modality/mechanism strata, reserves, quality
   control, power/precision targets, and reviewer capacity are frozen;
6. no evaluation-family prompt/retrieval/fusion tuning is permitted.

Otherwise return `DATA_SCALE_UP_HOLD`. Return `DATA_SCALE_UP_NO_GO` if
construct yield, rights throughput, or labor makes the target infeasible
without weakening the scientific contract.

### `PAPER_CLAIM_READY`

Issue this decision only when:

1. all prior scientific gates, including `DATA_SCALE_UP_GO`, are true;
2. every R01–R18 check is `PASS`, except a genuinely unused API path may be
   R12 `NOT_APPLICABLE`;
3. the frozen evaluation includes at least four preregistered system classes,
   including strong learned long-context/non-agent and learned-agent baselines;
4. the principal finding survives source, domain, model-capacity, modality,
   retrieval, prompt, intervention-trigger, and metric sensitivity analyses;
5. the complete dashboard includes video-cluster uncertainty, costs, invalid
   runs, denominators, corrections, negative/null strata, and release scope;
6. a dated novelty audit and a sentence-level abstract/conclusion claim ledger
   find no unsupported wording;
7. public release claims match the rights-approved release bill of materials
   and reproducibility package.

Any unresolved critical/high blocker yields `PAPER_CLAIM_HOLD`, not a softened
`READY`. A failure of the core construct or causal isolation yields
`PAPER_CLAIM_NO_GO` until the thesis or benchmark design is changed.

## 7. Current disposition

This document does not score any check. All entries in the companion checklist
are `NOT_RUN`. The canonical project files therefore continue to control the
current gate state; this review plan supplies only the evidence needed for a
future independent decision.
