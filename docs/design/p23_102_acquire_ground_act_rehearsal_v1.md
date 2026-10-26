# P23_102 Acquire / Ground / Act rehearsal v1

**Frozen:** 2026-10-13  
**Status:** `PROSPECTIVE_DEVELOPMENT_ONLY_CONFIGURATION`  
**Configuration:** `data/rehearsal_plan/p23_102_acquire_ground_act_rehearsal_v1.json`  
**Validation:** `tooling/tests/test_p23_102_acquire_ground_act_rehearsal.py`

## 1. Decision and non-claim

This document freezes an executable **future** rehearsal contract for
machine-provisional candidate families mined from EPIC-KITCHENS
`P23_102`. It does not run a model, decode media, create a family, create a
human label, establish H2, or report a result.

The completion token at the end means only that the prospective
configuration, paths, schemas, hashes, and invariants are specified. It does
not override the current blockers:

- the exact acquisition manifest is not complete at the frozen boundary;
- the P23_102 full-timeline index has not been built;
- no P23_102 machine-provisional family/evidence/intervention registry exists;
- the restoration-v2 leakage gate has not run;
- the P23-specific exogenous-restoration adapter and runner do not yet exist;
- the existing small learned-agent stack requires a fresh competence check;
  and
- H2 has not been claimed.

Any future outputs are development diagnostics only.

## 2. Source and split boundary

The source group is the entire participant lineage `P23`. Every P23
recording, native stream, annotation, index, clip, encode, and derivative is
one source group. Candidate families from P23_102 are not source-disjoint from
one another.

The split rule is deliberately stronger than merely withholding the exact
video:

1. prompt tuning, controller tuning, calibration, and learned fusion training
   for this rehearsal must exclude all P23 material;
2. all P23_102 families are development-only and permanently ineligible for a
   future test split;
3. a future evaluation split must exclude all P23 media and derivatives; and
4. a single-source P23 rehearsal cannot support source-cluster
   generalization, benchmark-level causality, or a paper claim.

The rehearsal may run before H2 only under the label
`FUTURE_MACHINE_PROVISIONAL_ONLY`. Scientific interpretation additionally
requires H2, human-valid family/evidence review, a fresh source-disjoint
evaluation split, powered preregistration, and independent replay.

## 3. Frozen stack

The rehearsal reuses, without silently substituting components:

| Layer | Frozen implementation / artifact |
|---|---|
| Fixed backend | `src/av_trace_scale1b_agent/backend.py:FullTimelineBackend` through a future P23 adapter |
| Learned visual retrieval | SigLIP2 `google/siglip2-base-patch16-224` at revision `75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2` |
| Learned ambient retrieval | CLAP `laion/clap-htsat-unfused` at revision `8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a` |
| Speech retrieval control | frozen Whisper tiny.en observations plus deterministic BM25 |
| Grounded generator | `Qwen/Qwen2.5-1.5B-Instruct` at revision `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` |
| Learned ReAct | `react` policy and frozen `react_v1.txt` prompt |
| Sufficiency agent | `evidence_sufficiency` policy and frozen `sufficiency_v1.txt` prompt |
| Scoring | `src/av_trace_scale1b_agent/evaluation.py` plus `docs/spec/metrics_protocol_v2.md` |

The configuration pins SHA-256 values for every implementation, prompt,
schema, model-acquisition manifest, P23 plan, and restoration-v2 input used to
define the rehearsal.

### Required adapter behavior

The current `FullTimelineBackend` contains historical action-contingent
restoration behavior. The future adapter must disable that behavior in the
primary matrix and place the v2 event in the runner:

- zero-based fixed action index `4`;
- after four completed action/response cycles;
- before the fifth model decision;
- independent of action identity, system identity, output, correctness, and
  `get_channel_status`; and
- evaluator-private restoration in `R`, with no restoration in `N`.

`get_channel_status`-contingent restoration may be run only in a separately
named secondary per-protocol condition.

## 4. Arms and mechanisms

Every family/mechanism/system slot has the four arm labels:

| Arm | State | Initial access | Event / endpoint |
|---|---|---|---|
| `C` | `CLEAN` | at least one machine-provisional accepted SES reachable | no event; supported-answer target |
| `B` | `BLOCKED` | registered route inaccessible | no event; calibrated insufficiency/access diagnosis |
| `R` | `RESTORED` | blocked prefix | neutral checkpoint plus hidden restoration; supported-answer target |
| `N` | `NO_TRIGGER` | same blocked prefix | byte-identical checkpoint without restoration; blocked continuation |

The normative evidence-universe phrase is **all accepted SESs discovered under
the frozen saturation protocol**. The rehearsal must not claim all possible or
exhaustive SESs.

The mechanisms are analyzed separately:

1. `SILENT_ROUTE_WITHHOLDING` removes a registered necessity group and its
   deterministic leaks without an explicit outage marker.
2. `EXPLICIT_CHANNEL_OUTAGE` returns the frozen typed unavailable response for
   exactly one registered channel.

They have separate `R-N` ITT estimands, denominators, failure counts, and
tables. No pooled primary restoration number is permitted.

## 5. System rows

The declarative matrix expands
`candidate family × mechanism × system × arm`. If both mechanisms are
applicable, that is 32 row slots per family. Inapplicable mechanisms and
non-staged systems are frozen before assignment; synthetic outcomes are
forbidden.

### 5.1 Direct long-context

This is a non-agentic state-endpoint baseline. It receives a deterministic
chronological, modality-round-robin packing of all state-accessible citable
observations up to 24,576 input tokens, then makes one grounded-generator
call.

- It performs no retrieval action.
- Acquire and Act metrics are `null`, not zero.
- It may be reported for `C/B/R/N` endpoint tables.
- Because it cannot pause after action index 4, its `R/N` primary status is
  `STRUCTURALLY_INELIGIBLE_BEFORE_ASSIGNMENT`.

This preserves the v2 prohibition on inventing staged outcomes for a
non-staged baseline.

### 5.2 Single-shot learned RAG

The row issues one frozen copy of the question to each retrieval channel:

1. SigLIP2 visual search;
2. Whisper/BM25 speech search;
3. CLAP ambient search;
4. inspect the first pointer selected by frozen reciprocal-rank fusion.

The v2 checkpoint follows the fourth response. The row may inspect the rest of
the already selected pointers and then calls the shared grounded generator,
but it may not reformulate or issue a post-checkpoint search. This makes it a
staged, nonadaptive RAG control: restoration can help only if an already
returned pointer becomes inspectable. No expected effect is asserted.

### 5.3 Learned ReAct

The frozen ReAct prompt selects bounded search, observation, status, finalize,
and query-reformulation actions from the public action menu. It receives no
state label, intervention ID, support-set label, answer key, or restoration
notice. It may adapt through ordinary actions after the checkpoint.

### 5.4 Learned evidence-sufficiency agent

The sufficiency row shares the same model, backend, retrieval universe,
generator, tools, costs, context cap, step cap, decoding, repair policy, and
failure handling as ReAct. Its controller state additionally represents:

- covered public claim handles;
- missing modalities;
- missing hop types;
- missingness cause;
- `p_sufficient`; and
- recovery intent.

Evaluator-private evidence IDs are mapped only after a valid public output.
The configuration makes no claim that this agent outperforms ReAct.

## 6. Budgets and public tools

Agentic and RAG rows use:

- maximum 10 actions;
- cost limit 12.0;
- search cost 1.0 per modality;
- `inspect_clip` cost 2.0;
- `read_transcript` cost 1.0;
- `get_channel_status` cost 0.25;
- `finalize` cost 0.0;
- retrieval `top_k = 5`, with schema maximum 20;
- deterministic generation;
- 512 generated tokens;
- at most one 512-token repair; and
- public-history cap 12.

The same budget is used across `C/B/R/N` for a matched
family/mechanism/system.

The public tool schemas are exactly:

- `docs/spec/agent_action_schema.json`;
- `docs/spec/tool_response_schema.json`;
- `docs/spec/final_answer_schema.json`; and
- `docs/spec/trajectory_schema.json`.

