# AV-TRACE semantic validator specification

**Version:** 0.2.0  
**Status:** normative specification; the core family rules and the versioned
manifest-to-episode provenance bridge are implemented as pre-annotation gates.

### Validation modes

`validate_family` has two explicit provenance modes:

- **`real`** — the fail-closed mode for downloaded, acquired, or otherwise
  real-media families. A matching verified-asset bridge record is mandatory.
- **`synthetic_testing`** — compatibility mode only for procedurally generated
  test fixtures. It may omit the bridge, but still requires the manifest and
  checks manifest content hash and duration.

When a caller does not specify a mode, only a narrowly recognized
project-owned synthetic fixture declaration selects `synthetic_testing`;
everything else is treated as real media. Production/certification callers
should pass their mode explicitly. Omitting a verified asset in real mode is
`PROV-005`.

JSON Schema validates object shape. This validator supplies the cross-reference,
graph, temporal, intervention, restoration, provenance, and family rules that
JSON Schema cannot express. A family must pass both layers.

## 1. Inputs and outputs

### Inputs

1. One episode family conforming to `episode_schema.json`.
2. Its frozen acquisition-manifest record conforming to
   `../data/acquisition_manifest_schema.json`.
3. Its versioned verified-asset record (`bridge_version = "1.0.0"`) binding the
   exact manifest hash to acquired bytes, streams, transformations, lineage,
   source-time mappings, and access decisions.
4. The immutable backend/intervention manifest referenced by each episode.
5. Validator trajectories used to establish SES and restoration feasibility.

### Output

The validator emits:

- `PASS` only when no error-level rule fails;
- `FAIL` with stable rule IDs, JSON Pointers, involved IDs, and a diagnostic;
- warnings that cannot change a gate result unless promoted by a frozen profile;
- hashes of all validated inputs and validator version.

No warning may silently repair an input.

## 2. Required rule classes

### 2.1 Identity and referential integrity

| Rule | Requirement |
|---|---|
| `ID-001` | IDs are unique within their namespace: claims, evidence units, hops, edges, SESs, necessity groups, episodes, interventions, and hooks. |
| `ID-002` | Every `answer_spec` claim ID resolves to exactly one graph claim with the matching requirement class. |
| `ID-003` | Every evidence, hop, claim, SES, necessity-group, stream, episode, intervention, and restoration reference resolves. |
| `ID-004` | Every episode `intervention_family_id` equals the family-level value. |
| `ID-005` | `BLOCKED.anchor_episode_id` and `RESTORED.anchor_episode_id` equal the `CLEAN.episode_id`; `CLEAN.anchor_episode_id` is null. |

### 2.2 Temporal and provenance validity

| Rule | Requirement |
|---|---|
| `TIME-001` | Every interval has finite numeric values and `end_s > start_s`. |
| `TIME-002` | Every interval lies in `[0, source.duration_s]`. |
| `TIME-003` | Evidence `stream_id` resolves to a source stream whose hash equals `provenance.stream_hash`. |
| `PROV-001` | `source.manifest_asset_id`, manifest revision, rights decision ID, acquired asset ID, and canonical upstream identity resolve through one verified-asset record to the exact frozen acquisition manifest. |
| `PROV-002` | Episode source content hash, duration, stream IDs, stream kinds/languages, and stream hashes equal the verified-asset values. Exact acquired bytes must match manifest integrity/media; derivatives must resolve to a registered manifest artifact. |
| `PROV-003` | The selected explicit gate profile passes. Public-core families require `public_core_release`; compatibility families require `external_compatibility_unpooled`. Neither is inferred from `acquisition_approved`. |
| `PROV-004` | Every evidence stream and transformation ID resolves in the verified-asset record. Evidence on a derived stream declares the registered transformation chain. |
| `TIME-004` | Every evidence interval on a derived asset or transformed stream is covered by an ordered, non-overlapping, auditable source-time mapping. |

### 2.2.1 Verified-asset bridge record

