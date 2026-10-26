# AV-TRACE synthetic MVP: independent scientific and implementation red-team review

**Review date:** 2026-09-05  
**Scope:** integrated offline synthetic MVP, including normative specifications, generated artifacts, backend, agents, metrics, tests, and reported results.  
**Reviewer posture:** a successful run is treated as evidence of executable plumbing, not by itself as evidence of construct validity or scientific thesis support.

## Executive verdict

The reviewed system is a useful **deterministic metadata-backed protocol simulator**. It demonstrates that the repository can generate schema-valid matched triplets, execute a fixed tool protocol, apply two intervention mechanisms, trigger restoration, validate trajectories, and aggregate results reproducibly within the present environment.

It does **not** demonstrate end-to-end audiovisual implementability or scientific support for the AV-TRACE thesis. Agent-facing behavior is driven by generated JSON labels and transcripts rather than decoded MP4/audio content. The four agents share fixture-oriented retrieval and answer logic; their clean performance and recovery ordering are substantially constructed. Several original metrics were scientifically misleading or under-specified. Confirmed implementation issues were fixed where this could be done without changing normative documents; unresolved limitations are explicitly reported below.

## Independent execution

Before edits, I ran:

```bash
PYTHONPATH=src pytest -q tests tests_mvp
python scripts/run_mvp.py all --probe --results-root /tmp/av_trace_pre_review_run1
python scripts/run_mvp.py all --probe --results-root /tmp/av_trace_pre_review_run2
```

Results:

- 99 tests passed before review.
- Both fresh pre-review runs produced 96/96 valid trajectories.
- The two fresh runs reproduced the checked-in generation, backend, experiment, validation, MP4, JSON, CSV, and Markdown hashes in the same environment.
- Runtime was approximately 17 seconds per full run; the test suite took approximately 36 seconds.

The original checked-in result directory was preserved unchanged at:

- `mvp/results/pre_review_20260905/`

Corrected results are at:

- `mvp/results/final/`

## Findings by severity

### Critical — actual media content is outside the execution path

`build_generated_backend` builds the retrieval index from timeline, evidence-inventory, transcript, and audio-event JSON. `inspect_clip` and `read_transcript` return indexed metadata payloads; they do not decode the MP4. MP4s are generated, hashed, and shallowly probed for one decodable video and audio frame.

Consequently, the MVP demonstrates:

- media generation and basic playability;
- metadata/index construction;
- deterministic lexical search;
- stateful masking and restoration;
- schema-valid tool interaction and reporting.

It has **not** demonstrated:

- visual recognition from pixels;
- speech recognition from waveform content;
- ambient-event recognition from samples;
- media-backed temporal retrieval;
- consistency between media bytes and returned observations;
- failure when media content is corrupt but metadata and hashes are regenerated.

The synthetic “speech” stream is tonal encoding paired with exact transcript metadata, not spoken language. This is acceptable for a protocol simulator, but it cannot support an end-to-end audiovisual implementability claim.

### Critical — original retrieval candidate set used gold family membership

Before correction, each family searched only records whose `used_by_family_ids` named that family. The full index had exactly 17 answer-bearing records for eight families and no integrated distractors. This made retrieval an answer-only sub-index rather than search over a source.

**Correction:** the generated backend now creates one record per source event and all families on a source search the same source-level candidate universe. Family annotations still define evaluator-private intervention routes, but no longer remove unrelated same-source events from ordinary search.

### Critical — original public identifiers and responses leaked evaluator state

Before correction:

- tool responses exposed episode IDs ending in `.clean`, `.blocked`, or `.restored`;
- generated result IDs embedded family IDs and semantic event names;
- the wrapper retained an introspectable reference to the evaluator session.

The bundled agents did not branch on the raw episode ID, but the interface was not leakage-resistant.

**Corrections:** agent-visible responses now use an opaque episode handle; generated record/result IDs are opaque hashes; tests cover the response redaction. The in-process wrapper remains **not a security boundary** against malicious Python code. Real model evaluation should use a serialized process or service boundary.

### Critical — fixture-specific query and answer scaffolding

The original modality query strings enumerated nearly all fixture answer vocabulary, and the answer function explicitly implemented the eight fixture forms with hard-coded values/defaults. All agents used `top_k=20`, inspected all returned pointers, and shared the same retrieval, sufficiency, parsing, citation, and finalization helpers.

**Corrections:** search queries are now formed from public question text plus modality-generic terms, and several value extractors were generalized. These changes reduce blatant value leakage but do not turn the policies into general agents. Their task-form parsing remains fixture-oriented.

