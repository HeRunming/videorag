# AV-TRACE MVP Go / No-Go decision

**Decision date:** 2026-09-05  
**Basis:** independent red-team review of the synthetic MVP, corrected implementation, preserved pre-review artifacts, and final rerun.

## Decision summary

| Decision area | Verdict | Rationale |
|---|---|---|
| Protocol implementability | **CONDITIONAL GO** | Core schemas, replay, state transitions, intervention masking/restoration, trajectory validation, and aggregation mechanics execute deterministically. This is implementability of a metadata-backed protocol simulator, not an audiovisual backend. |
| Scientific thesis support from synthetic evidence | **NO-GO** | Clean success and baseline separation are constructed by shared fixture logic, answer-oriented synthetic metadata, and trigger-policy alignment. No independent audiovisual systems or real perceptual uncertainty were tested. |
| Readiness for 3–5 real-video / 12-family rehearsal | **CONDITIONAL GO AFTER BLOCKERS** | A tightly controlled rehearsal is warranted only after media-backed tool adapters, validator trajectory records, process isolation, and metric/report completion are implemented and tested. |
| Readiness for broad data acquisition | **NO-GO** | The real-media evidence path, annotation-to-media consistency checks, rights workflow execution, labor estimates, and rehearsal yield are not yet demonstrated. |
| Readiness for CVPR-scale annotation | **NO-GO** | The system lacks a validated real-video rehearsal, complete required metrics, robust anti-shortcut controls, independent SES/restoration validation, and stable operational/cost evidence. |

## 1. Protocol implementability — CONDITIONAL GO

### Passed

- Structural schemas load and validate.
- Eight families instantiate exactly CLEAN/BLOCKED/RESTORED.
- Both Pilot-0 intervention mechanisms execute.
- Blocking closure and exact restoration checks run.
- The fixed backend enforces budget, step, request, cost, and finalization rules.
- 96/96 final trajectories validate.
- Same-environment reruns are deterministic.
- Family-within-video aggregation and video-cluster bootstrap mechanics execute.
- The runtime supports both status-trigger and fixed-call restoration code paths; the latter is now regression-tested.

### Conditions

This verdict is limited to **protocol control-plane implementability**. It excludes media perception and untrusted-agent isolation. Documentation and claims must use “metadata-backed protocol simulator” until the following blockers are resolved:

1. `inspect_clip` must consume decoded media or the project must explicitly scope it out.
2. Agent execution must cross a serialization/process boundary for leakage claims.
3. Validator trajectories must be persisted and linked for SES, restoration, and premature-stop feasibility.
4. Required metric outputs and strata must be completed.

## 2. Scientific thesis support from synthetic evidence — NO-GO

The synthetic result does not provide scientific evidence that an audiovisual agent recognizes insufficiency, diagnoses access failure, changes search policy, or recovers better after restoration.

Reasons:

- MP4/audio content does not determine observations.
- The synthetic speech track does not contain semantic speech.
- All four systems share the same fixture-oriented extraction and answer engine.
- CLEAN=1.0 is expected by construction.
- Restoration separation is largely determined by whether policy code calls the one trigger used in every family.
- The exact-text evaluator mapper and one-composite-claim design simplify scoring substantially.
- There are only four source clusters and eight synthetic families.

Permissible claim: **the implementation can mechanically express and replay the proposed intervention logic.**

Impermissible claim: **the synthetic experiment supports comparative agent behavior or the scientific thesis.**

## 3. Readiness for a 3–5 real-video / 12-family rehearsal — CONDITIONAL GO AFTER BLOCKERS

A small rehearsal is the correct next empirical step, but do not start content annotation until these blockers are closed:

### Required before rehearsal

1. **Media-backed evidence path**
   - `inspect_clip` decodes requested intervals from the registered media asset.
   - Audio observations derive from decoded samples or a frozen, documented model pipeline.
   - Transcript provenance is tied to an actual speech track and frozen ASR/subtitle artifact.
   - Corrupt or inconsistent media fails validation.

2. **Leakage-resistant execution boundary**
   - Agents receive serialized public messages only.
   - Episode/family/state/intervention/evidence IDs are opaque or absent.
   - Result ordering and identifiers are tested for shortcut sensitivity.

3. **Source-level retrieval and distractors**
   - Every question searches the same source index.
   - Same-modality and cross-modal distractors are present.
   - Held-out values and paraphrased questions replace fixture memorization.

4. **Validator evidence**
   - At least two independent validator trajectories per family.
   - Per-SES satisfiability and leave-one-out tests.
   - Recorded final-decision route feasibility for premature-stop denominators.

5. **Metric completion**
   - common-endpoint restoration estimand frozen;
   - calibration bins;
   - Claim-Response Consistency;
   - per-hop metrics;
   - recovery latency/failure modes;
   - modality/mechanism strata and denominators;
   - missing-pair accounting.

6. **Trigger balance**
   - exercise both `get_channel_status` and `fixed_call_index` triggers;
   - avoid aligning one favored policy with every restoration trigger;
   - specify whether unrelated status requests can trigger restoration.

If these conditions are met, a 3–5-video, 12-family rehearsal is a **GO** for learning operational failure modes, not for estimating model rankings.

## 4. Readiness for broad data acquisition — NO-GO

Broad acquisition should wait for the real-video rehearsal because the current MVP does not establish:

- usable media-backed tool behavior;
- real annotation throughput or rejection rate;
- alternative-evidence search burden;
- inter-validator agreement;
- restoration feasibility yield;
- privacy/rights review throughput;
- storage and compute costs for the actual media pipeline;
- robustness to distractors and non-literal language.

Acquiring broadly now risks collecting assets that cannot yield valid families or cannot be served through the eventual backend.

## 5. Readiness for CVPR-scale annotation — NO-GO

CVPR-scale annotation is premature. Required gates include:

- successful 12-family real-video rehearsal;
- media-backed end-to-end runs;
- no critical leakage path;
- frozen, general system prompts/configurations;
- complete metric implementation;
- independent validator trajectory linkage;
- measured annotation time, rejection, adjudication, and repair rates;
- rights and release gates exercised on actual assets;
- simulation-based operating characteristics using rehearsal-derived ICC and missingness;
- a versioned normative correction to the restoration estimand.

## Required normative follow-up

No normative files were edited in this review. A future accepted decision must supersede or amend D-012 and `metrics_protocol.md` section 7:

- retain state-specific grounded success by state;
- define paired restoration gain using the **same supported-answer endpoint** in BLOCKED and RESTORED;
- treat BLOCKED diagnostic success as a separate outcome;
- define triggered recovery, common-failure correction, and timing/cost quantities separately.

## Final recommendation

Proceed only to **engineering completion and then a small real-video rehearsal**. Do not use the synthetic dashboard as evidence for the scientific thesis, do not begin broad acquisition, and do not begin CVPR-scale annotation.
