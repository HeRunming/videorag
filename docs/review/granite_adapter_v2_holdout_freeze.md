# Granite adapter-v2 unseen fictional holdout freeze

**Task:** 176  
**Date:** 2026-10-02 (Asia/Shanghai)  
**Decision:** `GRANITE_ADAPTER_V2_HOLDOUT_FROZEN`  
**Suite ID:** `granite-v2-fictional-holdout-20261002`  
**Freeze label:** `GRANITE_ADAPTER_V2_HOLDOUT_2026-10-02`  
**Execution state:** sealed, unseen, and not run

## Executive finding

Exactly one new source-free fictional competence suite was generated for the
Granite-native adapter v2 and sealed before any model execution. The suite is
sufficiently composed to apply the frozen Gate C controller/finalizer
thresholds without weakening them. The public packet, evaluator-private key,
generation metadata, prompt policy, model binding, thresholds, one-run
authorization, prohibited tuning sources, and governing hashes are frozen.

Granite was not loaded or run. No model inference, GPU/API use, scientific
family access, real/scientific source content, or outcome inspection occurred.
The evaluator-private target rows were not manually inspected after
generation. Their structure was checked by an automated schema test, while the
independent audit used only their sealed bytes/hash and the aggregate
composition emitted by the generator.

## Inputs and governing decisions

The freeze followed:

- Task 149's exact primary Granite controller/finalizer model binding and Gate
  C competence floors;
- Task 172's frozen no-go, including the requirement that a future attempt use
  a prospective adapter/prompt/runtime and a newly frozen unseen suite; and
- Task 175's Granite-native factorized adapter and prospective suite
  generator.

Task 158/172 public fictional cases and the Task-172 prompt source were used
only by the automated overlap audit. Task-172 private targets were not used to
author, validate, tune, or inspect this holdout.

## Strong random seed

The seed was generated and recorded before suite generation at
`2026-10-02T15:50:08+08:00` using Python `secrets.randbits(256)` with the high
bit set.

```text
decimal:
78196802424380082776318973058337920883482433466228251028861878547570995846291

hex:
ace1d25d2a7ec207cb8a552150071e83f630c05d3128a8dfc5ecc168bf515c93
```

The seed is 256 bits and differs from the consumed Task-158/172 seed
`15820260924`. It is recorded in the restricted evaluator key and freeze
manifest, not in the public suite.

## Frozen suite composition

The public packet contains 51 cases:

| Group | Count | Frozen strata |
|---|---:|---|
| Controller | 24 | 3 each: route vision, route speech, route ambient, observe pointer, blocked status, restoration reacquire, no-trigger terminal, finalize-ready terminal |
| Finalizer | 16 | 8 oracle-complete, 4 restoration-complete, 4 blocked-partial |
| Runtime fail-closed | 11 | malformed action/state/claim/citation factors, wrong snapshot, provider failure, timeout, process failure, OOM, exhausted budget, prohibited cross-factor semantic retry |

Controller policies are balanced 12 `react_v2` / 12 `sufficiency_v2`. Aggregate
private-label checks establish:

- expected tools: 6 finalizes, 3 status checks, 3 pointer inspections, 3
  ambient searches, 6 speech searches, and 3 visual searches;
- every controller recovery-intent stratum appears exactly three times;
- all three missing modalities and the required route/state/terminal causes
  are represented;
- finalizers contain 12 answer and 4 abstention rows;
- finalizer required modalities are 6 vision, 5 speech, and 5 ambient;
- blocked-partial cases cover speech content, event detection, ambient event,
  and temporal order; and
- all 11 runtime cases require a typed fail-closed outcome and no final answer.

The fixture vocabulary is generated from invented cards, relays, chambers,
emblems, colors, shapes, call-signs, and tone patterns. There is no real or
scientific source content.

## Frozen model and adapter binding

Both learned roles are bound to the same exact local snapshot:

```text
repo_id: ibm-granite/granite-3.3-8b-instruct
revision: 51dd4bc2ade4059a6bd87649d68aa11e4fb2529b
processor_revision: 51dd4bc2ade4059a6bd87649d68aa11e4fb2529b
tokenizer_revision: 51dd4bc2ade4059a6bd87649d68aa11e4fb2529b
```

Roles are `TOOL_CONTROLLER_BACKBONE` and `GROUNDED_FINALIZER`. The frozen
adapter schema is `av-trace.granite-native-adapter/2.0`. The authorized run is
bound to the file hashes in `freeze_manifest.json`; changing the adapter,
contracts, generator, prompt policy, model identity, or thresholds voids this
suite for execution and requires a new suite ID, seed, and freeze.

## Frozen prompt and retry policy

The prompt policy is stored separately at
`data/restricted/strong_baselines/granite_v2_holdout/prompt_policy.json`.
Its semantic SHA-256 is:

```text
sha256:7a0cac94f09e31952d1688e0a886e9405179f3b7a30a116ccb1c4cbebff72e18
```

It freezes:

- public projection only;
- one no-argument native function per exact controller menu action;
- an independently authored six-head evidence state;
- five independently authored finalizer factors;
- rejection-only projection and mechanical serialization;
- at most one schema-only retry per factor;
- zero semantic retries;
- zero cross-factor retries; and
- no voting, best-of-N, deterministic answer substitution, claim insertion,
  citation selection, diagnosis replacement, or inferred action.

