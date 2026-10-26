# AV-TRACE Pilot-0 metrics protocol

**Version:** 0.3.0  
**Scope:** construct validation on matched `CLEAN`/`BLOCKED`/`RESTORED`
families. No weighted primary composite and no confirmatory ranking claim.

**2026-09-20 semantic amendment:** D-024 and D-025 supersede the restoration
and premature-stop semantics in version 0.2.0. Historical generated artifacts
remain historical; new experiments must use this version.

## 1. Common definitions

For family \(f\), state \(s\in\{C,B,R\}\), and system \(m\):

- \(G_{f,s,m}\): binary grounded task success;
- \(p_{f,s,m,t}\): probability that observations before action \(t\) are
  sufficient;
- \(y_{f,s,m,t}\): oracle observed-sufficiency label at that time;
- \(c_{f,s,m}\): final tool cost;
- \(B_f\): common family budget.

Structured claim IDs are primary. Natural-language text is display-only. If a
system cannot emit registered IDs, a frozen mapper is used and mapper errors are
reported separately.

`CLEAN` and terminal `RESTORED` target supported answers. `BLOCKED` targets
calibrated insufficiency, no unsupported required claims, and an access-failure
diagnosis.

## 2. Grounded task success

### `CLEAN` and `RESTORED`

\(G=1\) only when:

- the protocol and budget are valid;
- final verdict is `sufficient`;
- all required claims are correct;
- no forbidden/contradictory claim is asserted; and
- citations instantiate an accepted support derivation.

### `BLOCKED`

\(G=1\) only when:

- the protocol and budget are valid;
- verdict is `insufficient`, or `uncertain` with \(p_\text{sufficient}<0.5\);
- no unsupported required claim is asserted;
- any partial claim is correct and supported; and
- the final missingness diagnosis assigns maximal probability to
  `evidence_in_source_but_inaccessible`.

Report state-specific rates. Do not collapse them into a primary scalar.

## 3. Insufficiency calibration

The stepwise sufficiency Brier score is:

\[
\operatorname{Brier}_{suff}=
\frac{1}{N}\sum_{f,s,m}\frac{1}{|V_{fsm}|}
\sum_{t\in V_{fsm}}(p_{fsmt}-y_{fsmt})^2.
\]

The belief attached to an action is scored against observations available
**before** that action. The belief attached to `finalize` is after the last tool
response.

Also report:

- final sufficiency Brier;
- equal-mass calibration plot;
- `BLOCKED` false-sufficient rate (FSR);
- high-confidence FSR at \(p_\text{sufficient}\ge0.8\).

Pilot-0 has no source-insufficient stratum.

## 4. Evidence-absence versus access-failure diagnosis

The final answer supplies a probability distribution over:

- `source_evidence_absent`;
- `evidence_in_source_but_inaccessible`;
- `evidence_accessible_but_not_found`;
- `not_missing`;
- `uncertain`.

Score multiclass Brier and accuracy. Gold targets are:

- `CLEAN`: `not_missing`;
- `BLOCKED`: `evidence_in_source_but_inaccessible`;
- `RESTORED`: `not_missing` at terminal state.

Stepwise cause reports are scored identically at each state.

## 5. Missing requirements

### Modalities

Alternative SESs can imply several valid minimal missing-modality sets. For a
predicted multilabel set \(\hat M\), score against the best matching gold set:

\[
F1_\text{modality}=\max_{M\in\mathcal M_f}F1(\hat M,M).
\]

Independent modality probabilities are also scored with the minimum multilabel
Brier loss over valid gold sets. They do not need to sum to one.

### Hops

Store both gold hop IDs and their controlled hop types. Final output predicts
types. Report example-based F1 and per-type F1.

## 6. Premature stop

A final-point route-feasibility certificate is evaluated after the last tool
response and before `finalize`. It is evaluator-private and independent of the
system's stated rationale.

A route is certified feasible only when the certificate contains a legal action
suffix that:

1. starts from the exact backend/channel/trigger state at the final decision
   point;
2. fits the remaining step and cost budget;
3. reaches an accepted support derivation;
4. includes any inspect/read operation needed to make the evidence citable;
5. leaves enough budget for a valid `finalize`; and
6. exposes no evaluator-private shortcut to the policy.

The certificate records the final action index, backend-state hash, remaining
steps/cost, acquired evidence, reachable route, channel/trigger state, complete
action suffix and cost including finalization, and validator/version identity.

For final observed evidence that is insufficient:

- if no route is certified feasible, a correctly typed and supported abstention
  or insufficiency declaration is not premature;
