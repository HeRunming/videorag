# P23_102 Technical Smoke v2 Freeze

**Frozen:** 2026-10-14  
**Decision token:** `P23_102_TECHNICAL_SMOKE_V2_FROZEN_NOT_AUTHORIZED`  
**Status:** `TECHNICAL_SMOKE_ONLY_FROZEN_NOT_AUTHORIZED`

## Boundary

This is a **prospective, superseding technical-smoke freeze** for the repaired current P23_102 plumbing. It supersedes the v1 rehearsal only for a future technical smoke. It does not edit or invalidate the old v1 configuration or attestation, is not the 640-assignment run, and is not a scientific protocol result.

The freeze itself runs no model and decodes no media. Hash matches and test passes do not authorize execution. `execution_authorized` remains `false` until separate, versioned **live-wiring** and **red-team** authorizations bind this exact freeze and an output root.

Machine-provisional REPAIR families and a weak or machine-provisional model are explicitly permitted as routing fixtures for this smoke only. No output may support claims about answer quality, competence, performance, system superiority, causality, H2, Gate A, accepted SESs, human validity, source generalization, or scientific readiness.

## Exact fixtures

The selection rule is outcome-free: take the first structurally valid REPAIR V+A near-local family and the first structurally valid REPAIR V+A coherent-far family by frozen source-registry rank.

| Selection ID | Family ID | Registry rank | Structural class | Frozen records |
|---|---|---:|---|---|
| `P23S2-LOCAL-VA-01` | `mpf.5814848825c9fad469ad` | 9 | local, near, one-hop V+A | `P23_102.fine.000065` |
| `P23S2-FAR-VA-01` | `mpf.bfda23807de4cb85f04b` | 1 | far-separated, multi-hop V+A | `P23_102.fine.000009`, `P23_102.fine.000340` |

Both remain `REPAIR`, are not accepted families or SESs, and have no human-valid answer, support, or necessity semantics. Both have frozen `SILENT_ROUTE_WITHHOLDING` and `EXPLICIT_CHANNEL_OUTAGE` interventions and C/B/R/N state surfaces.

## Minimal 32-assignment matrix

Required systems are:

1. `single_shot_rag`
2. `learned_react`
3. `learned_evidence_sufficiency`

Direct long context is excluded to preserve the 32-assignment cap and because it cannot test staged R/N restoration. A later authorization may use it only as endpoint sanity, never as an R/N causal cell.

The smoke contains exactly **32 assignments**:

- 24 assignments: R and N for every `2 families × 2 mechanisms × 3 systems` cell;
- 8 assignments: one C/B endpoint probe per family × mechanism, balanced across the three systems.

This is the minimum plan that exercises every required system under both mechanisms and both structural family types, while still probing C/B endpoints. The authoritative order and every assignment ID are in `data/rehearsal_plan/p23_102_technical_smoke_v2.json`; reordering or appending retries as assignments is prohibited.

C/B endpoint probes are allocated as follows:

| Family | Mechanism | C/B system |
|---|---|---|
| local | silent withholding | `single_shot_rag` |
| local | explicit outage | `learned_react` |
| far | silent withholding | `learned_evidence_sufficiency` |
| far | explicit outage | `single_shot_rag` |

R/N is retained for every system in every family/mechanism cell. Each R and N continuation must use a fresh continuation session forked from one byte-identical blocked public prefix. Every assignment also uses a fresh provider session and isolated cache namespace.

## Canonical checkpoint

The only authoritative serialization is the implementation in `src/av_trace_scale1b_agent/checkpoint.py`:

```text
UTF-8 JSON; json.dumps(sort_keys=true,separators=(',',':'),ensure_ascii=false,allow_nan=false); SHA-256 over bytes with no trailing newline
```

Canonical event bytes:

```json
{"cost":0.0,"event_type":"protocol_checkpoint","event_version":"2.0.0","message":"Scheduled protocol checkpoint completed."}
```

Canonical event hash:

```text
sha256:c580c16af6401b4d12df1d39085bbddee6f63e6d81772f6b3186a0fcc84c996c
```

