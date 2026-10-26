# P23_102 deterministic query authoring v2

**Decision:** `R23_A_IMPLEMENTATION_READY`  
**Repair status:** `P23_102_QUERY_AUTHORING_SEMANTIC_GATES_READY`  
**Date:** 2026-10-23  
**Execution state:** designed and locally implemented; no target media was
decoded and no model was run by this work.

## R23-A pure implementation repair

R23-A is implementation-ready only. It does not authorize a model run,
change Canary selection/governance/markers/authorization/capsules, touch a
real authoring output, or claim Canary GO. R22 remains permanently NO-GO.

The far-family local-clause contract is now exact and mechanical:

- every `composition_clauses[]` row binds by ordinal to the accepted
  `visual_description` and `ambient_description`;
- summaries are compared after the frozen normalization and must be both
  exactly equal and SHA-256 equal to that description projection;
- clause count, exact key set, and ordinal must match;
- swapped ordinals, a missing clause, a one-word mutation, or the wrong
  ambient event fail closed with `BINDING_MISMATCH`;
- local coverage is a separate result and uses accepted descriptions only,
  never `visual_query` or `ambient_query`, with `COVERAGE_INVALID`; and
- local reference/continuity is a third result with
  `LOCAL_REFERENCE_INVALID`.

This does not weaken the independent family-compositional query gate.
Ordered visual coverage and per-component ambient coverage remain evaluated
against the accepted visual/ambient queries. Description exact binding and
family-query ordered coverage are separate results. Retained real R21
`family-005` and `family-003` evidence is covered by model-free regressions:
their unmodified mechanical clauses pass exact local binding while their
family queries continue through the independent ordered coverage gate.

The local visual reference rule is deliberately narrow. A sentence such as
`A kitchen ... a table with various items on it.` passes because the same
sentence has an explicit noun antecedent before locative `on it`. Bare or
unresolved `it`, `this`, and `they` remain invalid. `same`, `again`,
`continues`, `previous`, and equivalent bridge markers remain invalid even
when a noun appears nearby. The exemption applies only inside one local
description span; cross-component relation continuity is still evaluated
after exact local spans are removed and receives no pronoun relaxation.

## R22 deterministic replay

`tools/p23_102_r22_deterministic_replay.py` reads only the restricted R22
terminal detailed audit and retained failure capsule. It verifies every
sealed byte count and SHA-256 before parsing, rebuilds the exact 13 accepted
factors and 26 final rows, and runs model-free gates for:

- accepted-factor/provenance exact binding;
- ambient semantic-tuple duplicates;
- lexical exact duplicates and same-kind near collisions;
- standalone handle references;
- query/description identity; and
- far ordered family-query coverage.

The replay calls no authoring model, ASR, SigLIP/embedding model, CLAP model,
media decoder, retrieval, or scoring route, and it makes no inference from
those unexecuted systems. A capsule tamper or hash mismatch fails closed.
The restricted replay report reproduces the R22 blocking collisions and
returns `NO-GO`; it never modifies the historical capsule.

R22-A also adds `ambient_semantic_tuple_duplicate_audit()`. It groups accepted
ambient factors by canonical tuple hash before ASR or embedding audit work:

- the same tuple repeated within one family is a blocking fail-closed
  condition;
- all canary/global duplicate groups and pairwise collisions are emitted in
  `ambient_semantic_tuple_collisions.json`;
- ordinal changes cannot hide a collision;
- no automatic rewrite, synonym template, semantic substitution, or
  authoring retry is permitted; and
- any family replacement remains an outer R22 selection-governance action.

The retained R21 `query-010`/`query-012` exact duplicate remains a failure.
The lexical threshold remains `0.92`, the embedding/CLAP threshold remains
`0.995`, and the R21 token trie, R20 ontology, R19 accepted-factor lifecycle,
budgets, and provenance checks remain unchanged.

## Purpose

The repaired P23 provisional bundle has 20 machine-provisional V+A families,
56 evidence handles, and exactly 28 unique target intervals. Twelve families
contain one interval and eight contain two chronologically ordered intervals.
This pipeline replaces repeated claim-template text with content-grounded,
neutral machine-authored text:

* one visual description and query for each of the 28 target intervals;
* one ambient/non-speech description and query for each target interval; and
* one family-compositional description and query for each of the 20 families.

The primary set therefore contains 76 queries. It remains development-only,
machine-authored, not human-validated, and unscored.

## Hard separation from retrieval and scoring

The authoring implementation has a narrow input allowlist:

1. `family_registry.json`, solely to obtain family order, one/two-component
   structure, and unfilled provisional slot names;
2. `evidence_registry.json`, solely to bind each family to exact target
   intervals and paired visual/ambient handles;
3. `source_split_manifest.json` and `leakage_gate.json`, solely to verify the
   development-only and leakage boundaries;
4. the exact P23 media file, decoded only into the 28 target intervals; and
5. pinned local model snapshots.

It does **not** open the full-timeline index, candidate ranking registry,
retrieval diagnostic outputs, non-target vectors, rank lists, retrieval
scores, evaluator outcomes, intervention outcomes, accepted-support labels,
answer keys, or human semantic labels. Private family/evidence IDs and clip
intervals are retained in sealed metadata but are not included in model
prompts.