**Scientific conclusion:** CLEAN=1.0 is constructed/trivial. It is evidence that the scripted smoke-test path works, not that four independent systems solve clean long-video QA.

### Critical — baseline separation is designed into trigger-policy alignment

All eight generated RESTORED episodes use `get_channel_status` as the restoration trigger. EvidenceBeliefState calls it whenever its shared sufficiency heuristic says evidence is missing; ReAct calls it only after a typed channel outage; the other two policies never call it. With four outage and four withholding families, the 1.0/0.5/0.0 recovery pattern follows directly from those branches.

This is a valid deterministic canary for restoration mechanics. It is not emergent evidence that one architecture reasons better. The generated set does not exercise `fixed_call_index`, although a regression test now exercises that runtime path.

### High — original “paired restoration gain” compared different outcomes

The normative formula subtracts `BLOCKED` grounded success from `RESTORED` grounded success. However:

- BLOCKED success means calibrated insufficiency/abstention plus access-failure diagnosis;
- RESTORED success means a supported answer.

Subtracting these heterogeneous targets is not scientifically interpretable as recovery. A system that succeeds in both states obtains zero; one that correctly diagnoses BLOCKED but fails to answer RESTORED obtains a negative value.

**Correction without normative edits:**

- `state_target_success_difference` retains the literal normative arithmetic for transparency but is explicitly labeled as a heterogeneous-target contrast.
- `paired_restoration_gain` now compares the same supported-answer endpoint in BLOCKED and RESTORED.
- Reports no longer call the heterogeneous contrast “restore gain.”

**Required future normative change:** revise `docs/spec/metrics_protocol.md` section 7 and decision D-012 so the primary paired restoration estimand uses a common endpoint, while BLOCKED diagnostic success remains a separate state-specific outcome.

### High — original premature-stop denominator was behavior-dependent

The original implementation treated an unused affordable `get_channel_status` call as a validator-demonstrated route. Eligibility therefore depended on the system’s own action history, checked only the status-call cost rather than a complete route, mishandled `budget_guard`, and produced contradictory rates between the dashboard and run manifest.

**Correction:** the MVP now reports premature-stop as unavailable because generated artifacts do not link validator-demonstrated feasible trajectories at each final decision point. Returning no denominator is scientifically preferable to inventing one. A future implementation must store route sequence, remaining cost/steps, trigger semantics, and finalization feasibility independently of system behavior.

### High — restoration-time diagnosis labels were static

The original code scored all RESTORED cause, modality, and hop beliefs against terminal `not_missing`/empty targets, even before restoration or when restoration never occurred.

**Corrections:**

- stepwise cause labels now distinguish pre-trigger blocked state, post-trigger accessible-but-not-yet-observed state, and observed-sufficient state;
- final cause labels depend on trigger and observed sufficiency;
- modality labels are derived from the evidence still missing from observations at each action;
- no-trigger RESTORED trajectories retain blocked terminal labels.

The sufficiency Brier timing was already correct: each action belief is labeled from observations available before that action, and `finalize` is labeled after the last tool response.

### High — evaluator trusted submitted claim IDs and weak evidence identity

Before correction, an agent-supplied non-null registered claim ID was trusted, and support scoring did not verify that claim text matched the registered claim. Observation-to-evidence mapping used modality and interval alone.

**Corrections:**

- evaluator mapping always overwrites agent-supplied registered IDs from exact normalized text;
- support requires accepted claim text/alias matching;
- backend observations carry evaluator-private hashed route references used for evidence identity;
- route references are removed from the policy-visible response.

Remaining limitation: exact-text mapping is intentionally brittle and all current families contain one composite required claim. Claim-level partial support for future multi-claim families remains unvalidated.

### High — `Recovery@Budget` was redundant and overstated

The original field was identical to “trigger fired and RESTORED grounded success.” It did not separately establish time/cost to first accepted SES or supported finalization.

**Correction:** renamed to `triggered_supported_recovery`. Recovery timing fields are now separated into trigger-to-first-SES and trigger-to-supported-finalization actions/cost. The name no longer implies a distinct metric beyond its implemented definition.

### Medium — restoration search-policy metric was not post-trigger

The original search-allocation change compared whole RESTORED and whole BLOCKED trajectories, despite the protocol requesting post-block/post-restoration allocation. The corrected implementation computes the RESTORED side after the trigger. It is still only a broad fraction of generic route tools, not a validated fraction directed at a declared recovery route.

