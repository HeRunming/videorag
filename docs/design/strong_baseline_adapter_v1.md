# AV-TRACE strong-baseline adapter v1

**Date:** 2026-09-24  
**Implementation status:** `STRONG_BASELINE_ADAPTER_READY`  
**Scientific execution status:** `NOT_AUTHORIZED`  
**Scope:** model-agnostic interfaces, dry fixtures, and offline competence
evaluation only

## 1. Purpose and precedence

This design implements the adapter layer requested by Task 148 and frozen by
Task 149. It follows:

- the Task 138 common system and budget contract;
- the Task 145 exogenous restoration protocol v2;
- the exact model selections and competence floors in Task 148; and
- the Task 149 prohibition on scientific execution, outcome-conditioned
  fallback mixing, deterministic answer substitution, and evaluator-private
  assistance.

The implementation lives under `src/av_trace_strong_baselines/`. It does not
modify canonical indexes, candidate registries, source tools, restricted
evaluation data, or historical baseline outputs. It does not download model
weights and contains no real model invocation path.

The implementation-ready token means the adapter and dry validation layer is
ready for later governed model integration. It does **not** mean that a model
is acquired, loadable, competent, or authorized for scientific evaluation.

## 2. Package map

| Module | Responsibility |
|---|---|
| `contracts.py` | Exact model bindings, common budgets, canonical tool costs, action/model-call ledger, load/inference status vocabulary |
| `schemas.py` | Strict JSON parsing, canonical action-schema validation, six-field evidence-state validation, final-answer/citation validation |
| `security.py` | Evaluator-private field rejection, private-ID rejection, observed-evidence lock, output-authorship checks, cache/session isolation |
| `runtime.py` | Framework-neutral model-driver protocol, pre-call identity gate, typed fail-closed outcomes, schema-only repair request |
| `adapters.py` | Direct A/V, single-shot RAG, same-backbone ReAct, same-backbone sufficiency, shared finalizer, oracle/partial bundle adapters |
| `restoration.py` | Task 145 four-cycle blocked-prefix freeze and fresh RESTORED/NO_TRIGGER fork |
| `comparator.py` | TRACE-style convergence adapter with mandatory non-reproduction disclosure |
| `deterministic.py` | Independent deterministic control action policies; no learned-run answer replacement |
| `fixtures.py` | Complete dry adapter matrix for every requested Task 148 row |
| `competence.py` | Deterministic fictional-suite generator and offline recorded-output evaluator |

## 3. Frozen common contract

`CommonBudget` rejects any configuration that changes the Task 138/148
primary contract:

- 10 canonical actions, including `finalize`;
- cost limit 12.0;
- search `top_k=5`;
- 32,768 processor-token context cap;
- 512 generated tokens per decision or finalization;
- at most 12 model calls including one schema-only repair;
- zero semantic repairs;
- `best_of_n=1`; and
- canonical tool costs:
  - search visual/speech/ambient: 1.0;
  - inspect clip: 2.0;
  - read transcript: 1.0;
  - channel status: 0.25;
  - finalize: 0.0.

`BudgetLedger` charges the same action and cost budget across adapters. It
rejects post-finalization actions, action/cost overruns, a changed search
depth, a second repair, and excess model calls.

The canonical tool surface is exactly:

1. `search_visual`;
2. `search_speech`;
3. `search_ambient_audio`;
4. `inspect_clip`;
5. `read_transcript`;
6. `get_channel_status`; and
7. `finalize`.

`validate_tool_action` validates the per-call tool objects. When an execution
runner needs a full protocol envelope, `build_canonical_agent_action` performs
a lossless wrap and validates it against
`docs/spec/agent_action_schema.json`. It refuses to infer a canonical belief
state from the six-field diagnostic state. A canonical belief state and final
answer must remain model-authored.

## 4. Exact model revision binding and fail-closed runtime

`ModelBinding` requires a 40-character immutable Git revision for the model,
processor, and tokenizer. The frozen primary bindings are:

| Role | Exact binding |
|---|---|
| Direct A/V | `Qwen/Qwen2.5-Omni-7B@ae9e1690543ffd5c0221dc27f79834d0294cba00` |
| Controller | `ibm-granite/granite-3.3-8b-instruct@51dd4bc2ade4059a6bd87649d68aa11e4fb2529b` |
| Finalizer | the same exact Granite snapshot, processor, and tokenizer |