Scoring is a later sealed stage. The authoring seal explicitly records that
scoring was not run and that rankings, outcomes, and non-target vectors were
not read.

## Model-visible surface

The retained R8 factorization splits each structural component into two
independently authored factors.
The visual factor key is `:component:N:visual`; it receives exactly one silent
video tensor, no audio placeholder or audio tensor, and returns only
`visual_description` and `visual_query`. The ambient factor key is
`:component:N:ambient`; it receives exactly one audio tensor, no video
placeholder or video tensor, and returns only `ambient_description` and
`ambient_query`. The two factors are paired mechanically only when family,
ordinal, exact clip, and modality all match. Missing, extra, cross-clip, or
cross-modality factors fail closed.

After all same-clip visual/ambient pairs for a family are accepted, the family
receives one `:family_composition` text-only call containing the frozen
shape/count and required controlled `relation_kind`. The composition schema
contains only `relation_kind`; it contains no media, component text, slot
names, or natural-language relation field. Full scope is exactly 28 visual +
28 ambient + 20 composition initial calls = 76.

The prompt contains no source name, IDs, timestamps, template sentences,
rankings, scores, vectors, answer keys, or semantic labels. Initial generation is greedy decoding (`do_sample=false`, seed 0). Visual
initial conversations contain one video placeholder and set
`use_audio_in_video=false`; ambient conversations contain one audio
placeholder; composition contains neither. Opposite-modality tensors and
processor features are forbidden for every factor.

Both the initial media-bearing call and the text-only schema-repair call use
constrained JSON decoding. When the decoder-only Qwen tokenizer represents the
minimal object start `{` as an exact, non-special, append-stable token, that
character is appended to the assistant generation prompt as a documented
prefill. If any tokenizer/model or chat-template-boundary compatibility check
fails, the prefill is disabled rather than approximated.

A deterministic incremental boundary tracks strings, escaped quotes and
backslashes, Unicode escapes, and nested arrays/objects. Generation stops on
the token that first makes the top-level object syntactically complete.
Candidates that would make the prefix invalid or terminate before closure are
masked. This prevents generation of a second object or trailing prose because
the generation call has already stopped. If the object has not closed by the
640-token cap, the attempt fails closed.

Persisted raw output is exactly the documented prefill followed by the
model-generated constrained token sequence. The parser consumes that complete
string. It does not extract a substring, remove fences or prose, or substitute
semantic content. Attempt evidence records stop reason, token cap, generated
token count, prefill text/count/compatibility reason, prompt token count with
and without prefill, and total constrained-output token count.

If and only if the raw output contains one recoverable semantic JSON value
with all required content fields, and the failure is structural JSON/schema
form, the same model may receive one schema-only repair prompt containing the
exact prior raw output and validation error. That repair conversation is
strictly text-only: it contains no media placeholders, and the processor and
model are called without `videos`, `audio`, or `use_audio_in_video`. Supplying
media tensors without matching placeholders, placeholders without matching
tensors, unequal video/audio component counts, or processor-produced media
features for a text-only prompt fails closed before generation. The repair
must preserve the exact multiset of semantic scalar values. Any semantic
change fails closed. Semantic/enum/range/ID errors are never retried. There is
no substring acceptance, prose stripping, deterministic substitution, voting,
best-of-N, or fallback authoring.

The primary model is the local snapshot:

* `Qwen/Qwen2.5-Omni-7B`
* revision `ae9e1690543ffd5c0221dc27f79834d0294cba00`

The code intentionally does not silently fall back to generic templates or a
different model. A Qwen2.5-1.5B plus sampled-frame/CLAP/ASR route may be added
as a separately frozen future authoring backend, but it is not needed for this
v2 implementation and is not implicitly selected.

## Exact-target decoding

Execution uses PyAV seek-and-decode to create 28 temporary exact-interval
array pairs: 16 evenly spaced RGB frames and the full interval resampled to
mono 16 kHz audio. Each pair is bound to the original microsecond interval and
hashed. Only these arrays are used for model inference and audit. The full
source is not scanned for authoring, and no non-target media is materialized.

The extraction records, source hash, interval bindings, coverage metadata,
array shapes, and array hashes are stored in `target_manifest.json`.

## Output schema

The visual model call returns exactly `visual_description` and
`visual_query`. The ambient model call returns exactly `ambient_description`
and `ambient_query`. The accepted pair is assembled mechanically into the
four-field component projection before composition. Each two-field factor is
independently fail-closed before pairing and composition. Component/segment/stage/hop meta-language that expresses
cardinality or cross-component reference is forbidden, including forms such
as `another component`, `other component`, `first/second component`,
`both components`, and `previous/next component`. This is scoped to authoring
meta-language: an ordinary observable object phrase such as `another bowl`
remains eligible. The same validator rejects explicit causal phrases,
including `leads/leading/led to`, `results/resulting/resulted in`,
`produces/producing`, `triggers/triggering`, and `makes/making ... happen`.
The noun `result` is not rejected without a causal phrase pattern.

