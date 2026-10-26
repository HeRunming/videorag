# Benchmark v0: matched evidence blocking and restoration

**Version:** 0.2.0 (2026-09-05)  
**Status:** normative design; no dataset has been acquired or frozen  
**Authority:** [`../project_charter.md`](../project_charter.md) and
[`../decisions.md`](../decisions.md)

## 1. Thesis and scope

AV-TRACE evaluates, under a fixed question and claim-evidence graph, whether a
long-video audio-visual agent:

1. recognizes insufficient observed evidence;
2. distinguishes evidence absence from access/tool failure;
3. changes its search policy; and
4. recovers after deterministic restoration.

Pilot-0 is construct validation, not a leaderboard or confirmatory ranking
study. The design does not claim priority for necessary evidence, audiovisual
reasoning, sufficiency checking, stopping, tool use, or counterfactual video
evaluation. Any novelty statement is qualified and bounded by a dated search.

REVEAL is treated as a sufficiency-verification and targeted re-retrieval
**method evaluated on existing benchmarks**, not as a source benchmark.

## 2. Unit of evaluation

A **base item** contains one source asset, one question, a structured answer
specification, and one adjudicated claim-evidence graph.

An **episode family** contains exactly:

| State role | Required state |
|---|---|
| `CLEAN` | At least one accepted minimal SES is reachable through the fixed backend. |
| `BLOCKED` | One declared necessity group or necessary modality channel is inaccessible; no accepted SES remains reachable. |
| `RESTORED` | Begins identically to `BLOCKED`; a deterministic trigger restores the declared route within the unchanged budget. |

Every family declares exactly one mechanism:

- `necessity_group_withholding`; or
- `modality_channel_outage`.

The source itself remains sufficient in all three states. Source-absence items
are not part of Pilot-0.

## 3. Evidence model

- **Evidence unit:** an atomic provenance-bearing observation with source-time
  intervals and modality `vision`, `speech`, or `ambient`.
- **Claim:** an atomic proposition in the structured answer.
- **Hop:** a controlled intermediate inference.
- **Minimal sufficient evidence set (SES):** an enumerated, validator-demonstrated
  set that supports its listed required claims and becomes insufficient after
  any member is removed.
- **Necessity group:** a set of substitutable evidence units that intersects
  every accepted minimal SES for its target claims.

All acceptable minimal SESs must be enumerated. If exhaustive alternative search
is not credible, the item is excluded. Necessity is defined over these sets,
not over the first clip an author found.

## 4. Intervention validity

### 4.1 Necessity-group withholding

`BLOCKED` makes every member of one necessity group, and every deterministic
derived leak of those members, inaccessible. The intervention is invalid if an
alternative SES remains reachable.

### 4.2 Modality/channel outage

`BLOCKED` disables one declared necessary channel or route using balanced typed
errors. Underlying media, unaffected indexes, costs, and question semantics do
not change. The family is invalid if another accepted route remains reachable.

### 4.3 Restoration

`RESTORED` is identical to `BLOCKED` before a predeclared fixed-call or
`get_channel_status` trigger. It reverses exactly the registered blocking
operation. Restoration never depends on model identity, answer correctness,
hidden reasoning, or rationale text.

At least two validator trajectories must demonstrate a supported answer after
restoration within the unchanged budget.

## 5. Deferred interventions

The following are not legal Pilot-0 states and must not appear in Pilot-0 family
manifests:

- ASR corruption;
- distractor insertion;
- answer-flipping replacement;
- generic retrieval corruption outside necessity withholding;
- broad budget stress/factorial sweeps;
- open-system tools.

They may be designed only after Pilot-0 under a versioned extension proposal.

## 6. Fixed tool protocol

The available names are:

- `search_visual`
- `search_speech`
- `search_ambient_audio`
- `inspect_clip`
- `read_transcript`
- `get_channel_status`
- `finalize`

Every action uses the common envelope in `agent_action_schema.json`. `finalize`
is not a separate format: its `action.arguments` validates against
`final_answer_schema.json`. Tool responses and complete logs validate against
`tool_response_schema.json` and `trajectory_schema.json`.

Belief state reports include:

- probability that currently observed evidence is sufficient;
- sufficiency verdict;
- independent missing-modality probabilities;
- controlled missing-hop types;
- a categorical probability distribution over source absence, inaccessible
  source evidence, accessible-but-not-found evidence, not missing, and uncertain.

Only returned citable observations may support final claims.

## 7. Tracks and data partitions

| Track | Purpose | Primary conclusions? |
|---|---|---|
| `PUBLIC_CORE_FIXED_BACKEND_TRIPLETS` | Rights-cleared public core with one frozen backend and matched triplets. | Yes |
| `EXTERNAL_COMPATIBILITY_UNPOOLED` | Existing benchmark/gated media under their own access terms. | No; separate tables only |
| `ORACLE_EVIDENCE_DIAGNOSTIC` | Diagnostic reasoning check with an accepted SES supplied. | No |

No score is pooled across public-core and compatibility tracks.

## 8. Pilot-0 target

- 20–30 source-disjoint, rights-cleared videos;
- 60 episode families;
- 180 core episodes/system;
- 4 initial systems;
- 720 core runs;
- 20–90 minute assets, target median at least 40 minutes;
- four analysis strata: vision, speech, ambient, and cross-modal.

Strata are reported, not treated as a complete factorial. The final video count
within 20–30 is determined by rights clearance and construct-valid family yield,
not by a forced domain quota.

## 9. Primary outcome dashboard

The primary result is the vector defined in
[`metrics_protocol.md`](metrics_protocol.md):

- grounded task success by state;
- insufficiency calibration and false-sufficient rate;
- premature stop;
- restoration response and paired recovery;
- cost and replay/completion.

There is no Pilot-0 weighted composite or primary sorting key.

## 10. Structural and semantic conformance

`episode_schema.json` validates structure. The rules in
`semantic_validator_spec.md` additionally enforce:

- IDs, references, DAGs, temporal bounds, and provenance;
- SES satisfiability and leave-one-out minimality;
- necessity-group hitting-set validity;
- intervention isolation;
- restoration exactness;
- family consistency and rights-manifest linkage.

Both layers must pass before content annotation can freeze.

## 11. Release acceptance

A Pilot-0 family may freeze only if:

1. its asset manifest is `annotation_approved` and has no applicable
   `unknown_hold`;
2. the source is 20–90 minutes and has usable original audio;
3. all required claims have accepted SESs;
4. all accepted SESs and necessity groups pass semantic validation;
5. two validators solve `CLEAN`, cannot support the blocked target in `BLOCKED`,
   and recover in `RESTORED`;
6. pair isolation and replay checks pass;
7. anti-shortcut and intervention-artifact audits pass;
8. the family remains within the declared public or compatibility track.

