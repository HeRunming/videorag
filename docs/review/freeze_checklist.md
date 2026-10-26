# AV-TRACE explicit freeze checklist

**Audit date:** 2026-09-05  
**Rule:** a checked box requires a named owner, dated evidence, and an immutable artifact or decision record. “Planned,” “likely,” a repository badge, or a public URL does not pass a gate.

## Gate A — Pre-acquisition freeze

No source-media bytes may be downloaded until every mandatory item below passes. Metadata and rights-document review may proceed.

### A1. Canonical scientific contract

- [x] The canonical thesis is frozen: matched blocking/restoration of validated necessity groups; no unsupported “first” or broad factorial claim.
- [x] Pilot-0 is frozen to `CLEAN`, `BLOCKED`, and `RESTORED` state roles.
- [x] Pilot-0 permits only the predeclared blocking mechanisms; recommended: necessity-group removal and channel outage.
- [x] “Individually necessary unit” has been removed from normative Pilot-0 language; minimal SESs and necessity groups are authoritative.
- [x] Counterfactual answer replacement, distractor injection, ASR corruption, broad budget factorials, and open-system evaluation are explicitly deferred.
- [x] The public core and restricted compatibility partition are defined as separate datasets and separate result tables.

### A2. Rights and acquisition control

- [ ] A counsel/institution-approved interpretation note distinguishes software/annotation license, source-media copyright, access permission, local processing permission, and redistribution authority.
- [x] `acquisition_manifest_schema.json` has fail-closed, non-null, artifact-specific rights decisions.
- [x] Conditional schema rules require exact license/agreement/public-domain evidence, version, licensor/rightsholder, snapshot hash, and reviewer.
- [x] Derived artifacts separately cover clips, frames, audio, transcripts/subtitles, captions, annotations, and features/embeddings.
- [x] The quota-driven web-crawl exception is removed.
- [x] Approved acquisition methods are enumerated: official direct download, official dataset tooling under recorded terms, platform-authorized API/export, or rightsholder delivery.
- [x] Cookie-based or generic downloading of platform video is prohibited unless expressly authorized.
- [ ] Every candidate has a file/item-level rights record; source-family reputation is not used as clearance.
- [ ] Public-core membership requires affirmative raw redistribution authority for the intended worldwide release, or an approved narrower jurisdiction statement.
- [ ] Music, subtitles, third-party inserts, logos/marks, identifiable people, minors, and sensitive content receive separate review.
- [ ] A takedown, quarantine, deletion, replacement, and benchmark-version policy is approved.
- [ ] Exactly **0 assets remain `unknown_hold`** among assets selected for transfer.
- [ ] Cleared candidates cover the selected 20–30 videos plus at least a 20% replacement reserve.

### A3. Source mix

- [x] Pilot-0 public-core candidates come only from asset-cleared NASA, NARA, NOAA, Wikimedia Commons, or direct creator/institution grants.
- [x] Gated academic datasets and existing web-derived benchmarks do not count toward the public-core quota.
- [ ] NASA items are confirmed NASA-authored and reviewed for third-party material, music, marks, endorsement, people, and jurisdiction.
- [ ] NARA items have an affirmative federal-work/public-domain basis or written permission; missing/ambiguous catalog rights are rejected.
- [ ] NOAA items are confirmed NOAA-authored; partner/contractor material is separately cleared or excluded.
- [ ] Wikimedia items have pinned page/revision IDs, source-chain evidence, exact license/version, attribution, and compatibility review.
- [ ] Direct grants cover acquisition, editing, ML evaluation, public raw redistribution, derivatives, and included audio/music.
- [ ] Every selected asset has usable original audio and meets the frozen duration rule.

**Gate A decision:** [ ] GO  [x] NO-GO  
**Owners/signatures/date:** ______________________________

## Gate B — Pre-annotation protocol freeze

No real content annotation may begin until all items pass.

### B1. Normative schemas

- [x] Episode schema includes `state_role`, `anchor_episode_id`, and `intervention_family_id`.
- [x] Separate JSON Schemas exist for agent actions, tool responses, final outputs, and replay logs.
- [x] `finalize` uses the common action envelope and contains a clearly timed final belief state.
- [x] Final output contains every field required by every scored metric.
- [x] Gold hop IDs and controlled hop types have a normative mapping.
- [x] Annotation statuses and transition rules are identical in schema, guideline, and pilot plan.
- [x] All tool names are identical across documents (`get_channel_status`, not aliases).
- [x] Counterfactual/replacement fields are removed from Pilot-0 or fully specified.
- [x] Project-controlled versioned schema URIs replace `example.org`.
- [ ] All documentation examples have been executed as schema-conformance fixtures.