The config, attestation, future prefix-pair rows, and future run manifest must use that exact hash. Alternate hashes from older bundle records are not authoritative for this smoke. The event is delivered after four completed action/response cycles and before the fifth model decision. It is not a model action, costs zero, reveals no restoration, and cannot be triggered by `get_channel_status`.

## Frozen implementation and artifact binding

The JSON freeze and attestation bind the repaired current hashes of:

- runner;
- backend;
- controller;
- isolated model process;
- checkpoint serialization/hash implementation;
- evaluation and metric helpers;
- public schemas;
- learned retrieval;
- ReAct, evidence-sufficiency, generator, and repair prompts;
- exact source manifest;
- full timeline index, build/resource/segment/observation/checkpoint manifests;
- machine-provisional family/evidence/intervention/state-surface/source-split bundle;
- generator/controller and retrieval model manifests;
- restoration v2 protocol and metric/output schemas.

Any mismatch is an immediate pre-invocation abort. The attestation includes process and checkpoint modules explicitly; neither may inherit the stale v1 hashes.

## Budgets

The tool contract remains fixed at 10 steps and cost 12.0. Generation is deterministic with a 24,576-token input cap, 512 output tokens, and one 512-token schema repair.

A provider generation request, including repair, counts as one model invocation. The frozen ceiling is:

- at most 11 provider invocations per assignment;
- at most 352 for the complete 32-assignment smoke;
- no retry beyond the single schema repair;
- one assignment at a time;
- 120 seconds per provider call and 900 seconds per assignment.

The ceiling is deliberately conservative; single-shot RAG normally needs at most two generator requests. It is a hard safety cap, not a target.

## Fail-closed aborts

Abort before starting the next assignment for any binding, order, checkpoint-hash, R/N-prefix, session-isolation, private-field, cache-namespace, output-root, invocation-budget, raw-retention, or replay-integrity failure. Also abort when the configured cumulative threshold is reached for model process crashes/timeouts, malformed-after-repair outputs, or tool-contract violations.

Partial records must remain on disk. A failed or malformed attempt may not be replaced with deterministic answer text or deleted to make the smoke appear clean.

## Non-evaluable outputs

Machine-provisional semantics, process failures, timeouts/OOM, malformed-after-repair output, early terminal before checkpoint, no finalization, over-budget outcomes, tool failures, missing/invalid citations, and structural ineligibility are non-evaluable for answer quality.

They must still retain, when serializable:

- assignment and terminal ledger rows;
- public trajectory;
- all raw attempts or raw-byte/text hash;
- citation validation row;
- metric-ready row with answer-quality fields null;
- replay and file-inventory hashes.

They are neither correct nor incorrect scientific answers. No positive or negative scientific endpoint may be imputed.

## Plumbing-only success

A future authorized smoke succeeds only if:

- all frozen hashes match before invocation;
- the exact 32 IDs appear in exact order;
- all 12 R/N pairs use fresh sessions and byte-identical public prefixes through the canonical checkpoint;
- both mechanisms produce their frozen surface behavior;
- raw failures are retained;
- citation validation references acquired observation IDs rather than search pointers;
- all per-assignment terminal ledgers, metrics records, replay records, and required output files close under the inventory;
- runtime leakage is reported as `NOT_ESTIMABLE_SINGLE_SOURCE`.

Unsupported answers, abstentions, empty evidence under a correctly blocked surface, weak behavior, and retained non-evaluable outputs do not fail the smoke by themselves. Conversely, fluent or correct-looking answers do not make it pass.

## Leakage boundary

The existing bundle `leakage_gate.json` is a construction/provenance firewall. It is not a runtime classifier result. Because P23_102 provides only one source group, the runtime leakage classifier remains:

```text
NOT_ESTIMABLE_SINGLE_SOURCE
```

It must never be reported as `PASS`. Byte-identical R/N prefixes are a required mechanical invariant, not an estimate of source-general runtime leakage.

## Authorization

This freeze is intentionally not executable by itself:

```text
execution_authorized = false
live_wiring_authorization_present = false
redteam_authorization_present = false
```

Required future approvals must separately cover live runner/model wiring and red-team checks for private-field exposure, session/cache isolation, and outage/restoration leakage. No competence, performance, causal, H2, Gate, or human-validity claim becomes permissible even if such a technical smoke later passes.