The bridge is a versioned object outside the frozen 0.2.0 JSON schemas. This
preserves the existing schema shape while making the following facts mandatory
before episode-source conversion:

- `canonical_upstream`: immutable namespace, asset ID, and revision matching
  the manifest's `dataset_id`, `source.source_identifier`, and
  `source.source_revision`;
- `lineage`: `original` with no parent, or `derived` with one or more hashed
  parents and a source-time mapping for each parent edge;
- `manifest`: manifest asset ID, immutable manifest revision, and SHA-256 of
  the complete canonical manifest JSON;
- `acquired_asset`: exact-manifest bytes or a registered derivative, its content
  hash, and its duration;
- `streams`: verified video and audio streams, hashes, durations, and any
  derived-stream parent/transformation references;
- `transformations`: tool identity/version, parameters hash, input/output
  streams, and source-time mapping;
- `access.technical_access`, `access.rights_status`, and
  `access.episode_access_class` as three independent fields.

Unknown keys and unknown/conflicting states fail closed. Technical
accessibility is never interpreted as a rights decision, and neither technical
access nor acquisition approval implies public-core eligibility.

An immutable revision is one atomic value accepted by the shared promotion
validator: a full 40- or 64-hex Git/Hugging Face object ID, or an explicitly
typed object-store `versionId:`/`generation:` value. Mutable names (`main`,
`master`, `HEAD`, `latest`), short hashes, ref expressions, compound display
strings, and unresolved placeholders are invalid at promotion, freeze,
verified-asset validation, and real-family certification. Reconnaissance
records may retain those observations, but they are not freezeable.

### 2.3 Graph validity and SES satisfiability

Let a support derivation contain evidence and hops connected by
`direct_support`, `supports_hop`, and `hop_supports_claim`.

| Rule | Requirement |
|---|---|
| `GRAPH-001` | The hop-dependency graph is acyclic. |
| `GRAPH-002` | Every support edge uses type-correct endpoints. |
| `SES-001` | Every accepted SES references at least one required claim and only existing evidence/hops. |
| `SES-002` | For every claim listed by an SES, the induced subgraph contains a complete derivation from the SES evidence through its hops to that claim. |
| `SES-003` | Every required claim is covered by at least one accepted SES. If the item requires all required claims jointly, at least one accepted SES lists all required claim IDs. |
| `SES-004` | Each SES is leave-one-out minimal: removing any evidence member makes at least one listed required claim unsupported. |
| `SES-005` | No accepted SES is a strict evidence-set superset of another accepted SES covering the same claim set. |
| `SES-006` | At least two independent validators demonstrated each accepted SES or the adjudicator recorded a reason-coded exception before freeze. Pilot-0 freeze does not permit exceptions. |

### 2.4 Necessity-group validity

For group \(N\) targeting claim set \(C_N\), define
\(\mathcal S(N)=\{S: C_N\subseteq claims(S)\}\).

| Rule | Requirement |
|---|---|
| `NEC-001` | Every necessity-group member resolves to evidence and the group targets at least one required claim. |
| `NEC-002` | For every \(S\in\mathcal S(N)\), `evidence_ids(S) ∩ member_evidence_ids(N)` is nonempty. |
| `NEC-003` | Removing all group members breaks support for every targeted claim; removing only one member is not presumed sufficient. |
| `NEC-004` | `required_modalities` equals the modality sets induced by the group members and accepted alternatives; it is not copied from one preferred SES. |
| `NEC-005` | Every `required_hop_id` resolves and maps deterministically to the stored controlled hop type. |

### 2.5 Family consistency

