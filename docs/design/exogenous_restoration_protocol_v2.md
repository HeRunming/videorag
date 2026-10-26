# Exogenous restoration protocol v2

**Frozen:** 2026-09-23  
**Status:** `FROZEN_PRE_ANNOTATION`  
**Decision token:** `CAUSAL_INTERVENTION_V2_READY`  
**Machine-readable contract:** `data/rehearsal_plan/exogenous_restoration_protocol_v2.json`  
**Validation schema:** `docs/spec/exogenous_restoration_execution_plan_schema_v2.json`  
**Evaluation semantics:** `docs/spec/metrics_protocol_v2.md`

## 1. Scope and precedence

This document freezes the primary causal/intervention contract before
annotation or scientific execution. It does not authorize human review, create
human labels, execute an episode, or report a model result.

For new causal evaluation, this v2 contract supersedes only the conflicting
restoration-scheduling and restoration-estimand language in:

- `docs/spec/episode_schema.json` version 0.2.0;
- `docs/spec/semantic_validator_spec.md` version 0.2.0;
- `docs/spec/tool_api.md` version 0.2.0;
- `docs/spec/metrics_protocol.md` version 0.3.0; and
- the restoration sections of Task 138's preregistration.

Those files remain historical compatibility contracts. They must not be used
to authorize a new primary causal run when they permit
`get_channel_status`-contingent restoration or call `RESTORED - BLOCKED` the
primary restoration effect.

The v2 contract is deliberately additive. It does not modify canonical
indexes, candidate registries, family-mining outputs, reviewer schemas, or any
scientific episode artifact.

## 2. Bounded causal claim

The permitted causal statement is:

> Under the frozen AV-TRACE interface, an evaluator-assigned, exogenous
> restoration of an adjudicated evidence-access route changes the supported
> answer endpoint relative to a matched sham continuation.

This is a causal claim about a controlled benchmark intervention. It is not a
claim about natural failure prevalence, real-world network or sensor failures,
universal modality necessity, every possible semantic route, or model
reasoning in general.

The evidence registry must always be described as:

> **all accepted SESs discovered under the frozen saturation protocol**

“All possible SESs,” “exhaustive SESs,” and equivalent universal language are
not permitted. A newly discovered sufficient route invalidates the affected
intervention and reopens the family; it is not treated as harmless annotation
noise.

## 3. States and assignment

Every eligible family-system assignment has four registered states:

| State | Initial access | Scheduled event | Terminal target |
|---|---|---|---|
| `CLEAN` (`C`) | At least one accepted SES reachable | none | supported answer |
| `BLOCKED` (`B`) | Registered route inaccessible | none | calibrated insufficiency/access diagnosis |
| `RESTORED` (`R`) | Byte/state-identical to blocked prefix | neutral checkpoint; hidden route restoration | supported answer |
| `NO_TRIGGER` (`N`) | Byte/state-identical to restored prefix | byte-identical neutral checkpoint; no hidden restoration | blocked continuation |

`R` and `N` are assigned before execution. Assignment is not conditional on
whether the system reaches the event, calls a particular tool, emits a
particular answer, or remains valid.

### 3.1 Frozen primary trigger

The primary schedule is `fixed_action_index` with zero-based
`action_index = 4`.

The event is delivered after exactly four completed canonical
action/response cycles and before requesting the fifth model action. The
schedule is the same for every system on the family. It is frozen before model
execution and cannot depend on:

- system identity or system class;
- selected action or tool name;
- `get_channel_status`;
- answer content, correctness, confidence, or rationale;
- hidden model state;
- wall-clock latency or provider behavior; or
- an outcome observed in another state.

An allowed future version may instead freeze a cost-budget threshold. Such a
threshold must be a numerical ledger boundary selected before runs, shared
across systems, and evaluated without reference to action identity or content.
It is not enabled by this v2 execution plan.

Every system in the primary restoration matrix must expose a staged adapter
that can pause at this canonical boundary, replay the frozen prefix, receive
the neutral event, and continue under the unchanged remaining budget. A
non-staged system is declared `STRUCTURALLY_INELIGIBLE_BEFORE_ASSIGNMENT` and
may appear only in state-endpoint tables. Structural ineligibility cannot be
decided after observing an output and is not missingness within the assigned
`R/N` population.

### 3.2 Prefix fork and sham event

For each assigned `R/N` pair:

1. run one blocked prefix under the frozen seed and decoding configuration;
2. if the prefix reaches the action-index boundary, freeze its canonical
   public transcript;
3. start two fresh, isolated continuation sessions and replay that exact
   public prefix into both;
4. inject the exact same public checkpoint event into both sessions;
5. change only evaluator-private route availability in `R`; and
6. leave the route blocked in `N`.

The public checkpoint event has the same serialized bytes, field order,
schema, cost, and latency bucket in `R` and `N`. It contains no condition
name, intervention ID, trigger status, restoration status, route identity,
answer hint, or state-specific nonce. The event is semantically neutral:

```json
{
  "event_type": "protocol_checkpoint",
  "event_version": "2.0.0",
  "message": "Scheduled protocol checkpoint completed.",
  "cost": 0.0
}
```

The `R/N` public transcript hash through and including this event must be
identical. If a policy terminates before the boundary, no post-terminal event
is delivered. Both assignments retain the same terminal prefix artifact and
remain in the intention-to-treat denominator with
`trigger_opportunity_reached=false`.

The event does not tell the system that access changed. Any post-event
discovery must occur through ordinary allowed actions.

## 4. Primary versus secondary restoration

### 4.1 Primary

The primary restoration evidence is the within-family, within-system
intention-to-treat contrast:

\[
\Delta^{A,\mathrm{ITT}}_{R-N,m,k}
=E_g\{E_f(A_{fRmk}-A_{fNmk}\mid g,k)\},
\]

where \(A\) is the common supported-answer endpoint and \(k\) is one
intervention mechanism.

Every assigned `R/N` run is retained:

- early termination before the trigger;
- failure to use a restored route;
- malformed output after the one allowed schema repair;
- timeout, provider failure, tool failure, or other typed invalidity; and
- trigger opportunity not reached.

Positive success endpoints use the existing fail-closed assignment for
invalid runs. Early termination is scored from the emitted terminal output; it
is never excluded merely because restoration was not received.

### 4.2 Secondary

Restoration caused by the policy calling `get_channel_status` is a separate
ecological condition. It is:

- `SECONDARY_PER_PROTOCOL_ACTION_CONTINGENT`;
- never substituted for the exogenous `R-N` estimate;
- never pooled with the exogenous condition;
- reported with the assigned denominator, trigger-reached denominator, and
  tool-calling denominator;
- explicitly labeled as selected on post-assignment policy behavior; and
- prohibited from supporting the primary causal wording.

Conditioning on “trigger fired” or “called `get_channel_status`” is
per-protocol/descriptive, not intention-to-treat.

## 5. Mechanisms are separate

### 5.1 Silent route withholding

`SILENT_ROUTE_WITHHOLDING` removes every member and deterministic derived leak
of one adjudicated necessity group while preserving the public API contract.
It must:

- introduce no explicit outage/error marker;
- preserve response schemas, field order, result-count policy, identifier
  format, cost, and latency bucket;
- preserve the relative order and payloads of unaffected candidates;
- backfill only from the already frozen unaffected candidate universe; and
- never add a synthetic distractor or state-specific message.

This mechanism tests adaptation to hidden evidence-route unavailability.

### 5.2 Explicit channel outage

`EXPLICIT_CHANNEL_OUTAGE` disables exactly one registered channel and returns
the frozen typed unavailable response. The response is intentionally visible.
The error code, message, cost, shape, and latency bucket must be identical in
`B`, pre-trigger `R`, and `N`, and may differ from `C` only as specified by the
outage contract.

This mechanism tests response to a known access failure. It does not test
inference of silent missingness.

### 5.3 No pooled primary number

The two mechanisms have separate co-primary `R-N` estimands, tables,
denominators, intervals, and invalid counts:

- `P1_RN_SILENT_ROUTE_WITHHOLDING_ITT`;
- `P2_RN_EXPLICIT_CHANNEL_OUTAGE_ITT`.

No average, weighted score, meta-analytic summary, or omnibus “restoration”
number across these mechanisms is a primary estimand. Any cross-mechanism
summary is exploratory, visibly labeled, and cannot replace either
mechanism-specific result.

`R-B` remains a mechanism-specific common-endpoint state contrast. It is
useful descriptively but is not the primary causal restoration effect because
`B` lacks the matched scheduled event and continuation.

## 6. State-surface invariants

Before any eligible episode is created, freeze a state-surface manifest that
classifies every policy-visible field as:

1. `INVARIANT_ALL_STATES`;
2. `INTENDED_MECHANISM_DIFFERENCE`;
3. `POST_EVENT_TREATMENT_MEDIATOR`; or
4. `FORBIDDEN_PRIVATE_FIELD`.

At minimum, the following are invariant across matched states unless the
mechanism explicitly requires otherwise:

- question and answer-facing instructions;
- tool names and tool-menu order;
- backend, index, decoder/ASR, serializer, and API versions;
- action, cost, token, and context budgets;
- request/response envelope, field order, ID format, and numeric formatting;
- result-count and pagination policy;
- unaffected result order, payload, hashes, and costs;
- latency bucketing and any padding policy;
- system prompt, model parameters, decoding settings, and seed policy; and
- checkpoint event bytes.

The following are evaluator-private and may never enter a model-visible
prompt, response, ID, path, cache key, or error:

- state role;
- assignment arm;
- intervention and necessity-group IDs;
- trigger-enabled flag;
- hidden route-availability bit;
- accepted SES labels;
- answer keys and evaluator decisions; and
- order-sequence identity.

