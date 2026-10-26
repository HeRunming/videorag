# Granite 3.3 8B frozen fictional competence audit

**Task:** 172  
**Date:** 2026-10-02 (Asia/Shanghai)  
**Decision:** `GRANITE33_COMPETENCE_NO_GO`  
**Frozen evaluator result:** `STRONG_BASELINE_COMPETENCE_REPAIR`  
**Scientific execution:** not authorized and not performed

## Executive decision

The exact acquired Granite 3.3 8B snapshot completed the full frozen
controller/finalizer competence group: 24 controller cases, 16 finalizer
cases, and 11 fail-closed runtime fixtures. The run used the exact Task-149 /
Task-158 primary controller and finalizer identity:

- repository: `ibm-granite/granite-3.3-8b-instruct`;
- revision: `51dd4bc2ade4059a6bd87649d68aa11e4fb2529b`;
- tokenizer revision: the same exact revision;
- processor revision: the same exact revision; and
- one shared local snapshot for both roles.

The run does **not** pass the Task-149/158 competence floors. The governing
Task-172 decision is therefore `GRANITE33_COMPETENCE_NO_GO`. This is a
candidate-level competence decision for this sealed configuration, not a
claim that every future prospectively versioned Granite adapter must fail.
Gate C remains unpassed.

The direct-A/V suite remains structurally ineligible for this text-only
Granite snapshot. Its 24 substantive cases and 6 runtime fixtures were not
executed, were not inserted into the controller/finalizer denominator, and
were not scored as zero.

## Frozen inputs and pre-run boundary

The run used:

- suite:
  `data/rehearsal_plan/strong_baseline_competence_suite_v1.json`;
- suite ID: `strong-baseline-fictional-public-v1`;
- suite hash:
  `sha256:7b8f8d021b24cb244f0df0f6b02b3da91120df3817a5366350895eb24f4646dc`;
- snapshot:
  `data/restricted/strong_baselines/models/ibm-granite--granite-3.3-8b-instruct--51dd4bc2ade4`;
- frozen evaluator:
  `scripts/evaluate_strong_baseline_competence.py`; and
- frozen scoring implementation:
  `src/av_trace_strong_baselines/competence.py`.

The suite is public, fictional, generated from abstract primitives, and
source-free. It contains no scientific family, real benchmark ground truth,
or evaluator-private benchmark fields. Model requests were constructed only
from `model_public_case(case)`, which exposes `case_type` and `public_input`
but not `case_id` or `scoring_target`.

## Governed runner

Task 172 added:

- `tools/granite33_competence.py`;
- `scripts/audit_granite33_competence_components.py`;
- `tests/test_granite33_competence.py`; and
- `tests/test_granite33_competence_audit.py`.

The runner enforced:

- CPU-only bfloat16 inference;
- 8 PyTorch threads and 1 inter-op thread;
- `local_files_only=True`;
- `trust_remote_code=False`;
- disabled proxy/token environment and an in-process network denial guard;
- zero recorded network attempts;
- greedy one-output generation;
- at most 512 new tokens per call;
- the 32,768-token common context cap;
- at most one schema-only retry;
- zero semantic retries;
- no parser extraction, JSON completion, field filling, action inference,
  answer substitution, citation substitution, voting, or best-of-N;
- every raw model-authored attempt retained;
- typed invalid results when strict validation failed;
- exact controller/finalizer binding checks before inference; and
- no interaction with GPUs, APIs, or unrelated Ray jobs.

The substantive run made 44 model generation attempts: one attempt for each
of the 40 cases plus one schema-only retry for each of the 4 blocked-partial
finalizer cases. No controller or answer case received a semantic repair.

Runtime:

- Python 3.13.11;
- PyTorch 2.10.0;
- Transformers 5.2.0;
- `GraniteForCausalLM`;
- `GPT2Tokenizer`;
- peak RSS: 19,079,000 KiB;
- recorded elapsed time across the two resumable child processes:
  approximately 4,631 seconds of per-case inference, with the final process
  recording 2,418 seconds;
- network attempts: 0.

The run was interrupted once after case 27 and resumed from the unsealed
progress journal. Already completed cases were not rerun. The model was
reloaded from the same verified local snapshot, and the prompt-policy/source
hashes and exact bindings were checked before resumption.

## Seal-before-evaluation

The execution phase wrote and then sealed:

- `submission.json`;
- `raw_attempts.jsonl`;
- `run_metadata.json`;
- `direct_av_eligibility.json`; and
- `runner_manifest.json`.

The seal was created at `2026-10-02T06:56:42Z`, before evaluation:

`data/restricted/strong_baselines/granite33_competence_v1/seal.json`

Seal SHA-256:

`f1a6496d245b09e5940efeade2fbaeb5bcff7e3ed280dabff480c210c1eede64`