| Rule | Requirement |
|---|---|
| `FAM-001` | Exactly three episodes exist in order: `CLEAN`, `BLOCKED`, `RESTORED`. |
| `FAM-002` | Question, answer specification, graph, source, backend version, index hash, tool costs, cost limit, and maximum steps are identical across the three states. |
| `FAM-003` | Exactly one family mechanism is declared and every intervention uses it. |
| `FAM-004` | `CLEAN` contains no active blocking or restoration intervention and is initially sufficient. |
| `FAM-005` | `BLOCKED` is initially and finally insufficient; source sufficiency remains true. |
| `FAM-006` | `RESTORED` begins with the same accessible evidence and enabled channels as `BLOCKED` and has final expected sufficiency `sufficient`. |
| `FAM-007` | `CLEAN` and restored terminal state expose at least one accepted SES. |
| `FAM-008` | Track is `PUBLIC_CORE_FIXED_BACKEND_TRIPLETS` for primary families. Compatibility families are labeled `EXTERNAL_COMPATIBILITY_UNPOOLED` and never co-aggregate. |

### 2.6 Intervention isolation

The validator computes normalized structural diffs after excluding only:
episode ID, state role, anchor ID, intervention objects, state availability fields,
oracle fields implied by the intervention, and replay hash.

| Rule | Requirement |
|---|---|
| `INT-001` | `CLEAN → BLOCKED` changes only registered intervention-controlled fields and artifacts. |
| `INT-002` | Necessity-group withholding makes every member and every deterministic derived leak inaccessible. |
| `INT-003` | Channel outage disables exactly the declared channel/route and does not mutate underlying media, indexes, question, graph, rank order in unaffected channels, costs, or messages beyond the balanced typed error contract. |
| `INT-004` | No accepted SES remains reachable in `BLOCKED`, including through alternative modalities or equivalent evidence. |
| `INT-005` | The intervention does not insert an answer-bearing redaction marker, condition label, timing artifact, or distinctive error string. |
| `INT-006` | Pilot-0 rejects any ASR mutation, distractor insertion, counterfactual replacement, retrieval-result mutation outside necessity withholding, or budget change. |

### 2.7 Restoration exactness

| Rule | Requirement |
|---|---|
| `REST-001` | `RESTORED` is byte/state-equivalent to `BLOCKED` before the trigger. |
| `REST-002` | The trigger is predeclared as a fixed call index or `get_channel_status`; it cannot depend on model identity, answer content, correctness, hidden reasoning, or free-form rationale. |
| `REST-003` | Restoration reverses exactly the registered blocking operation and introduces no new semantic evidence. |
| `REST-004` | At least one accepted SES becomes reachable within the unchanged remaining budget under at least two validator trajectories. |
| `REST-005` | Restored observations have the same payload/result IDs, ordering, hashes, and costs as their clean counterparts unless an explicitly registered deterministic wrapper is necessary; wrappers must be semantically empty. |

### 2.8 Trajectory semantic checks

| Rule | Requirement |
|---|---|
| `TRJ-001` | Step indices are contiguous; request IDs are unique; action and response episode/request/tool IDs agree. |
| `TRJ-002` | Each belief state is evaluated against observations preceding that action. The `finalize` belief is after the last response. |
| `TRJ-003` | Citations resolve to returned citable observations, use matching modalities, and stay within observation and source bounds. |
| `TRJ-004` | Costs are monotone, equal the frozen schedule, and do not exceed budget except for a typed rejected call followed by zero-cost finalization. |
| `TRJ-005` | `final_output` equals the `finalize.arguments` object and `finalize` is the last agent action. |
| `TRJ-006` | Every cause-probability object sums to 1 within \(10^{-6}\). Modality probabilities are independent multilabel values and need not sum to 1. |

## 3. Positive synthetic fixture

This abbreviated family is semantically valid after expanding hashes and backend
objects to their schemas:

