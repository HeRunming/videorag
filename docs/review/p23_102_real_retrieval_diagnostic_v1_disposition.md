# P23_102 real retrieval diagnostic v1 authoritative disposition

**Date:** 2026-10-15  
**Artifact-integrity gate:** **READY**  
**Paper-facing Acquire-evidence gate:** **NO-GO; v2 required**  
**Decision token:** `P23_102_REAL_RETRIEVAL_V1_PAPER_NO_GO_V2_REQUIRED`

## Binding decision

The independent audit is accepted as authoritative. The v1 artifacts remain
hash-valid, deterministic, internally consistent development artifacts, so
their artifact-integrity status remains `READY`. That engineering status does
not authorize a scientific interpretation.

For every paper, table, figure, abstract, result, comparison, ablation,
supplement, or benchmark claim about Acquire, v1 is a binding **NO-GO**. This
disposition supersedes `P23_102_REAL_RETRIEVAL_DIAGNOSTIC_READY` only as an
authorization signal for paper-facing Acquire evidence. The historical v1
files, status strings, hashes, and measurements remain unchanged and may be
used only for provenance, reproducibility, debugging, and v2 repair.

The only defensible substantive result is:

> The 76 nominal queries are only seven generic placeholder templates. Every
> learned ranker gives identical rankings to queries sharing a template, so
> the run cannot identify the intended families or evidence targets. The
> audit found no literal target-record ID, source ID, timestamp, or exact ASR
> text leakage in query text.

No model, modality, temporal-stratum, or fusion conclusion may be drawn from
v1.

## Exact independent-audit finding

### Query collapse and ranking collisions

| Audit item | Exact value |
|---|---:|
| Families | 20 |
| Evidence handles | 56 |
| Nominal queries | 76 |
| Family queries | 20 |
| Handle queries | 56 |
| Unique query texts | 7 |
| Duplicate-text groups | 7 |
| Duplicate-group sizes | 16, 12, 12, 12, 8, 8, 8 |
| Queries in duplicate groups | 76 of 76 |
| Distinct same-text query pairs | 402 |
| Learned rankers audited | 3 |
| Same-text learned-ranking pair collisions | 1,206 |
| Learned query/ranker ranking records | 228 |
| Unique learned ranking lists after collapse | 21 |

The three learned rankers are SigLIP visual-only, CLAP audio-only, and
equal-weight RRF. For each of the seven texts and each learned ranker, every
query in that text group has the same complete ordered ranking and scores.
This is not an incidental tie at a cutoff: it is a full-ranking collision.

The seven texts are generic unfilled forms such as
`[OBJECT_OR_STATE_TRANSITION]`,
`[NON_SPEECH_EVENT_OR_AUDIO_PROPERTY]`,
`[EARLIER_OBJECT_OR_STATE]`, and `[LATER_OBJECT_OR_STATE]`. They encode a
template class, not the identity or semantics of an individual family or
target. Consequently, the observed target ranks are functions of seven
generic prompts plus differing evaluator-private target assignments; they
are not measurements of target-specific semantic retrieval.

### Leakage result

The negative literal-leakage checks remain valid:

- target record ID in query text: false;
- source ID in query text: false;
- timestamp in query text: false;
- query exactly equals stored ASR text: false; and
- direct query-to-index text leakage detected: false.

This is a useful negative audit result, but it does not repair
non-identifiability. Absence of literal ID, timestamp, or exact-ASR leakage
does not make a generic placeholder query target-identifying.

## Target accounting

The v1 target ledger is internally consistent and must be preserved as the
minimum v2 accounting surface:

| Surface | Near/local | Far/separated | Total |
|---|---:|---:|---:|
| Families / family queries | 12 | 8 | 20 |
| Family-query target handles | 24 | 32 | 56 |
| Handle queries | 24 | 32 | 56 |
| Vision handles | 12 | 16 | 28 |
| Ambient-audio handles | 12 | 16 | 28 |

Each near/local family has two target handles. Each far/separated family has
four target handles. Across both family-query and handle-query views there
are 56 unique evidence-handle IDs, 28 unique index record IDs, 28 vision
handles, and 28 ambient-audio handles. Family queries account for all 56
handles once at the family level; handle queries account for all 56 handles
once individually.

These counts establish bookkeeping only. They do not validate the semantic
content of any target, modality label, local/far label, family, or route.

## Quarantined v1 measurements

The following values are reproduced exactly to bind the historical run, not
to authorize scientific interpretation.

### Execution and persistence

- visual index records: 1,115;
- audio index records: 1,115;
- persisted ranking records: 380;
- persisted ranked items: 423,700;
- per-query metric rows: 456;
- aggregate metric rows: 36;
- CPU threads: 1;
- elapsed time: 18.322274 seconds;
- text-embedding time: 12.56659 seconds;
- peak RSS: 1,623,556 KiB; and
- deterministic rerun SHA-256:
  `sha256:1e2cffceb6a4670cc5bcea53699b8405c75c8e9b1b30f23cee1a07a7b1f6c595`.

