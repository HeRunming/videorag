# AV-TRACE canonical project charter

**Charter version:** 1.1  
**Frozen:** 2026-09-20  
**Owner:** Design integration lead  
**Status:** normative for preflight design; no media acquisition, content annotation, or
model execution is authorized by this document.

## Mission

AV-TRACE is a matched interventional evaluation of whether a long-video
audio-visual agent:

1. acquires a minimally sufficient multimodal evidence set;
2. uses and attributes that evidence claim by claim;
3. recognizes when its observed evidence is insufficient;
4. distinguishes evidence absence from access or tool failure;
5. changes its search policy in response to that diagnosis;
6. recovers after deterministic restoration of an evidence route; and
7. stops only when the evidence or a protocol-valid terminal declaration
   justifies stopping.

Answer accuracy alone is not the reliability target. The paper must separately
state its benchmark contribution, diagnostic-protocol contribution, and
empirical-findings contribution. The canonical falsifiable thesis and claim
gates are frozen in `docs/paper/cvpr_thesis_and_evidence_gates.md`.

The unit of analysis is a **family** built from one frozen question and
claim-evidence graph, replayed as exactly three core episodes:

- `CLEAN`
- `BLOCKED`
- `RESTORED`

Each family declares exactly one Pilot-0 intervention mechanism:

- `necessity_group_withholding`; or
- `modality_channel_outage`.

## Pilot-0 purpose and limits

Pilot-0 is **construct validation and feasibility testing**, not a leaderboard
paper and not a confirmatory model-ranking study.

The target is:

- **20–30 rights-cleared, source-disjoint videos**;
- **60 base questions / episode families**;
- **180 core episodes per system**;
- **4 systems initially**, producing **720 core runs** before diagnostics,
  retries, or invalid-run reserve.

Pilot-0 does not make a confirmatory ranking claim. It may report descriptive
system differences with video-cluster uncertainty.

## Scientific contract

### Evidence semantics

- A **minimal sufficient evidence set (SES)** is an enumerated set of evidence
  units that supports all required claims and is leave-one-out minimal.
- A **necessity group** is a set of substitutable evidence units that intersects
  every accepted minimal SES for its target claim or claims.
- Necessity is never inferred from one conveniently selected clip.
- `BLOCKED` must remove or make inaccessible every member and derived leak of
  one declared necessity group, with no accepted SES remaining reachable under
  the blocked state.
- `RESTORED` starts from the exact `BLOCKED` state and deterministically restores
  the predeclared route within the common budget.

### Deferred extensions

The following are outside Pilot-0:

- ASR corruption;
- distractor insertion;
- answer-flipping counterfactual replacement;
- broad budget stress or factorial budget sweeps;
- open-system evaluation;
- a source-absence benchmark partition.

They require separate decisions, schemas, controls, rights review, and power
analysis before activation.

## Evaluation contract

The primary result is a **dashboard**, not a weighted composite:

1. grounded task success by `CLEAN`, `BLOCKED`, and `RESTORED`;
2. insufficiency calibration and false-sufficient rate;
3. premature-stop rate;
4. restoration response using a common supported-answer endpoint, triggered
   recovery, and recovery cost;
5. tool cost, decoded duration, latency, and completion/replay rate.

Any scalar summary is secondary, must be preregistered before model runs, and
cannot replace the dashboard. Pilot-0 has no primary ranking scalar.

State-specific `BLOCKED` diagnostic success is not subtracted from
`RESTORED` supported-answer success and called restoration gain. Abstention is
not automatically exempt from premature stopping: a valid final-point route
certificate and any predeclared typed terminal-declaration exception control
that decision. The exact semantics are in `docs/spec/metrics_protocol.md`.

Primary denominators are family-defined and system-independent. Family results
are averaged within video before video-cluster uncertainty is computed.

## Data and rights contract

Only a **rights-cleared public core** contributes to primary Pilot-0 conclusions.
External benchmark compatibility results are separate, unpooled, and cannot
satisfy public-core quotas.

No media bytes may be acquired and no content annotation may begin until the
asset record:

- validates against `docs/data/acquisition_manifest_schema.json`;
- records explicit acquisition, processing, derivative-release,
  annotation-release, transcript-release, and raw-media-release decisions;
- contains no `unknown_hold` decision at the relevant gate;
- identifies the authority, evidence snapshot, reviewer, and decision date; and
- passes the applicable acquisition and annotation gates.

Source-family reputation, public availability, a repository license, or an
official downloader is not asset-level clearance.

## Claims and publication posture

- Do not claim “first,” “unique,” or equivalent priority.
- All comparison statements are qualified and date-bounded.
- Prior work is credited for necessary evidence, audiovisual retrieval,
  sufficiency verification, stopping, counterfactual evaluation, and video
  agents.
- Scale-up is justified by construct validity, rights, replay, cost, and
  uncertainty—not by a desired ranking inversion.
- New non-human-gold artifacts use
  `MACHINE_ADJUDICATED_PROVISIONAL`; experiment phase is recorded separately.
  This stage never implies human review, gold annotation, or final benchmark
  validation.
- Paper claims advance only through the CVPR evidence ladder in
  `docs/paper/cvpr_thesis_and_evidence_gates.md`. Engineering readiness never
  implies a later construct, learned-agent, scale, paper, or release gate.

## Governance

Normative decisions are recorded in `docs/decisions.md`. The following files
form the Pilot-0 specification set:

- `docs/spec/benchmark_v0.md`
- `docs/spec/episode_schema.json`
- `docs/spec/agent_action_schema.json`
- `docs/spec/tool_response_schema.json`
- `docs/spec/final_answer_schema.json`
- `docs/spec/trajectory_schema.json`
- `docs/spec/tool_api.md`
- `docs/spec/metrics_protocol.md`
- `docs/paper/cvpr_thesis_and_evidence_gates.md`
- `data/rehearsal_plan/cvpr_claim_evidence_ledger.json`
- `docs/spec/annotation_guideline_v0.md`
- `docs/spec/semantic_validator_spec.md`
- `docs/spec/schema_fixtures.md`
- `docs/data/acquisition_manifest_schema.json`
- `docs/pilot/pilot_0_plan.md`

If these documents conflict, this charter and the latest accepted decision-log
entry control until all affected documents are corrected.
