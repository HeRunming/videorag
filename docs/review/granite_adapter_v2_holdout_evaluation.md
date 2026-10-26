# Granite adapter-v2 unseen holdout evaluation

**Task:** 177  
**Date:** 2026-10-02 (Asia/Shanghai)  
**Decision:** `GRANITE_ADAPTER_V2_HOLDOUT_NO_GO`  
**Gate C:** not passed  
**Scientific execution:** not authorized and not performed

## Executive decision

The one and only Task-176-authorized full-suite execution of the frozen
Granite adapter-v2 fictional holdout completed and was sealed before the
private evaluator was opened. The exact acquired Granite 3.3 8B snapshot ran
all 24 controller cases, 16 finalizer cases, and 11 fail-closed runtime
fixtures. The independent audit reverified the sealed run and reproduced the
frozen evaluator result on the single allowed deterministic replay.

The result is `GRANITE_ADAPTER_V2_HOLDOUT_NO_GO`. The v2 factorized interface
substantially improved the grounded answer path: 11/16 finalizer envelopes
were valid and all eight oracle-complete cases passed supported-answer
scoring. It did not establish controller competence, blocked-partial
abstention, restoration competence, or the required overall structured-output
rate. The controller action factor was valid in only 5/24 cases because
Granite usually copied tool arguments into functions frozen as no-argument;
no argument stripping or semantic repair was permitted. Separately, no
controller evidence-state projection was accepted, and no controller state
matched all six frozen heads.

This suite has now been consumed. It may not be rerun or used for tuning. Gate
C and scientific execution remain unauthorized.

## Frozen identity and one-run authorization

Preflight reverified the Task-176 governance seal, public/private suite hashes,
prompt-policy semantic hash, thresholds, immutable v2 implementation hashes,
acquisition evidence, and exact local snapshot before model loading.

- Suite ID: `granite-v2-fictional-holdout-20261002`
- Freeze label: `GRANITE_ADAPTER_V2_HOLDOUT_2026-10-02`
- Public suite SHA-256:
  `2d2bec156d238032dd75a54a40d91f4e31bea352d25f51fe1f75307a0b12837b`
- Private key SHA-256, verified without loading before the run:
  `3e7a37cb46fd3f6a192112b6df72f1b9482ee23923871c4f81b99ad64515d090`
- Task-176 governance freeze seal SHA-256:
  `ba29d189504e56783c5e657f8e28e12fd76579b73b12941a13290337dca9ddc7`
- Model: `ibm-granite/granite-3.3-8b-instruct`
- Revision, tokenizer revision, and processor revision:
  `51dd4bc2ade4059a6bd87649d68aa11e4fb2529b`
- Snapshot:
  `data/restricted/strong_baselines/models/ibm-granite--granite-3.3-8b-instruct--51dd4bc2ade4`
- Adapter schema: `av-trace.granite-native-adapter/2.0`

Before execution, the run directory did not exist, no matching run process
was active, and the Task-176 independent preflight reported no premature run
artifacts. The authorization claim was written before model loading. Run ID:

`task177-2026-10-02T08:17:45Z-9c3c4f495994`

No restart occurred. The full suite was executed once. This execution consumed
the sole authorization.

## Governed execution

The run enforced:

- CPU-only bfloat16 inference;
- 8 PyTorch threads and 1 inter-op thread;
- `local_files_only=true`;
- `trust_remote_code=false`;
- disabled proxy/token environment and an in-process network-denial guard;
- zero network attempts;
- no GPU and no external or paid API;
- greedy single-output generation;
- 512 maximum new tokens per factor;
- 32,768-token context cap;
- one native function action factor and a separate six-head state factor for
  every controller case;
- disposition, answer text, claim drafts, citation selections, and diagnosis
  as five independent finalizer factors;
- at most one schema-only retry per factor;
- zero semantic retries, cross-factor retries, voting, best-of-N, parser field
  fill, argument stripping, answer substitution, or citation substitution;