The separate composition call returns only `relation_kind`, fixed by shape:
`local_cooccurrence` for one component and `ordered_1_then_2` for two ordered
components. The pipeline mechanically constructs
`family_compositional_description` from accepted component description fields
and `family_compositional_query` from accepted component query fields. Frozen
connectors are the only added words, and a content-word firewall rejects
mechanical text containing any other token. Explicit causal phrase checks are
also rerun over the final mechanical relation texts.

R7 keeps component-local clause validation scoped to the clause's own
visual/acoustic coverage plus explicit continuity, causality, and unresolved
reference language. A local clause may therefore repeat its accepted
component's own observable agent or entity, including `person` or `operator`;
those nouns are not treated as cross-component bridges in isolation. Explicit
phrases such as `the same person`, `continues`, `again`, causal wording, or
unresolved references still fail closed. Cross-component relation and final
family gates remain unchanged and continue to reject same-agent, same-object,
continuity, and causality bridges across a two-component family.

R7 adds one narrow local-coreference exception: possessive `their`, `his`, or
`her` is not treated as a cross-component continuity reference when the same
clause contains an earlier explicit human-agent antecedent such as `a person`
or `the worker`, the pronoun is used as a possessive determiner, and the clause
contains no bridge marker such as `same`, `again`, `continues`, `still`,
`previous`, or `next`. A bare possessive without that antecedent remains
rejected. This exception is used only by component-local and one-component
mechanical validation; the two-component relation/final-text gate is not
relaxed.

Acoustic normalization maps `clear`, `clears`, `clearing`, or `cleared`
plus a possessive/determiner and `throat`, as well as nominal `throat
clearing`, to canonical `throat-clearing`. It is a specific acoustic event and
a clearly non-lexical human vocalization. The normal ASR degeneracy and
vocalization quarantine still runs, and any lexical speech wording still
fails closed. Mixed ambient wording that also describes a visible action does
not bypass the ambient gate: for example, a query asking only what sound a
person makes before placing a lid must itself contain a recognized specific
acoustic event or fail that field's acoustic grounding check.

R9 narrowed the deterministic ambient lexical gate. Specific acoustic concepts
are divided into two classes:

* unambiguous acoustic events such as `clank`, `hiss`, `thud`, `beep`,
  `rustle`, and `throat-clearing`, which may pass directly; and
* ambiguous action tokens such as `impact`, `tap`, `click`, `scratch`,
  `scrape`, `knock`, `snap`, `ring`, `rattle`, `splash`, `crumpling`, and
  `crinkling`, which pass only when a local structured helper binds the event
  to an auditory marker or controlled sound-event syntax.

Accepted bindings include event-plus-noun forms (`scraping noise`, `clicking
sounds`), perception or property forms (`a sharp tap is heard`, `an audible
click`), response forms (`a knock echoes`), `sound of <event>`, and a
conservative event-noun form with adjacent acoustic modifiers such as
`metallic`, `sharp`, `brief`, or `chopping`. A sentence-level occurrence of
`sound`, `noise`, or `quiet` elsewhere does not bind an action token. Thus
`sound menu button click` remains rejected, as do purely visual or abstract
uses such as `color choice impacts appearance`, `person taps a button`,
`clicks a menu button`, and `hand scratches a label`.

R10 is a narrow independent-review repair over that gate:

* ambient descriptions and queries alone may contain two normalized words,
  but both fields still pass the same specific-acoustic and lexical-speech
  gates; visual descriptions and queries retain the three-word minimum;
* `scraping noise` and `throat clearing` therefore pass end to end, while
  generic `sound quiet` remains invalid;
* every ambiguous acoustic-token mention in an ambient field must have valid
  local acoustic binding. A valid `beep` elsewhere cannot rescue `beep ...
  taps a button`; `color choice impacts sound quality` and `click sound menu
  button` also fail;
* controlled positives include `sound of a button click` and `audible
  clicking`; and
* lexical speech uses an exact inflection lexicon rather than broad prefix
  matching. `single` no longer matches `sing`, `ready` no longer matches
  `read`, while `ask/asks/asked/asking`,
  `question/questions/questioned/questioning`, and
  `answer/answers/answered/answering` fail closed. Thus `a beep sounds while
  a person asks a question` is rejected.

Raw initial and repair text is retained on both success and failure, including
UTF-8 byte length, base64 bytes, byte SHA-256, exact structured conversation,
exact rendered prompt text/hash, parser error, model identity, clip manifest
hashes, token counts, latency, network-attempt counts, and the explicit media
contract. Token evidence distinguishes assistant-prefill tokens from generated
tokens and records why generation stopped. The contract records placeholder
counts, supplied tensor counts, processed video/audio placeholder-token
counts, processor media-feature keys, and whether in-video audio was enabled.
Descriptions are marked
machine-authored and explicitly carry no human semantic label.

Primary rows no longer use `content_grounded=true`. That flag asserted more
than machine checks could establish. Every query and description starts with
`machine_observation_status=PENDING_MACHINE_SEMANTIC_GATES`,
`human_grounded=false`, and a field-specific gate map. After auditing, the
machine status becomes `MACHINE_GATES_PASSED` or
`MACHINE_GATES_FAILED_CLOSED`; no route emits a human-grounded assertion.

