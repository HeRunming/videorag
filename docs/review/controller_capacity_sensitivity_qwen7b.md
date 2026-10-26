# Qwen2.5-7B controller capacity sensitivity

**Date:** 2026-09-21  
**Scope:** synthetic/development-only; not scientific evaluation

## Decision

```text
QWEN7B_CONTROLLER_SYNTHETIC_COMPETENCE_NO_GO
```

The suite replaced only the frozen controller backbone with the exact Qwen2.5-7B-Instruct snapshot. Prompts, cases, action menu, schemas, repair budget, scoring, and frozen thresholds were unchanged.
preserved model authorship, allowed at most one repair per output,
failed closed on invalid output, and used no deterministic answer
substitution.

## Preregistered floors and observed metrics

| Gate | Floor | Observed | Pass |
|---|---:|---:|---|
| Valid structured outputs after <=1 repair | >=90% | 68.8% (11/16) | False |
| Supported-answer success on oracle-evidence cases | >=80% | 25.0% (1/4) | False |
| Unsupported required claims | 0 | 0 | True |

## Paired comparison by case

| Case | 1.5B semantic | 7B semantic | Delta | 7B errors |
|---|---:|---:|---:|---|
| `dev-route-speech` | PASS | PASS | +0 | None |
| `dev-route-vision` | FAIL | FAIL | +0 | MALFORMED_AFTER_REPAIR |
| `dev-route-ambient` | FAIL | FAIL | +0 | WRONG_MODALITY |
| `dev-inspect-visual-pointer` | PASS | FAIL | -1 | MALFORMED_AFTER_REPAIR |
| `dev-read-speech-pointer` | PASS | FAIL | -1 | WRONG_ACTION_TYPE, WRONG_POINTER_ID |
| `dev-claim-coverage-finalize` | FAIL | FAIL | +0 | WRONG_ACTION_TYPE |
| `dev-no-progress-repeat-guard` | PASS | FAIL | -1 | MALFORMED_AFTER_REPAIR |
| `dev-missing-hop-diagnosis` | FAIL | FAIL | +0 | MALFORMED_AFTER_REPAIR |
| `dev-blocked-route-status` | FAIL | FAIL | +0 | WRONG_ACTION_TYPE, WRONG_MODALITIES |
| `dev-restored-route-search` | PASS | PASS | +0 | None |
| `dev-finalize-visual` | PASS | PASS | +0 | None |
| `dev-finalize-speech` | FAIL | FAIL | +0 | MALFORMED_AFTER_REPAIR |
| `dev-finalize-two-claims` | FAIL | FAIL | +0 | WRONG_VERDICT, ORACLE_CASE_NOT_ANSWERED, MISSING_REQUIRED_CLAIM:devslot.shape, MISSING_REQUIRED_CLAIM:devslot.sound |
| `dev-finalize-shared-observation` | FAIL | FAIL | +0 | WRONG_VERDICT, ORACLE_CASE_NOT_ANSWERED, MISSING_REQUIRED_CLAIM:devslot.cube, MISSING_REQUIRED_CLAIM:devslot.label |
| `dev-abstain-missing-speech` | FAIL | FAIL | +0 | EXPECTED_MISSING_HOP_NOT_DIAGNOSED |
| `dev-abstain-missing-order` | FAIL | PASS | +1 | None |

## Paired comparison by capability

| Capability | 1.5B success | 7B success | Delta |
|---|---:|---:|---:|
| `claim_slot_coverage` | 0/3 | 0/3 | +0 |
| `exact_observation_id_citation_copy` | 1/3 | 1/3 | +0 |
| `finalization` | 1/4 | 1/4 | +0 |
| `initial_modality_routing` | 1/3 | 1/3 | +0 |
| `inspect_read` | 2/2 | 0/2 | -2 |
| `justified_abstention` | 0/3 | 1/3 | +1 |
| `missing_hop_diagnosis` | 0/4 | 1/4 | +1 |
| `no_progress_repeated_action_handling` | 1/1 | 0/1 | -1 |
| `recovery_after_route_restoration` | 1/2 | 1/2 | +0 |

## Covered capabilities

- initial modality routing
- inspect/read selection
- claim-slot coverage
- exact observation-ID citation copying
- finalization
- justified abstention
- no-progress/repeated-action handling
- missing-hop diagnosis
- recovery after route restoration

## Failed semantic probes

- `dev-route-vision`: MALFORMED_AFTER_REPAIR
- `dev-route-ambient`: WRONG_MODALITY
- `dev-inspect-visual-pointer`: MALFORMED_AFTER_REPAIR
- `dev-read-speech-pointer`: WRONG_ACTION_TYPE, WRONG_POINTER_ID
- `dev-claim-coverage-finalize`: WRONG_ACTION_TYPE
- `dev-no-progress-repeat-guard`: MALFORMED_AFTER_REPAIR
- `dev-missing-hop-diagnosis`: MALFORMED_AFTER_REPAIR
- `dev-blocked-route-status`: WRONG_ACTION_TYPE, WRONG_MODALITIES
- `dev-finalize-speech`: MALFORMED_AFTER_REPAIR
- `dev-finalize-two-claims`: WRONG_VERDICT, ORACLE_CASE_NOT_ANSWERED, MISSING_REQUIRED_CLAIM:devslot.shape, MISSING_REQUIRED_CLAIM:devslot.sound
- `dev-finalize-shared-observation`: WRONG_VERDICT, ORACLE_CASE_NOT_ANSWERED, MISSING_REQUIRED_CLAIM:devslot.cube, MISSING_REQUIRED_CLAIM:devslot.label
- `dev-abstain-missing-speech`: EXPECTED_MISSING_HOP_NOT_DIAGNOSED

## Boundaries

- No NOAA evaluation family was opened or executed.
- No eligible-family annotations or results were changed.
- The excluded r017 gate was not rerun.
- This result is a development competence result, not a benchmark.
- No redistribution claim is made.
- Reopening the excluded r017 competence gate is not permitted by this synthetic capacity gate.

## Frozen provenance

- Contract hash: `sha256:b0f280487b936d82e14b118c16eb07ab1f4e189a74efe1000177487221002091`
- Prompt/config hash: `sha256:7bfb36b8ad01105ea83e14e82676e036a70f70e8da46901169b4c2e304c46252`
- Peak RSS: 16403644416 bytes

## Artifacts

- `data/restricted/scale1b/controller_dev_qwen7b/suite_contract.json`
- `data/restricted/scale1b/controller_dev_qwen7b/calls.jsonl`
- `data/restricted/scale1b/controller_dev_qwen7b/results.json`
- `data/restricted/scale1b/controller_dev_qwen7b/summary.json`
- `data/restricted/scale1b/controller_dev_qwen7b/paired_comparison.json`