### Historical family-query metrics

All-evidence success was 0.0 at R@1, R@5, and R@10 for all six reported
methods. At family-query R@10:

| Method | Evidence recall | Mean first-target rank | Median first-target rank |
|---|---:|---:|---:|
| Audio-only | 0.0125 | 438.50 | 489.0 |
| Equal-weight RRF | 0.0000 | 377.90 | 327.0 |
| Oracle modality routing | 0.0125 | 238.25 | 180.0 |
| Deterministic random | 0.0000 | 411.05 | 330.0 |
| Temporal midpoint | 0.0000 | 513.90 | 589.5 |
| Visual-only | 0.0000 | 406.20 | 293.5 |

Joint minus best unimodal was 0.0 at R@1, 0.0 at R@5, and -0.0125 at
R@10. These numbers are quarantined because the queries cannot identify
their targets. The machine-readable disposition binds the full 36-row
aggregate table and all 18 joint-minus-best-unimodal cells exactly.

## Prohibited uses

V1 is not usable to support any claim about:

1. **Model quality or ordering.** It cannot compare SigLIP, CLAP, random,
   temporal, or any future ranker.
2. **Modality.** It cannot establish visual-versus-audio retrieval quality,
   modality necessity, modality routing, or modality complementarity.
3. **Near/local versus far/separated retrieval.** The temporal-stratum
   comparisons inherit the same generic-template confound.
4. **RRF or fusion.** It cannot show that equal-weight RRF helps, hurts, or
   is neutral relative to unimodal retrieval.
5. **Oracle routing.** Evaluator-private target-modality routing is not an
   inference-time system and remains uninterpretable here.
6. **Acquire success, failure, or difficulty.** The run does not test whether
   target-specific public questions can retrieve their required evidence.
7. **Benchmark validity, semantic support, accepted SES status, H-tier,
   Gate-A, causal effects, or source-level generalization.**

No favorable cell, unfavorable cell, ranking, recall, first-target rank,
stratum, or baseline comparison may be selected from v1 for paper use.

## Mandatory v2 repair requirements

V2 must be a new version and must satisfy every requirement below before any
paper-facing Acquire result can be considered.

1. **Author target-identifying semantics.** Replace every placeholder with a
   completed, natural-language, target-specific question, answer, and atomic
   claim. A query must describe observable source-world content rather than
   an ID, timestamp, index location, annotation label, or template class.
2. **Require 76 target-specific query texts.** Preserve 20 family queries and
   56 handle queries, but require 76 unique normalized query texts. Any
   duplicate text across different target sets, families, handles, or
   evaluator assignments is a fail-closed v2 error.
3. **Preserve exact target accounting.** V2 must account for all 20 families
   and all 56 handles: 12 near/local families with 24 handles, eight
   far/separated families with 32 handles, 28 vision handles, and 28
   ambient-audio handles. Missing, duplicated, orphaned, or multiply counted
   handles invalidate the run.
4. **Freeze query-to-target bindings before retrieval.** Hash and freeze the
   completed semantic queries, target sets, family/handle scope, modality,
   temporal stratum, and source-disjoint status before embedding or ranking.
   No outcome-aware query rewriting or target reassignment is allowed.
5. **Independently review identifiability.** A reviewer who did not author
   the query must verify that it distinguishes the intended target from
   same-template families using public semantic content alone. The review
   must occur without exposing record IDs, timestamps, rank outcomes, or
   evaluator-private shortcuts.
6. **Repeat and strengthen leakage checks.** Retain literal record-ID,
   source-ID, timestamp, and exact-ASR checks; add normalized and token-level
   checks for near-literal timestamp/ID encodings, annotation-label copying,
   answer leakage, and target-only metadata.
7. **Prove collision freedom.** Before metrics are released, verify that
   different target bindings do not produce identical normalized texts,
   embeddings, score vectors, or complete learned rankings. Any unexplained
   collision is a NO-GO.
8. **Precommit model and fusion comparisons.** Pin encoders, index, score
   normalization, tie-breaking, RRF `k`, modality weights, candidate
   universes, and cutoffs before execution. Oracle routing must remain
   separately labeled and cannot be used as an available-system result.
9. **Align reporting with the Acquire retrieval budget.** Report the frozen
   primary `top_k=5` and the preregistered maximum `top_k=20`; any additional
   cutoff is secondary. Do not choose a cutoff, modality, stratum, or fusion
   rule after observing outcomes.
10. **Keep claim gates separate.** Artifact integrity, query
    identifiability, target validity, retrieval execution, and paper-facing
    scientific authorization are separate gates. V2 must receive an
    independent paper-facing GO; successful execution alone is insufficient.

## Mandatory v2 budget changes

The v1 runtime embedded only seven unique texts per encoder. V2 must budget
for at least 76 unique texts per encoder:

| Budget item | V1 | Mandatory v2 minimum | Change |
|---|---:|---:|---:|
| Unique query texts per encoder | 7 | 76 | +69; 10.857142857× |
| Total query-text embeddings across two encoders | 14 | 152 | +138; 10.857142857× |
| Family semantic authoring/adjudication units | 0 completed | 20 completed | +20 |
| Handle semantic authoring/adjudication units | 0 completed | 56 completed | +56 |
| Independently reviewed query bindings | 0 | 76 | +76 |
| Primary reported retrieval cutoff | 10 in the v1 summary | 5 | align to frozen Acquire `top_k` |
| Maximum preregistered retrieval cutoff | 10 | 20 | align to frozen schema maximum |

If the same 76 queries, five persisted ranking methods, and 1,115-item
candidate space are retained, ranking persistence remains 380 ranking
records and 423,700 ranked items. The compute and memory plan must not assume
seven-text deduplication, and it must include collision, leakage,
identifiability, and independent-review costs.

The existing agentic Acquire budget of 10 actions and cost limit 12.0 is not
changed or validated by this disposition. V2 must not tune that downstream
budget from v1 retrieval outcomes.

## Hash-bound v1 record

All hashes below are direct file SHA-256 values.

| V1 artifact | SHA-256 |
|---|---|
| `docs/review/p23_102_real_retrieval_diagnostic_v1.md` | `af99b5dabe219a334a141c87d1f1c7d12570f83a7551f4fae6c45b30c28cdcf0` |
| `data/rehearsal_plan/p23_102_real_retrieval_diagnostic_v1.json` | `6c5b6e5d4c80236bcfde1fc1fa483ecc54ea43a72fd00a02e64138778dcbee4e` |
| `tools/p23_102_real_retrieval_diagnostic_v1.py` | `e3b49e7fc449153316d2cb10a575e5f71811db46f32a8eeebaf5317f8961d5fc` |
| `tooling/tests/test_p23_102_real_retrieval_diagnostic_v1.py` | `78e45bbd7b3811a417614c0e8512702b041848259f9a10105d7361c12ac7ac61` |
| `data/restricted/p23_102_real_retrieval_diagnostic_v1/audit.json` | `51c8eecb2656968f8df473af02d624af2341f797ffffeabfd3cb63bffc39a050` |
| `data/restricted/p23_102_real_retrieval_diagnostic_v1/config.json` | `3beedad2a147fe38475d0cc445493d5aa4173b208b3019fb80e911bc9a98f0c9` |
| `data/restricted/p23_102_real_retrieval_diagnostic_v1/deterministic_payload.json` | `3de4f248eb15b574fe77e6afa9686596a81b6093782ec8615ba261b1bbb65777` |
| `data/restricted/p23_102_real_retrieval_diagnostic_v1/leakage_audit.json` | `838b157317d9294199455353a312fce0563393593d559462864445c796fcd9d7` |
| `data/restricted/p23_102_real_retrieval_diagnostic_v1/metric_tables.json` | `c71d228ccb0b0a2f6aba6e02f7bac3ce23a4e9bf42ab2f3b85cc99d5ad4e8d94` |
| `data/restricted/p23_102_real_retrieval_diagnostic_v1/per_query_metrics.json` | `62e82461e441f8c487cdadc512524cf5621cf64ebf8cb82a2f0c7b806c81b914` |
| `data/restricted/p23_102_real_retrieval_diagnostic_v1/queries.json` | `c57318513bc727ef25723f5f1b2f99fd7d800c0cc080c16656c9888203b32a8f` |
| `data/restricted/p23_102_real_retrieval_diagnostic_v1/rankings.jsonl.gz` | `f835f7fe9c86b02d2072f0a5df11be88bbab108e389b20e89d6ac5fa1dcc0ce2` |
| `data/restricted/p23_102_real_retrieval_diagnostic_v1/resource_runtime.json` | `ec87847d8eed301d1e42bb3c23c1013270b0f54a2f776e36e7eb476892ddc758` |

The v1 configuration hash is
`sha256:1654ae730fd15ef28751c55e79ce4ffc4713da574b01b9086bd0f2377adb18e5`;
the public-summary payload hash is
`sha256:06eba9f25c097c7f6c8e14f7bb76ced2a62aaad54a4482fa3befe6bd800542ac`;
and the restricted audit payload hash is
`sha256:6af551d3789d9d61bccad5912bf95bd1d74a1e25dd0f763eea0596679d7155a4`.
The machine-readable disposition additionally binds all nine configured
input-file hashes, seven upstream canonical hashes, both frozen model
inventories, and the complete historical aggregate metric tables.

## Final disposition

- **Artifact integrity:** `READY`
- **Paper-facing Acquire evidence:** `NO_GO`
- **In-place v1 repair:** forbidden
- **Required successor:** v2
- **Authoritative token:**
  `P23_102_REAL_RETRIEVAL_V1_PAPER_NO_GO_V2_REQUIRED`

