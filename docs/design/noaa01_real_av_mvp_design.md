# NOAA-01 real-A/V provisional episode MVP design

**Task:** 86  
**Date:** 2026-09-10  
**Stage:** `MACHINE_ADJUDICATED_PROVISIONAL_MVP`  
**Decision:** `READY_AFTER_TASK85`

## 1. Scope and non-claims

This document specifies the smallest executable bridge from the NOAA-01
restricted media audit and Task 84 machine adjudication to a real-media
protocol MVP. It does **not** promote any item to human-reviewed gold.

The design is ready to implement only after the independent Task 85 gate:

1. Task 85 must return `GO_PROVISIONAL_EPISODE_CONSTRUCTION` or a
   `CONDITIONAL_GO` whose item-level removals can be applied deterministically.
2. This audit preserves mappings for the seven candidates originally handed to
   Task 86. During the concurrent red-team repair, `noaa01-review-003` was
   downgraded to `defer`; the current authoritative Task 84 retained set is
   therefore six windows. The implementation set is the intersection of that
   current retained set and the final Task 85 retained set.
3. The run requires at least five usable episode families spanning all three
   pilot assets, including at least one speech-bearing family and the
   `noaa01-review-004` ambient candidate. Otherwise the next task must resample
   or return `NO_GO`; it must not silently relax the gate.

Every resulting record, report, and plot must retain:

```text
MACHINE_ADJUDICATED_PROVISIONAL_MVP
human_reviewed = false
gold_annotation = false
```

The current assets belong only in `EXTERNAL_COMPATIBILITY_UNPOOLED`. Their
acquisition records do not authorize public redistribution, and the current
manifest/authorization artifacts do not yet constitute the normative
annotation/release provenance bridge required by `validate_family(...,
media_mode="real")`.

## 2. Inputs and compatibility finding

### 2.1 Inputs inspected

- `docs/spec/episode_schema.json`
- `docs/spec/metrics_protocol.md`
- `docs/spec/tool_api.md`
- `docs/spec/semantic_validator_spec.md`
- `mvp/README.md`, `mvp/README_backend.md`,
  `mvp/README_experiment.md`
- `mvp/media_backed_v2/README.md`
- `src/av_trace_mvp/`
- `src/av_trace_media_pipeline/`
- `src/av_trace_agent_runtime/`
- `src/av_trace_validation/`
- Task 84 restricted export, detailed records, model manifest, and run manifest
- NOAA-01 acquisition manifest and media audit
- Task 85 prompt; its output is intentionally treated as a pending gate

### 2.2 What is reusable

| Component | Exact reusable interface | Use in the real-A/V MVP |
|---|---|---|
| Registered-byte decoding | `av_trace_media.reader.PyAVMediaReader` | Hash-check and decode exact source-time intervals. |
| Frozen index mechanics | `av_trace_mvp.index.FixedIndex`, `BackendManifest` | Stable ranking, hashes, record counts, costs, and fail-closed loading. |
| Tool/state machine | `av_trace_mvp.backend.FixedBackend` | Existing seven-tool surface, budgets, citable observations, and deterministic responses. |
| Intervention semantics | `av_trace_mvp.interventions.InterventionRuntime` | Exact CLEAN/BLOCKED/RESTORED start state and restoration behavior. |
| Blind process boundary | `av_trace_agent_runtime.runtime.SubprocessEpisodeRuntime` and `PolicyView` | Prevent policies from receiving family graph, state role, intervention, or oracle fields. |
| Trajectory schemas | `docs/spec/agent_action_schema.json`, `tool_response_schema.json`, `final_answer_schema.json`, `trajectory_schema.json` | Preserve the existing wire contract and citation representation. |
| Graph/trajectory validation | `av_trace.semantic.validate_family`, `av_trace_validation.graph`, `trajectory`, `generator`, `certifier` | Use only after provisional evidence and counterfactual gates have produced a promotable family. |
| Metric foundations | `av_trace_mvp.metrics` and `av_trace_validation.metrics_adapter` | Reuse claim/citation, cost, paired-state, and certified feasible-route machinery after the gaps below are closed. |

### 2.3 What is not directly reusable

1. `MediaPerception.synthetic`, `SyntheticVisualAdapter`,
   `SyntheticSpeechCodec`, and `SyntheticAmbientAdapter` recognize procedural
   fixtures, not natural NOAA media.
