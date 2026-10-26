# Qwen3 adapter-v2 unseen fictional holdout freeze

**Task:** 182  
**Date:** 2026-10-08 (Asia/Shanghai)  
**Decision:** `QWEN3_ADAPTER_V2_HOLDOUT_FROZEN`  
**Suite ID:** `qwen3-v2-fictional-holdout-20261008`  
**Freeze label:** `QWEN3_ADAPTER_V2_HOLDOUT_2026-10-08`  
**Execution state:** frozen, unseen, not run

## Decision

Exactly one new source-free fictional competence suite has been generated and
sealed prospectively for the adapter-v2 Qwen3 fallback row. It contains 51
fixtures, preserves the existing Gate C floors, and is bound to the exact
Qwen3 snapshot acquired and smoke-checked in Task 181.

Qwen3 was not loaded or run for Task 182. No inference, GPU/API use, network
access, scientific-family access, or real-source content was used. The
evaluator-private target rows were created mechanically by the generator and
were not manually inspected. The independent audit authenticated the key by
byte count and hash and checked only the generator's aggregate composition.

## Governing inputs

The freeze follows:

- Task 149's Qwen3 fallback identity and frozen Gate C competence floors;
- Task 175's factorized adapter-v2 contracts and prospective suite design;
- Task 176's pre-execution sealing, one-run, and private-target handling
  pattern;
- Task 177's consumed Granite v2 outcome, which remains unavailable for
  post-freeze tuning; and
- Task 181's exact Qwen3 acquisition and native-tool transport evidence.

Task 158, the consumed Granite v2 holdout, Task 172/177 prompt surfaces, and
the Task 181 public smoke prompts/cases were used only by automated overlap
checks. Their evaluator-private targets were not used.

## Fresh cryptographic seed

The seed was generated and recorded before suite generation at
`2026-10-08T13:43:46+08:00` with Python `secrets.randbits(256)` and the high
bit set:

```text
decimal:
109907551937852608386308284603829029741725434053982647623141715162619717541482

hex:
f2fd784c8c7e3b58bb50ba6a52bea0d73e0c5b6868ac2a60ccbb8590215ade6a
```

It is 256 bits and is neither the consumed Task 158 seed nor the Granite v2
holdout seed. The value is retained in the restricted evaluator key and
freeze manifest, not in the public packet.

## Frozen composition

| Group | Count | Strata |
|---|---:|---|
| Controller | 24 | 3 each: route vision, route speech, route ambient, observe pointer, blocked status, restoration reacquire, no-trigger, finalize-ready |
| Finalizer | 16 | 8 oracle-complete, 4 restoration-complete, 4 blocked-partial |
| Runtime | 11 | malformed action/state/claim/citation, wrong snapshot, provider failure, timeout, process failure, OOM, budget exhaustion, cross-factor semantic retry |

Additional aggregate coverage:

- controller policies: 12 `react_v2` and 12 `sufficiency_v2`;
- routing controller cases: 15;
- state cases: all 24 controller fixtures;
- terminal controller cases: 6;
- restoration cases: 3 controller plus 4 finalizer = 7;
- no-trigger cases: 3;
- oracle finalizer cases: 8;
- partial/abstention finalizer cases: 4;
- expected tools: 6 finalize, 3 status, 3 inspect, 3 ambient search, 6
  speech search, and 3 visual search;
- finalizer required modalities: 6 vision, 5 speech, 5 ambient; and
- blocked-partial hops: speech content, event detection, ambient event, and
  temporal order.

The generated domain consists only of imaginary depots, registers, dockets,
materials, motifs, watchwords, and acoustic signatures.

## Exact model and adapter binding

Both learned roles require the same exact snapshot:

```text
repo_id: Qwen/Qwen3-8B
revision: b968826d9c46dd6066d109eabc6255188de91218
processor_revision: b968826d9c46dd6066d109eabc6255188de91218
tokenizer_revision: b968826d9c46dd6066d109eabc6255188de91218
```

The roles remain `TOOL_CONTROLLER_BACKBONE` and `GROUNDED_FINALIZER`. The
frozen adapter schema is `av-trace.granite-native-adapter/2.0`, used here with
the Qwen3 native tool-call transport proved by Task 181. The prompt/runtime
profile freezes Qwen chat-template tool calls, `enable_thinking=false`,
greedy decoding, one schema-only retry per factor, zero semantic retries,
zero cross-factor retries, and no voting or semantic substitution.

## Frozen Gate C floors

The Task 148/149 controller/finalizer floors are unchanged:

- minimum sealed cases: 48;
- parser/schema and injected-failure fixtures: 100%;
- valid structured substantive calls: at least 90%;
- correct first actions: at least 85% overall and at least 75% in every
  stratum;
- exact six-field state: at least 75%;
- every state head: at least 80%;
- oracle supported answer: at least 80%;
- blocked-partial correct abstention: at least 80%;
- restoration reacquisition: at least 80%;
- unsupported required claims: 0;
- private-field exposures: 0; and
- deterministic answer substitutions: 0.

