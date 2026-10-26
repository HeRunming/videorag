# Qwen3 adapter-v2 unseen holdout evaluation

**Task:** 185  
**Date:** 2026-10-08 (Asia/Shanghai)  
**Decision:** `QWEN3_ADAPTER_V2_HOLDOUT_NO_GO`  
**Gate C:** not passed  
**Scientific execution:** not authorized and not performed

## Executive decision

The one and only Task-182-authorized execution of the frozen Qwen3
adapter-v2 fictional holdout completed all 51 cases and was sealed before the
private evaluator was opened. The exact acquired Qwen3-8B snapshot ran the 24
controller and 16 finalizer cases; the remaining 11 cases were frozen
fail-closed runtime fixtures. The independent audit authenticated the sealed
inputs, verified all retained raw-attempt hashes, and used the one allowed
deterministic evaluator replay. The replay reproduced the decision, metrics,
gate checks, and case scores byte-identically after excluding the evaluation
timestamp.

The result is `QWEN3_ADAPTER_V2_HOLDOUT_NO_GO`. Qwen3 performed strongly on
the supported finalizer path: 15/16 canonical envelopes were valid, all five
finalizer factors were individually schema-valid in 16/16 cases, and 7/8
oracle-complete cases passed supported-answer scoring. It did not establish
controller competence, exact evidence-state competence, blocked-partial
diagnosis, the overall structured-output floor, or restoration competence.
Multiple independent frozen Gate C floors therefore fail.

The suite is consumed. It may not be rerun, and these outputs may not be used
to tune and rerun this holdout. Gate C and scientific execution remain
unauthorized.

## Frozen identity and one-run authorization

Preflight reverified the Task-182 independent freeze audit, governance seal,
public/private suite hashes, prompt-policy semantic hash, frozen
implementation hashes, acquisition evidence, and exact local snapshot before
model loading.

- Suite ID: `qwen3-v2-fictional-holdout-20261008`
- Freeze label: `QWEN3_ADAPTER_V2_HOLDOUT_2026-10-08`
- Public suite SHA-256:
  `b8e7529ff620522c0de45d22988cf0d5c706cfc70123332943d3090e0bf66696`
- Private key SHA-256, verified without loading before execution:
  `0bf2ea7996c64f75601758e5d48169b5a847b3a764a1b5b780167d1c3b2a31cc`
- Governance freeze seal SHA-256:
  `87a831a2fea63b6876ce98fd914b18f026eff842c1b2be58cc9e9cd102e55873`
- Model: `Qwen/Qwen3-8B`
- Revision, tokenizer revision, and processor revision:
  `b968826d9c46dd6066d109eabc6255188de91218`
- Snapshot:
  `data/restricted/strong_baselines/models/Qwen--Qwen3-8B--b968826d9c46`
- Adapter schema: `av-trace.granite-native-adapter/2.0`
- Adapter profile: `qwen3-native-transport-factorized-v2`

Before execution, the run directory did not exist and no matching run process
was active. The authorization claim was written before model loading. No
restart or rerun occurred.

The sealed run identifier is:

`task184-2026-10-08T06:21:00Z-dca250a593fe`

This is a harness/provenance identifier, not evidence of another model run.
During the long-running execution, a concurrent repository worker replaced
the unsealed local wrapper with the same Qwen-specific harness labeled Task
184. The already-running process sealed that identifier. Task 185 preserved
the sealed bytes and obeyed the no-restart policy rather than rewriting or
rerunning them. The suite ID, freeze label, exact model binding, frozen
adapter/transport hashes, prompts, cases, thresholds, and one-run claim are
the Task-182-authorized values.

## Governed execution

The run enforced:

- CPU-only bfloat16 inference;
- 8 PyTorch threads and 1 inter-op thread;
- `local_files_only=true`;
- `trust_remote_code=false`;
- `enable_thinking=false`;
- greedy single-output generation;
- Qwen chat-template native tool calls for action selection;
- 512 maximum new tokens per factor and a 32,768-token context cap;
- disabled network/proxy/token environment plus an in-process network-denial
  guard;