For `R/N`, normalized public transcripts must be byte-identical through the
checkpoint. For silent withholding, non-semantic surface features must also be
balanced between `C` and `B`. For explicit outage, the standardized outage
response is an intended mechanism difference, but it must be identical across
all blocked prefixes.

## 7. Fresh-session and cache isolation

Every state and every `R/N` continuation uses:

- a new provider conversation/session ID;
- a new model KV/prefix-cache namespace, or disabled provider prompt caching;
- a state-scoped retrieval/result cache namespace;
- a state-scoped tool-response cache namespace;
- a state-scoped working directory and artifact namespace; and
- no memory, summary, hidden scratchpad, or retry transcript from another
  state.

Shared immutable model weights, immutable indexes, and read-only media bytes
are allowed. Mutable cache entries, conversation memory, generated summaries,
retrieval results, tool responses, and model KV state are not shared.

If a provider cannot prove prompt-cache isolation, each state receives a
unique non-visible transport salt that is stripped before model-visible
serialization, and the provider cache policy is recorded. A visible salt is
forbidden.

The evaluator records fresh-session attestations and cache namespace hashes.
Any collision or cross-state read is `INVALID_CROSS_STATE_CONTAMINATION`.

## 8. Randomized and counterbalanced order

Order is frozen before outcomes using four Williams sequences:

1. `C-B-N-R`
2. `B-R-C-N`
3. `R-N-B-C`
4. `N-C-R-B`

Assignment is deterministic from a preregistered seed and immutable
`source_group_id`, `family_id`, and `system_config_id`, stratified by
intervention mechanism. The four sequences are allocated as evenly as
possible within each stratum. The `R/N` continuation order within its shared
prefix fork follows the assigned sequence.

No sequence may be changed after an output, failure, or cost is observed.
Order is a diagnostic covariate and sensitivity analysis; it is not pooled
away to rescue a failed primary result.

## 9. Metadata-only leakage classifier gate

The gate is executed before scientific outcomes are unblinded. It uses only
protocol state labels and non-semantic public-surface features; it creates no
human label.

### 9.1 Allowed features

- field-presence/type signatures;
- list lengths and result counts;
- serialized byte lengths and padding lengths;
- identifier length and character-class patterns;
- numeric formatting and bucketed cost;
- typed error presence/code;
- response/event ordering;
- bucketed latency;
- token counts; and
- cache/session namespace collision indicators.

Question text, answer text, transcript/OCR/ASR content, captions, media
features, embeddings, retrieval scores, semantic result payloads, claim/SES
labels, and source identity are forbidden.

### 9.2 Frozen classifier and split

Use a fixed L2-regularized logistic regression over one-hot categorical and
standardized numeric features. No test-fold hyperparameter tuning is allowed.
Evaluation is leave-one-source-group-out; all families and states from one
source group remain in the same fold.

The primary leakage task is balanced `R` versus `N` classification using the
public transcript through and including the checkpoint. Required secondary
tasks are `B` versus pre-trigger `R`, `B` versus pre-trigger `N`, and, for
silent withholding only, `C` versus `B` using non-semantic features.

### 9.3 Gate

For every required task:

- the cross-validated balanced accuracy must not exceed the corresponding
  majority-class baseline;
- a source-group-blocked label-permutation test must have one-sided
  \(p \ge 0.05\);
- no single feature may deterministically identify the state; and
- exact `R/N` prefix-plus-event transcript hashes must match.

Any violation is `LEAKAGE_GATE_REPAIR`. A deterministic state feature,
private-field exposure, cache collision, or unresolved `R/N` transcript
mismatch is `LEAKAGE_GATE_NO_GO`. The gate cannot be waived because semantic
performance appears plausible.

The classifier is not run in this repair task. Its status remains
`NOT_RUN_BLOCKS_SCIENTIFIC_EXECUTION`.

## 10. Freeze and execution gates

Before scientific execution, all of the following must be present and valid:

1. H2 eligibility under the construct-validity process;
2. all accepted SESs discovered under the frozen saturation protocol;
3. a frozen mechanism-specific intervention manifest;
4. a frozen state-surface manifest;
5. independent route-closure and restoration-feasibility checks;
6. an `R/N` prefix-fork replay test;
7. fresh-session/cache-isolation attestations;
8. a frozen counterbalanced order assignment;
9. a passing metadata-only leakage classifier gate; and
10. an analysis manifest containing both mechanism-specific ITT estimands and
    the complete assigned denominator.

Missing evidence produces `REPAIR` or `NO_GO`; it never causes silent
exclusion or adaptive protocol change.

## 11. What this repair establishes

This repair establishes a pre-annotation design and validation target only.
It does not establish:

- that any real family is H2;
- that any route is necessary;
- that restoration is feasible for any real family;
- that the leakage gate passes;
- that any system recovers;
- that one system outperforms another; or
- that scientific execution is authorized.
