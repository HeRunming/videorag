# CaptainCook4D family mining implementation audit

**Task:** 190  
**Date:** 2026-10-10  
**Decision:** `CAPTAINCOOK4D_FAMILY_MINING_IMPLEMENTATION_READY`  
**Real-source mining executed:** no  
**Candidate output written:** no

## Scope

The implementation was reviewed against Tasks 144, 145, 149, 153, 165, 166,
167, and 188. Task189 was concurrently preparing the canonical CaptainCook4D
index. Task190 treated its package, plan, scripts, tests, checkpoints, and
output root as read-only.

Task190 owns only:

- `src/av_trace_captaincook4d_family_mining/`;
- `scripts/build_captaincook4d_family_candidates.py`;
- `scripts/verify_captaincook4d_family_candidates.py`;
- `tests_captaincook4d_family_mining/`;
- the Task190 design, rehearsal plan, audit, and result.

The implementation did not edit Task189 code or touch its active output.

## Findings

### Task189 gate

The candidate loader first requires the terminal result token
`CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_READY`. It fails before reading canonical
index artifacts when that result is absent. If the token exists, it then
requires the exact full, non-smoke canonical index, three source/hash/group
bindings, twelve checkpoints, artifact/self hashes, permissions, plan/count
bindings, and a clean index terminal boundary.

The Task189 result did not exist during validation. A deliberate
development-mode probe returned:

```text
TASK189_READY_RESULT_MISSING:
orchestration/results/189_captaincook4d_wave0_full_timeline.txt
```

No candidate file or candidate directory was created.

### Semantic firewall

Initial mining accepts only canonical OpenCV, CLIP, Whisper, and AST
observations. The adapter rejects semantic CaptainCook4D field names and
annotation/task-graph/error-label path fragments. Provenance records false for
action annotations, steps, task graphs, recipe labels, and error labels.

Task153 artifacts are accepted only by the post-mining authoring layer. Direct
inspection accepts only the exact local source media paths supplied by the
canonical index plan.

### Exactly two substantive leads per source

Registry validation requires:

- three exact source IDs;
- exactly two ordinal leads per source;
- six total;
- only P0/P1/P2 machine tiers.

Lead selection prioritizes dynamic procedure motion and concrete non-speech
AST routes, with static/text risk penalized. The second lead uses a coherent
multi-hop structure when available or a distinct one-hop/local fallback.

One-hop/far is rejected. Multi-hop requires component claims, a composed
claim, a procedure coherence basis, and an explicit arbitrary-pairing
prohibition. Far is available only to multi-hop pairs separated by at least
120 seconds.

### Bounded substantive authoring assistance

The authoring layer can decode selected raw-local intervals with:

- at most 32 seconds of frames per component;
- at most 32 seconds of audio per component;
- at most 12 sampled frames per component;
- no persisted media derivative.

It emits nonempty provisional question, answer, claim, and evidence
hypotheses. The helper does not generate semantic action names, captions, OCR,
or sound identities. Audio semantics explicitly require human listening.
Every scaffold is marked `MACHINE_EXPERT_PROVISIONAL` and
`human_semantic_validation_status=NOT_PERFORMED`.

### Risks

Every lead must include:

- machine-suspected recurrence and full-source closure;
- person leakage;
- environment/kitchen leakage;
- speech/ASR substitution;
- caption/OCR/package-label/text substitution.

Machine recurrence is explicitly not adjudication.

### Task153 modes

Normal Gate-A mode fails closed without a completed, trained-human, READY,
all-source-pass Task153 bundle. Development mode may author provisional
hypotheses after Task189, but is permanently Gate-A and future-test
ineligible.

### Task145

All leads include inert C/B/R/N templates with action index 4 and the
mechanism-specific R-N ITT boundary. Validation rejects active or executed
interventions.

## Validation

Safe checks were run without consuming Task189 output:

```text
PYTHONPATH=src pytest -o addopts='' -q \
  tests_captaincook4d_family_mining
13 passed

ruff check src/av_trace_captaincook4d_family_mining \
  scripts/build_captaincook4d_family_candidates.py \
  scripts/verify_captaincook4d_family_candidates.py \
  tests_captaincook4d_family_mining
All checks passed

python -m py_compile \
  src/av_trace_captaincook4d_family_mining/*.py \
  scripts/build_captaincook4d_family_candidates.py \
  scripts/verify_captaincook4d_family_candidates.py
PASS

python -m json.tool \
  data/rehearsal_plan/captaincook4d_family_mining_v1.json
PASS

PYTHONPATH=src python \
  scripts/build_captaincook4d_family_candidates.py --show-plan
PASS; plan matches committed JSON and Task189 is not read
```

The fail-closed not-run probe exited 2 with the missing Task189 READY result,
reported `candidate_generation_executed=false`, and left the candidate output
absent.

## Current status

- Task189 READY result available during Task190 implementation: no.
- Canonical Task189 index consumed by Task190: no.
- Raw CaptainCook4D frame/audio inspection run by Task190: no.
- Real candidate mining run: no.
- Candidate registry written: no.
- Synthetic fixtures used: yes.
- Human Task153 prescreen completed: no.
- H1/H2 assigned: 0/0.
- Active interventions: 0.
- Gate A changed: no.

The implementation is ready for later explicit execution after Task189. Gate-A
mode remains additionally blocked on human Task153 completion.

**Final: `CAPTAINCOOK4D_FAMILY_MINING_IMPLEMENTATION_READY`.**
