# P23_102 query authoring v2 real A/V canary

**Decision:** `P23_102_QUERY_AUTHORING_V2_CANARY_READY`  
**Repair status:** `P23_102_QUERY_AUTHORING_SEMANTIC_GATES_READY`  
**Date:** 2026-10-15  
**Execution state:** separate wrapper implemented and tested with synthetic and
mock stages; no real canary was run.

## Purpose and boundary

This is a small, fail-closed real audio/video canary for
`tools/p23_102_query_authoring_v2.py`. It does not change the main authoring
pipeline or its plan. Its only intended real execution is one separately
authorized run over exactly two machine-provisional families:

* one local, one-component family;
* one far, ordered two-component family; and
* no more than four unique exact target clips.

For the currently frozen structural bundle, deterministic selection yields
`family-009` and `family-005`, spanning three unique clips. These public
canary keys are conveniences only. Authorization binds the exact structural
family hashes, not merely the keys.

## Hash-only deterministic selection

The wrapper first uses the main pipeline's narrow structural loader. For each
eligible family it constructs a structural identity containing only:

* the internal family identity;
* the one- or two-component shape;
* exact interval bounds and clip keys; and
* the paired evidence-handle identities.

It deliberately excludes template text, provisional slot names, structural
scores, ranks, retrieval roles, semantic hypotheses, and human labels from the
family hash. It hashes each structural identity, then computes a domain-
separated selection rank bound to the frozen bundle file hashes, the family
class, and the structural family hash. The lexicographically minimum rank is
selected independently for the local and far classes.

Selection therefore does not use a semantic score, model output, retrieval
rank, or manual preference. A changed source bundle or structural family
identity changes the authorization scope and fails closed.

## Restricted subset staging

Execution creates a mode-0700 staging directory beside the fixed output path:

`data/restricted/p23_102_query_authoring_v2_canary_run_v1`

The wrapper writes a canary-only structural bundle containing the selected
families and their unique targets. The original bundle is never rewritten.
The exact target arrays are extracted inside staging, consumed by authoring
and audits, and removed before the final seal. Their hashes, shapes, sizes,
coverage metadata, and sanitized ephemeral paths remain in the target
manifest.

The staging directory is atomically renamed to the fixed output only after
every required file exists and all audits pass. On exception, no successful
canary output is installed. Instead, clip arrays are deleted and the remaining
staging evidence is atomically preserved as a restricted, create-once failure
capsule keyed by the authorization ID.

## Reused real A/V stages

The wrapper directly calls the same implementation functions used by the main
v2 pipeline:

1. PyAV exact-interval video and audio extraction;
2. Qwen2.5-Omni processor/model loading and deterministic direct A/V
   generation;
3. strict JSON and content-field validation plus the parent's sole guarded
   schema-only repair path;
4. Whisper transcription of exact targets for copied-speech leakage audit;
5. literal, duplicate, lexical, SigLIP2 text, and CLAP text collision audits;
6. ambient acousticness, degenerate-ASR quarantine, cross-kind paraphrase,
   far-family composition, standalone-reference, and query/description
   identity gates; and
7. sealed output hashing.

The only count adaptation is a temporary, exception-safe scope around the
parent validation constants so that the same materialization and audit code
validates 2 families and 8 canary queries rather than the full 20-family,
76-query run.

There is no fallback authoring route, semantic repair, best-of-N choice,
prose-stripping acceptance, substring extraction, or template substitution.
The parent constrains both initial and text-only repair decoding to one
top-level JSON object. It conditionally prefills only the exact minimal `{`
when tokenizer/model compatibility and chat-template-boundary tokenization are
exact, tracks nested delimiters plus quoted and escaped content
incrementally, and stops on the first syntactically complete top-level object
before runaway prose or a second object. An object that does not close by the
token cap fails closed. Persisted raw output is the documented prefill plus
the exact generated constrained sequence, and the whole value is parsed.
Exactly one repair call is allowed only for recoverable structural JSON/schema
form. Initial calls contain one video placeholder and one matched video/audio
tensor pair per selected component, with in-video audio enabled. The repair
prompt contains only text, the prior raw output, and validation error; its
processor and model calls receive no `videos`, `audio`, or
`use_audio_in_video`. The parent now checks placeholder/tensor cardinality and
also rejects any media tokens or media features produced for the text-only
repair. The parent's scalar-multiset guard rejects any semantic change.
Invalid semantic values, ordinals, enums, ranges, or IDs do not trigger a
repair. Model, decode, parse, repair, media-contract, or audit failure blocks
successful sealing.

The canary has no separate semantic policy. It calls the parent's frozen gate
suite under the temporary two-family/eight-query count scope:

* ambient fields require explicit acoustic lexicon or the CLAP-text classifier
  (`positive cosine >= 0.20`, margin `>= 0.08`);
