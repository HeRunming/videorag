# P23_102 rehearsal readiness interface repair

Date: 2026-10-14

Decision token:
`P23_102_REHEARSAL_READINESS_INTERFACE_REPAIR_READY`

## Scope

The readiness audit in
`tools/p23_102_post_acquisition_orchestrator.py` now interprets the frozen
rehearsal configuration as a prospective interface and validates the
authoritative current artifacts without modifying that configuration.
Validation remains fail-closed. The audit does not execute the rehearsal,
load models, run agents, or authorize scientific interpretation.

## Current-versus-prospective compatibility

| Frozen prospective requirement | Authoritative current contract |
| --- | --- |
| Timeline `build_manifest.json` status `COMPLETE_VERIFIED_READY` | Status `COMPLETE` and decision `EPIC_P23_102_FULL_TIMELINE_PIPELINE_READY`, with a valid build-manifest self-hash, complete artifact hashes, and a successful `verify_full_timeline` receipt. |
| Full index binding named `source_sha256_and_frozen_model_revisions` | Source, model revisions, observation configuration, checkpoint payloads, build artifacts, resource manifest, exact manifest, and independent verifier receipt are checked as one referential chain. |
| Observation manifest status `COMPLETE` | The observation self-hash, segment binding, configuration hash, model revisions, checkpoint payload hashes, checkpoint file hashes, and full-index reference are validated. |
| Prospective family-bundle paths and statuses | The six current files under `data/restricted/epic_p23_102_machine_provisional_families_v1` are accepted only with exact schema/status/decision checks, payload self-hashes, frozen input hashes, timeline bindings, cross-file payload hashes, reference integrity, index-record ranges, and claim-firewall checks. |
| Evidence registry phrase asserting coverage of accepted SESs | Current machine-provisional evidence must explicitly **not** assert that phrase. Zero accepted SESs, no human validation, and `coverage_phrase_compatibility.asserted == false` are required. |
| Adapter status | The current adapter attestation schema/status/boundary is checked, along with every artifact hash it attests. |
| Runner pseudo-status `IMPLEMENTED_AND_HASH_FROZEN` | The current runner is bound by its direct SHA-256 in the readiness report and receipt, must be valid Python, must expose validate-only and execute modes, and must retain static no-execution/scientific-nonclaim boundaries. The readiness audit never invokes it. |

The generated readiness report includes this mapping explicitly in
`current_vs_prospective_compatibility`.

## Receipt handling

The readiness schema is now version 2.0. A prior readiness receipt cannot be
reused because the command controls, output schema, and validation result have
changed. For the internal readiness stage only, a stale receipt is removed
before the audit is safely recomputed. Other stale stage receipts continue to
fail closed.

## Security and regression coverage

Targeted tests cover:

- current authoritative timeline and machine-provisional bundle acceptance;
- schema drift rejection;
- malicious status/decision-only spoof rejection even when the spoofed
  document is re-sealed;
- missing frozen input hash binding rejection;
- frozen rehearsal configuration immutability;
- existing orchestration idempotence, stale-receipt, and command-failure
  behavior.

## Boundary

Readiness means the frozen development rehearsal interface is mechanically
available. It does not establish accepted SESs, human-valid family semantics,
H-tier status, Gate A, causal findings, strong learned-agent competence, or
authorization to execute the rehearsal.
