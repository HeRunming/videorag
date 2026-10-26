# P23_102 query-authoring v2 canary failure repair

**Date:** October 15, 2026  
**Status:** `P23_102_QUERY_AUTHORING_SEMANTIC_GATES_READY`

## Observed failure

The first authorized real A/V canary successfully extracted three exact target
clips and loaded the pinned Qwen2.5-Omni snapshot, but the first authoring
response did not satisfy the strict JSON contract. Execution failed closed
with `MODEL_OUTPUT_NOT_STRICT_JSON`; retrieval scoring was not run and no
scientific or model-quality claim was made.

## Repair

The full and canary authoring paths now share the same guarded output policy:

1. Preserve the exact prompt and initial raw output, hashes, parser error,
   model identity, clip-manifest hashes, timings, and peak RSS.
2. Permit at most one schema-only repair only for structurally recoverable
   output.
3. Require the repair to preserve the multiset of semantic scalar values.
4. Reject semantic, enum, range, ordinal, or identifier changes.
5. Never extract a JSON substring, strip prose or fences, vote, use best-of-N,
   or substitute deterministic content.
6. Persist an atomic failure capsule even when ephemeral clip arrays are
   removed.

The authorization schema was advanced so prior receipts cannot authorize the
repaired code.

## Complete JSON followed by runaway text

Subsequent evidence identified a separate decoding failure mode: the model can
finish a complete JSON object and continue with prose or another value.
Accepting an extracted prefix would violate the raw-output contract, while
letting generation continue causes strict whole-output parsing to fail.

The repair is generation-time constrained decoding, not output
post-processing:

1. The decoder-only assistant prompt is prefixed with only `{`, and only when
   that text is an exact non-special, round-tripping token sequence whose
   concatenation is stable at the rendered chat-template boundary.
2. An incremental state machine tracks strings, escapes, Unicode escapes, and
   nested object/array delimiters.
3. Invalid next-token candidates and premature stop tokens are masked.
4. Generation stops on the token that first completes one syntactically valid
   top-level JSON object, before a second object or trailing prose.
5. If closure never occurs by the token cap, the attempt fails and records
   `json_object_unclosed_at_token_cap`.
6. Raw evidence is exactly the documented prefill plus generated constrained
   sequence. The parser reads all of it; no fence/prose stripping, substring
   extraction, or semantic replacement is performed.
7. The same mechanism applies to initial A/V authoring and text-only schema
   repair. The semantic scalar-multiset guard remains required for repair.

## Proven repair-stage media mismatch

Processor-level reconstruction of the failed route proved a second defect in
the bounded repair implementation. The initial authoring conversation
correctly contained one or two video placeholders and received corresponding
video plus in-video audio tensors. The schema-only repair conversation
contained only text and the prior raw output, but the repair call incorrectly
reused the initial video/audio tensors and passed `use_audio_in_video=true`.
That violated the Qwen2.5-Omni processor contract because the repair text had
no media placeholders to consume those tensors.

The repaired generation API now makes media presence explicit:

1. An initial call declares `media_present=true`; placeholder counts must equal
   both video- and audio-tensor counts.
2. A repair call declares `media_present=false` and supplies no video tensor,
   audio tensor, or `use_audio_in_video` option to either processor or model.
3. Media tensors without placeholders, placeholders without tensors, unequal
   component counts, missing processed media tokens/features, or any media
   token/feature on the text-only route fail closed before generation.
4. Attempt evidence records the enforced media contract.
5. The semantic scalar-multiset guard remains unchanged and still rejects any
   repair that changes authored content.

Because full authoring authorization binds the exact parent pipeline SHA-256,
and canary authorization binds both exact source hashes through its input
fingerprint, all authorization receipts created before this source repair are
invalid. This work did not create a replacement receipt or run the model.

## Validation

- Real local Qwen2.5-Omni processor tests, without model-weight loading, cover
  one- and two-component initial prompts and the text-only repair prompt.
- Initial processing produces nonzero video and in-video audio placeholder
  tokens plus the expected video/audio feature structures.
- Repair processing produces zero media placeholder tokens and zero media
  feature structures.
- Unit coverage proves the second `author_one_family` generation is text-only
  and that semantic scalar mutation still fails closed.
- Unit coverage exercises incremental chunks, nested arrays/objects, braces in
  escaped strings, multiple objects, trailing prose, unfinished JSON, exact
  prefill accounting, token-cap failure, and fake generation that stops before
  scripted trailing prose.
- Real repaired canary: not rerun by this repair.

The combined repair establishes auditable failure retention, a bounded
structural retry, and an explicit processor/model media contract. It does not
establish query quality, retrieval performance, semantic validity, or
scientific readiness.

## Binding independent semantic audit of sealed v1.5

The independent review of the successful v1.5 canary is binding. Although the
old artifact reported `PASS`, it exposed failures not covered by the old
leakage and same-kind collision checks:

* “A pot is set on the stove” was an action-only ambient paraphrase;
* Whisper produced highly degenerate repeated `Ugh` and `Yeah` transcripts,
  yet a human cough/throat-clearing claim was not quarantined;
* a later handle used “The person” and its description used “then”;
* the far query assumed one continuing person and omitted the required non-
  speech relation;
* several queries duplicated their paired descriptions; and
* every row asserted `content_grounded=true` without sufficient machine gates.

The sealed v1.5 output remains untouched and is not reclassified as passing.

## Semantic-gate repair

The parent now owns one frozen fail-closed suite used unchanged by full and
canary execution:

1. explicit acoustic lexicon or CLAP-text acousticness classification;
2. degenerate-ASR analysis and conservative vocalization quarantine;
3. component-local visual-versus-ambient lexical plus SigLIP/CLAP checks;
4. ordered far-component coverage, required acoustic relation, and rejection
   of unsupported continuity, causality, and anaphora;
5. standalone handle-query checks;
6. machine-only observation and per-field gate status instead of
   `content_grounded=true`; and
7. query-to-description identity checks.

Thresholds and rules are frozen in the design documents and audit artifact.
Tests use generalized synthetic positives and negatives rather than matching
only the exact v1.5 wording.

## Incremental failure accounting

Extraction and ASR now retain a progress manifest after each completed clip,
raw attempts remain persisted after every initial or repair call, and failed
stages record partial elapsed time. Capsule installation reconstructs clip,
ASR, initial-call, and repair-call counts from retained evidence. Substantial
authorized work can no longer appear as zero merely because its stage raised
before returning aggregate counters.

No real model was run, no authorization was created, and no sealed v1.5 file
was modified. Since authorization binds source SHA-256, all earlier receipts
are invalid.

## Semantic repair validation

Synthetic tests reproduce every listed v1.5 failure, a valid local V+A case
passes, a conservative nonlexical cough case passes under degenerate ASR, and
retained-evidence tests recover clip, ASR, initial, and repair counts. Ruff,
targeted pytest, and `py_compile` are required before readiness.