2. `av_trace_media_pipeline.indexing._scan_source` and
   `project_observation` contain a synthetic vocabulary and cannot represent
   Whisper/AST/OpenCV/Codex outputs faithfully.
3. `AlwaysAnswerAgent` is not a direct-long-context baseline: it uses search.
   All four current agents contain fixture-specific query and answer rules.
4. `episode_schema.json` asserts
   `satisfiability_validated=true`, `minimality_validated=true`, and
   `removal_validated=true`. Therefore the seven Task 84 records cannot be
   serialized as schema-valid episode families until the counterfactual and
   independent-validator steps have actually passed.
5. Real-media semantic validation requires a verified-asset bridge. The
   NOAA-01 acquisition/media-audit manifests are strong technical evidence but
   are not that bridge.
6. Existing `score_episode` exposes `evidence_coverage` but not the requested
   alternative-set-aware Evidence Recall, All-Evidence Success, Citation F1, or
   eligibility-aware Modality Recall. Its internal premature-stop denominator
   is deliberately unavailable unless the validator adapter is supplied.

The implementation task must therefore use a **two-stage representation**:

- a provisional blueprint record (the JSON companion to this document), which
  is allowed to carry pending hypotheses; then
- a normative 0.2.0 family only after Task 85, answer verification,
  alternative-evidence search, leave-one-out tests, two independent validator
  trajectories, and the real-media provenance bridge pass.

No schema field may be set to `true` merely to make the validator pass.

## 3. Source assets

| Asset | Duration | Exact acquired SHA-256 | Current technical status |
|---|---:|---|---|
| `cand-049` | 2465.329542 s | `1934c31cb0311a46daab367f840eb549d29bb1e9e1475a73287912bba03069e5` | Original MP4 hash-verified; video/audio decoded; timeline plausible. |
| `cand-051` | 3718.581542 s | `279f6b3841188e805b153ab0c7f0c85cdc584dd6bce6090f9e2a0b2d06d951b2` | Original MP4 hash-verified; video/audio decoded; timeline plausible. |
| `cand-052` | 3781.144042 s | `c4f5d8c6e60d6802bb60e26f811f5dcabc9698626a29c6cb8aabcc373db4eef1` | Original MP4 hash-verified; video/audio decoded; timeline plausible. |

The exact MP4 paths and model outputs remain restricted. Public-facing
artifacts may expose opaque asset IDs, source-time intervals, aggregate
statistics, and approved annotations only after a separate release gate.

## 4. Episode-construction protocol

### 4.1 Common rules

Each mapped window initially creates one **candidate family**, not one accepted
gold family. A mapped window that Task 84/85 downgrades remains only as
traceable design provenance and is not built.

For every candidate:

1. Decode the exact eight-second interval from the registered original MP4.
2. Re-run or bind the pinned Task 84 observation outputs. Preserve model ID,
   revision, parameters, output hash, and source interval.
3. Convert the question seed into a structured question and one or more atomic
   claims. Do not add semantic detail that is absent from the restricted
   record.
4. Search all 18 reviewed windows and the bounded neighboring source regions
   for equivalent answer support. Register every acceptable support set, or
   leave `alternative_search_completed=false`.
5. Run silent-video, transcript-only, ambient-only, question-only,
   metadata-only, neighboring-snippet, and duplicate-evidence checks as
   applicable.
6. Run leave-one-evidence and leave-one-modality counterfactuals. A modality
   remains a `candidate_role` until those tests and two independent validators
   agree.
7. Only then generate the normative graph, SES, necessity group, intervention
   triplet, feasible-route records, and certificate.

Evidence observations in the provisional layer must distinguish:

- `direct_model_output`: Whisper or AST output from exact decoded bytes;
- `deterministic_visual_proxy`: OpenCV feature-router output;
- `machine_semantic_synthesis`: Task 84 semantic description or question seed;
- `validated_episode_annotation`: unavailable until the promotion gate passes.

### 4.2 Candidate blueprints

#### `noaa01-review-003` → `noaa01-r003-waterfront-demonstration`

- **Source/interval:** `cand-049`, `[578.195, 586.195)`.
- **Current disposition:** `defer`; mapped for completeness but excluded from
  implementation unless a later explicit gate re-admits it.