- byte-preservation and SHA-256 recording for every raw model response and
  every adapter input; and
- no scientific family, key, real source, or scientific source content.

Runtime:

- Python 3.13.11;
- PyTorch 2.10.0;
- Transformers 5.2.0;
- `GraniteForCausalLM` and `GPT2Tokenizer`;
- 7,928.08 seconds in the child process;
- peak RSS: 20,691,516 KiB;
- 148 substantive factor generation attempts;
- 20 schema-only retries: 19 action factors and 1 diagnosis factor; and
- 14 injected runtime-fixture attempt records.

## Seal before evaluator

The execution phase sealed the authorization claim, preflight report,
submission, raw attempts, run metadata, and runner manifest before loading the
private key.

- Run seal:
  `data/restricted/strong_baselines/granite_v2_holdout_run/seal.json`
- Run seal SHA-256:
  `6b473244c5ef26c6c732654733e910f7a4361fffd4776b0374eda6db490f6b8b`
- Seal state: `SEALED_BEFORE_PRIVATE_EVALUATION`

The evaluator verified this seal, then loaded the private labels and applied
the exact frozen thresholds. Evaluation outputs were separately sealed after
the independent replay/component audit.

## Frozen Gate C metrics

| Metric | Floor | Observed | Gate |
|---|---:|---:|---|
| Total sealed cases | >=48 | 51 | pass |
| Parser/schema and injected failures | 100% | 11/11 = 100% | pass |
| Valid structured substantive calls | >=90% | 11/40 = 27.5% | fail |
| Correct first actions overall | >=85% | 4/24 = 16.7% | fail |
| Correct actions in every stratum | >=75% | 0%–100%; seven of eight strata below floor | fail |
| Exact six-field state | >=75% | 0/24 = 0% | fail |
| Every state head | >=80% | 4.2%–37.5% | fail |
| Oracle supported answer | >=80% | 8/8 = 100% | pass |
| Blocked-partial correct abstention | >=80% | 0/4 = 0% | fail |
| Restoration reacquisition | >=80% | 3/7 = 42.9% | fail |
| Unsupported required claims | 0 | 0 | pass |
| Private-field exposures | 0 | 0 | pass |
| Deterministic answer substitutions | 0 | 0 | pass |
| Identity/injected failures fail closed | 100% | 11/11 = 100% | pass |
| Cross-state isolation failures | 0 | 0 | pass |

### Action strata

- `route_vision`: 0/3
- `route_speech`: 0/3
- `route_ambient`: 0/3
- `observe_pointer`: 0/3
- `blocked_status`: 0/3
- `restoration_reacquire`: 0/3
- `no_trigger`: 3/3
- `finalize_ready`: 1/3

### Six state heads

- `p_sufficient`: 1/24 = 4.2%
- `covered_claim_handles`: 3/24 = 12.5%
- `missing_modalities`: 2/24 = 8.3%
- `missing_hops`: 5/24 = 20.8%
- `missingness_cause`: 6/24 = 25.0%
- `recovery_intent`: 9/24 = 37.5%
- joint exact state: 0/24

## Independent replay and component audit

The independent audit:

- reverified the complete run seal;
- verified every stored raw-output and adapter-input SHA-256;
- confirmed no factor exceeded one schema-only retry;
- detected no semantic or cross-factor repair;
- ran the single allowed deterministic evaluator replay;
- reproduced the decision, metrics, gate checks, and case scores identically
  after excluding the evaluation timestamp; and
- passed all 11 runtime fixtures.

Controller component findings:

- native action factor valid: 5/24 = 20.8%;
- raw native action correct: 4/24 = 16.7%;
- state factor syntax/enum valid: 18/24 = 75.0%;
- state projection accepted: 0/24;
- exact six-field state: 0/24.