### Medium — required reporting remains incomplete

The family/video aggregation function correctly averages within family, then video, then bootstraps videos. A regression test confirms equal video weighting under unbalanced family counts. With only four source videos, intervals are mechanically reproducible but scientifically weak.

Still missing or incomplete relative to `metrics_protocol.md`:

- equal-mass calibration data/plot;
- Claim-Response Consistency;
- per-hop-type F1;
- first useful call rank;
- query reformulation and repeat/fallback indicators;
- evaluator-validated recovery-route allocation;
- retained-error and correction-without-grounding rates;
- common-failure and own-failure recovery;
- source-family sensitivity;
- complete cost dashboard including tokens and wall time;
- generated mechanism/modality-stratified aggregate tables.

Episode rows now contain `intervention_mechanism` and `modality_stratum`, but final stratified summaries remain future work.

## Coverage audit

All eight intended families are present and semantically validate:

| Family | Mechanism | Modalities | Accepted SESs | Trigger |
|---|---|---|---:|---|
| `syn_f01_visual_order` | necessity-group withholding | vision | 1 | status |
| `syn_f02_speech_sequence` | channel outage | speech | 1 | status |
| `syn_f03_bell_then_square` | necessity-group withholding | ambient + vision | 1 | status |
| `syn_f04_star_bin` | channel outage | vision + speech | 1 | status |
| `syn_f05_alternative_route` | necessity-group withholding | speech + vision | 2 | status |
| `syn_f06_motor_identity` | channel outage | ambient | 1 | status |
| `syn_f07_hexagon_chime` | necessity-group withholding | vision + ambient | 1 | status |
| `syn_f08_count_status` | channel outage | speech | 1 | status |

Coverage totals:

- four withholding and four outage families;
- vision, speech, and ambient represented;
- four cross-modal families;
- one alternative-SES family.

Limitations:

- the alternative SES consists of near-duplicate speech announcements, not materially distinct reasoning routes;
- all generated triggers are the same status action;
- independent validator trajectories required for SES/restoration feasibility are asserted in metadata but not stored and evaluated;
- failed grounded episodes are listed, but not assigned diagnostic reason codes in a dedicated failed-family table.

## Reproducibility audit

Same-environment determinism is strong. Pre-review fresh runs reproduced all checked-in hashes. Corrected runs are likewise deterministic under the current environment. The final run manifest now records exact Python-package and FFmpeg library versions.

Cross-environment byte reproducibility is not established:

- dependencies use lower bounds rather than a lockfile;
- encoder, font, and rendering behavior may vary;
- the fallback font is not frozen;
- current configured media are effectively seed-independent because configured event types do not use the randomized noise branch.

## Changes made

Implementation and report fixes were made under allowed paths:

- source-level rather than family-only search universe;
- opaque generated record IDs and non-answer-bearing previews;
- question-derived generic queries and less value-specific parsers;
- agent-visible episode-ID redaction;
- evaluator overwrite of submitted claim IDs and text/ID consistency checks;
- evaluator-private route references for evidence identity;
- action-timed RESTORED diagnosis/modality labels;
- premature-stop marked unavailable without validator route records;
- common-endpoint paired restoration gain plus separately named state-target contrast;
- renamed triggered recovery and split recovery timing fields;
- recorded runtime dependency/FFmpeg versions;
- regression tests for these issues and fixed-call restoration.

## Final scientific interpretation of corrected results

The corrected dashboard remains a deterministic canary:

- all policies obtain CLEAN grounded success 1.0;
- EvidenceBeliefState obtains supported recovery on all families;
- ReAct obtains it on outage families;
- AlwaysAnswer and SingleShotRAG do not trigger recovery;
- premature-stop is unavailable because its required denominator is unavailable.

These numbers should not be interpreted as model comparisons. They are generated by shared scripted extraction logic and trigger-specific control policies over metadata, not by independent audiovisual systems.

## Bottom line

**Implementability shown:** schemas, deterministic metadata index, stateful matched episodes, intervention closure, restoration state machine, agent/trajectory orchestration, evaluator plumbing, video-cluster aggregation mechanics, and same-environment replay.

**Implementability not shown:** media-backed tools, adversarial agent isolation, general retrieval/answering, independent validator routes, complete metric protocol, or real-video operational workflow.

**Scientific thesis support from this synthetic evidence:** none beyond proof that a hand-constructed simulator can be made to emit the expected qualitative pattern.