The fallback bindings are Phi-4 multimodal at
`93f923e1a7727d1c4f446756212d9d3e8fcc5d81` and Qwen3-8B at
`b968826d9c46dd6066d109eabc6255188de91218`. Selecting them still requires the
Task 149 pre-sealed-suite amendment.

Before every call, `invoke_fail_closed` checks the observed binding and
`LoadStatus.LOADED_VERIFIED`. A mismatch returns
`SNAPSHOT_MISMATCH`; an absent or unverified load returns
`LOAD_NOT_VERIFIED`; neither condition calls the driver. Timeout, OOM,
provider/process failure, and invalid output retain typed status and no answer.

`DryModelDriver` raises if called. It exists to prove that planning, suite
generation, and tests do not silently perform inference.

One repair may be built only with `build_schema_only_repair_request`. The
accepted error allowlist contains serialization/schema failures. A semantic
error such as a wrong action, unsupported claim, or incorrect answer raises
`SEMANTIC_REPAIR_FORBIDDEN`.

## 5. Adapter interfaces

### 5.1 Direct A/V

`DirectAVAdapter` prepares one non-agent finalization request from a frozen
media exposure manifest. It enforces:

- source-ordinal then chronological ordering;
- question-independent packing;
- explicit modalities and intervals;
- the common context and output caps; and
- a disclosed distinction between strict native A/V and packed-frame A/V.

The adapter is not staged for the Task 145 primary R/N causal estimand and is
therefore marked `STRUCTURALLY_INELIGIBLE_BEFORE_ASSIGNMENT` in the dry matrix.
It remains eligible for state-endpoint tables.

Direct citations are restricted to `exposure_id` values in the exact media
manifest passed to the model. A citation to a dropped, future, or unexposed
item is invalid.

### 5.2 Single-shot RAG

`SingleShotRAGAdapter` creates exactly one frozen question-derived search for
each of vision, speech, and ambient audio at `top_k=5`. It provides:

- fixed, equal-weight reciprocal-rank fusion with `rrf_k=60`;
- deterministic pointer tie-breaking;
- inspect/read acquisition charged against the common budget;
- rejection of pointer citations because search pointers are non-citable;
- reservation of an action for `finalize`; and
- one shared grounded finalizer call.

The adapter has no adaptive second search. If used in the Task 145 primary
matrix, its retrieval/acquisition execution must expose the generic
four-completed-cycle pause and continuation interface.

### 5.3 Same-backbone ReAct

`SameBackboneReActAdapter` presents a public action menu, current observed
evidence, recent public history, and remaining common budget. It parses only:

```json
{
  "evidence_state": {
    "p_sufficient": 0.0,
    "covered_claim_handles": [],
    "missing_modalities": ["vision"],
    "missing_hops": ["event_detection"],
    "missingness_cause": "evidence_accessible_but_not_found",
    "recovery_intent": "search_vision"
  },
  "action_index": 0
}
```

The action is selected by index from a case-local validated menu. The adapter
does not infer a missing action, rewrite a query, or use the diagnostic state
to author an answer.

### 5.4 Same-backbone evidence sufficiency

`SameBackboneEvidenceSufficiencyAdapter` uses the same implementation,
binding, tool universe, observations, budget, parsing, and finalizer as ReAct.
Its only designed difference is `policy="evidence_sufficiency"`. Constructor
validation rejects a different controller/finalizer repository, model
revision, processor revision, or tokenizer revision.

### 5.5 Shared grounded finalizer

`SharedGroundedFinalizer` is used by RAG, ReAct, sufficiency, oracle, partial,
and the TRACE-style comparator. The final output envelope contains:

- `final_answer`, validated against
  `docs/spec/final_answer_schema.json`; and
- a redundant `claim_to_citations` mapping that must exactly equal the
  citations in each claim.

All answer-bearing fields must be attested as model-authored. The adapter may
copy validated IDs into storage but cannot write answer text, claims,
diagnosis, verdict, or answer mode. Deterministic authorship of any
answer-bearing path is `DETERMINISTIC_ANSWER_SUBSTITUTION`.