- **Question hypothesis:** “Where are the two presenters standing?”
- **Answer hypothesis:** “On a waterfront platform.”
- **Claim:** two presenters stand on a waterfront platform.
- **Evidence:** one provisional vision unit over the exact interval, backed by
  Task 84 visual observations `0..6` and its machine semantic synthesis.
- **Candidate role:** `V`.
- **Still only a hypothesis:** that vision uniquely supplies a sufficiently
  specific location answer. The earlier demonstration-action wording was
  rejected by red-team inspection.
- **Required counterfactual:** verify the location label independently; confirm
  that speech, captions, metadata, and neighboring clips do not state the same
  answer; silent-video succeeds and transcript-only fails.
- **Distractors:** `noaa01-review-001`, `002`, `005`, and `006`, retaining their
  exact registered intervals.
- **Abstention rule:** omit the family under its current `defer` disposition;
  if re-admitted, abstain unless the location is independently verified.

#### `noaa01-review-004` → `noaa01-r004-surf-av`

- **Source/interval:** `cand-049`, `[1011.842, 1019.842)`.
- **Question hypothesis:** “What water conditions are depicted around the
  person, and which environmental sounds are detected in the same interval?”
- **Answer hypothesis:** visible breaking surf/rough water; detected
  ocean/waves/surf and wind.
- **Claims:** (1) a person is shown in breaking surf and rough water; (2) the
  audio event model detects ocean/waves/surf and wind in the same interval.
- **Evidence:** one vision unit plus one ambient unit. The ambient observation
  is supported by AST probabilities `Ocean=0.57266438`,
  `Waves, surf=0.51786554`, and `Wind=0.26152700`.
- **Candidate role:** `V+A`.
- **Still only a hypothesis:** event identity and modality necessity. AST is
  clip-level and does not localize or establish human-perceived audibility.
- **Required counterfactual:** vision-only must fail the explicitly audible
  claim; ambient-only must fail the depicted-person claim; the joint pair must
  support both; speech must not duplicate the ambient claim; independent
  review must confirm the sounds.
- **Distractors:** `noaa01-review-001`, `002`, `005`, and `006`.
- **Abstention rule:** if either modality is absent or unverified, return only
  the supported partial claim and mark the joint answer insufficient.

#### `noaa01-review-007` → `noaa01-r007-opening-plastic-waste`

- **Source/interval:** `cand-051`, `[0.000, 8.000)`.
- **Question hypothesis:** “What kind of discarded material is shown in the
  opening montage?”
- **Answer hypothesis:** plastic waste.
- **Claim:** the opening montage contains close views of plastic waste.
- **Evidence:** one provisional vision unit backed by Task 84 visual
  observations `0..6` and semantic synthesis.
- **Candidate role:** `V`.
- **Still only a hypothesis:** whether a more specific object label can be
  safely annotated and whether title graphics make the answer trivial.
- **Required counterfactual:** silent-video succeeds; transcript/audio and
  title-only crops fail to identify the answer; question-only and title-card
  shortcuts are below the frozen threshold.
- **Distractors:** `noaa01-review-008`, `009`, `010`, and `012`.
- **Abstention rule:** do not upgrade “plastic waste” to a specific object
  unless that object is separately verified.

#### `noaa01-review-011` → `noaa01-r011-litter-cleanup`

- **Source/interval:** `cand-051`, `[3055.773, 3063.773)`.
- **Question hypothesis:** “What cleanup action is the person carrying a bag
  performing?”
- **Answer hypothesis:** collecting litter beside a fence.
- **Claim:** a person carrying a bag collects litter beside a fence.
- **Evidence:** one provisional vision unit backed by Task 84 visual
  observations `0..6` and semantic synthesis.
- **Candidate role:** `V`.
- **Still only a hypothesis:** that narration does not independently reveal the
  action; Task 84 also found intelligible speech in the interval.
- **Required counterfactual:** silent-video supports the claim; transcript-only
  and audio-only do not fully support it; neighboring snippets and metadata do
  not leak it.
- **Distractors:** `noaa01-review-008`, `009`, `010`, and `012`.
- **Abstention rule:** if the visible action cannot be distinguished from
  merely carrying a bag, abstain rather than infer litter collection.

#### `noaa01-review-014` → `noaa01-r014-storm-formation`

- **Source/interval:** `cand-052`, `[443.899, 451.899)`.
- **Question hypothesis:** “What weather formation is shown while explanatory
  captions appear?”