## Frozen Gate C thresholds

The existing Task-148/149 controller/finalizer thresholds are preserved:

- at least 48 sealed cases;
- parser/schema and injected failure fixtures: 100%;
- valid structured substantive model calls: at least 90%;
- correct first actions: at least 85% overall and 75% in every action stratum;
- exact six-field state: at least 75%;
- every state head: at least 80%;
- oracle supported answers: at least 80%;
- blocked-partial correct abstention: at least 80%;
- restoration reacquisition: at least 80%;
- unsupported required claims: 0;
- private-field exposures: 0; and
- deterministic answer substitutions: 0.

No threshold was selected from model outcomes; no model outcomes exist.

## One-run authorization

This freeze authorizes **at most one complete future competence execution** of
the exact sealed 51-case suite under the exact frozen model, adapter, prompts,
factor schemas, decoding/runtime policy, and hashes. Task 176 itself does not
execute that authorization.

Before the run, the execution task must verify both seals and the exact local
model/environment binding. Subset model runs, smoke inference on holdout
cases, partial runs, and development probes are prohibited. After any model
output is produced, there is no rerun or replacement attempt on this suite.
The sealed submission may be evaluated once, including the one deterministic
evaluator replay needed to produce and verify the final report.

## Prohibited tuning sources

The following may not inform any prompt, adapter, runtime, decoding, schema,
threshold, or model change for this frozen suite:

- the evaluator-private labels or any derived target;
- any holdout model output;
- any holdout evaluator report, component/error audit, or manual error review;
- scientific families, scientific keys, or scientific source content;
- Task-172 evaluator-private targets;
- Task-172 outputs used for any post-freeze change; and
- any outcome-conditioned model, prompt, adapter, runtime, or threshold
  selection.

Task-172 outputs were already consumed for Task-175 development. Their use for
additional post-freeze tuning is expressly prohibited.

## Independent overlap and content audit

The independent audit compared all 51 new public controller/finalizer/runtime
cases with all 51 Task-158/172 public controller/finalizer/runtime cases:

- 2,601 pairwise public-case comparisons;
- exact public-input matches: 0;
- exact question matches: 0;
- maximum normalized sequence ratio: `0.702179`, below `0.84`;
- maximum content-token Jaccard: `0.466667`, below `0.72`;
- controller prompt sequence ratio versus Task 172: `0.185301`;
- finalizer prompt sequence ratio versus Task 172: `0.237519`; and
- no prohibited real/scientific source marker found.

The overlap script does not load or parse the new private key.

## Sealed artifacts and principal hashes

| Artifact | SHA-256 |
|---|---|
| Public rehearsal packet | `2d2bec156d238032dd75a54a40d91f4e31bea352d25f51fe1f75307a0b12837b` |
| Restricted private evaluator key | `3e7a37cb46fd3f6a192112b6df72f1b9482ee23923871c4f81b99ad64515d090` |
| Generation manifest | `d077469637aac0826e60b50b19304a34812765ba85cb7adb15909a7c67310ef5` |
| Prompt-policy file | `636ca256a88638f1f66b76612a42f1f460a7b81eb7d6c1d077b7c38e0482bafb` |
| Pre-execution suite seal | `45d45d8163ab9f1ae2250ff752b2a1dbc599ed4829491bd092084a05b361dffd` |
| Freeze manifest | `e72efe0af35c0850111737db6787f65668777440beb5cb0679109c55993d640d` |
| Governance freeze seal | `ba29d189504e56783c5e657f8e28e12fd76579b73b12941a13290337dca9ddc7` |
| Independent audit report | `4da847cad023e1163a9cb4edc99ce536fb1adf2ddaca945cbde59db72341fe9f` |

The restricted directory is mode `0500`; restricted JSON artifacts are mode
`0400`.

## Validation

```text
ruff check src/av_trace_strong_baselines_v2 \
  scripts/generate_granite_adapter_v2_suite.py \
  scripts/audit_granite_adapter_v2_holdout.py \
  tests/test_granite_native_adapter_v2.py \
  tests/test_granite_adapter_v2_holdout.py
```

Result: `All checks passed!`

```text
pytest -q tests/test_granite_native_adapter_v2.py \
  tests/test_granite_adapter_v2_holdout.py
```

Result: `16 passed`.

Compatibility suite:

```text
pytest -q tests/test_granite_native_adapter_v2.py \
  tests/test_granite_adapter_v2_holdout.py \
  tests/test_strong_baseline_adapters.py \
  tests/test_granite33_8b_acquisition.py \
  tests/test_granite33_competence.py \
  tests/test_granite33_competence_audit.py
```

Result: `70 passed`.

All public/restricted JSON files parse. The independent audit reproduced the
stored audit report byte-for-byte.

## Decision

The new Granite adapter-v2 fictional competence suite is prospectively frozen,
unseen by Granite, and eligible for its single separately governed execution.
This is not a competence result and does not authorize scientific evaluation.

`GRANITE_ADAPTER_V2_HOLDOUT_FROZEN`
