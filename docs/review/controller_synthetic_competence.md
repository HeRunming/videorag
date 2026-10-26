# Synthetic learned-controller competence

**Date:** 2026-09-20  
**Scope:** synthetic/development-only; not scientific evaluation

## Decision

```text
CONTROLLER_SYNTHETIC_COMPETENCE_NO_GO
```

The suite used the pinned Qwen2.5-1.5B-Instruct snapshot offline,
preserved model authorship, allowed at most one repair per output,
failed closed on invalid output, and used no deterministic answer
substitution.

## Preregistered floors and observed metrics

| Gate | Floor | Observed | Pass |
|---|---:|---:|---|
| Valid structured outputs after <=1 repair | >=90% | 62.5% (10/16) | False |
| Supported-answer success on oracle-evidence cases | >=80% | 25.0% (1/4) | False |
| Unsupported required claims | 0 | 0 | True |

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

- `dev-route-vision`: WRONG_MODALITY
- `dev-route-ambient`: WRONG_MODALITY
- `dev-claim-coverage-finalize`: WRONG_ACTION_TYPE, WRONG_CLAIM_COVERAGE
- `dev-missing-hop-diagnosis`: MISSING_HOP_NOT_DIAGNOSED
- `dev-blocked-route-status`: MALFORMED_AFTER_REPAIR
- `dev-finalize-speech`: MALFORMED_AFTER_REPAIR
- `dev-finalize-two-claims`: MALFORMED_AFTER_REPAIR
- `dev-finalize-shared-observation`: MALFORMED_AFTER_REPAIR
- `dev-abstain-missing-speech`: MALFORMED_AFTER_REPAIR
- `dev-abstain-missing-order`: MALFORMED_AFTER_REPAIR

## Boundaries

- No NOAA evaluation family was opened or executed.
- No eligible-family annotations or results were changed.
- The excluded r017 gate was not rerun.
- This result is a development competence result, not a benchmark.

## Artifacts

- `data/restricted/scale1b/controller_dev/suite_contract.json`
- `data/restricted/scale1b/controller_dev/calls.jsonl`
- `data/restricted/scale1b/controller_dev/results.json`
- `data/restricted/scale1b/controller_dev/summary.json`