- **Answer hypothesis:** dark rotating storm clouds.
- **Claim:** dark rotating storm clouds appear with explanatory captions.
- **Evidence:** one provisional vision unit backed by Task 84 visual
  observations `0..6` and semantic synthesis.
- **Candidate role:** `V`.
- **Still only a hypothesis:** whether captions or speech duplicate the visual
  answer and whether “rotating” is reliably observable.
- **Required counterfactual:** independently confirm the visual label; compare
  silent-video, transcript-only, caption-masked, and temporally shuffled
  variants.
- **Distractors:** `noaa01-review-013`, `015`, and `018`.
- **Abstention rule:** if rotation cannot be independently verified, answer
  only “storm clouds” or remove the family according to the frozen answer spec.

#### `noaa01-review-016` → `noaa01-r016-three-factors-vs`

- **Source/interval:** `cand-052`, `[1331.698, 1339.698)`.
- **Question hypothesis:** “How many hurricane-formation factors are stated in
  the narration and introduced by the graphic?”
- **Answer hypothesis:** three.
- **Claims:** (1) the narration states a count of three factors; (2) the
  educational graphic introduces three hurricane-formation factors; (3) the
  two modalities agree on the count.
- **Evidence:** one speech unit linked to
  `noaa01-review-016-asr-1`, plus one vision unit linked to Task 84 visual
  observations `0..6`.
- **Candidate role:** `V+S` corroboration.
- **Still only a hypothesis:** neither V nor S is currently minimal; each may
  independently reveal the answer token. This family tests channel-attributed
  corroboration, not yet multimodal necessity.
- **Required counterfactual:** for the two channel-attribution claims, V-only
  must fail the narration claim and S-only must fail the graphic claim. Also
  test whether either channel alone answers the unqualified count question;
  if so, do not report V+S answer minimality.
- **Distractors:** `noaa01-review-013`, `015`, and `018`.
- **Abstention rule:** a single-channel observation may support a partial count
  claim but not the cross-modal agreement claim.

#### `noaa01-review-017` → `noaa01-r017-north-atlantic-basin`

- **Source/interval:** `cand-052`, `[2663.396, 2671.396)`.
- **Question hypothesis:** “Which basin does the speaker identify as a main
  area of hurricane activity?”
- **Answer hypothesis:** North Atlantic Basin.
- **Claim:** the speaker identifies the North Atlantic Basin as a main area of
  hurricane activity.
- **Evidence:** one speech unit linked to
  `noaa01-review-017-asr-1`; Task 84 reports 29 lexical tokens, mean generated
  token log probability `-0.16288089`, and AST speech probability
  `0.94753802`.
- **Candidate role:** `S`.
- **Still only a hypothesis:** speech necessity; webinar visuals or neighboring
  text could duplicate the answer.
- **Required counterfactual:** independently verify the transcript; show
  transcript/audio succeeds while silent-video, metadata, neighboring
  snippets, and on-screen text do not provide the answer.
- **Distractors:** `noaa01-review-013`, `015`, and `018`.
- **Abstention rule:** if the basin name is not recovered from a citable speech
  observation, do not complete it from topic priors.

## 5. Frozen candidate pool and distractors

The first MVP is deliberately a **bounded candidate-pool retrieval pilot**, not
yet an exhaustive full-video retrieval benchmark. The source remains the full
20–90 minute video, but the initial fixed index contains the 18 reviewed
eight-second windows. This limitation must appear in every result report.

For each asset:

- index all reviewed windows from that asset, not only the answer window;
- emit modality-specific records only for observed channels;
- derive searchable content from frozen media-model observations, never from
  question text, answer text, graph descriptions, or reviewer rationales;
- use opaque hashed record IDs and generic pointer previews;
- mark every direct or derived answer-bearing record with all applicable
  evaluator-private route references;
- freeze ranking, tokenization, tie-breaking, top-k, models, and hashes before
  any baseline run.

Hard distractors are selected from same-asset non-answer windows by lexical or
embedding similarity after removing answer aliases. A distractor is admissible
only if an evaluator-private entailment check finds no support for any required
claim. If fewer than two admissible distractors remain for an episode, that
episode is not eligible for the retrieval comparison.

## 6. CLEAN / BLOCKED / RESTORED protocol

### 6.1 Common invariants

