# EPIC P23_102 development-only family-mining pipeline v1

**Repair date:** 2026-10-14  
**Implementation token:** `EPIC_P23_102_FAMILY_MINING_PIPELINE_READY`  
**Repair token:** `EPIC_P23_102_FAMILY_MINING_REPAIR_READY`  
**Acceptance status:** no family, SES, H tier, or Gate-A credit is assigned

## 1. Purpose and repaired status

This package deterministically mines machine-provisional structural leads from
the completed canonical full-timeline index for EPIC source `P23_102`. The
October 14 repair is prospective and follows the binding zero-candidate audit.
It does not reinterpret the prior zero as evidence, inspect semantic
annotations, decode media, run models, or manually inspect content.

The miner can emit:

- `V+A` structural leads without using untrusted ASR;
- `V+S` and `V+S+A` leads only when actual quality-gated searchable speech is
  present at every required speech component;
- coherent far/multi-hop leads from all eligible separated fine-window pairs,
  using either a quality-gated speech bridge or a speech-free V+A structural
  bridge.

Every output remains a machine hypothesis. `KEEP`, `REPAIR`, and `REJECT` are
review priorities, not acceptance decisions or modality-necessity findings.

## 2. Input and semantic firewall

Mine mode consumes the six validated files beneath
`data/restricted/epic_p23_102_full_timeline_index_v1/` and requires source
`P23_102`, build status `COMPLETE`, no smoke limit, and the index-only terminal
boundary. Plan mode still reads no index and writes no restricted output.

Allowed inputs are exact intervals, searchable SigLIP2 and CLAP vectors,
quality flags, audio RMS, quality-gated Whisper/BM25 records, and deterministic
temporal/recurrence computations. EPIC action, narration, sound, task,
benchmark, human, and prior-family annotations remain sealed. Inventory-only
ASR text is counted for diagnostics but is never promoted to searchable and is
never attached to a candidate.

## 3. Source-calibrated visual-transition rule

The impossible fixed `0.18` floor is removed. For every run, the miner computes
its transition distribution over **all searchable fine visual windows**:

`max(1 - cosine(previous,current), 1 - cosine(current,next))`

The frozen, non-label-informed threshold is:

`max(0.02, p95_linear, median + 2 * MAD)`

where MAD is the median absolute deviation of the same source-derived
transition values. The absolute `0.02` term is a robust minimum effect; p95
prevents a source with generally small embedding motion from being compared to
an impossible global scale; the median-plus-MAD term protects against a flat or
pathological upper tail. The rule, interpolation, distribution summary,
components, selected threshold, and pass count are persisted in
`calibration_diagnostics.visual_transition`.

For the completed index the selected threshold is `0.08093195`: p95 is
`0.08093195`, the robust-MAD value is `0.06970799`, the absolute floor is
`0.02`, and 45 of 892 fine windows pass. These are routing measurements, not
semantic transition labels.

## 4. Local structural generation

A local row first clears the calibrated visual threshold. It then follows one
of two routes:

1. **Speech route:** overlap an actual quality-gated searchable speech chunk
   and clear the frozen speech-quality floor. It may be `V+S+A` only if aligned
   audio also clears the audio structural rule.
2. **Speech-free route:** when no quality-gated speech overlaps, permit a `V+A`
   lead only if aligned audio clears novelty, RMS, near-silence, and sparse
   searchable-speech checks. This never treats inventory-only ASR as speech.

Local rows are ranked deterministically, deduplicated by the frozen 12-second
center separation, limited to two per 300-second time bin, and capped at 12.
The cap is a review bound, not a quota.

## 5. Correct audio accounting

Audio novelty uses the aligned fine audio window and its immediate neighbors
in the independently time-sorted audio sequence. A precomputed segment-to-
position map prevents repeated scans and makes the accounting explicit.

The miner records, separately:

- novelty distribution and novelty pass count;
- RMS pass count;
- not-near-silence count;
- joint novelty/RMS/silence pass count;
- joint structural plus sparse-searchable-speech pass count.

Audio eligibility is always the conjunction of those stated gates. Empty final
candidate sets are not reported as proof that no audio window passed. CLAP
geometry does not identify a sound or establish answer-bearing work.

## 6. Decoupled far-pair generation

Far generation no longer uses local rows or a 40-anchor subset. It evaluates
all unordered searchable fine-window pairs separated by at least 120 seconds.
The funnel is:

1. temporal separation;
2. visual continuity cosine at least `0.88`;
3. one of:
   - quality-gated speech at both components plus a shared salient term, or
     visual continuity at least `0.96`; or
   - audio structural floors at both components plus cross-window audio
     continuity cosine at least `0.80`.

The speech-free route emits `V+A`, never invents speech work, and remains
`REPAIR` or `REJECT` pending human review. Distance alone is never credited.
Every far lead includes exact handles, measured continuity, an unfilled
source-world coherence hypothesis, recurrence routes, and substitution risks.

To prevent combinatorial floods, far rows are ranked deterministically and
then limited to one use per endpoint, two leads per separation bucket, two per
600-second first-component bin, and eight total. Rejection counts for each
of these diversity controls are persisted.

## 7. Sparse-speech policy

The completed index has 119 speech chunks but only one quality-gated searchable
chunk. The repaired miner reports total, quality-pass, searchable, and
inventory-only counts. It reports `inventory_only_promoted_to_searchable: 0`.

Consequences:

- `V+S` and `V+S+A` require actual quality-gated speech handles;
- inventory-only chunks cannot create local or far speech routes;
- lack of emitted speech leads is not a source-level claim that speech work is
  absent;
- V+A local and far structural leads may still be emitted from visual/audio
  evidence, subject to the stated floors and caps.

## 8. Candidate semantics and governance

Candidates retain exact timestamps, source binding, unfilled atomic claim
templates, modality-work hypotheses, recurrence checks, alternative routes,
and shortcut/substitution risks. They do not fabricate modality necessity.

The registry always keeps:

- accepted family count `0`;
- accepted SES count `0`;
- H-tier count `0`;
- Gate-A credit count `0`;
- future-test eligibility `false`.

A source-uniform human prescreen remains mandatory before any separate future
acceptance process. It must use the same form and full-source exposure policy
for every machine lead and complete full-source recurrence review. Prescreen
labels cannot feed back into generation or ranking, and even a completed
prescreen does not accept or tier a lead in this tool.

## 9. Diagnostics and validation

Each registry contains:

- source calibration diagnostics;
- exact local and all-fine far filter-flow counts;
- speech and audio quality accounting;
- deterministic diversity rejection counts and caps;
- profile and independent-work accounting that avoids source-level absence
  claims;
- candidate and registry payload hashes.

Validation checks hashes, exact record/timestamp bindings, profile-required
modalities (including speech-free `V+A`), far coherence structure, the repair
completion token, provisional statuses, and the no-acceptance boundary.

## 10. Commands

```bash
python tools/epic_p23_102_family_mining_v1.py --mode plan
pytest -q tooling/tests/test_epic_p23_102_family_mining_v1.py
python tools/epic_p23_102_family_mining_v1.py \
  --mode mine \
  --output data/restricted/epic_p23_102_family_mining_v1_dev/candidate_registry.json
python tools/epic_p23_102_family_mining_v1.py \
  --mode check \
  --registry data/restricted/epic_p23_102_family_mining_v1_dev/candidate_registry.json
```

The mine command writes the machine-provisional registry. A successful check
prints `EPIC_P23_102_FAMILY_MINING_REPAIR_READY`.

**EPIC_P23_102_FAMILY_MINING_REPAIR_READY**