Final query and description text must omit:

* source or dataset names;
* private/public IDs;
* timestamps or interval values;
* provisional slot literals;
* copied four-token ASR phrases;
* answer keys;
* explicit modality labels such as “visual,” “video,” “audio,” or “ambient.”

Concrete event words such as “clatter,” “scrape,” “pouring,” or “impact” are
permitted because they describe the event rather than naming a modality.

## Audits

All audits must pass before an output can be sealed.

### Literal leakage

The audit checks all authored queries and descriptions for source literals,
private IDs, timestamps, slot names, and explicit modality labels. A pinned
local `openai/whisper-tiny.en` snapshot transcribes only each exact target
clip. The transcript is never shown to the authoring model. Any contiguous
four-token overlap between authored text and the applicable transcript fails
closed.

### Duplicate and lexical collision

Normalized exact duplicates fail. Same-kind query pairs also fail at token
Jaccard similarity at or above 0.92 when at least five tokens are shared.
All 20 normalized family-compositional queries must be unique.

### Query-only embedding similarity

The pinned local SigLIP2 text encoder audits visual and family-compositional
queries. The pinned local CLAP text encoder audits ambient and
family-compositional queries. Same-kind pairs at cosine similarity 0.995 or
higher fail closed.

Only query text is embedded. Target vectors, non-target vectors, index shards,
and rankings are never read. Query embeddings are not persisted; only audit
thresholds, maximum pairs, and collision findings are stored.

### Frozen semantic authoring gates

Full and canary execution call the same parent gate suite. The following
thresholds and rules are frozen and are tested with synthetic variants rather
than only the exact canary wording:

1. **Ambient acoustic grounding.** Every ambient query and description must
   pass the deterministic structured lexical gate. Unambiguous acoustic
   events pass directly. Ambiguous action tokens pass only with locally bound
   auditory context or controlled sound-event syntax; whole-sentence
   `sound`/`noise` keyword presence is insufficient. Generic `sound` or
   `quiet` without a specific event also fails. CLAP text acousticness remains
   recorded as a later embedding diagnostic for rows lacking explicit
   concepts, using the same four acoustic and four visual-action anchors and
   frozen `0.20` positive-cosine / `0.08` margin thresholds, but it does not
   override the fail-closed lexical decision.
2. **Degenerate ASR quarantine.** Whisper output is degenerate when an
   eight-or-more-token transcript has unique-token ratio below `0.25`, one
   short vocalization occupies at least `0.70` of four or more tokens, or the
   transcript has at most two unique low-information tokens. A human-
   vocalization ambient field on such a clip is quarantined. It passes only
   when conservative terms identify a nonlexical event (`cough`, `sneeze`,
   `gasp`, `sigh`, `groan`, `moan`, `laugh`, or throat-clearing) and no
   speech term is present.
3. **Cross-kind distinctness.** A component's visual and ambient queries fail
   with at least four shared tokens and token Jaccard at or above `0.72`.
   They also fail when both SigLIP-text and CLAP-text cosine are at least
   `0.94`, or either cosine is at least `0.985`.
4. **Far-family composition.** A two-component family query must cover both
   visual component events in chronological order and include an explicit
   acoustic term overlapping a component ambient query. It rejects same-
   person/object claims, continuation words (`continues`, `still`, `again`),
   and causal language (`because`, `causes`, `therefore`, `so that`).
5. **Standalone handle queries.** Handle queries reject unresolved pronouns
   and deixis including `it`, `they`, `this`, `that`, `then`, `prior`,
   `previously`, `former`, `latter`, and `thereafter`. Initial definite human
   references such as “the person” also fail.
6. **Query-to-description identity.** Normalized equality fails, as does token
   Jaccard at or above `0.90` with at least five shared tokens.

Audit artifacts retain every threshold, applicable field result, and whether
the ambient field used the lexical or CLAP route. Embeddings remain ephemeral.

### Template-only control

No template-only row is allowed in the primary query set. An optional
`--emit-explicit-template-baseline` writes a separately named baseline whose
rows are marked:

* `content_grounded=false`
* `template_only_control=true`
* `eligible_for_primary_query_set=false`
* `eligible_for_scientific_scoring=false`

It is never merged into the 76 primary queries.

## Fail-closed behavior

`--preflight` verifies the repaired bundle, source media, PyAV/NumPy runtime,
and all four local snapshots. If Qwen, Whisper, SigLIP2, or CLAP is
unavailable, execution is blocked. Network access is disabled by offline
environment variables and a socket-denial context.

`--execute` additionally requires a version-2 separate authorization receipt
binding the pipeline ID, exact SHA-256 of the current pipeline source, exact
bundle file hashes, output path, and one local run. A version-1 receipt is
invalid after this repair. Because authorization also binds the exact current
pipeline source hash, every receipt issued before the media-contract repair is
invalid as well. The constrained-decoding source change changes that bound
hash again, so every earlier receipt remains invalid. No receipt is created by
this implementation task. Output is built in a staging directory and
atomically installed only after all model calls and audits pass.