- `CLEAN` exposes the frozen source-level candidate universe and every
  provisionally answer-bearing route.
- `BLOCKED` starts from the same immutable index, ranking function, costs,
  question, graph, and budget. It changes exactly one registered route.
- `RESTORED` starts byte/state-identically to `BLOCKED`. A predeclared trigger
  reverses exactly the block. The agent must then reacquire citable evidence.
- A permanent deletion is not recovery and is ineligible for `Recovery`.
- No condition label, intervention ID, gold evidence ID, source basename,
  title, question seed, answer alias, or state-bearing filename is visible to
  the policy.

### 6.2 Per-family intervention

| Family | Mechanism | BLOCKED operation | RESTORED trigger/action | Seed |
|---|---|---|---|---:|
| `r003` | `necessity_group_withholding` | Hide the complete vision route and every derived record linked to it; keep same-source distractors. | At fixed call index 2, reverse the withholding. Success still requires a subsequent reformulated visual search and inspection. | 86003 |
| `r004` | `modality_channel_outage` | Disable ambient and hide the ambient route; visual remains available, yielding only a partial answer. | `get_channel_status(["ambient"])`, followed by ambient search/inspection. | 86004 |
| `r007` | `necessity_group_withholding` | Hide the complete opening-waste vision route and derived records; keep distractors. | Fixed call index 2, then a new visual query/inspection. | 86007 |
| `r011` | `necessity_group_withholding` | Hide the cleanup-action vision route and derived records; keep distractors. | Fixed call index 2, then a new visual query/inspection. | 86011 |
| `r014` | `necessity_group_withholding` | Hide the storm-formation vision route and derived records; keep distractors. | Fixed call index 2, then a new visual query/inspection. | 86014 |
| `r016` | `modality_channel_outage` | Disable speech/transcript and hide the speech route; the graphic can support only the visual channel-attribution claim. | `get_channel_status(["speech","transcript"])`, followed by speech search/transcript read. | 86016 |
| `r017` | `modality_channel_outage` | Disable speech/transcript and hide the answer-bearing speech route. | `get_channel_status(["speech","transcript"])`, followed by speech search/transcript read. | 86017 |

The four withholding families may only be promoted after the candidate route is
shown to intersect every acceptable support set. Otherwise their intervention
must be redesigned or the family removed.

### 6.3 Executable checks

For each promoted family:

1. `CLEAN` has at least one reachable accepted support set.
2. `BLOCKED` has none, but retains at least two admissible same-source
   distractors in the affected search channel when using withholding.
3. `RESTORED` pre-trigger hashes and responses equal `BLOCKED`.
4. The registered trigger fires at exactly the declared action/call index.
5. Post-trigger answer-bearing observations have the same IDs, payload hashes,
   intervals, ranking, and costs as `CLEAN`.
6. Two independent validator trajectories can reach an accepted set and
   supported finalization within the unchanged remaining budget.
7. A negative-control trajectory that does not trigger restoration cannot
   acquire the blocked evidence.
8. A permanent-deletion mutant fails the restoration proof and is excluded
   from recovery denominators.

### 6.4 Leakage checks

Fail the family if:

- question or answer aliases occur in pointer previews, opaque IDs, filenames,
  state labels, or public metadata;
- answer-bearing transcript text leaks through visual/ambient payloads or
  neighboring transcript snippets;
- visual answer text leaks through transcript, captions, title metadata, or
  reviewer rationale;
- any answer-bearing derivative lacks the route reference needed for
  transitive withholding;
- distractors entail a required claim;
- a classifier can predict CLEAN/BLOCKED/RESTORED above chance from non-content
  response formatting, latency, result count padding, IDs, or errors;
- the question alone or source title produces the answer above the frozen
  shortcut threshold.

## 7. Backend and baseline plan

### 7.1 Real-A/V backend

The next task should add a natural-media adapter rather than modify
`MediaPerception.synthetic`.

Its fixed observation store should be created offline from:

- exact interval decoding by `PyAVMediaReader`;
- pinned Whisper outputs for speech;
- pinned AST outputs for ambient events;
- a versioned visual semantic observation source. Until a genuine local visual
  model is available, Task 84 machine semantic synthesis may be used only as an
  explicit evaluator-side oracle field.

