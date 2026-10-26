# P23_102 development rehearsal runner v1

**Frozen:** 2026-10-14  
**Runner:** `scripts/run_p23_102_acquire_ground_act_rehearsal.py`  
**Attestation:** `data/restricted/p23_102_acquire_ground_act_rehearsal_v1/adapter_attestation.json`  
**Status:** validation-ready; execution fail-closed

## Boundary

This runner implements the already frozen P23_102 Acquire / Ground / Act
development rehearsal. It does not establish strong model competence, H2,
human family validity, a causal result, or Gate A. The P23 bundle is
machine-provisional and not human validated. All P23 derivatives remain one
development source group and are ineligible for a future test split.

The current Qwen 2.5 1.5B competence record says
`LEARNED_AGENT_INCOMPLETE`. The current family registry also has no accepted
family or accepted SES and assigns no Gate A credit. Therefore:

- `--validate-only` may return `READY`;
- `--plan` may emit the complete frozen assignment plan;
- `--execute` returns `EXECUTION_NOT_AUTHORIZED`; and
- no live model inference or media decoding is performed by validation or
  planning.

The execution code path exists so the protocol and output contract can be
tested with synthetic/mock models and backends. It is not an authorization
bypass.

## Exact matrix

The only system rows are:

1. `direct_long_context`
2. `single_shot_rag`
3. `learned_react`
4. `learned_evidence_sufficiency`

Each row is represented across `C`, `B`, `R`, and `N` for both:

- `SILENT_ROUTE_WITHHOLDING`
- `EXPLICIT_CHANNEL_OUTAGE`

Direct long-context `R/N` rows are frozen
`STRUCTURALLY_INELIGIBLE_BEFORE_ASSIGNMENT`; they receive no synthetic
outcome. All staged `R/N` runtime and protocol failures remain in the
intention-to-treat denominator with positive endpoints set to zero.

The two mechanisms are never pooled for a primary restoration contrast.
Silent withholding omits the registered route and deterministic derivatives.
Explicit outage returns the registered typed unavailable response. Their
assignments, trajectories, failures, denominators, and aggregate tables remain
separate.

## Exogenous restoration v2

The primary restoration event is a runner event, not a model action.

- index base: zero
- fixed action index: `4`
- boundary: after four completed action/response cycles and before the fifth
  model decision
- checkpoint cost: `0.0`
- dependency on action identity: none
- dependency on system identity: none
- dependency on correctness or output: none
- dependency on `get_channel_status`: none

For every staged family/mechanism/system cell, the runner constructs one
blocked prefix. It canonicalizes the four public cycles plus the neutral
checkpoint, then creates fresh `R` and `N` continuations. The public bytes and
checkpoint hash are identical through the fork. The registered route is
opened evaluator-privately only in `R`; it remains blocked in `N`.

If the prefix terminates early, that terminal prefix is copied to both
assignments, both assignments remain in ITT, and the pair difference is zero.
No missing pair is dropped.

## Adapter

`P23FullTimelineBackendAdapter` subclasses the existing
`src/av_trace_scale1b_agent/backend.py:FullTimelineBackend` contract while
loading the P23 full-timeline index and machine-provisional bundle instead of
the historical NOAA paths.

It preserves:

- the existing public tool vocabulary;
- the 10-step and 12.0-cost budgets;
- learned SigLIP2 and CLAP query encoders when execution is authorized;
- BM25 over quality-gated searchable speech records;
- non-citable search pointers;
- citable acquired observation IDs;
- route suppression, explicit typed outage, and hidden restoration;
- evaluator-private evidence-handle mapping; and
- existing controller and grounded-finalization functions.

The adapter deliberately does not manufacture semantic captions. The current
P23 index provides source-derived visual/audio vectors and inventory-only ASR,
but no human-valid semantic visual or ambient descriptions. A visual or
ambient observation therefore states only that the source interval was
acquired and that semantic text is unavailable. This is sufficient to test
plumbing and citation identity, but insufficient for semantic scientific
execution.

## Modes

```bash
PYTHONPATH=src python scripts/run_p23_102_acquire_ground_act_rehearsal.py \
  --repo-root . --validate-only
```

Validates the frozen configuration, source/index/bundle bindings, hashes,
adapter attestation, exact rows, arms, mechanisms, budgets, checkpoint, model
manifests, and competence record. It does not load model weights or media.

```bash
PYTHONPATH=src python scripts/run_p23_102_acquire_ground_act_rehearsal.py \
  --repo-root . --plan
```

Emits all 640 current row slots: 20 families × 2 mechanisms × 4 systems × 4
arms. Counterbalancing is deterministic from the frozen seed. Structural
ineligibility and ITT retention are explicit fields.

```bash
PYTHONPATH=src python scripts/run_p23_102_acquire_ground_act_rehearsal.py \
  --repo-root . --execute
```

Fails closed under the current artifacts. A future superseding attestation
would need, at minimum, a passed learned-agent competence gate and acceptable
bundle semantics. Human validity, H2, source-disjoint evaluation, and Gate A
remain separate scientific requirements and are not implied by mechanical
authorization.

## Frozen outputs

An authorized run writes restricted `0700` directories and `0600` files using
temporary files, `fsync`, and atomic rename:

- `run_manifest.json`
- `assignments.jsonl`
- `raw_trajectories.jsonl`
- `raw_model_calls.jsonl`
- `factor_model_raw_outputs.jsonl`
- `citation_outputs.jsonl`
- `r_n_prefix_pairs.jsonl`
- `episode_metrics.jsonl`
- `metric_ready_records.jsonl`
- `failure_ledger.jsonl`
- `aggregate_metrics.json`
- `replay_manifest.json`
- `file_inventory.json`

Raw model text is retained. Factor/controller public-state outputs are
retained. Citation records include the acquired observation catalog and
validation result. The replay manifest hashes public trajectories and records
R/N prefix integrity. Completed output directories are not overwritten.

There is no deterministic answer substitution. Malformed, timeout, OOM,
process, tool, budget, no-finalization, citation, and protocol failures remain
typed failures.

## Interpretation

`READY` from validation means only that the development runner, adapter
contract, hashes, plan, and fail-closed controls are coherent against the
current local artifacts on 2026-10-14. It is not a model result and does not
upgrade the machine-provisional P23 families.

Completion token: `P23_102_REHEARSAL_RUNNER_READY`
