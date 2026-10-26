# EPIC P23_102 zero-candidate audit

**Date:** 2026-10-14  
**Decision:** `MINER_REPAIR`  
**Current registry disposition:** keep its candidate set at zero until repair and rerun  
**Completion token:** `EPIC_P23_102_ZERO_CANDIDATE_AUDIT_READY`

## 1. Scope and constraints

This audit explains why the completed P23_102 family miner emitted zero
candidates. It inspected:

- the six canonical full-index manifests;
- all four checkpoint JSON documents and their manifest bindings;
- the frozen miner plan and miner code;
- the completed candidate registry.

The audit recomputed only lightweight structural diagnostics from JSON. It did
not run a model, decode or inspect media, open semantic annotations, make a
semantic claim, or fabricate a candidate.

The machine result is reproducibly zero, but it is **not** a trustworthy
source-level claim that independent modality work is absent. The primary
recommendation is `MINER_REPAIR`, with secondary speech-index review.

## 2. Executive finding

The exact generation funnel is:

| Stage | Count |
|---|---:|
| Searchable fine visual windows | 892 |
| Visual transition `>= 0.18` | **0** |
| Transition windows with searchable speech | 0 |
| Raw local rows | 0 |
| Retained local rows | 0 |
| Far anchor pool, which is derived only from raw local rows | 0 |
| Exact far pairs tested | 0 |
| Final candidates | **0** |

The first and decisive failure is the visual transition gate. The miner uses
the maximum cosine distance to an immediate visual neighbor. Across all 892
fine visual windows:

- maximum: `0.0962067246`;
- p99: `0.090018509`;
- p95: `0.0809319466`;
- median: `0.0362027884`;
- frozen minimum: `0.18`.

Thus the frozen threshold is almost 1.87 times the observed maximum and cannot
pass any window in this completed index. This is an over-strict,
index-uncalibrated miner gate.

A second severe bottleneck is speech routing: all 119 ASR chunks have nonempty
machine text, but only one chunk passes the frozen quality gate and is
searchable (`1/119`, or `0.8403%`). The visual gate would still force zero even
with this one chunk, but sparse speech also prevents a meaningful far join and
makes source-level absence claims unsafe.

## 3. Index and checkpoint integrity

No path or schema mismatch was found.

- Build status is `COMPLETE`; smoke mode is absent.
- The checkpoint manifest has four records: source probe, speech ASR, SigLIP2
  visual, and CLAP audio.
- Every checkpoint file hash, size, record count, and payload hash matches its
  manifest.
- Checkpoint speech core fields match the indexed speech documents.
- Checkpoint visual and audio segment documents exactly match the corresponding
  index documents.
- The 892 fine segment IDs match all 892 searchable fine visual IDs and all 892
  searchable fine audio IDs.
- All 1,115 temporal segment IDs match the visual and audio document sets.

Therefore zero is not caused by a missing file, stale path, malformed schema,
record-ID mismatch, or lost vector layer.

## 4. Coverage and speech quality

### 4.1 Visual and audio vectors

| Layer | Fine windows | Searchable | Coverage |
|---|---:|---:|---:|
| SigLIP2 visual | 892 | 892 | 100% |
| CLAP audio | 892 | 892 | 100% |

All audio fine windows pass the RMS floor of `1e-5`, and none is marked
`NEAR_SILENCE`.

### 4.2 Speech

| Measure | Count |
|---|---:|
| Total 30-second chunks | 119 |
| Nonempty machine transcripts | 119 |
| `token_count >= 5` | 88 |
| mean generated-token log probability `>= -0.85` | 3 |
| Pass both frozen quality conditions | 1 |
| Searchable | **1** |

Quality flags are:

- `LOW_GENERATED_TOKEN_LOGPROB`: 116 chunks;
- `TOO_FEW_LEXICAL_TOKENS`: 31 chunks;
- no flags: one chunk.

The mean generated-token log-probability median is `-1.66908217`, p95 is
`-0.923962953`, and the frozen gate is `-0.85`. This does not show a broken
checkpoint; it shows that the current quality policy leaves almost the entire
speech index inventory-only. Since the miner requires searchable speech at
each local component and both far components, speech coverage is structurally
inadequate for its joins.

## 5. Gate-by-gate recomputation

### 5.1 Local V+S generation

The miner applies gates in this order:

1. searchable fine visual window;
2. visual transition `>= 0.18`;
3. overlapping searchable speech;
4. derived speech quality `document_length / 8 >= 0.2`;
5. rank and 12-second center deduplication.

Counts are `892 -> 0 -> 0 -> 0 -> 0`.

For sensitivity only—not as candidate generation—the observed transition
counts are:

| Transition threshold | All visual windows | Also overlap searchable speech |
|---:|---:|---:|
| 0.18 | 0 | 0 |
| 0.10 | 0 | 0 |
| 0.05 | 273 | 2 |
| 0.02 | 675 | 9 |
| 0.01 | 882 | 9 |

This confirms that the zero is threshold-driven, while also showing that merely
lowering the visual floor would not solve the underlying speech-coverage
problem.

### 5.2 Audio structural floors