The evaluator verified this seal before reading the submission. Evaluation
outputs were separately recorded in `evaluation_seal.json`. The component
audit also reverified the sealed inputs and recomputed the frozen evaluator
report byte-for-byte before writing `component_audit.json`.

## Frozen evaluator result

The unmodified Task-158 evaluator returned:

`STRONG_BASELINE_COMPETENCE_REPAIR`

Only these gates passed:

- minimum case count;
- all parser/schema and injected runtime fixtures;
- cross-state namespace isolation;
- no deterministic substitution;
- no evaluator-private exposure;
- zero evaluator-counted unsupported claims; and
- fail-closed identity/runtime behavior.

These competence gates failed:

- valid structured model calls;
- correct first actions overall;
- correct actions in every stratum;
- exact six-field state;
- every individual state component;
- oracle supported answers;
- blocked-partial abstentions; and
- restoration reacquisition.

### Frozen headline metrics

| Metric | Floor | Observed | Gate |
|---|---:|---:|---|
| Valid structured substantive calls | >= 90% | 7.5% (3/40) | fail |
| Correct first actions overall | >= 85% | 12.5% (3/24) | fail |
| Correct first actions, every stratum | >= 75% | 0%–100%; seven of nine strata below floor | fail |
| Exact six-field state | >= 75% | 0% (0/24) | fail |
| Every state component | >= 80% | 0% for each under strict evaluator | fail |
| Oracle supported answer | >= 80% | 0% (0/8) | fail |
| Blocked-partial correct abstention | >= 80% | 0% (0/4) | fail |
| Restoration reacquisition | >= 80% | 0% (0/7 combined controller/finalizer rows) | fail |
| Unsupported required claims | 0 | 0 evaluator-counted | pass, qualified below |
| Private-field exposures | 0 | 0 | pass |
| Deterministic substitutions | 0 | 0 | pass |
| Runtime fixtures fail closed | 100% | 100% (11/11) | pass |

The frozen evaluator counts an action or state component only when the full
controller object passes strict state validation. It likewise scores answer
support only after the entire canonical final-answer envelope validates.
Accordingly, the independent audit below reports raw parseable subcomponents
as diagnostics only; they do not rescue invalid cases or change the verdict.

## Independent component audit

### Action syntax and correctness

All 24 controller outputs were parseable single JSON objects and all 24
contained an integer `action_index` within the supplied menu. Only 3/24
(12.5%) were fully valid controller envelopes, however.

On the raw in-range action indices, before invalid state envelopes are
fail-closed:

- overall action correctness: 11/24 (45.8%);
- route vision: 2/3;
- route speech: 1/3;
- route ambient: 0/3;
- observe pointer: 1/3;
- blocked status: 2/3;
- restoration reacquire: 0/3;
- no-progress guard: 2/2;
- no-trigger: 1/1; and
- finalize ready: 2/3.

This raw diagnostic remains below the 85% overall floor and below the 75%
per-stratum floor in seven of nine strata. The frozen strict action metric is
3/24 because invalid evidence-state envelopes are typed invalid rather than
partially credited.

### State heads and joint state

Raw exact-match diagnostics across all 24 controller outputs:

| State head | Correct | Rate |
|---|---:|---:|
| `p_sufficient` | 17/24 | 70.8% |
| `covered_claim_handles` | 3/24 | 12.5% |
| `missing_modalities` | 6/24 | 25.0% |
| `missing_hops` | 3/24 | 12.5% |
| `missingness_cause` | 13/24 | 54.2% |
| `recovery_intent` | 6/24 | 25.0% |
| Joint six-field exact state | 0/24 | 0% |

None reaches the 80% component floor, and the joint state misses its 75%
floor. The dominant controller failure was marking a claim as covered while
also declaring missing evidence. Strict validation rejected 20 cases as
`FULL_COVERAGE_WITH_MISSING_REQUIREMENT`; one additional case used an invalid
missing-hop enum.

### Terminal behavior

There were six controller terminal cases:

- raw selection of `finalize`: 5/6;
- raw correct action: 5/6 (83.3%);
- fully valid controller envelope plus correct action: 3/6 (50.0%).

The three no-progress/no-trigger cases selected `finalize`, but they
incorrectly claimed full support and `finalize_answer` rather than a
fail-closed abstaining state. Two of three finalize-ready cases selected
`finalize`; all three had state defects, and one selected another visual
search.

### Finalizer syntax, oracle answers, and restoration answers

All 16 finalizer outputs were parseable single JSON objects. None was a valid
canonical grounded-finalizer envelope.

The 12 answer-mode cases omitted the required top-level
`claim_to_citations` map. They also commonly:

- placed `start_s`/`end_s` directly on citations instead of under
  `interval`;
