# EPIC family mining implementation audit

**Date:** 2026-09-28  
**Decision:** `EPIC_FAMILY_MINING_IMPLEMENTATION_READY`  
**Real-source mining executed:** no; synthetic unit fixtures only

## Scope reviewed

The implementation was checked against Tasks 144, 145, 149, 153, 159,
161, 162, and 163, plus the existing
`src/av_trace_mini_pilot_families/` framework. No Task-164 result existed
during the audit; the active canonical index remained incomplete.

Owned artifacts are limited to the new EPIC family-mining package, two
scripts, focused tests, the design, rehearsal plan, this audit, and the Task
165 result. The active index root, active checkpoints, source media,
prescreen forms, and prior family outputs were not edited.

## Findings

### Complete-index gate

`load_canonical_epic_index` requires a full, non-smoke, self-consistent EPIC
index and frozen plan/count bindings. It fails before opening checkpoint
payloads when top-level artifacts are missing. The observed active root had
only `segment_manifest.json`, `resource_manifest.json`, and an incomplete
checkpoint tree, so no mining command was executed.

### Semantic-label firewall

Initial mining accepts only the canonical index adapter and a CLIP text
encoder. It has no prescreen or official-annotation parameter. The adapter
rejects EPIC action/narration/EPIC-SOUNDS semantic field names and
annotation-vault path components. Human semantic prescreen data is joined only
after initial machine leads exist.

### Substantive event routing

The implementation uses:

- OpenCV visual change plus CLIP event/static-text prompt contrasts;
- Whisper ASR observations without copying transcripts into proposal answers;
- AST observations with generic/speech labels separated from possible
  non-speech events.

It records separate hypotheses for dynamic non-text visual,
board/OCR/static/overlay, speech, and non-speech. Scores remain routing hints,
not semantic claims.

### Structural candidate constraints

- Exactly two leads are required for each of `P27_101` and `P28_103`.
- One-hop records are forced to `near_local`.
- Multi-hop records require two component claim placeholders, a composed
  claim placeholder, and one of three allowed event relations.
- Distinct intervals alone cannot establish multi-hop.
- Every output tier must be P0, P1, or P2.
- H tiers, accepted-family flags, active interventions, and scientific
  execution authority are rejected by validation.

### Human-prescreen and development boundaries

Normal output requires a schema-valid, trained-human-completed Task-153
prescreen with READY/pass results for both sources. Dynamic visual and ambient
authoring additionally require that the source prescreen contain a positive
human event in the corresponding category. Interval-overlapping facts can
strengthen scaffolding but do not validate the lead.

Development-only mode can emit proposals after the full index exists but is
hard-coded as ineligible for Gate A. Its dynamic/ambient authoring assistance
remains blocked without human observations.

### Risks and Task-145 templates

Every lead includes flags for repeated events, participant/kitchen leakage,
transcript, OCR/static/overlay, narration, and annotation-vault prohibition.
Each also carries an inert Task-145 C/B/R/N template with fixed action index 4,
matched R/N checkpoint semantics, mechanism-specific ITT language, and no
active intervention.

## Validation

The following safe checks were run without mining the active index:

```text
PYTHONPATH=src pytest -o addopts='' -q tests_epic_family_mining
18 passed

PYTHONPATH=src pytest -o addopts='' -q \
  tests_epic_family_mining tests_mini_pilot_families
31 passed

ruff check src/av_trace_epic_family_mining \
  scripts/build_epic_family_candidates.py \
  scripts/verify_epic_family_candidates.py \
  tests_epic_family_mining
All checks passed

python -m py_compile src/av_trace_epic_family_mining/*.py \
  scripts/build_epic_family_candidates.py \
  scripts/verify_epic_family_candidates.py
PASS

python -m json.tool data/rehearsal_plan/epic_family_mining_v1.json
PASS

PYTHONPATH=src python scripts/build_epic_family_candidates.py --show-plan
PASS; no index read
```

Focused tests cover incomplete-index failure, smoke-index rejection, complete
fixture loading, annotation-vault path rejection, exact two-lead accounting,
four-way modality classification, one-hop/near enforcement, compositional
multi-hop placeholders, P-tier-only validation, Task-145 inert templates,
development Gate-A exclusion, missing-prescreen failure, and verifier
fail-closed behavior.

## Current operational status

- Active canonical EPIC index complete: no.
- Task-164 completion artifact present: no.
- Human EPIC semantic prescreen complete: no.
- Real EPIC candidate mining run: no.
- Synthetic in-memory miner tests: yes.
- Candidate output written: no.
- H1/H2 assigned: 0/0.
- Active interventions: 0.
- Gate A decision changed: no.

The code is ready for later use after the active index is complete. Normal
candidate input remains additionally blocked on a completed human prescreen.

**Final: `EPIC_FAMILY_MINING_IMPLEMENTATION_READY`.**