No floor was selected from holdout outputs. No holdout output exists.

## Overlap audit

The independent audit found zero exact or threshold-defined near overlaps:

| Comparison corpus | Pairs | Exact public inputs | Exact questions | Near pairs | Max sequence | Max token Jaccard |
|---|---:|---:|---:|---:|---:|---:|
| Task 158 public suite | 2,601 | 0 | 0 | 0 | 0.563218 | 0.297297 |
| Granite v2 holdout | 2,601 | 0 | 0 | 0 | 0.661654 | 0.395349 |
| Task 181 public smoke | 102 | 0 | 0 | 0 | 0.367470 | 0.078947 |

For public prompt policy surfaces, 56 comparisons against 28 consumed prompt
entries found 0 exact and 0 near overlaps; maxima were 0.563200 sequence and
0.285714 token Jaccard.

The expanded rendered-prompt audit covered:

- 256 new initial/retry factor prompts;
- 343 consumed Task 172, Granite v2, and Task 181 rendered prompts;
- 87,808 pairwise token-overlap comparisons;
- 1,280 sequence comparisons among the five lexically closest candidates per
  new prompt;
- exact matches: 0;
- near-overlap pairs: 0;
- maximum candidate sequence ratio: 0.719688; and
- maximum token Jaccard: 0.669725.

The frozen near-overlap thresholds are sequence ratio below 0.84 and content
token Jaccard below 0.72.

## Prompt policy and private-key boundary

The prompt policy is sealed at
`data/restricted/strong_baselines/qwen3_v2_holdout/prompt_policy.json`.
Its semantic SHA-256 is:

```text
sha256:bd5539e0a06838b9c3b36ced145bca7d6f2f0c2838d8899b05a26c06e352303f
```

The public packet contains no expected action index, expected evidence state,
answer-term target, accepted-support target, or expected runtime status. The
private key may be opened only by the later authorized evaluator after the
sealed model submission exists. Until then, verification is limited to
sealed bytes/hash and aggregate counts.

## One-run authorization

This freeze authorizes exactly one future complete execution of all 51 cases,
under the frozen model, adapter, transport, prompt, factor schemas, budget,
decoding policy, and hashes.

- Holdout subset, smoke, development, or partial model runs: 0 authorized.
- Reruns after any model output: 0 authorized.
- Pre-run seal, environment, model, adapter, and one-run-state verification
  is mandatory.
- One deterministic evaluator replay is allowed after the sealed submission.
- Task 182 does not consume the authorization.
- Any mutation of a frozen binding or source hash voids this suite and
  requires a new suite ID, seed, and freeze.

## Prohibited tuning

The following may not influence any later model, prompt, adapter, parser,
runtime, decoding, schema, or threshold choice for this suite:

- private labels or derived targets;
- Qwen3 holdout outputs;
- holdout evaluator, component, or error reports;
- manual holdout error review;
- scientific families, keys, or source content;
- Task 158 or Granite v2 private targets;
- Task 172/177 outputs for any post-freeze change;
- Task 181 smoke outputs for any post-freeze change; or
- any outcome-conditioned change or selection.

## Sealed artifacts and hashes

| Artifact | SHA-256 |
|---|---|
| Public packet / restricted public suite | `b8e7529ff620522c0de45d22988cf0d5c706cfc70123332943d3090e0bf66696` |
| Private evaluator key | `0bf2ea7996c64f75601758e5d48169b5a847b3a764a1b5b780167d1c3b2a31cc` |
| Generation manifest | `c5667263717a4ad61c7687588b167815faf37debad4c6383ec8e0dcd775f6a37` |
| Prompt-policy file | `f705415d302dda7041134d301bf47df5d23798cdb81c3d2e7b84e52fe782d573` |
| Pre-execution suite seal | `4676bb2f4ef582efff4040d39868a7024e6f7c28b94deb356667f720efc08868` |
| Freeze manifest | `6457f8e8ff179668b14f198ac1944c31dc95d09c5afcf0551fe79a59552fb24f` |
| Governance freeze seal | `87a831a2fea63b6876ce98fd914b18f026eff842c1b2be58cc9e9cd102e55873` |
| Independent audit report | `fbe531bf483323dccd79b485631147f9d9fe974edfec469f61508d2f63f74973` |

The restricted directory is mode `0500`; restricted JSON files are mode
`0400`.

## Validation

- Focused Ruff: PASS.
- Focused Task 175/181/182 tests: 28 passed.
- Compatibility suite: 82 passed.
- Every public/restricted JSON file parses.
- Independent audit replay reproduced the stored audit byte-for-byte.
- Qwen3 inference during Task 182: NO.

## Final

The Qwen3 adapter-v2 fictional competence suite is prospectively frozen,
unseen, and eligible only for its separately governed one-time execution. No
competence result or scientific-execution permission is asserted.

`QWEN3_ADAPTER_V2_HOLDOUT_FROZEN`
