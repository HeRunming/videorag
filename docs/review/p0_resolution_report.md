# P0 resolution report

**Date:** 2026-09-05  
**Scope:** design/specification remediation only  
**Historical inputs preserved:** `preflight_audit.md` and
`cross_document_conflicts.csv` were not edited.

## Executive disposition

All eight P0 findings now have a coherent normative resolution in the planning
and specification documents. The P1 design conflicts that prevented a coherent
Pilot-0 have also been resolved.

This does **not** authorize media acquisition, content annotation, or model
runs. Operational gates remain closed because there are no reviewed asset
manifest instances, no implemented semantic validator/server fixture, no frozen
dataset, and no frozen run manifest.

## P0 findings

| Audit finding | Resolution | Status |
|---|---|---|
| P0-1 No asset passed rights gate | Charter, data audit, pilot plan, and checklist explicitly keep cleared count at zero and allow metadata/rights review only until real manifests pass. | Design resolved; operationally open |
| P0-2 Rights schema fails open | Replaced manifest schema with orthogonal copyright/acquisition/processing fields and explicit acquisition, processing, derivative, annotation, transcript, raw-media, and commercial-use decisions. `unknown_hold` never passes a gate. | Resolved in schema |
| P0-3 Pilot evidence semantics | Pilot and spec now require all accepted minimal SESs and validated necessity groups; single-clip necessity language is removed from normative Pilot-0 docs. | Resolved |
| P0-4 Episode contract mismatch | Episode schema and all normative docs use exactly `CLEAN`, `BLOCKED`, `RESTORED`, one family ID, anchor linkage, and one of two mechanisms. | Resolved |
| P0-5 Unsupported counterfactual replacement | Removed from Pilot-0; Claim-Response Consistency is used for withholding/restoration. | Resolved |
| P0-6 Crawl exception | Removed. Only enumerated authorized acquisition routes are permitted; quotas never authorize download. | Resolved |
| P0-7 Incomplete machine protocol | Added Draft 2020-12 schemas for actions, responses, final answers, and trajectories; `finalize` uses the common action envelope. | Resolved in specification |
| P0-8 Missing semantic linter | Added normative semantic-validator rules and positive/negative fixtures. | Spec resolved; implementation open |

## P1 coherence issues

Resolved:

- primary outcome is a dashboard, not IDS/Intervention Utility;
- final modality and missingness-cause probabilities are serialized;
- primary recovery is paired `RESTORED − BLOCKED`;
- premature-stop conditions match prose;
- budget curves require checkpoints or separate capped runs;
- video is the primary cluster;
- Pilot-0 is construct validation, not confirmatory ranking;
- only modality × mechanism stratification is retained; no broad factorial;
- core count is 180 episodes/system × 4 systems = 720;
- non-core diagnostics and reserves must be separately counted;
- labor/storage estimates are pending a measured rehearsal/frozen manifest;
- public core and compatibility tracks are separate and unpooled;
- statuses, hop IDs/types, and `get_channel_status` are harmonized;
- required modality uses a set-valued target over alternative SESs;
- LongShOT and similar web-derived packages default to compatibility-only.

Still operationally open:

- four-system snapshot/run manifest;
- measured 12-family rehearsal;
- operating-characteristic simulations;
- implemented metric library and semantic validator;
- real asset selection, signatures, and rights evidence.

## Factual/data inventory corrections

The following red-team corrections were applied without modifying
`docs/research/`:

- NASA wording no longer makes US copyright status conditional on
  educational/informational noncommercial use; asset-level third-party, marks,
  likeness, music, privacy, and jurisdiction review remains required.
- NARA catalog metadata is treated as evidence, not a warranty; ambiguous items
  remain `unknown_hold`.
- LoVR, LongVidSearch, LongShOTBench, and TRACE/VES-Bench license conclusions are
  marked pending a pinned repository/dataset revision, exact license text/hash,
  scope, and upstream-media record.
- EPIC-KITCHENS annotation licensing is separated from raw video/audio rights;
  raw media remains `unknown_hold`.
- Assembly101 quantities and terms are withdrawn from planning and marked
  pending verification rather than guessed.

## Normative deliverables

Created:

- `docs/project_charter.md`
- `docs/decisions.md`
- `docs/spec/agent_action_schema.json`
- `docs/spec/tool_response_schema.json`
- `docs/spec/final_answer_schema.json`
- `docs/spec/trajectory_schema.json`
- `docs/spec/semantic_validator_spec.md`
- this report

Revised:

- data rights schema/audit/inventory/risk register;
- benchmark, episode, tool, metric, and annotation specifications;
- Pilot-0 plan, backlog, paper outline, cost model, and risk register;
- freeze checklist statuses only where the normative issue is actually resolved.

## Validation performed

- Every repository JSON file parses.
- Every schema passes `jsonschema` Draft 2020-12 schema checking.
- Cross-schema positive and negative fixtures are documented in
  `tool_api.md` and `semantic_validator_spec.md`.
- Canonical counts and terms were checked across editable spec/pilot/data docs.

Implementation and execution validation remain future gated work.

## Current gate decision

- **Gate A — pre-acquisition:** NO-GO
- **Gate B — pre-annotation:** NO-GO
- **Gate C — dataset freeze:** NO-GO
- **Gate D — model runs:** NO-GO

Permitted now: metadata-only discovery, rights-document collection, counsel
review, synthetic validator/server implementation, and synthetic fixtures.