On failure, the successful output path is not installed. Instead, the staging
directory is converted atomically into a create-once restricted failure
capsule named from the output and authorization ID. Temporary clip arrays are
removed, but prompt manifests, raw initial/repair output evidence, target
manifest hashes, contract/model identity, parser errors, runtime/RSS/stage
times, and a bounded stderr/traceback summary are retained. Stage timing is
incremental: an exception records `<stage>_partial_seconds`. Target and ASR
manifests are rewritten after every completed record, and model-call counts
are reconstructed from `raw_attempts.jsonl`, so completed work is not lost
when a stage raises. Thus cleanup can no longer destroy the evidence needed to
diagnose a real model failure.

## Artifacts from a future authorized run

* `authoring_contract.json`
* `target_manifest.json`
* `prompt_manifest.json`
* `raw_attempts.jsonl`
* `asr_audit_inventory.json`
* `authored_queries.json`
* `audits.json`
* `resource_runtime.json`
* `seal.json`
* optional, excluded `explicit_template_baseline.json`

## Commands

Model-free plan and synthetic checks:

```bash
python tools/p23_102_query_authoring_v2.py --plan
python tools/p23_102_query_authoring_v2.py --synthetic-self-test
pytest -q tooling/tests/test_p23_102_query_authoring_v2.py
```

The targeted tests load the pinned local Qwen2.5-Omni processor without
loading model weights. They verify nonzero, component-scaled video and audio
placeholder tokens/features for one- and two-component initial prompts, zero
media tokens/features for the repair prompt, fail-closed mismatch handling,
the incremental JSON state machine including escaped braces and nested values,
rejection of multiple objects/prose/fences/unfinished JSON, prefill accounting,
a fake generation that stops before scripted trailing prose, token-cap failure,
and a text-only second repair generation call guarded by semantic scalar
preservation.
They also reproduce the v1.5 semantic failures with synthetic variants:
action-only ambient text, repeated-vocalization ASR with unsupported speech
claims, cross-kind paraphrases, unresolved `then`/pronouns, unsupported far-
family continuity, a missing acoustic relation, and query/description
identity. Separate positives cover a valid local visual-plus-acoustic case and
a conservative nonlexical cough case. R5 regressions additionally cover the
exact one-component `another component` inheritance attack, two-component
component-local cross-reference, the expanded causal phrase family, final
mechanical causal-text rejection, ordinary `another bowl`, and nominal
`result` content.
R7 adds the exact observed family-005 component-1 ambient factor
`A person clears their throat and then places a pot lid on the counter.` as a
passing component-local coverage regression. It also covers bare
`their throat clearing` without an antecedent, `same person clears their
throat again`, and a two-component `their` bridge as negatives; all supported
throat-clear inflections normalize to `throat-clearing`; and lexical speech
remains rejected. The retained R8 negative `metal pot placed` is rejected
because it names no specific acoustic event. R9 adds exact negatives for
`color choice impacts appearance`, `person taps a button`, `clicks a menu
button`, and `hand scratches a label`, plus an unbound-keyword bypass
regression such as `sound menu button click`. Positive fixtures include `a
sharp tap is heard`, `metallic clicking sounds`, `scraping noise`, and `a
knock echoes`; unambiguous events and R7 throat-clearing remain eligible.
Generic sound/quiet and lexical speech remain rejected. R8 modality isolation,
factor namespace/provenance, and the 76-call budget are unchanged.
R10 adds end-to-end `validate_ambient_factor_output` coverage for two-token
specific phrases, generic sound, mixed valid-plus-unbound ambiguous mentions,
controlled click patterns, exact speech inflections, and the `single`/`ready`
prefix false positives. It does not change R8 modality isolation, factor
namespace/provenance, the 76-call budget, or attested-integrity boundaries.
R11 is an additional narrow token-role repair: when an ambiguous form is
already consumed as the controlled auditory response marker of an accepted
event, as `echoes` is for `knock` in `a knock echoes`, that token is not
re-counted as a second independent ambiguous mention. The end-to-end ambient
validator now accepts both three-word and two-word fixtures for that pattern.
Independent visual or abstract echo uses remain fail-closed: `the design
echoes a theme` and `echo button` are rejected, including when mixed with an
otherwise valid event. `an echo is heard` remains valid through explicit local
auditory context. All R10 negatives and mixed-mention rejection remain in
force. R8 modality isolation, factor namespace/provenance, the 76-call budget,
and authorization/integrity boundaries are unchanged.

R12 adds the paired-factor semantic boundary required by the R11 failure
capsule. `ACOUSTIC_CONCEPT_REGISTRY` is now the single source of truth for
exact unambiguous and ambiguous acoustic forms, concept maps, and the registry
manifest hash. It includes conservative exact inflections for creaks, clinks,
jingles, dings, pings, pops, crunches, grinding, screeches, squeals, rumbles,
whooshes, swishes, drips, trickles, gurgles, sloshes, bubbles, ticks, alarms,
sirens, bells, horns, footsteps, applause, barks, meows, and chirps. No broad
prefix or `startswith` acoustic acceptance is used. `slam`, `drop`, `break`,
`shatter`, `tear`, `rip`, `chop`, `cut`, `stir`, `pour`, `clap`, `stomp`,
`open`, `close`, and `slide` remain ambiguous and require local auditory
binding.