### B2. Semantic validation

- [ ] Implemented semantic linter checks interval `end > start` and source bounds.
- [ ] Implemented validator confirms IDs are unique and every reference resolves.
- [ ] Implemented validator confirms the claim–hop–evidence graph is acyclic.
- [ ] Implemented validator confirms every required claim has an accepted derivation.
- [ ] Implemented validator confirms every accepted SES is validator-supported and leave-one-out minimal.
- [ ] Implemented validator confirms every necessity group intersects every accepted SES for the target claim.
- [ ] Implemented validator confirms `BLOCKED` removes every accessible member and derived leak of the selected necessity group.
- [ ] Implemented validator confirms no alternative SES remains reachable in an unrecoverable blocked state.
- [ ] Implemented validator confirms `RESTORED` begins from the identical blocked state and restores a predeclared route within budget.
- [ ] Implemented pair-diff validation proves that only registered fields/artifacts differ.
- [ ] Implemented validator confirms observation provenance links to the frozen acquisition-manifest revision and rights decision.

### B3. Synthetic end-to-end fixture

- [ ] One synthetic family executes CLEAN/BLOCKED/RESTORED through the real server.
- [ ] Replay reproduces result IDs, ordering, costs, errors, and payload hashes.
- [ ] Valid and invalid actions are tested.
- [ ] Budget exhaustion and forced finalization are tested.
- [ ] Missing evidence, partial answer, and abstention are scored correctly.
- [ ] Restoration is not triggered by model identity, hidden reasoning, or answer correctness.
- [ ] Every documentation example is run as a conformance fixture.

### B4. Annotation protocol

- [ ] Author, alternative-evidence finder, two validators, and adjudicator independence is operationally enforced.
- [ ] Full-source alternative search is required before necessity claims.
- [ ] Modality-removal tests distinguish speech from ambient audio and visual text.
- [ ] Question-only, metadata-only, transcript-only, silent-video, ambient-only, temporal-shuffle, snippet-only, duplicate-evidence, contamination, and intervention-artifact audits are specified.
- [ ] Field-specific agreement statistics and minimum denominators are preregistered.
- [ ] A 12-item rehearsal measures authoring, alternative search, validation, ablation, adjudication, rejection, and rights-review time.
- [ ] Pilot schedule and budget are revised from observed rehearsal data.

**Gate B decision:** [ ] GO  [x] NO-GO  
**Owners/signatures/date:** ______________________________

## Gate C — Pilot-0 dataset freeze

### C1. Scope and composition

- [ ] Between 20 and 30 source-disjoint cleared videos are frozen.
- [ ] Exactly 60 accepted families are frozen; per-video family counts and source concentration are reported.
- [ ] Exactly 180 core episodes exist: 60 CLEAN, 60 BLOCKED, 60 RESTORED.
- [ ] Vision, speech, ambient, and cross-modal strata meet their preregistered feasible counts; no unsupported equal-balance claim is made.
- [ ] Each intervention mechanism meets its predeclared minimum count.
- [ ] Source, domain, duration, and question-format distributions are reported; no unsupported factorial-balance claim is made.
- [ ] Families never cross splits.

### C2. Validity and quality

- [ ] Both validators solve CLEAN with supported claims.
- [ ] Both validators fail to support the blocked claim in BLOCKED.
- [ ] At least two validator trajectories recover in RESTORED within budget.
- [ ] Question-only and prohibited-modality controls pass frozen rejection thresholds.
- [ ] Intervention-artifact classifier is at or below the frozen threshold.
- [ ] No unresolved alternative SES exists.
- [ ] Pair-isolation pass rate meets the frozen threshold.
- [ ] Critical blind-audit error rate meets the frozen threshold.
- [ ] All disagreements and adjudications are reason-coded.
- [ ] Source and derivative hashes, time bases, transformations, and annotation versions are complete.

### C3. Rights and release

- [ ] Every public-core raw asset has affirmative redistribution authority.
- [ ] Every released derivative has a separate affirmative decision.
- [ ] Attribution/notices are generated and manually checked.
- [ ] Public and restricted storage/build pipelines are physically or logically separated.
- [ ] The release manifest can be reconstructed without institution-specific secrets.
- [ ] Compatibility-suite items are excluded from the primary public-core score.

**Gate C decision:** [ ] GO  [ ] REVISE  [x] NO-GO  
**Owners/signatures/date:** ______________________________