Search returns non-citable pointers. Only `inspect_clip` and
`read_transcript` create citable observation IDs. Final claims must cite
acquired observation IDs; a search result ID is not a citation. The
restoration checkpoint is a runner event, not a model action or tool result.

## 7. R/N fork and intention-to-treat

For each eligible `R/N` assignment:

1. execute one blocked prefix under the frozen seed;
2. freeze the normalized public transcript after four completed cycles;
3. start fresh isolated continuation sessions;
4. replay the exact prefix into both sessions;
5. inject the exact same canonical checkpoint object into both;
6. restore the evaluator-private route only in `R`; and
7. continue with unchanged remaining budget.

If the prefix terminates before the boundary, the identical terminal prefix is
copied to both assignments. No event is injected after terminal output. Both
arms remain in the ITT denominator and their pair difference is zero.

All preregistered `R/N` assignments remain in ITT:

- early terminal;
- route not inspected;
- evidence not reacquired;
- malformed output after one repair;
- timeout, OOM, process crash, tool failure, or over-budget;
- invalid prefix/event/cache isolation; and
- event opportunity not reached.

Positive success endpoints are zero for invalid assigned runs. Structural
ineligibility is different: it is frozen before assignment and receives no
synthetic outcome.

## 8. Acquire / Ground / Act metrics

### Acquire

Primary:

- Evidence Recall;
- All-Evidence Success.

Secondary diagnostics include retrieval recall@5, candidate-modality routing
coverage, and complete SES reacquisition. Direct long-context has these
metrics `null`.

### Ground

Primary:

- Answer Score;
- Citation F1;
- Supported-Claim Rate.

The common causal endpoint, `supported_answer_endpoint`, additionally
requires an in-budget answer with all required claims correct and supported by
acquired citations instantiating a machine-provisional accepted support
derivation.

### Act

Primary:

- Success@Budget;
- Premature Stop;
- Recovery.

Secondary diagnostics include false sufficiency, calibrated refusal, access
diagnosis, restored-route inspection, and post-event cost. Act is `null` for a
non-staged trajectory.

All metrics retain the warning
`LOW_N_MACHINE_PROVISIONAL_P23_102_DEVELOPMENT_REHEARSAL`.

## 9. Primary and no-trigger estimands

The two co-primary development estimands are:

- `P1_RN_SILENT_ROUTE_WITHHOLDING_ITT`;
- `P2_RN_EXPLICIT_CHANNEL_OUTAGE_ITT`.

Each is the assigned within-family `RESTORED - NO_TRIGGER` difference in the
supported-answer endpoint among systems declared staged before assignment.
Mechanisms are never pooled for a primary result. `R-B` is only a
mechanism-specific state contrast.

Required no-trigger diagnostics are:

- `N_FALSE_RECOVERY_RATE`: supported answer while the registered route remains
  blocked;
- `RN_PREFIX_INTEGRITY_RATE`: byte-identical public prefix and checkpoint; and
- `RN_REACQUISITION_DIFFERENCE`: complete SES reacquired in `R` minus `N`.

Reports must retain assigned, structurally ineligible, early-terminal,
event-reached, restoration-applied, route-inspected, complete-SES-reacquired,
valid, invalid, and supported-answer denominators.

## 10. Raw outputs

The future run root is:

```text
data/restricted/p23_102_acquire_ground_act_rehearsal_v1/runs/{run_id}
```

It must contain, at minimum:

- `run_manifest.json`;
- `assignments.jsonl`;
- `raw_trajectories.jsonl`;
- `raw_model_calls.jsonl`;
- `citation_outputs.jsonl`;
- `r_n_prefix_pairs.jsonl`;
- `episode_metrics.jsonl`;
- `failure_ledger.jsonl`;
- `aggregate_metrics.json`;
- `replay_manifest.json`; and
- `file_inventory.json`.

Raw trajectories preserve public belief states, action/response envelopes,
costs, neutral checkpoints, terminal outputs, replay hashes, and evaluator
metadata. Citation output preserves claim handles, assertion text, observation
IDs, intervals, modalities, payload hashes, schema validity, and
evaluator-private post-mapping. Hidden chain-of-thought is neither requested
nor an output requirement.