* degenerate ASR uses unique ratio `< 0.25` from eight tokens, repeated short-
  vocalization dominance `>= 0.70` from four tokens, and a low-information
  rule; human-vocalization claims are quarantined unless conservative
  nonlexical terms exclude speech;
* visual/ambient pairs fail at lexical Jaccard `>= 0.72` with four shared
  tokens, both embedding cosines `>= 0.94`, or one cosine `>= 0.985`;
* far queries must cover both components in order, state a non-speech
  acoustic relation, and omit unsupported continuity, causality, and
  anaphora;
* every handle query stands alone; and
* query/description equality or Jaccard `>= 0.90` with five shared tokens
  fails.

Rows expose machine observation and per-field gate status only. They never
assert `content_grounded=true` or human grounding.

## Authorization receipt

`--execute` requires a separately created JSON receipt with exactly these
bindings:

* canary ID and canary configuration hash;
* exact selected local and far structural family hashes;
* exact SHA-256 of the main authoring pipeline source file;
* exact SHA-256 of the canary wrapper source file;
* all four source-bundle file hashes;
* verified content hashes for the Qwen2.5-Omni, Whisper, SigLIP2, and CLAP
  snapshots;
* exact source-media SHA-256;
* the fixed repository-relative output path; and
* `single_local_run=true`.

Model snapshot hashes are computed only after every file listed in each
snapshot's `SHA256SUMS` has been checked. Authorization schema version 2 binds
both repaired source hashes; the pre-repair version-1 receipt is invalid. An
unknown field, missing field, changed hash, changed output path, absent
receipt, or existing output fails closed. The wrapper does not generate a
receipt and does not maintain a mutable authorization ledger; one-run behavior
is enforced by the fixed, create-once output or failure-capsule path.

The canary configuration and authorization fingerprints include the exact
current parent pipeline source hash. Therefore the parent media-contract
change invalidates every earlier canary authorization receipt even though the
authorization schema version remains 2. The later constrained-decoding source
change also changes that bound hash, so no earlier receipt can authorize this
version.

## Outputs and measurements

A successful authorized run seals:

* `canary_contract.json`
* `canary_subset_bundle.json`
* `target_manifest.json`
* `prompt_manifest.json`
* `raw_attempts.jsonl`
* `asr_audit_inventory.json`
* `authored_queries.json`
* `audits.json`
* `resource_runtime.json`
* `seal.json`

Raw initial and repair Qwen strings are retained with exact prompt text,
UTF-8/base64 bytes and hashes, parser errors, model identity, and clip manifest
hashes. Each attempt also records constrained-decoding stop reason, generated
and prefill token counts, prefill compatibility, the token cap, and the
explicit media contract, including
placeholder/tensor counts, processed media-token counts, feature keys, and
whether in-video audio was enabled. Raw Whisper result objects are retained.
`resource_runtime.json` records total wall time, per-stage wall times, peak
RSS, initial and repair model-call counts, and exact-target decode count. A
failure capsule records the same available evidence plus failure-stage and
stderr/traceback summaries, while omitting only ephemeral clip arrays.
Clip and ASR progress manifests are written after every completed record,
authoring counts are reconstructed from retained attempts, and a stage that
raises records `<stage>_partial_seconds`.

## No retrieval scoring or claims

This canary is solely an operational test of the real A/V authoring path.
It does not open retrieval indexes, rankings, candidate scores, target or
non-target retrieval vectors, diagnostic outcomes, or scientific scoring
artifacts. It emits no retrieval metric and makes no quality, validity,
support, necessity, generalization, or scientific claim.

The seal and authored-query artifact explicitly record:

* retrieval scoring not executed;
* retrieval results empty;
* scoring results empty;
* scientific claims empty; and
* human semantic validation absent.

## CLI

Model-free plan validation:

```bash
python tools/p23_102_query_authoring_v2_canary.py --plan
```

Availability and exact-hash preflight without model loading or media decode:

```bash
python tools/p23_102_query_authoring_v2_canary.py --preflight
```

One future authorized real canary:

```bash
python tools/p23_102_query_authoring_v2_canary.py \
  --execute \
  --authorization <approved-canary-receipt.json>
```

Validate a sealed result:

```bash
python tools/p23_102_query_authoring_v2_canary.py --validate-output
```

Synthetic/mock tests and lint:

```bash
pytest -q tooling/tests/test_p23_102_query_authoring_v2_canary.py
ruff check \
  tools/p23_102_query_authoring_v2_canary.py \
  tooling/tests/test_p23_102_query_authoring_v2_canary.py
```

This implementation task did not run the real canary. Source edits change the
parent and canary SHA-256 authorization bindings, so every earlier receipt is
invalid; this task created no receipt.