At tool time, `inspect_clip`/`read_transcript` must re-check the original media
hash and exact interval. Serving Task 84 JSON without touching registered media
is a **metadata-only protocol run** and must not be called a real-A/V system
evaluation.

### 7.2 Baseline families

| Baseline | Existing compatibility | MVP execution | Eligible claims |
|---|---|---|---|
| Direct long-context | No existing equivalent; `AlwaysAnswer` uses retrieval. | A separate deterministic protocol oracle receives all accessible frozen observations for the source candidate pool in one pass and emits claims/citations. Acquire and Act metrics are undefined. A future VLM must replace it for model conclusions. | End-to-end scoring plumbing, abstention, claim/citation evaluator behavior only. |
| Single-shot RAG | Reuse runtime/backend; rewrite fixture-specific policy. | One frozen query plan, top-k search, one inspection/read round, then answer or abstain; no status call or retry. | Single-shot retrieval/grounding over real-derived observations; no recovery credit. |
| ReAct/recovery | Reuse runtime/backend and control pattern; replace vocabulary/rules. | Iterative modality routing, query reformulation, typed outage handling, optional status call, reacquisition, finalize. | Tool trajectory, failed-search recovery, costs, and supported finalization. |
| Evidence-sufficiency agent | Reuse structured belief schema and control pattern; replace fixture sufficiency heuristic. | Maintain acquired provisional evidence/claim coverage; predict missing modality/hop/cause; continue or abstain until a support set is observed. | Sufficiency calibration, premature stop, modality routing, recovery, and supported grounding—conditioned on provisional annotations. |

The deterministic agents are protocol probes, not learned baselines. Their
results may establish engineering operability and whether the diagnostic
metrics separate intentionally different policies. They cannot establish
general video-understanding quality, natural-language planning ability,
state-of-the-art retrieval, or superiority over published models.

## 8. Metrics and denominators

Let \(O\) be the evaluator-private evidence IDs acquired by a trajectory and
\(\mathcal E_f\) the set of all accepted support sets for family \(f\).

### Acquire

- **Evidence Recall:**  
  \(\max_{E\in\mathcal E_f}|O\cap E|/|E|\). Eligible only when at least one
  support set has passed satisfiability review. Before final validation it is
  labeled `hypothesis_conditioned`.
- **All-Evidence Success:**  
  \(1[\exists E\in\mathcal E_f:E\subseteq O]\). Same eligibility.
- **Modality Recall:** best-match recall against modality sets induced by
  independently counterfactually validated acceptable support sets. It is
  `null` when modality necessity remains a routing hypothesis. A separate
  non-primary `candidate_modality_routing_coverage` may be reported.

Search pointers do not count as acquired evidence; only citable observations
do. Direct-long-context has all three Acquire metrics `null`.

### Ground

- **Answer Score:** structured required-claim correctness, with frozen aliases
  and no forbidden/contradictory claim. Eligible after the answer hypothesis
  passes the Task 85/answer verification gate.
- **Citation precision:** asserted claims with at least one valid supporting
  derivation divided by asserted claims with citations.
- **Citation recall:** required claims with a valid cited derivation divided by
  required claims.
- **Citation F1:** harmonic mean of citation precision/recall; `null` when
  either denominator is structurally ineligible, and zero when an eligible
  system supplies no required citation.
- **Supported-Claim Rate:** supported asserted claims divided by asserted
  claims. For a correct abstention with zero claims this is `null`, not one.

Alternative support is handled by maximizing over independently accepted
support sets or by a registered claim-evidence entailment relation with
temporal overlap. Matching only one preferred clip is forbidden.

### Act

- **Success@Budget:** supported final success with a valid trajectory,
  unchanged family budget, and no post-budget evidence.
- **Premature Stop:** eligible only when a certified feasible route remains at
  the final decision point under the remaining steps/cost. Otherwise both
  numerator and denominator are zero/undefined.
- **Recovery:** eligible only for a matched `RESTORED` episode whose block is
  valid, source evidence exists, restoration is exact, the trigger fires, and
  a feasible post-trigger route remains. Success requires acquisition of an
  acceptable set and supported finalization after the trigger.

Direct-long-context and single-shot RAG receive `Recovery=null`, never zero or
credit. Recovery-agent results must also report trigger rate, recovery
conditional on trigger, and unconditional matched-family recovery.

### Tiny-slice reporting