Writes are restricted (`0700` directories, `0600` files), atomic, hashed, and
non-overwriting after run completion.

## 11. Failure handling

Every row has exactly one terminal or exclusion status. Important classes are:

- preassignment: `STRUCTURALLY_INELIGIBLE_BEFORE_ASSIGNMENT`,
  `INAPPLICABLE_MECHANISM_BEFORE_ASSIGNMENT`;
- missing inputs: `SOURCE_NOT_READY`, `INDEX_NOT_READY`,
  `FAMILY_REGISTRY_NOT_READY`, `INTERVENTION_NOT_READY`,
  `LEAKAGE_GATE_NOT_RUN`;
- invalid protocol: `INVALID_RN_PREFIX_MISMATCH`,
  `INVALID_CHECKPOINT_EVENT_MISMATCH`,
  `INVALID_CROSS_STATE_CONTAMINATION`,
  `INVALID_RESTORATION_SCHEDULE`, `PRIVATE_FIELD_EXPOSURE`;
- learned/runtime: `MALFORMED_AFTER_REPAIR`, `MODEL_TIMEOUT`, `MODEL_OOM`,
  `MODEL_PROCESS_CRASH`, `TOOL_TIMEOUT`, `TOOL_RATE_LIMITED`,
  `TOOL_ACCESS_FAILURE`, `OVER_BUDGET_STEPS`, `OVER_BUDGET_COST`,
  `NO_FINALIZATION_WITHIN_STEP_LIMIT`; and
- replay: `BACKEND_HASH_MISMATCH`, `MODEL_SNAPSHOT_MISMATCH`,
  `NONDETERMINISTIC_REPLAY`, `MISSING_CITATION_OUTPUT`.

Failures are visible in the ledger and are never silently converted to a
deterministic answer.

## 12. Exact future prerequisites

The JSON configuration contains the complete path list. The critical missing
future artifacts are:

```text
data/restricted/epic_p23_102_source_v1/manifests/epic_p23_102_exact_manifest.json
data/restricted/epic_p23_102_source_v1/media/P23/P23_102.MP4
data/restricted/epic_p23_102_full_timeline_index_v1/build_manifest.json
data/restricted/epic_p23_102_full_timeline_index_v1/full_timeline_index.json
data/restricted/epic_p23_102_full_timeline_index_v1/observation_manifest.json
data/restricted/epic_p23_102_machine_provisional_families_v1/family_registry.json
data/restricted/epic_p23_102_machine_provisional_families_v1/evidence_registry.json
data/restricted/epic_p23_102_machine_provisional_families_v1/intervention_manifest.json
data/restricted/epic_p23_102_machine_provisional_families_v1/state_surface_manifest.json
data/restricted/epic_p23_102_machine_provisional_families_v1/source_split_manifest.json
data/restricted/epic_p23_102_machine_provisional_families_v1/leakage_gate.json
data/restricted/p23_102_acquire_ground_act_rehearsal_v1/adapter_attestation.json
scripts/run_p23_102_acquire_ground_act_rehearsal.py
```

The future runner command is preregistered but must fail closed until the
runner exists and every development prerequisite passes:

```bash
PYTHONPATH=src python scripts/run_p23_102_acquire_ground_act_rehearsal.py \
  --config data/rehearsal_plan/p23_102_acquire_ground_act_rehearsal_v1.json \
  --mode development-rehearsal
```

Schema and invariant validation is safe now and must not load a model, open
media, or access the network:

```bash
python -m pytest -q \
  tooling/tests/test_p23_102_acquire_ground_act_rehearsal.py
```

## 13. Determinism

The configuration freezes:

- SHA-256 for all existing inputs;
- SHA-256 for the four public schemas;
- canonical SHA-256 for the checkpoint event;
- canonical SHA-256 for the input bundle;
- canonical SHA-256 for the schema bundle;
- canonical SHA-256 for the matrix;
- a self-hash computed with only its own value removed; and
- deterministic counterbalancing seed `2310220261013`.

The test recomputes each value from canonical UTF-8 JSON and verifies every
pinned existing file. No model or media code is imported or executed.

`P23_102_ACQUIRE_GROUND_ACT_REHEARSAL_READY`