## Gate D — Pre-model-run freeze

### D1. Evaluation definitions

- [x] One primary track is frozen: `PUBLIC_CORE_FIXED_BACKEND_TRIPLETS`.
- [x] Pilot-0 has no primary sorting key; the metric dashboard is primary and any future scalar must be secondary and preregistered.
- [x] No IDS or Intervention Utility composite is used for ranking.
- [ ] CLEAN, BLOCKED, and RESTORED outcome definitions are implemented and unit-tested.
- [x] Primary restoration effect is `RESTORED − BLOCKED` over all eligible families.
- [x] Common-failure correction recovery is secondary; own-failure recovery is descriptive.
- [x] Premature-stop formula includes answer mode, route declaration, reachability, and budget-guard exception.
- [x] Budget curves use checkpoint predictions or separately capped runs, not retrospective truncation of a single final output.
- [x] Claim-Response Consistency is named separately from true counterfactual replacement.
- [x] Required-modality scoring handles alternative SESs correctly.
- [x] Source-insufficient reporting is removed or a distinct absence partition exists.

### D2. Statistics

- [x] Video is the primary resampling cluster; source-level sensitivity is specified.
- [x] Family averaging precedes video-level aggregation.
- [x] Pilot-0 is declared construct validation, not confirmatory ranking.
- [ ] Simulation-based operating characteristics specify ICC, effect sizes, missingness, and minimum common-failure count.
- [ ] One confirmatory endpoint/comparison set is named.
- [ ] Holm controls confirmatory pairwise comparisons; BH is restricted to labeled secondary/exploratory analyses.
- [ ] Practical tie region is frozen.
- [x] No ranking-inversion result is required for Pilot-0 success.

### D3. Run and cost manifest

- [x] Core count is fixed at 180 episodes/system and four systems, or every deviation is recorded before runs.
- [ ] Repeats, oracle diagnostics, ablations, judges, retries, canaries, invalid-run reserve, and reruns are explicitly counted.
- [ ] Model snapshot, prompt hash, tool/backend/index versions, decoding parameters, seed, and retry policy are frozen.
- [ ] One frozen/open reproducibility anchor is runnable end to end.
- [ ] Storage estimate is recomputed from actual asset bytes and includes originals, derivatives, indexes, logs, backups, and retention.
- [ ] Human-labor estimate is recomputed from rehearsal observations.
- [ ] Approved budget includes contingency without reducing validation or rights review.

**Gate D decision:** [ ] GO  [ ] REVISE  [x] NO-GO  
**Owners/signatures/date:** ______________________________

## Gate E — Post-Pilot novelty and scale decision

- [ ] Primary results report paired effect sizes and video-cluster uncertainty.
- [ ] Construct-validity failures are separated from model failures.
- [ ] Direct comparisons include LongVidSearch, FLARE, V-RAGBench, LongShOTBench, MOV-Bench, VideoGAIA, REVEAL, TRACE/VES-Bench, HERBench, and OmniHalluc-L where runnable.
- [ ] The later-work audit includes From Intent to Evidence, Omni-Decision, VideoTreeSearch, OmniAgent, AVHBench, VideoAgent2, VideoDR, ViSAGE, MetaVideoAgent, and VideoHarness-RSI.
- [ ] No “first” claim remains unless a final dated search and exact capability table support it.
- [ ] REVEAL is described as a method on existing benchmarks.
- [ ] Iterative retrieval is not mislabeled as recovery from an imposed failure.
- [ ] V-RAGBench is not described as a matched causal intervention.
- [ ] LongVidSearch distractors are labeled partial unless injected matched distractors are verified.
- [ ] Public-core and compatibility results are unpooled.
- [ ] Scale-up is approved only if rights, construct validity, replay, cost, and uncertainty—not a desired rank inversion—support it.

**Final decision:** [ ] GO TO PILOT-1  [ ] REVISE PILOT-0  [ ] STOP CURRENT THESIS  
**Owners/signatures/date:** ______________________________


## 2026-09-05 design-integration update

Checked items above have been resolved at the **normative document/specification** level only. They do not imply that software, assets, annotations, signatures, or model runs exist. In particular:

- Gate A remains **NO-GO** because counsel/institution approval and real asset-level manifests do not exist.
- Gate B remains **NO-GO** because the semantic validator and end-to-end server fixture are specified but not implemented/executed.
- Gates C and D remain **NO-GO** because no real dataset or run manifest is frozen.
- Historical findings remain in `preflight_audit.md` and `cross_document_conflicts.csv`; this checklist records only present status.