```json
{
  "family_id": "syn_alarm_001",
  "intervention_mechanism": "necessity_group_withholding",
  "claim_evidence_graph": {
    "claims": [{"claim_id": "c_cause", "requirement": "required"}],
    "evidence_units": [
      {"evidence_id": "e_speech_a", "modality": "speech"},
      {"evidence_id": "e_speech_b", "modality": "speech"},
      {"evidence_id": "e_visual", "modality": "vision"}
    ],
    "accepted_sufficient_sets": [
      {"set_id": "ses_a", "claim_ids": ["c_cause"], "evidence_ids": ["e_speech_a", "e_visual"]},
      {"set_id": "ses_b", "claim_ids": ["c_cause"], "evidence_ids": ["e_speech_b", "e_visual"]}
    ],
    "necessity_groups": [
      {"group_id": "ng_cause_speech", "claim_ids": ["c_cause"], "member_evidence_ids": ["e_speech_a", "e_speech_b"]}
    ]
  },
  "episodes": [
    {"episode_id": "syn_alarm_001.clean", "state_role": "CLEAN", "anchor_episode_id": null},
    {"episode_id": "syn_alarm_001.blocked", "state_role": "BLOCKED", "anchor_episode_id": "syn_alarm_001.clean"},
    {"episode_id": "syn_alarm_001.restored", "state_role": "RESTORED", "anchor_episode_id": "syn_alarm_001.clean"}
  ]
}
```

Why it passes: both minimal SESs require one of the two speech alternatives; the
necessity group intersects both; `BLOCKED` withholds both alternatives; and
`RESTORED` returns the same route without changing the graph or budget.

## 4. Negative synthetic fixtures

Each fragment must fail with the named rule.

### Alternative SES survives (`NEC-002`, `INT-004`)

```json
{
  "accepted_sufficient_sets": [
    {"set_id": "ses_a", "evidence_ids": ["e_speech_a", "e_visual"]},
    {"set_id": "ses_visual_only", "evidence_ids": ["e_visual", "e_text"]}
  ],
  "blocked_group": {"member_evidence_ids": ["e_speech_a"]}
}
```

### Non-minimal SES (`SES-004`, `SES-005`)

```json
{
  "accepted_sufficient_sets": [
    {"set_id": "ses_min", "evidence_ids": ["e1", "e2"]},
    {"set_id": "ses_nonminimal", "evidence_ids": ["e1", "e2", "e3"]}
  ]
}
```

### Restoration changes budget (`FAM-002`, `REST-003`)

```json
{
  "BLOCKED": {"budget": {"cost_limit": 12}},
  "RESTORED": {"budget": {"cost_limit": 20}}
}
```

### Invalid provenance (`PROV-001`)

```json
{
  "episode_source": {"manifest_asset_id": "asset_A", "rights_decision_id": "rd_A"},
  "manifest": {"asset_id": "asset_B", "rights": {"rights_decision_id": "rd_B"}}
}
```

### Unknown rights at a release gate (`PROV-003`)

```json
{
  "track": "PUBLIC_CORE_FIXED_BACKEND_TRIPLETS",
  "rights": {"decisions": {"raw_media_release": "unknown_hold"}}
}
```

### Model-dependent restoration (`REST-002`)

```json
{
  "trigger_type": "when_answer_is_wrong"
}
```

## 5. Gate profiles

The implemented `GateProfile` values are:

- **`acquisition`:** acquisition and local processing are allowed; planned or
  completed acquisition is accepted. This gate does not authorize annotation
  or release.
- **`annotation`:** acquisition is completed and the manifest is at least
  `annotation_approved`. Unknown rights decisions fail, but this general
  manifest gate alone does not select a publication track.
- **`public_core_release`:** manifest status is
  `public_release_approved`; acquisition, processing, derivative release,
  annotation release, transcript release, and raw-media release are all
  `allowed`; prohibited embedded components fail. The verified-asset
  `rights_status` must explicitly be `approved_for_public_release` and the
  episode access class must be `public_core_redistributable`.
- **`external_compatibility_unpooled`:** acquisition and annotation use are
  approved and completed, while public redistribution decisions may remain
  prohibited or not applicable. The episode access class must be
  `restricted_compatibility`, and downstream episodes must use
  `EXTERNAL_COMPATIBILITY_UNPOOLED`.

`GateProfile.PUBLIC_RELEASE` and the input string `public_release` remain a
backward-compatible profile with the same requirements as
`public_core_release`; new code should use the explicit canonical name.

Dataset freeze, pre-model-run, and release additionally require the backend,
trajectory, and exact release-build checks described elsewhere in this
specification.