- used a probability object instead of a numeric claim confidence;
- used a string instead of an array for `hop_types`;
- used a string instead of a boolean for `recovery_route_declared`; and
- copied a slot description into claim text rather than stating the required
  answer term.

Raw natural-language answers contained every required answer term in all
8/8 oracle cases and all 4/4 restoration-complete cases. This is not a
supported-answer pass: the model-authored registered claim text omitted the
required term in 12/12 answer cases, and no full grounded envelope validated.
The frozen oracle supported-answer result is therefore 0/8, and strict
restoration-complete answer success is 0/4.

### Abstentions

All four blocked-partial outputs expressed raw `answer_mode="abstain"`,
returned empty claims, and put at least 0.5 probability on the requested
missing modality. Three of four named the required hop if a scalar string is
read descriptively. None represented `hop_types` in the required array
shape, all omitted required `natural_language_answer`, and other schema
fields were invalid. Strict correct abstention is therefore 0/4.

### Unsupported claims

The frozen evaluator reports zero unsupported required claims. This value
must not be interpreted as successful grounding: no answer-mode finalizer
output passed structural validation far enough to enter claim-support
scoring.

The independent raw diagnostic found:

- 12/12 natural-language answers contained the required factual terms;
- 12/12 registered claim texts omitted at least one required term; and
- 11/12 raw citation IDs were within the accepted public support set.

These diagnostics do not repair the invalid envelopes and are not substitute
scores.

### Invalids and runtime failures

Substantive typed invalids:

- `INVALID_OUTPUT`: 37/40;
- valid substantive outputs: 3/40.

Strict error distribution:

- `FULL_COVERAGE_WITH_MISSING_REQUIREMENT`: 20;
- `MISSING_HOPS_ENUM`: 1;
- `FINAL_ENVELOPE_FIELD_SET_MISMATCH`: 12; and
- `FINAL_ANSWER_SCHEMA_INVALID`: 4.

All 11 runtime fixtures passed:

- malformed output: 2/2 typed `INVALID_OUTPUT` after the sole schema retry;
- wrong snapshot: 2/2 typed `SNAPSHOT_MISMATCH` before a model call;
- provider failure: 2/2 typed `PROVIDER_FAILURE`;
- timeout: 2/2 typed `TIMEOUT`;
- process failure: 1/1 typed `PROCESS_FAILURE`;
- OOM: 1/1 typed `OOM`; and
- budget exhaustion: 1/1 typed `BUDGET_EXHAUSTED` before a model call.

No fixture produced a fallback answer.

## Direct-A/V disposition

`ibm-granite/granite-3.3-8b-instruct` is the selected text controller and
grounded finalizer. It has no native or packed audiovisual processor contract.
Therefore:

- eligibility: `STRUCTURALLY_INELIGIBLE`;
- direct-A/V substantive cases executed: 0/24;
- direct-A/V runtime fixtures executed: 0/6;
- direct-A/V score rows created: 0;
- scored as zero: no; and
- controller/finalizer denominator affected: no.

## Decision rationale and allowed next step

`GRANITE33_COMPETENCE_GO` is impossible because most competence floors fail.
The governing decision is `GRANITE33_COMPETENCE_NO_GO`, rather than silently
treating the frozen run as repairable, because this exact sealed configuration
is disqualified by the preregistered stop rule that any competence floor
failure stops the affected row. It cannot be rerun on the same frozen suite
after prompt tuning and still count as an unseen competence run.

A future attempt would require a prospective versioned adapter/prompt/runtime
revision and a newly frozen unseen fictional competence suite. It must not use
these Task-172 outcomes as evaluator assistance for the current suite, and it
does not authorize scientific families or Gate C.

## Validation

- `ruff check` on Task-172 runner/auditor/tests: pass.
- Focused compatibility pytest: 54 passed.
- Exact Task-158 frozen evaluator replay: pass and identical to stored report.
- Input seal verification: pass.
- Component-audit seal verification: pass.
- Scientific-family content accessed: no.
- GPU/API used: no.
- Unrelated Ray/H20 jobs touched: no.

## Artifacts

Restricted run directory:

`data/restricted/strong_baselines/granite33_competence_v1/`

Contains:

- `submission.json`;
- `raw_attempts.jsonl`;
- `run_metadata.json`;
- `direct_av_eligibility.json`;
- `runner_manifest.json`;
- `seal.json`;
- `evaluator_report.json`;
- `independent_audit.json`;
- `evaluation_seal.json`;
- `component_audit.json`; and
- `component_audit_seal.json`.

Public review/result artifacts:

- `docs/review/granite33_competence_v1_audit.md`;
- `orchestration/results/172_granite33_competence_v1.txt`.

## Final token

`GRANITE33_COMPETENCE_NO_GO`