The registry says no CLAP window clears novelty, RMS, near-silence, and
sparse-ASR floors. JSON recomputation contradicts that explanation:

- 459/892 windows have local-neighbor CLAP novelty `>= 0.16`;
- 892/892 pass RMS and near-silence checks;
- nine fine windows overlap the sole searchable speech chunk;
- five of those nine also pass novelty, RMS, near-silence, and the maximum
  eight searchable-speech-token condition.

No `V+S+A` candidate is warranted from those counts alone: structural CLAP
novelty does not establish answer-bearing non-speech work. But the reason for
zero `V+S+A` is **not** that no audio window clears the stated floors. The
audio-capable windows are never evaluated for candidate attachment because no
visual transition passes first.

### 5.3 Far continuity and joins

The exact implementation builds its far anchor pool only from `local_rows`.
Because local rows are zero, the far anchor pool and far pair count are also
zero. The registry's claim that no pair clears distance and continuity is
therefore stronger than what the code actually tested.

For structural diagnosis, an all-fine-window count gives:

| Far stage | Count |
|---|---:|
| Pairs separated by at least 120 seconds | 371,952 |
| Also visual continuity cosine `>= 0.88` | 61,084 |
| Also visual continuity cosine `>= 0.96` | 289 |
| Continuity pairs with searchable speech at both windows | **0** |
| Final lexical/strong-visual bridge with speech at both windows | **0** |

This does not produce or imply candidates. It shows two independent facts:

1. visual far continuity is plentiful under the miner's own threshold; and
2. the speech join is empty, while the implementation never reaches that join
   because far discovery is coupled to local transition anchors.

Far mining should be decoupled from local V+S generation so its funnel can
report these stages honestly.

### 5.4 Recurrence

Only three unordered fine-window pairs are at least 16 seconds apart and have
visual cosine similarity `>= 0.985`. Recurrence is not a candidate-generation
gate in this miner; it is computed after candidate construction to assign
status and alternative-route risks. It has no causal role in this zero because
no candidate reaches recurrence evaluation.

The 12-second local separation filter and candidate caps also have no causal
role: they execute after raw local rows, of which there are none.

## 6. Registry explanation audit

The registry's counts—892 visual windows read, one searchable speech chunk,
892 audio windows read, zero local rows, zero far rows, and zero
candidates—match recomputation. Several zero explanations do not:

1. **`V+S` explanation is vacuous.** It says every retained V+S route clears
   the stricter audio floor. There are no retained routes. The actual first
   failing gate is the unreachable visual-transition floor.
2. **`V+S+A` and ambient-work explanations are false as structural gate
   statements.** Five windows clear all stated audio structural floors when
   paired with the sole searchable speech chunk. They never reach candidate
   attachment.
3. **Far explanation overstates search coverage.** Exact far search considered
   zero pairs because its anchor pool was empty. It did not independently test
   all far continuity pairs.
4. **`honest_zero` conflates no emitted lead with modality absence.** With no
   media or semantic review, and with structurally inadequate speech coverage,
   this run cannot establish an honest absence of independent speech or
   ambient answer-bearing work.

## 7. Cause classification

### Actual index evidence: **yes**

- Visual/audio index coverage is complete.
- The observed visual transition distribution is entirely below `0.18`.
- Searchable speech coverage is only one chunk.

### Overly strict or buggy miner logic: **yes**

- The visual floor is unreachable for this index.
- Far search is incorrectly conditional on local V+S rows.
- Zero-reason logic derives explanations from empty final profile sets rather
  than measured per-gate failures.

### Path or schema mismatch: **no**

All structural bindings and checkpoint/index records agree.

### Honest absence of independent modality work: **not proven**

This audit cannot make that semantic claim. Structural audio-capable windows
exist, and speech coverage is too sparse to distinguish source absence from
index/gate absence.

## 8. Recommendation

### Primary: `MINER_REPAIR`

Keep the current candidate registry at zero until a repaired miner is rerun.
Do not invent candidates from the diagnostic counts.

Required miner repairs:

1. calibrate the visual transition gate against the actual index distribution,
   or use a frozen deterministic rank/quantile rule with an absolute safety
   floor;
2. discover far anchors independently of local V+S rows, then report distance,
   continuity, speech, and lexical joins separately;
3. persist deterministic counts at every gate;
4. derive each zero reason from the actual first failing gate;
5. stop treating empty final candidates as proof that audio or speech
   structural floors had no passing records.

### Secondary: speech `INDEX_REPAIR` review

Review or rebuild the speech routing policy because `1/119` searchable chunks
cannot support a miner that requires speech at every component. Possible
repair must remain deterministic and source-derived; this audit does not
prescribe a transcript, threshold, or semantic interpretation.

`INDEX_REPAIR` is secondary rather than primary because the index is
structurally intact, visual/audio coverage is complete, and miner thresholding,
far coupling, and accounting remain defective even if speech is rebuilt.

### Why not `KEEP_ZERO`

The zero is reproducible but not an honest absence result. An unreachable
visual threshold, empty speech join, coupled far search, and inaccurate zero
reasons require repair before the source can be retained as a trustworthy
zero-candidate outcome.

**EPIC_P23_102_ZERO_CANDIDATE_AUDIT_READY**
