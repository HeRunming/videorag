# Scale-1B learned generation/agent pilot: Go/No-Go

**Date:** 2026-09-20  
**Stage:** `MACHINE_ADJUDICATED_PROVISIONAL`  
**Scope:** Task 110 bounded actual-Qwen smoke and learned-agent readiness gate

## Executive decision

```text
LEARNED_GENERATION_READY
LEARNED_AGENT_INCOMPLETE
END_TO_END_DIAGNOSTIC_INCONCLUSIVE
DATA_SCALE_UP_HOLD
FINAL_BENCHMARK_NOT_YET_VALIDATED
```

The pinned Qwen2.5-1.5B-Instruct snapshot loaded offline and produced a valid,
model-authored grounded answer on the excluded `r017` development family. The
two learned controllers did not both satisfy the preregistered completion
floor. Per the owner-specified stopping rule, no eligible-family experiment was
run and no further prompt tuning was performed.

## What was implemented

Task 110 now contains:

- a strict Qwen technical gate bound to the exact Task 109 manifest;
- an offline JSONL subprocess for real Qwen inference;
- versioned grounded-generator, ReAct, evidence-sufficiency, and one-repair
  prompts;
- a public action-menu/action-index controller interface;
- opaque public claim, pointer, and observation handles;
- a matched `F-CTRL` / `F-VA` full-timeline backend;
- `CLEAN` / `BLOCKED` / `RESTORED` and no-trigger mechanics;
- structured final verdict, answer, claim/citation, missingness, sufficiency,
  recovery-intent, and stop-rationale validation;
- typed malformed, timeout, OOM, crash, and over-budget handling;
- per-trajectory atomic checkpoints and strict metric/replay verification;
- the frozen 185-case full-pilot contract, which was not executed because the
  learned-agent smoke failed.

No deterministic answer was substituted for a failed Qwen output. The
deterministic policies exist only as explicit protocol controls in the frozen
contract.

## Actual-Qwen smoke

The final bounded smoke is stored at:

```text
data/restricted/scale1b/ga_pilot/actual_qwen_smoke.json
```

It uses:

```text
Qwen/Qwen2.5-1.5B-Instruct
revision 989aa7980e4cf806f80c7fef2b1adb7bc71aa306
CPU / bfloat16 / offline / do_sample=false
```

The family is permanently excluded from scientific evaluation:

```text
noaa01-r017-north-atlantic-basin
scientific_evaluation_eligible=false
exclusion_reason=PROMPT_DEVELOPMENT_ONLY_PER_USER_BOUNDARY
```

### Outcomes

| System | Status | Final verdict | Actual Qwen calls | Outcome |
|---|---|---:|---:|---|
| Grounded generator | completed | answer | 1 | Strict JSON, public claim handle, real citation |
| Learned ReAct | typed failure | none | 6 | Four valid actions, then repeated search; one repair also malformed |
| Learned evidence-sufficiency | typed failure | none | 5 | Chose search/status/finalize, but finalizer remained invalid after one repair |

The generator's claim and citation were valid. Its display-level
`answer_text` was awkward, reinforcing that structured atomic claims—not free
prose—must remain primary.

## Exact controller failures

### Learned ReAct

The controller selected:

1. speech search;
2. three distinct speech observations;
3. an already-used search while additional unobserved pointers remained.

The no-progress guard correctly rejected the repeated search. Qwen's one
allowed repair response was malformed JSON, so the trajectory failed closed:

```text
MALFORMED_AFTER_REPAIR at turn 4
```

This is a controller termination/no-progress failure, not a retrieval failure:
the accepted speech evidence had already been acquired.

### Learned evidence-sufficiency

The controller selected:

1. speech search;
2. channel-status check;
3. finalize.

The model-authored grounded finalization then used wrong field names and
invented citation placeholders/answer content. One allowed repair still failed
the exact schema:

```text
MALFORMED_AFTER_REPAIR
phase=grounded_finalization
turn=2
```

No fallback answer was fabricated.

## Why the eligible two-family pilot was not run

The owner specified a hard stop:

> Run the two untouched families only if generator, ReAct, and
> evidence-sufficiency all complete the final bounded smoke.

Only the generator completed. Running on `r004/r016` or other eligible families
would therefore violate the preregistered competence gate and consume
evaluation examples during further prompt development.

## Interpretation

This result supports:

- real learned grounded-generation infrastructure;
- real Qwen action selection through a constrained public interface;
- strict fail-closed behavior;
- evidence that a 1.5B text controller is not yet reliable enough for the
  planned agent comparison under the current prompting/one-repair budget.

It does **not** support:

- learned-agent readiness;
- end-to-end diagnostic separation;
- recovery superiority;
- a data-scale-up decision;
- human-valid benchmark claims.

## Recommended next step

Do not tune on another evaluation family. Before resuming scientific
evaluation, use a separate synthetic/development set to improve:

1. valid controller finalization after evidence acquisition;
2. no-progress recognition;
3. claim-slot coverage updates;
4. exact citation copying;
5. typed abstention under failed finalization.

Then rerun the same excluded `r017` competence gate. Only after all three
systems complete should the frozen two-family diagnostic be opened.