- if a route is certified feasible, termination by `answer`, `partial_answer`,
  or `abstain` is premature unless the episode contract predeclares an allowed
  typed terminal declaration and the emitted declaration satisfies its
  oracle-checked conditions.

The current `diagnosis.recovery_route_declared` boolean and free-text
description do not by themselves create an exemption. Unless a track
predeclares an allowed declaration type, the exemption set is empty.
`budget_guard` is valid only if no complete certified route fits the remaining
budget.

The primary denominator is every episode whose final observed evidence is
insufficient and for which at least one feasible route is certified,
independent of system behavior. If the required certificate is absent or
invalid, premature stop is `null`, not zero. Correct abstention and typed
diagnosis are reported separately.

## 7. Restoration response and recovery

### Primary common-endpoint paired restoration gain

Define \(A_{f,s,m}\), the supported-answer endpoint, identically in both
`BLOCKED` and `RESTORED`. \(A=1\) only when:

- the protocol and budget are valid;
- final verdict is `sufficient` and mode is `answer`;
- all required claims are correct;
- no forbidden, contradictory, or unknown claim is asserted; and
- citations from observations actually acquired by the system instantiate an
  accepted support derivation for every required claim.

\[
\Delta_{\mathrm{restore}}^{\mathrm{supported}}=
\frac{1}{|F_{\mathrm{eligible}}|}
\sum_{f\in F_{\mathrm{eligible}}}
\left(A_{f,R,m}-A_{f,B,m}\right).
\]

This common-endpoint quantity is computed over all eligible families and is the
primary restoration estimand.

`BLOCKED` grounded task success \(G_{f,B,m}\) remains the separately reported
state-specific target for calibrated insufficiency/access diagnosis. Directly
subtracting that heterogeneous target from `RESTORED` supported-answer success
is prohibited as restoration gain. If retained for historical parity, name it
`state_target_success_difference` and label it diagnostic-only and non-causal.

Also report:

- change in \(p_\text{sufficient}\), access-failure diagnosis, and search-policy
  allocation from `BLOCKED` to `RESTORED`;
- actions, cost, and decoded seconds from restoration trigger to first accepted
  SES and supported finalization;
- retained-error and correction-without-grounding rates.

Correction recovery on a preregistered **common-failure set** is secondary.
System-specific own-failure recovery is descriptive because its denominator
depends on the system.

## 8. Search-policy change

Predeclare policy features before runs:

- calls by tool/modality;
- first useful call rank;
- query reformulation indicator;
- `get_channel_status` use;
- repeat-call and fallback indicators;
- fraction of post-block actions directed at a valid recovery route.

Report paired `CLEAN→BLOCKED` and `BLOCKED→RESTORED` changes. Rationale text is
not scored.

## 9. Claim-Response Consistency

This name is reserved for withholding/outage transitions. Counterfactual
Grounding Consistency is not used in Pilot-0.

- `CLEAN→BLOCKED`: clean-supported affected claims should be omitted or moved to
  a supported partial answer; unaffected claims should remain stable.
- `BLOCKED→RESTORED`: affected claims should return only when grounded.

Report changed-claim sensitivity and unchanged-claim invariance separately.

## 10. Cost dashboard

Report by state and family stratum:

- tool cost;
- calls;
- decoded video/audio seconds;
- input/output tokens;
- wall time;
- cost per grounded success;
- completion and deterministic replay rate.

Costs are never hidden in a weighted score.

## 11. Budget curves

Pilot-0 does not require budget curves. If reported, they must use:

1. separate runs under frozen budget caps; or
2. declared non-terminating checkpoint predictions.

Retrospective truncation of one terminal output is invalid.

## 12. Aggregation and uncertainty

1. Compute state and paired quantities within family.
2. Average families within each source video.
3. Bootstrap videos for 95% intervals.
4. Report source-family sensitivity when enough sources exist.
5. Show modality and intervention-mechanism strata with denominators.
6. Label all between-system comparisons descriptive in Pilot-0.

Holm correction is reserved for a later preregistered confirmatory comparison
set. BH may be used only for explicitly exploratory secondary analyses.

## 13. Required Pilot-0 dashboard

| System | CLEAN grounded success | BLOCKED diagnostic success | BLOCKED supported-answer endpoint | BLOCKED FSR ↓ | Sufficiency Brier ↓ | Access-failure diagnosis | Premature stop ↓ | RESTORED grounded success | Common-endpoint paired restoration gain | Claim-response consistency | Median cost | Replay completion |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

Public-core and external-compatibility rows are displayed in separate,
explicitly unpooled tables.