- zero network attempts;
- no GPU and no external or paid API;
- no scientific family, key, real source, or scientific source content;
- one independent action factor and six-field state factor per controller
  case;
- five independent finalizer factors: disposition, answer text, claim
  drafts, citation selections, and diagnosis;
- at most one schema-only retry per factor;
- zero semantic repair, cross-factor retry, argument stripping, field
  filling, answer/citation substitution, voting, or best-of-N; and
- exact retention and SHA-256 recording of every raw response and adapter
  input.

Runtime:

- Python 3.13.11;
- PyTorch 2.10.0;
- Transformers 5.2.0;
- `Qwen3ForCausalLM` and `Qwen2Tokenizer`;
- elapsed child-process time: 5,493.12 seconds;
- peak RSS: 19,559,424 KiB;
- 140 substantive model attempts;
- 12 schema-only retries, all on action factors;
- 14 injected runtime-fixture records; and
- 154 total retained attempt records.

## Seal before evaluator

The execution phase sealed the authorization claim, preflight report,
submission, raw attempts, run metadata, and runner manifest before private
evaluation.

- Run seal:
  `data/restricted/strong_baselines/qwen3_v2_holdout_run/seal.json`
- Run seal SHA-256:
  `d2a3fa3accab1bdf9d5fbaa722fdea69e2b34c57fbba091660aba6802ddd92e7`
- Seal state: `SEALED_BEFORE_PRIVATE_EVALUATION`

After that seal was verified, the evaluator loaded the private labels and
applied the exact frozen thresholds. The evaluation report and independent
component audit were then sealed in:

`data/restricted/strong_baselines/qwen3_v2_holdout_run/evaluation_seal.json`

## Frozen Gate C metrics

| Metric | Floor | Observed | Gate |
|---|---:|---:|---|
| Total sealed cases | >=48 | 51 | pass |
| Parser/schema and injected failures | 100% | 11/11 = 100% | pass |
| Valid structured substantive calls | >=90% | 15/40 = 37.5% | fail |
| Correct first actions overall | >=85% | 11/24 = 45.8% | fail |
| Correct actions in every stratum | >=75% | 0%–100%; six of eight strata below floor | fail |
| Exact six-field state | >=75% | 0/24 = 0% | fail |
| Every state head | >=80% | 12.5%–70.8% | fail |
| Oracle supported answer | >=80% | 7/8 = 87.5% | pass |
| Blocked-partial correct abstention | >=80% | 0/4 = 0% | fail |
| Restoration reacquisition | >=80% | 5/7 = 71.4% | fail |
| Unsupported required claims | 0 | 0 | pass |
| Private-field exposures | 0 | 0 | pass |
| Deterministic answer substitutions | 0 | 0 | pass |
| Identity/injected failures fail closed | 100% | 11/11 = 100% | pass |
| Cross-state isolation failures | 0 | 0 | pass |

### Action strata

- `route_vision`: 2/3 = 66.7%
- `route_speech`: 0/3 = 0%
- `route_ambient`: 0/3 = 0%
- `observe_pointer`: 2/3 = 66.7%
- `blocked_status`: 3/3 = 100%
- `restoration_reacquire`: 1/3 = 33.3%
- `no_trigger`: 3/3 = 100%
- `finalize_ready`: 0/3 = 0%

### Six state heads

- `p_sufficient`: 17/24 = 70.8%
- `covered_claim_handles`: 3/24 = 12.5%
- `missing_modalities`: 13/24 = 54.2%
- `missing_hops`: 9/24 = 37.5%
- `missingness_cause`: 6/24 = 25.0%
- `recovery_intent`: 11/24 = 45.8%
- joint exact state: 0/24

## Independent replay and component audit

The independent audit passed and confirmed:

- the complete run seal;
- all 154 raw-output and adapter-input records and hashes;
- no factor exceeded one schema-only retry;
- no semantic or cross-factor repair was detected;
- all 11 runtime fixtures failed closed as specified;
- the single allowed evaluator replay was byte-identical to the recorded
  report after removing the evaluation timestamp; and
- the recorded Gate C decision and metrics were reproduced.

Controller component findings:

- native action factor valid: 12/24 = 50.0%;
- correct first action: 11/24 = 45.8%;
- state factor syntax/enum valid: 24/24 = 100%;
- state projection accepted: 0/24;
- exact six-field state: 0/24.

Twelve controller action factors used their single schema-only retry. After
the retry, ten remained invalid with
`NATIVE_ARGUMENTS_NOT_EMPTY_OBJECT`, and two were rejected with
`SCHEMA_RETRY_CHANGED_CONTENT`. The Qwen native-wrapper normalization was
transport-only; it never stripped arguments or changed the selected action.

All 24 state factors were independently schema-valid, but every state
projection was rejected with
`FULL_COVERAGE_WITH_MISSING_REQUIREMENT`. The evaluator retained the authored
states unchanged and scored each of the six heads separately.

Finalizer component findings:

- disposition valid: 16/16;
- answer text valid: 16/16;
- claim drafts valid: 16/16;
- citation selections valid: 16/16;
- diagnosis valid: 16/16;
- canonical finalizer envelopes: 15/16 = 93.8%;
- required terms in answer text: 12/12;
- required terms in claim text: 12/12;
- blocked raw abstain mode: 4/4;
- blocked empty answer/claims/citations: 4/4; and
- blocked required diagnosis: 0/4.

The one invalid finalizer envelope selected abstention while retaining answer
content, so rejection-only assembly returned `ABSTAIN_WITH_ANSWER_CONTENT`.
The four blocked-partial rows otherwise used a clean abstention shape, but
none identified both the required missing modality and required missing hop,
so the frozen blocked-partial semantic metric was 0/4.

## Decision rationale

`GO` is impossible because the structured-output, overall/per-stratum action,
joint/all state-head, blocked-partial, and restoration floors fail. `REPAIR`
is not the controlling disposition for this consumed configuration because
multiple independent substantive competence gates fail. Under the frozen
decision rule, the exact Qwen3 adapter-v2 row is `NO_GO`.

No post-hoc change, tuning pass, or rerun is authorized. Any future Qwen3
attempt would require a prospective new adapter/prompt/runtime version, a new
suite ID and seed, a new pre-execution freeze, and separate written
authorization.

## Artifacts and validation

Restricted outputs:

- `data/restricted/strong_baselines/qwen3_v2_holdout_run/authorization_claim.json`
- `data/restricted/strong_baselines/qwen3_v2_holdout_run/preflight_report.json`
- `data/restricted/strong_baselines/qwen3_v2_holdout_run/submission.json`
- `data/restricted/strong_baselines/qwen3_v2_holdout_run/raw_attempts.jsonl`
- `data/restricted/strong_baselines/qwen3_v2_holdout_run/run_metadata.json`
- `data/restricted/strong_baselines/qwen3_v2_holdout_run/runner_manifest.json`
- `data/restricted/strong_baselines/qwen3_v2_holdout_run/seal.json`
- `data/restricted/strong_baselines/qwen3_v2_holdout_run/evaluator_report.json`
- `data/restricted/strong_baselines/qwen3_v2_holdout_run/component_audit.json`
- `data/restricted/strong_baselines/qwen3_v2_holdout_run/evaluation_seal.json`

Implementation/audit outputs:

- `tools/qwen3_adapter_v2_holdout.py`
- `scripts/audit_qwen3_adapter_v2_holdout_run.py`
- `tests/test_qwen3_adapter_v2_holdout_run.py`
- `docs/review/qwen3_adapter_v2_holdout_evaluation.md`
- `orchestration/results/185_qwen3_adapter_v2_holdout_evaluation.txt`

Validation:

- Task-182 independent preflight replay: pass.
- Frozen suite, governance, implementation, acquisition, and snapshot hashes:
  pass before model loading.
- Run seal: pass.
- Evaluation seal: pass.
- Independent evaluator replay: pass and identical modulo timestamp.
- Independent component audit: pass.
- Scientific source content accessed: no.
- GPU/API used: no.
- Network attempts: 0.
- Reruns: 0.

## Final token

`QWEN3_ADAPTER_V2_HOLDOUT_NO_GO`
