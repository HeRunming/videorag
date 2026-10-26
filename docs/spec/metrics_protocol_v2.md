# AV-TRACE exogenous-restoration metrics protocol

**Version:** 0.4.0  
**Frozen:** 2026-09-23  
**Status:** normative for new primary causal evaluation  
**Scope:** restoration scheduling, assignment populations, and
mechanism-specific evaluation semantics

This protocol supersedes Sections 7, 8, 12, and 13 of
`docs/spec/metrics_protocol.md` version 0.3.0 wherever the older text conflicts
with this file. All non-conflicting supported-answer, citation, calibration,
premature-stop, cost, invalid-run, and source-cluster rules remain in force.

## 1. Terminology

The normative evidence-universe phrase is:

> all accepted SESs discovered under the frozen saturation protocol

No result may imply enumeration of all possible SESs. Discovery of a new
sufficient route reopens and invalidates the affected frozen intervention
until the evidence graph, necessity group, states, and audits are repeated.

## 2. Assignment and endpoint

For family \(f\), system \(m\), mechanism \(k\), and assigned state
\(s\in\{R,N\}\), let:

- \(Z_{fs}=1\) for `RESTORED` and \(0\) for `NO_TRIGGER`;
- \(A_{fsmk}\) be the common supported-answer endpoint;
- \(E_{fsmk}\) indicate that the scheduled event opportunity was reached;
- \(X_{fsmk}\) indicate that hidden restoration was actually applied;
- \(I_{fsmk}\) indicate typed invalidity; and
- \(Q_{fsmk}\) indicate early terminal output before the scheduled event.

\(A=1\) only under the existing supported-answer definition: valid protocol
and budget, sufficient answer verdict, every required claim correct, no
forbidden/contradictory/unknown claim, and acquired citations instantiating an
accepted support derivation.

Assignment occurs before execution. \(Z\) is not changed by \(E\), \(X\),
early termination, tool choice, output validity, or outcome.

The primary restoration matrix contains only systems whose adapter was frozen
as staged and event-capable before assignment. A non-staged system is
`STRUCTURALLY_INELIGIBLE_BEFORE_ASSIGNMENT`, receives no synthetic `R/N`
outcome, and may be reported only in state-endpoint tables. This eligibility
decision cannot be made after outcomes are observed.

## 3. Primary estimands

The primary restoration effect is the assigned, within-family `R-N`
intention-to-treat contrast:

\[
\Delta^{A,\mathrm{ITT}}_{R-N,m,k}
=E_g\{E_f(A_{fRmk}-A_{fNmk}\mid g,k)\}.
\]

There are exactly two separate co-primary mechanism estimands:

1. `P1_RN_SILENT_ROUTE_WITHHOLDING_ITT`;
2. `P2_RN_EXPLICIT_CHANNEL_OUTAGE_ITT`.

They must have separate denominators, source-group estimates, uncertainty,
invalid counts, and tables. A pooled or weighted primary restoration estimate
across mechanisms is prohibited.

`R-B` is a mechanism-specific common-endpoint state contrast and must be named
`restored_minus_blocked_state_contrast`. It is secondary/descriptive because
`BLOCKED` does not receive the matched checkpoint continuation. It cannot
replace `R-N` as causal restoration evidence.

Subtracting BLOCKED diagnostic success from RESTORED supported-answer success
remains prohibited.

## 4. Intention-to-treat accounting

The primary denominator contains every preregistered `R/N` assignment.

1. Early terminal before the event remains included. Score its terminal
   output normally, set \(Q=1\), \(E=0\), and \(X=0\).
2. If a shared blocked prefix terminates before the fork, copy that exact
   terminal prefix artifact to both assigned arms. Both assignments remain in
   the denominator and their within-pair difference is zero.
3. Failure to inspect or reacquire a restored route remains included.
4. Typed invalid runs remain included under the existing fail-closed rules:
   positive success is zero; lower-is-better endpoints additionally report
   event-or-invalid and valid-run-only sensitivity.
5. Missing pairs are never silently dropped. Original assignment accounting
   is primary; complete-valid-pair analysis is secondary.
6. No trigger-reached, exposed, tool-calling, or valid-only subset may be
   presented as the primary restoration effect.

Report, without changing the denominator:

- assigned count;
- early-terminal count;
- event-opportunity-reached count;
- hidden-restoration-applied count;
- restored-route-inspected count;
- complete accepted SES reacquired count;
- valid/invalid count; and
- supported-answer count.

## 5. Exogenous event semantics

The primary event is scheduled at the frozen zero-based action index 4: after
four completed action/response cycles and before the next model decision.

`R` and `N` share one frozen blocked prefix. Each continuation begins in a
fresh session from an exact replay of that prefix. Through and including the
checkpoint:

- public transcript bytes are identical;
- event bytes, cost, schema, and latency bucket are identical;
- model-visible state, intervention, trigger, and assignment labels are
  absent; and
- the only difference is the evaluator-private access-state transition in
  `R`.

If the event opportunity is not reached, no post-terminal event is injected.

## 6. Action-contingent restoration

`get_channel_status`-triggered restoration is
`SECONDARY_PER_PROTOCOL_ACTION_CONTINGENT`.

It must be run as a separate condition with separate assignment IDs and
tables. Report:

- all assigned runs;
- runs that called `get_channel_status` while blocked;
- runs in which the action-contingent restoration fired; and
- supported outcomes in each denominator.

Any effect conditioned on calling the tool or firing the trigger is
per-protocol/descriptive because the conditioning variable is post-assignment
policy behavior. It is not pooled with the exogenous estimate and cannot
support the primary causal claim.

## 7. Mechanism-specific interpretation

### Silent route withholding

The route is absent without an explicit error. The primary estimate measures
the effect of hidden restoration relative to a matched hidden no-restoration
continuation under a balanced public surface.

### Explicit channel outage

The channel returns a standardized unavailable response while blocked. The
primary estimate measures recovery from a known access failure after hidden
restoration relative to the matched sham continuation.

The mechanisms answer different questions and may not be pooled as a primary
estimand.

## 8. Aggregation and uncertainty

For each mechanism and system:

1. score all assigned episodes;
2. form the within-family `R-N` contrast;
3. average families equally within source group;
4. average source groups equally; and
5. use the preregistered paired source-cluster uncertainty procedure.

Report leave-one-source-out, family-weighted, valid-run-only, order-sequence,
and event-opportunity-reached analyses as sensitivity analyses. None may
replace the ITT estimate.

Any stratum with fewer than five contributing source groups is
`SPARSE_STRATUM_DESCRIPTIVE_ONLY`.

## 9. Required restoration dashboard

Use separate tables for silent withholding and explicit outage.

| System | R assigned | N assigned | early terminal R/N | event reached R/N | invalid R/N | R supported answer | N supported answer | R-N ITT | route inspected after restore | complete SES reacquired | median post-event cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

Additional tables must report:

- mechanism-specific `R-B` state contrast;
- no-trigger false recovery;
- action-contingent `get_channel_status` per-protocol results;
- order-sequence sensitivity;
- metadata-only leakage-gate status; and
- fresh-session/cache-isolation failures.

No weighted robustness score or pooled primary restoration row is allowed.
