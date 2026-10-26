# External gateway public competence suite v1

**Date:** 2026-10-12  
**Status:** prospectively frozen; not run  
**Terminal state:** `EXTERNAL_GATEWAY_PUBLIC_COMPETENCE_SUITE_FROZEN_NOT_RUN`  
**Scientific or restricted execution:** not authorized

## 1. Purpose

This suite is a prospective public, source-free, fictional competence
sensitivity for an external strong controller/finalizer. It is intended for
the same Gate C purpose as the v2 Granite and Qwen controller/finalizer
holdouts: determine whether a candidate can reliably select actions, represent
evidence state, abstain when blocked, recover after route restoration, and
produce grounded final answers with exact citations.

The freeze does **not** execute a model or gateway. It does not authorize a
run, establish competence, or authorize scientific, real-source, restricted,
H1/H2, or SES evaluation.

The implementation is
`tools/external_gateway_public_competence_suite.py`. The frozen artifact is
`data/rehearsal_plan/external_gateway_public_competence_suite_v1.json`.

## 2. Compatibility with factorized v2 semantics

The evaluator reuses the existing v2 parsers and projections without semantic
repair:

- controller factors: `action_choice` and the exact six-field
  `evidence_state`;
- finalizer factors: `disposition`, `answer_text`, `claim_drafts`,
  `citation_selections`, and `diagnosis`;
- one initial response and at most one schema-only retry per factor;
- no semantic retry, cross-factor retry, voting, best-of-N, or deterministic
  answer substitution;
- controller state projection may accept or reject but may not fill fields;
- finalizer assembly may mechanically copy citation interval/modality metadata
  from selected public observations but may not write semantic content; and
- malformed, missing, inconsistent, or incomplete submissions fail closed.

The suite binds to adapter schema
`av-trace.granite-native-adapter/2.0`. This is a semantics/interface binding,
not a Granite model binding.

## 3. Public/private boundary

Each model-facing packet explicitly declares:

- `public_fictional=true`;
- `source_free=true`;
- `prospective_unseen=true`; and
- a notice that the packet is wholly fictional, synthetic, source-free, and
  contains no real source material or media.

The only authorized prompt projection is
`public_suite.packets`, returned by `public_packet_projection()`. Evaluator
labels remain under `evaluator_private` and are never included in that
projection.

Leakage guards recursively reject:

- evaluator targets, expected action/state values, answer terms, accepted
  citations, scoring targets, and the private canary;
- H1, H2, SES terminology;
- known real-source family names;
- scientific/restricted source or trigger language;
- `http:`, `https:`, `file:`, and `data:` URIs; and
- common audio, image, and video file suffixes.

All observations are short fictional text records. There are no media bytes,
paths, source identifiers, transcripts copied from sources, or externally
resolvable references.

## 4. Balanced case design

The freeze contains 40 substantive packets.

### Controller: 24 cases

There are three cases in each of eight strata:

1. `route_vision`
2. `route_speech`
3. `route_ambient`
4. `blocked_status`
5. `restoration_recovery`
6. `finalize_ready`
7. `premature_stop_guard`
8. `no_route_abstain`

These jointly probe exact action choice, every evidence-state field, blocked
route diagnosis, restoration/recovery, supported stopping, continuation when
a useful route remains, and safe abstention when no route exists.

### Finalizer: 16 cases

There are four cases in each of four strata:

1. `supported_single`
2. `supported_dual`
3. `restored_support`
4. `blocked_abstention`

These probe supported answer text, one- and two-claim grounding, exact
claim-to-observation citation selection, post-restoration finalization, and
empty-content abstention with the correct missing modality and hop.

The combined restoration denominator is seven cases: three controller
recovery cases and four finalizer cases with recovered public observations.
The premature-stop denominator is three controller cases whose menu contains
both `finalize` and a useful acquisition action.

## 5. Genuine non-overlap

At freeze time, each candidate packet is compared against:

- `granite_adapter_v2_holdout_public.json`;
- `qwen3_adapter_v2_holdout_public.json`; and
- both external-gateway development smoke fixtures.

The deterministic audit requires all of the following to be empty for every
comparator:

- case-ID overlap;
- normalized full-question overlap; and
- complete `public_input` canonical-hash overlap.

The committed overlap audit is `PASS`. Reference file SHA-256 values are
recorded in the freeze manifest so later validation fails if the compared
reference artifacts drift.

## 6. Prospective thresholds

The frozen Gate C thresholds are:

| Metric | Threshold |
|---|---:|
| Complete case set | required |
| Minimum cases | 40 |
| Valid structured model calls | at least 95% |
| Correct first actions overall | at least 87.5% |
| Correct first actions in each controller stratum | at least 2/3 |
| Exact six-field evidence state | at least 80% |
| Each evidence-state component | at least 87.5% |
| Blocked finalizer abstention | at least 75% |
| Restoration/recovery | at least 6/7 |
| Supported finalization | at least 10/12 |
| Exact citation selection | at least 11/12 |
| Premature-stop prevention | 100% |
| Unsupported required claims | 0 |
| Unobserved citation selections | 0 |
| Private-label exposures | 0 |
| Deterministic answer substitutions | 0 |

Malformed or absent metric structures fail their checks rather than receiving
defaults.

Decision mechanics:

- **GO:** every integrity and competence check passes.
- **REPAIR:** all integrity checks pass and exactly one competence check fails.
- **NO_GO:** any integrity check fails, or two or more competence checks fail.

Integrity checks include the full case set, minimum count, zero unsupported
claims, zero unobserved citations, zero private-label exposure, and zero
deterministic answer substitution.

## 7. Deterministic freeze and manifest

Generation uses fixed literals and no randomness, timestamps, UUIDs, model
calls, network calls, or environment-dependent ordering. Canonical SHA-256
values cover:

- every public packet;
- the complete public suite;
- evaluator-private labels;
- prompt policy;
- thresholds;
- overlap audit; and
- the complete freeze payload excluding its manifest.

`validate_frozen_artifact()` rebuilds the artifact and requires exact equality
with the committed JSON. It also rechecks prompt privacy, case balance,
one-shot state, non-overlap, packet hashes, component hashes, reference-file
hashes, and the complete payload hash.

## 8. One-shot governance

The initial state is:

```text
state=NOT_RUN
gateway_calls=0
model_outputs_present=false
partial_runs=0
full_suite_runs=0
maximum_full_suite_runs=1
execution_authorized_by_freeze=false
```

A separate explicit execution authorization is required. This tool exposes no
gateway runner or model command, and the freeze operation cannot consume the
one allowed run. After any model output exists, reruns are forbidden by the
frozen policy.

## 9. Commands

Rebuild the deterministic artifact without executing a gateway:

```text
PYTHONPATH=src python tools/external_gateway_public_competence_suite.py \
  --write-freeze
```

Validate the committed freeze and deterministic rebuild:

```text
PYTHONPATH=src python tools/external_gateway_public_competence_suite.py \
  --validate-freeze
```

Print only the prompt-authorized public packet projection:

```text
PYTHONPATH=src python tools/external_gateway_public_competence_suite.py \
  --print-public-packets
```

The evaluator can later replay a separately produced, complete, sealed
submission:

```text
PYTHONPATH=src python tools/external_gateway_public_competence_suite.py \
  --evaluate-submission <submission.json>
```

Evaluation performs no inference and makes no gateway call.

## 10. Freeze outcome

No gateway or model was executed while designing, generating, testing, or
freezing this suite. The terminal freeze token is:

`EXTERNAL_GATEWAY_PUBLIC_COMPETENCE_SUITE_FROZEN_NOT_RUN`