The dominant action-factor failure was
`NATIVE_ARGUMENTS_NOT_EMPTY_OBJECT` in 18 cases. Granite selected a declared
function but emitted the frozen action's arguments even though the v2
function schema required `{}`. Those arguments were preserved, and the factor
remained invalid; the runner did not strip or replace them. One further action
factor remained malformed JSON. Six state factors used an invalid enum, and
18 syntactically valid state factors were rejected for
`FULL_COVERAGE_WITH_MISSING_REQUIREMENT`.

Finalizer component findings:

- disposition valid: 16/16;
- answer text valid: 16/16;
- claim drafts valid: 16/16;
- citation selections valid: 16/16;
- diagnosis valid: 15/16;
- canonical finalizer envelope valid: 11/16 = 68.8%;
- required terms in answer text: 12/12;
- required terms in claim text: 12/12;
- oracle supported answers: 8/8;
- restoration-complete supported answers: 3/4;
- blocked raw abstain mode: 4/4;
- blocked empty answer/claims/citations: 0/4;
- blocked required diagnosis: 1/4.

The four blocked-partial rows selected `answer_mode="abstain"` but also authored
nonempty answer/claim content, so the rejection-only projection correctly
returned `ABSTAIN_WITH_ANSWER_CONTENT`. One restoration-complete row had an
extra diagnosis field; its sole schema-only retry preserved the extra field
and remained invalid.

## Decision rationale

`GO` is impossible because the controller, structured-output, state,
blocked-partial, and restoration floors fail. `REPAIR` is also not the
controlling disposition for this consumed configuration: multiple independent
substantive competence gates fail, including every controller state gate and
seven of eight action strata. Under the Task-148 stop rule, the affected
learned row is disqualified, and this unseen suite cannot be tuned and rerun.
The exact frozen adapter-v2/Granite configuration is therefore `NO_GO`.

This does not authorize a post-hoc v2.1 attempt on this suite. Any future
Granite work would require a prospective new adapter/prompt/runtime version,
a new seed and suite ID, and a newly frozen unseen suite under separate
written authorization. The Task-177 outputs, labels, evaluator results, and
component findings may not be used to alter and rerun this holdout.

## Artifacts and validation

Restricted outputs:

- `data/restricted/strong_baselines/granite_v2_holdout_run/authorization_claim.json`
- `data/restricted/strong_baselines/granite_v2_holdout_run/preflight_report.json`
- `data/restricted/strong_baselines/granite_v2_holdout_run/submission.json`
- `data/restricted/strong_baselines/granite_v2_holdout_run/raw_attempts.jsonl`
- `data/restricted/strong_baselines/granite_v2_holdout_run/run_metadata.json`
- `data/restricted/strong_baselines/granite_v2_holdout_run/runner_manifest.json`
- `data/restricted/strong_baselines/granite_v2_holdout_run/seal.json`
- `data/restricted/strong_baselines/granite_v2_holdout_run/evaluator_report.json`
- `data/restricted/strong_baselines/granite_v2_holdout_run/component_audit.json`
- `data/restricted/strong_baselines/granite_v2_holdout_run/evaluation_seal.json`

Implementation/audit outputs:

- `tools/granite_adapter_v2_holdout.py`
- `scripts/audit_granite_adapter_v2_holdout_run.py`
- `docs/review/granite_adapter_v2_holdout_evaluation.md`
- `orchestration/results/177_granite_adapter_v2_holdout_evaluation.txt`

Validation:

- Task-176 independent preflight replay: pass.
- Frozen suite, governance, implementation, acquisition, and snapshot hashes:
  pass before model loading and unchanged after evaluation.
- Focused v2/holdout/acquisition/competence compatibility tests: 39 passed.
- Ruff on Task-177 runner/auditor: pass.
- Run seal verification: pass.
- Independent evaluator replay: pass and identical modulo timestamp.
- Independent component audit: pass.
- Scientific source content accessed: no.
- GPU/API used: no.
- Network attempts: 0.
- Reruns: 0.

## Final token

`GRANITE_ADAPTER_V2_HOLDOUT_NO_GO`