Visual and ambient factor validators now reject normalized identity and
token-set identity immediately with
`MODEL_VISUAL_QUERY_DESCRIPTION_IDENTITY` or
`MODEL_AMBIENT_QUERY_DESCRIPTION_IDENTITY`. These semantic failures are not
schema-repair eligible, so an exact copied pair produces one authoring call
and no repair call. The later Jaccard near-identity gate remains active as a
separate defense.

Each accepted query must also be semantically contained by its paired
description. Controlled question scaffolds and exact acoustic-concept
inflection equivalence are allowed, but a query cannot introduce a new
specific source, material, object, direction, state, or action. Thus
`crumpling sound` to `crumpling paper`, and `door creaks` to an
`open`/`closing` query, fail closed. Visual generic scaffolds such as
`What is the person doing?` also fail when they do not preserve concrete
content anchors. The prompt states the distinct field roles and contains
mechanically checkable positive and negative examples.

The R11 observed `a door creaks open` output now passes the acoustic concept
recognizer because `creaks` is an exact registry form, then fails at factor
identity before repair. Canary2 tracks the active stage explicitly, so this
class of validator failure is recorded as `omni_authoring`, not
`query_collision_audits`. R8 modality isolation, accepted-factor provenance,
attested-integrity boundaries, and the 76 initial-call budget are unchanged.
All authorization receipts bound to pre-R12 code or plans are invalid.

R13 introduced an extremely narrow paired-query and local-binding repair. Its
acoustic half remains active. R15 supersedes and disables the later R14
visual-agentive-passive allowance.

For context-bound acoustic events, an auditory adjective marker may now occur
immediately after the event token as well as immediately before it. Thus
`A bell rings audibly.` and `A bell is audibly ringing.` use equivalent local
binding. The repair is a one-token adjacency pattern, not a sentence-level
window: a distant `audibly` or `sound` attached to another event cannot bind
an earlier `rings`, and every other ambiguous mention must still bind
independently. R9/R10 mixed valid-event plus unbound-mention negatives remain
fail-closed. The registry, factor identity, semantic containment,
failure-stage accounting, R8 isolation/provenance, attested-integrity
boundary, and 76 initial-call budget are unchanged. All authorization
receipts bound to pre-R13 code or plans are invalid.

R15 stops parsing visual passive-agent relations. The controlled passive
action map and description-side active-relation proof are removed. Every
standalone normalized `by` token in `visual_query` now fails closed before
paired-content comparison. This rejects every agentive
`participle by <agent>` query, including the former valid R14 example
`Which metal bowl is lifted by the hand from the counter?`. It also
conservatively rejects a genuine locative-preposition use of `by`; that
precision tradeoff is intentional. The ordinary token `nearby` is not split
and remains unaffected.

For `A hand lifts a metal bowl from a counter.`, accepted alternatives include
`Which metal bowl is a hand lifting from the counter?`,
`Which metal bowl is being lifted from the counter?`, and
`metal bowl lifting from the counter`. Prompts direct authoring toward active
questions, agent-free passive questions, concrete noun/action phrases, and
specific object/action retrieval wording. Generic visual queries and any new
noun, material, state, direction, or action still fail under the unchanged
identity and semantic-containment gates.

The former R14 anchor bypasses remain rejected:
`worker + sealed box stand nearby -> sealed by worker`,
`covered bowl + resting hand -> covered by hand`, and
`red ... by hand`. They are now rejected by the uniform standalone-`by`
boundary rather than by role parsing.

The R13 postposed auditory-marker repair remains unchanged. Registry,
description/query identity, paired containment, Canary2 failure-stage
accounting, R8 modality isolation and accepted-factor provenance,
attested-integrity boundaries, and the 76 initial-call budget are unchanged.
All authorization receipts bound to pre-R15 code or plans are invalid.

Availability check without loading the models:

```bash
python tools/p23_102_query_authoring_v2.py --preflight
```

Future execution requires a separately approved receipt:

```bash
python tools/p23_102_query_authoring_v2.py \
  --execute \
  --authorization <approved-authorization-receipt.json>
```

This task does not run that command.

## R16 structured ambient semantics

R16 replaces ambient model-authored natural language with one closed semantic
tuple: `event_kind`, perceptual-only nullable `source_hint`, and nullable
`timbre`, `loudness`, and `temporal_pattern`. The model sees audio only and may
copy only listed enum values. Action/state directions such as open, close,
drop, chop, pour, place, cut, break, shatter, tear, rip, stir, clap, stomp,
slide, and slam are not event kinds. Factual sources/materials such as
`metal_object`, paper, person, and button are not source hints. The only
non-null R16 hint is the conservative perceptual value `door_like`, rendered
mechanically as `door-like` and compatible only with a tiny event allowlist.

`ambient_description` and `ambient_query` are generated by two deterministic
mechanical templates from the same canonical tuple. They consume zero model
calls, carry identical semantic atom sets, have distinct structures, and are
checked across every allowed tuple for deterministic pair uniqueness and
round-trip validation. Unknown tuples and source-hint/event combinations fail
closed. The legacy natural-language acoustic helpers remain solely for
historical R9–R15 tests and derived-text sanity; they are not the ambient model
semantic entry point.