Every metric row carries numerator, denominator, eligible family count, and
eligible source count. Any slice with fewer than five families or three source
videos is labeled `LOW_N_NO_INFERENCE`. With only three source videos, bootstrap
intervals may be shown descriptively but cannot support significance or model
ranking claims. Undefined values remain JSON `null`; they are never coerced to
zero.

## 9. Implementation gaps

1. **Task 85 adapter:** parse its decision and item-level retain/downgrade/drop
   verdicts; fail closed if absent or inconsistent.
2. **Authorization/provenance:** record the user's internal provisional
   annotation authorization in a normalized acquisition-manifest-compatible
   record, and build one verified-asset bridge per source with exact content,
   stream, duration, lineage, and access fields.
3. **Provisional blueprint validator:** validate pending fields without
   pretending that schema 0.2.0 minimality booleans have passed.
4. **Natural-media observation adapter:** package exact Task 84 Whisper/AST
   inference and a versioned visual observation source behind the existing
   tool payload contract. Do not call synthetic adapters.
5. **Bounded real index builder:** freeze all 18 same-source candidate windows,
   generic previews, route closure, distractors, ranking, hashes, and no-leak
   checks.
6. **Promotion builder:** after counterfactual validation, emit normative
   families, backend artifacts, intervention manifests, and validator inputs.
7. **Real baseline policies:** implement all four families without synthetic
   keywords or answer templates and label deterministic oracle use.
8. **Metric extension:** add alternative-set Evidence Recall,
   All-Evidence Success, Citation F1, denominator eligibility, null handling,
   and low-N flags.
9. **Real validator/certifier integration:** pass acquisition gate, verified
   asset bridge, two validator plans, minimality, blocking, restoration, route
   feasibility, denominator, replay, and leakage tests.
10. **Run/report separation:** keep restricted transcripts/model outputs below
    `data/restricted/noaa01`; emit only approved aggregate public fields.

## 10. Go/No-Go protocol

### `ENGINEERING_GO`

All must hold:

- Task 85 gate accepted and applied;
- at least five families across `cand-049`, `cand-051`, and `cand-052`;
- exact media hashes and interval A/V decoding pass;
- frozen index contains all retained evidence and at least two admissible
  same-source distractors per retrieval-eligible family;
- all promoted families pass structural, semantic, provenance, intervention,
  trajectory, and certification checks;
- all four baseline harnesses complete deterministically; every applicable
  trajectory is valid;
- CLEAN/BLOCKED/RESTORED invariants and replay hashes pass;
- no leakage or persistent media-derivative violation occurs.

### `PROVISIONAL_SCIENTIFIC_GO`

Requires `ENGINEERING_GO`, plus:

- retained set includes at least one visual, one speech, one cross-modal, and
  the independently retained ambient candidate;
- at least one recovery-eligible family succeeds after a real registered
  restoration trigger;
- acquisition shows a non-tied failure/rank pattern across at least two
  applicable systems;
- grounding shows at least one diagnostic separation not visible in answer
  correctness alone, such as correct answer with invalid/incomplete citations
  or unsupported claims;
- action shows at least one difference in recovery or premature-stop behavior
  between ReAct/recovery and evidence-sufficiency policies;
- the observed separation is present in all three diagnostic families
  (Acquire, Ground, Act), not merely in code completion or tool cost;
- every conclusion is labeled descriptive,
  machine-adjudicated, provisional, and low-N.

If the four deterministic policies separate only because of hard-coded
question templates or oracle answer access, the scientific gate fails even if
all tests pass.

### `FINAL_BENCHMARK_NOT_YET_VALIDATED`

This remains mandatory for this milestone. Removing it requires, at minimum:

- human verification and adjudication of questions, answers, evidence, and
  modality counterfactuals;
- complete alternative-evidence search;
- release/redistribution and privacy review;
- public-core provenance;
- broader source/domain scale;
- genuine learned visual/audio-language and agent baselines;
- preregistered confirmatory metrics and a sufficiently large independent test
  set.

## 11. Final design decision

`READY_AFTER_TASK85`

The existing protocol is sufficient as the **promotion target**, and its fixed
backend, intervention runtime, process boundary, and validator architecture are
strong reusable foundations. The next task must not bypass the pending Task 85
gate, the real-media provenance bridge, or counterfactual validation. Until
those pass, the seven mappings are executable blueprints rather than schema
0.2.0 gold families.