### 5.6 Oracle and partial evidence

`EvidenceBundleAdapter` creates generator-only diagnostics:

- `ORACLE_EVIDENCE` requires declared coverage of every public claim handle;
- `PARTIAL_EVIDENCE` requires a strict proper subset.

The model sees only the public observations. It does not see the selection
rationale, accepted-support mapping, removed item, answer key, or evaluator
label.

### 5.7 TRACE-style comparator

`TraceStyleAdaptation` implements a visual-subset, growing-evidence,
consecutive-answer-convergence interface with a final verification pass over
the same evidence. The exact required label is:

> AV-TRACE TRACE-style adaptation; not an official TRACE reproduction

Changing or omitting this label is rejected. Candidate answers are hashed for
convergence; the adapter does not merge, vote over, repair, or author them.

### 5.8 Deterministic controls

`DET-REACT` and `DET-SUFF` are separate control systems. They can select a
public action from a frozen menu. Their output type cannot contain a final
answer, and `reject_learned_substitution` prevents use of a control result as
the result for a learned system.

`NO-TRIGGER` is the sham continuation generated by the staged R/N fork. It is
not an answer fallback.

## 6. Six-field state and canonical final answer

The exact six diagnostic fields are:

1. `p_sufficient`;
2. `covered_claim_handles`;
3. `missing_modalities`;
4. `missing_hops`;
5. `missingness_cause`; and
6. `recovery_intent`.

Validation follows the controller-v2 canonical ordering and controlled
vocabularies. There is no missing-field fill, probability coercion, enum
fallback, array sorting, or cross-field semantic repair.

The six-field state is intentionally separate from the richer canonical
`belief_state` in `agent_action_schema.json`. A runner may pass a separately
model-authored canonical belief state to the canonical action envelope, but it
may not deterministically translate the six fields into answer-bearing model
output.

The final-answer validator additionally enforces:

- only public claim handles;
- all required handles for `answer` mode;
- no answer content for `abstain`;
- exact observed observation ID, interval, and modality;
- no pointer, unknown, future, or out-of-exposure citation; and
- exact redundant citation-map agreement.

Semantic claim support is evaluated separately against the fictional scoring
target. Schema validity never stands in for support.

## 7. Public-surface and observed-evidence lock

`assert_public_surface` recursively rejects evaluator-private field names,
including:

- state/assignment arm;
- intervention or necessity-group ID;
- trigger or hidden route bit;
- accepted-SES labels;
- answer/evaluator keys;
- private support maps; and
- expected answers.

It also rejects known private identifier forms used by historical AV-TRACE
artifacts. This is a defense-in-depth check, not a claim that string filtering
alone proves absence of leakage.

`ObservedEvidenceLock` creates an immutable allowlist and fingerprint from the
current trajectory. Citations must match an observed ID and its exact interval
and modalities. Search pointers are not observations and cannot be cited.

## 8. Task 145 staged exogenous event

`FrozenBlockedPrefix.freeze` accepts exactly four completed canonical
action/response cycles and a ledger at exactly four actions. It refuses a
terminal prefix at that boundary.

`fork_restored_no_trigger` then:

1. checks fresh provider, model-cache, retrieval-cache, tool-cache, artifact,
   and generated-memory namespaces;
2. replays the same blocked public prefix;
3. appends the exact neutral checkpoint:

   ```json
   {
     "event_type": "protocol_checkpoint",
     "event_version": "2.0.0",
     "message": "Scheduled protocol checkpoint completed.",
     "cost": 0.0
   }
   ```

4. preserves the same remaining budget;
5. verifies identical public transcript hashes through the event; and
6. changes only the private route-availability value.

The arm and route-availability values are excluded from
`model_visible_payload`. A cache/session collision raises
`INVALID_CROSS_STATE_CONTAMINATION`.

An early terminal run has no post-terminal event and must be handled by the
execution coordinator as the same copied terminal prefix in both assigned
arms, consistent with Task 145 intention-to-treat semantics. The adapter does
not synthesize an outcome for such a run.

## 9. Fictional competence suite

The checked-in suite is:

`data/rehearsal_plan/strong_baseline_competence_suite_v1.json`

It is regenerated by:

```bash
python scripts/generate_strong_baseline_competence_suite.py --repo-root .
```

and checked without rewriting by:

```bash
python scripts/generate_strong_baseline_competence_suite.py \
  --repo-root . --check
```

The suite contains:

- 51 entries in the controller/finalizer group:
  - 24 controller cases;
  - 16 finalizer cases;
  - 11 fail-closed runtime fixtures;
- 30 entries in the direct-A/V group:
  - 24 complete or masked direct A/V cases;
  - 6 processor/identity/provider failure fixtures.

All semantic content is newly fictional and generated from small public
primitives: abstract colors, shapes, codes, tones, and synthetic event
descriptions. No scientific source, scientific family, restricted evaluator
key, real answer, model output, or human label is present.

The checked-in suite intentionally contains fictional `scoring_target`
objects so that the evaluator is reproducible and public. `model_public_case`
returns only `case_type` and `public_input`; it never exposes the scoring
target or case identifier to a model.

### 9.1 Frozen controller/finalizer gates

These are copied without weakening from Task 148:

- at least 48 cases;
- 100% deterministic parser/schema/failure fixtures;
- at least 90% valid structured outputs;
- at least 85% correct first actions overall;
- at least 75% correct first actions in every frozen stratum;
- at least 75% exact six-field state;
- at least 80% for every state component;
- at least 80% supported answers on oracle-complete evidence;
- at least 80% correct blocked/partial abstention;
- at least 80% restoration/reacquisition;
- zero unsupported required claims;
- zero private-field exposures;
- zero deterministic answer substitutions;
- 100% fail-closed identity/injected-failure behavior; and
- zero cross-state isolation failures.

### 9.2 Frozen direct-A/V gates

- at least 24 cases;
- 100% processor/input-manifest and injected-failure fixtures;
- at least 90% valid strict final outputs;
- at least 80% complete-evidence supported answers;
- at least 75% in every modality stratum;
- at least 80% partial/masked abstention;
- zero unsupported required claims;
- zero out-of-exposure citations;
- 100% observed-evidence lock;
- 100% required-modality-drop behavior; and
- 100% byte-identical parsed output on deterministic replay pairs.

### 9.3 Offline evaluation

The evaluator accepts only already-recorded results:

```bash
python scripts/evaluate_strong_baseline_competence.py \
  recorded_submission.json --repo-root .
```

It requires:

- the exact suite hash;
- the complete case set;
- `LOADED_VERIFIED`;
- the exact frozen model/processor/tokenizer binding;
- explicit output provenance;
- typed no-answer failure records; and
- R/N prefix-hash and mutable-namespace isolation attestations for the
  controller/finalizer group.

The evaluator never imports a model runtime or invokes a model.

## 10. Negative guarantees and tests

Focused tests cover:

- evaluator-private field and private-ID leakage;
- semantic repair/fallback attempts;
- malformed output;
- deterministic answer substitution;
- unknown, future, or interval-mismatched citations;
- cross-state cache collisions;
- wrong model snapshots and unverified loads;
- Task 145 wrong trigger boundary;
- nonchronological direct packing;
- same-backbone snapshot mixing;
- altered suite thresholds/hash;
- unsupported claims;
- the exact stored suite versus its generator;
- perfect synthetic recorded submissions through the evaluator; and
- deterministic RRF, replay, and dry controls.

## 11. Boundaries and next gate

Implemented:

- adapter interfaces: yes;
- dry fixture matrix: yes;
- source-free public competence suite: yes;
- offline evaluator: yes;
- focused tests and lint: yes.

Not performed or established:

- weight acquisition: no;
- model loading: no;
- model inference: no;
- paid API call: no;
- competence passage by any real model: no;
- Task 145 metadata leakage gate: not run;
- H2 evidence availability: zero remains controlling;
- scientific evaluation authorization: no.

The next action is a separately authorized acquisition/load integration,
followed by sealed fictional competence execution. No scientific episode may
run before the independent construct, split, causal-isolation, and leakage
gates pass.

**Final implementation token:** `STRONG_BASELINE_ADAPTER_READY`