Accepted ambient factors bind the canonical tuple, both derived strings, the
tuple/description/query/joint hashes, and the structured registry,
generator, and template hashes. Raw attempt `parsed_output_sha256` binds the
model-authored tuple. Accepted manifests, final-row factor bindings,
provenance rebuild, seals, and Canary2 attested-integrity validation reject
any tuple, derived text, registry, generator, or template tamper. Schema-only
repair remains scalar-exact; enum and semantic failures are not repairable.
The full budget remains 28 visual + 28 ambient + 20 composition = 76 initial
calls, with zero calls for mechanical ambient text.

## R17 strict derived-text parse-back and template commitment

R17 retains the R16 tuple schema and all R15 visual rules, but closes three
P1 integrity gaps. `AMBIENT_TEMPLATE_SPEC` is now the sole declarative source
of truth for the description grammar, query grammar, property order,
separators, null omission, and source-hint rendering. The forward generator,
template manifest, template hash, and generator manifest/hash are all derived
from that one object. Runtime generation fails closed if the committed
manifest or hashes no longer match the live spec.

The derived-text check is a real parse-back. A controlled parser separately
matches the complete description and complete query against their frozen
template grammars, extracts `event_kind`, `source_hint`, `timbre`, `loudness`,
and `temporal_pattern`, rebuilds the canonical tuple, and requires exact
dictionary equality with the model-authored tuple. It performs no permissive
NLP and has no fallback. Missing, reordered, duplicated, extra, or unknown
properties fail with a field-specific parse or tuple-mismatch error.

The generator self-audit now asserts exactly **8040** allowed combinations and
exactly **8040** unique description/query pairs. Every one of the 8040
descriptions and every one of the 8040 queries independently parses back to
its originating tuple. Accepted-factor construction and validation,
provenance replay, final-row validation, and sealed-output validation all
recompute the derived strings, independently parse both strings, and verify
the registry, generator, and template hashes.

The future-run inventory explicitly includes
`accepted_factor_manifest.json`. The 76 initial-call budget, R8
isolation/provenance contract, R15 visual contract, relation-kind behavior,
`omni_authoring` failure stage, and no-real-execution/no-real-GO boundary are
unchanged. Every pre-R17 authorization receipt is stale.

## R18 source-free acoustic tuple

R18 is a narrow correction prompted by the first real R17 ambient raw:
`event_kind=crinkle`, `source_hint=paper`, `timbre=crisp`,
`loudness=soft`, `temporal_pattern=repeated`. R17 correctly rejected `paper`
because it was outside the hint enum, but the field itself encouraged the
model to guess a source or material. R18 therefore removes `source_hint`
entirely from the model-facing schema, canonical tuple, registry, generator,
template, parser, content atoms, accepted bindings, provenance, final rows,
manifest and seal validation.

The exact top-level ambient keys are now only `event_kind` and
`acoustic_properties`; the nested exact keys remain `timbre`, `loudness`, and
`temporal_pattern`. Any `source_hint` key is explicitly forbidden, including
values such as `paper`, `bell_like`, or `null`. A raw object containing that
field is not schema-repair eligible because the scalar-preserving repair
contract forbids deleting semantic content. The corresponding pure-acoustic
tuple `crinkle + crisp + soft + repeated` passes and derives:
`A soft repeated crisp crinkle is audible.` and
`Find the audible crinkle event matching crisp, repeated, soft.`

The prompt now permits only a heard event and acoustic timbre, loudness, and
temporal pattern. It explicitly forbids source, material, object, agent,
location, direction, action state, and source-similarity inference. Mechanical
description/query text contains no source-like dimension. Content atoms have
exactly four dimensions: event, timbre, loudness, and temporal pattern.

With 63 closed event kinds, 6 timbre values, 4 loudness values, and 5 temporal
pattern values, the exhaustive space is exactly **7560** combinations and
**7560** unique description/query pairs. Both strings independently parse
back for every combination. Registry, generator, and template hashes change;
all tuple/derived/provenance/manifest/final-row/seal validators continue to
bind and recompute those hashes.

R18 retains the R17 single-template commitment, event-kind closed set, R15
visual contract, R8 modality isolation/provenance, 76 initial-call budget,
repair and `omni_authoring` failure-stage behavior, accepted-manifest
inventory, and no-real-execution/no-real-GO boundary. Every pre-R18
authorization receipt is stale.

## R19 explicit raw/accepted ambient lifecycle

R19 is an extremely narrow lifecycle correction prompted by the real R18 raw
tuple `crinkle + crisp + soft + repeated`. The raw tuple correctly crossed
`validate_ambient_factor_output` and became an accepted ambient factor with
canonical semantics, both derived strings, and all tuple/derived/registry/
generator/template hashes. Assembly then incorrectly sent that accepted
factor back through the raw tuple validator, which rejected the additional
accepted fields.

The lifecycle is now explicit and fail closed:

* raw model tuples enter only `validate_ambient_factor_output`;
* accepted ambient factors enter only `validate_accepted_ambient_factor`;
* complete accepted visual-plus-ambient components enter the accepted
  component boundary before composition;
* composition sees only the validated four-string projection, while the
  assembled component retains the complete ambient tuple, derived fields, and
  hashes.

Sending an accepted factor to the raw validator or a raw tuple to the accepted
validator is a field-set error. Assembly, mechanical composition, accepted
manifest/final-row materialization, provenance rebuild, seal validation, and
output validation consume accepted factors. Raw-attempt replay alone parses
the raw JSON tuple, validates it through the raw boundary, and requires exact
equality with the independently validated accepted binding.

The established `parsed_output_sha256` convention is unchanged: an ambient
attempt binds the accepted factor's canonical `ambient_semantics` hash, not
the larger accepted factor object or either derived string. Regression tests
fix this convention, exercise the exact R18 tuple through the synthetic
`author_one_family` path, and retain all accepted-factor tamper rejection.

R19 changes no model-facing schema, enum, template, parser, registry,
generator, prompt semantics, call budget, media isolation, visual policy, or
authorization boundary. R18 source-free semantics, R17 parse-back/template
commitment, R15 visual behavior, R8 isolation/provenance, and the 76-call
budget remain unchanged. Every pre-R19 authorization receipt is stale.

## R20 token-trie constrained ambient authoring

R20 makes the closed ambient tuple set a decoder-time token constraint rather
than only a post-generation validator. The ambient model call alone uses an
exact token-prefix trie over canonical JSON strings. Visual and composition
generation retain the existing incremental single-JSON-object boundary. The
ambient trie is built mechanically after the local tokenizer is loaded and
does not count as a model call.

The authoritative ambient inventory is exactly **64 event kinds** × 6 timbre
values × 4 loudness values × 5 temporal-pattern values = **7680 tuples**.
Every tuple has a unique derived description/query pair, both strings parse
back independently, and every canonical tuple is a reachable trie leaf.
`continuous_liquid_flow` is the added acoustic event: continuous or pulsed
liquid-flow sound without asserting pouring, source, container, location, or
direction. It is explicitly distinguished from `drip`, `trickle`, `slosh`,
`splash`, `gurgle`, and `bubble`. `pour`, `open`, `chop`, `stir`, and `drop`
remain illegal event kinds and their canonical strings are unreachable.

The tokenizer-independent constraint manifest, its SHA-256, leaf count, and
reachable count are sealed through the prompt manifest, accepted ambient
factor, accepted-factor manifest, final-row bindings, authoring contract,
runtime, seal, and validators. Raw ambient attempts additionally bind the
tokenizer fingerprint, exact trie hash, assistant prefill, stop-token IDs, and
observed leaf/reachable counts. Validators recompute the accepted-factor type
counts and require exact constraint field sets at every boundary; missing,
extra, or altered kind/hash/count/runtime fields fail closed. Visual and
composition attempts carry only the explicit `json_object_boundary` record
and must not carry an ambient tuple constraint.

Assistant prefill is used only when `{` round-trips exactly for the decoder
tokenizer and chat-template boundary. Ambient generation may stop only after
a legal leaf emits an approved EOS/stop token; the terminal stop token is
excluded from JSON decoding. Ambient schema or semantic errors never enter
schema repair and therefore consume exactly one authoring call. The initial
budgets remain 76 for the full pipeline and 13 for Canary2; the maximum repair
budgets are 48 and 8 respectively because only visual and composition factors
are repair-eligible.

R19 accepted-factor lifecycle rules, R18 source-free semantics, R17 template
commitment, R15 visual behavior, R8 isolation/provenance, and the
no-real-execution/no-real-GO boundary remain active. Every pre-R20
authorization receipt and every R19 output fixture is stale.

## R21 trusted runtime-constraint validation

R21 closes the output-only metadata gap in R20. Output validation no longer
accepts a syntactically plausible trie hash, tokenizer hash, stop-token list,
or assistant prefill. Each validation process loads only the tokenizer from
the fixed local Qwen2.5-Omni snapshot, hashes the fixed tokenizer/config
files, regenerates all 7680 canonical strings from the code-owned enum, and
rebuilds the exact token-prefix trie without loading model weights or
decoding media. The trusted context is cached for the remainder of that
validation process.

Every ambient raw attempt must exactly equal the trusted manifest and
manifest hash, canonical-string commitment, trie hash, tokenizer fingerprint,
ordered stop-token IDs, assistant prefill, and 7680 leaf/reachable counts.
Reordered or extra stop IDs, an empty prefill, fake hashes, or altered counts
fail closed. Visual and composition attempts must exactly equal the trusted
JSON-object-boundary field set. The first validation in a process may spend
several seconds loading the local tokenizer and rebuilding the trie; this
runtime is reported as `trusted_constraint_context_build_seconds` and is not
reduced by weakening the check.

R20's 64-enum/7680-trie and `continuous_liquid_flow` contract, R19 lifecycle,
R8 isolation/provenance, 76 initial calls, 48 maximum schema repairs, and the
no-real-execution/no-real-GO boundary remain unchanged. Every pre-R21
authorization receipt and output fixture is stale.
