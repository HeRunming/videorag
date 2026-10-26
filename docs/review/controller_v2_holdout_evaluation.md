# Controller-v2 sealed holdout evaluation

**Date:** 2026-09-22  
**Decision:** `CONTROLLER_V2_HOLDOUT_NO_GO`

## Scope and integrity

- Evaluated the already sealed 28-case paired run; no model was rerun.
- Independently verified exactly six sealed execution artifacts, plus the single output seal.
- Recomputed every sealed byte count and SHA-256 hash, all frozen contract/public/schema/design commitments, and the protected Task-111 hashes.
- Verified key mode `0600` and its committed SHA-256 only after the pre-key seal and execution audit passed.
- Verified 28 v1 rows, 28 v2 rows, one shared model process, and exact `v1 -> v2` ordering within every case.
- Reconstructed public-only request hashes and parsed results from raw outputs rather than trusting runner summaries.
- Raw outputs, evaluator labels, and case-level scores remain under `data/restricted/`; this report contains aggregates only.

## Aggregate metrics

| Metric | v1 | v2 |
|---|---:|---:|
| Action syntax valid | 18/28 | 28/28 |
| Action correct | 5/28 | 15/28 |
| State syntax valid | 18/28 | 28/28 |
| Finalization syntax valid (all reached) | 4/4 | 4/4 |
| Exact six-field state | 0/28 | 0/28 |
| End-to-end terminal correct | 0/8 | 0/8 |
| Supported answers | 0/4 | 0/4 |
| Correct abstentions | 0/4 | 0/4 |
| Unsupported required claims | 0 | 0 |
| Process failures | 0 | 0 |
| Constraint-runtime failures | 0 | 0 |

### v2 six-field state correctness

- `p_sufficient`: 12/28
- `covered_claim_handles`: 4/28
- `missing_modalities`: 3/28
- `missing_hops`: 3/28
- `missingness_cause`: 2/28
- `recovery_intent`: 9/28

Terminal decomposition: v2 reached finalization on 4/8 terminal cases and all 4 reached outputs were syntactically valid. The four answer-terminal cases were not finalized; the four reached abstention outputs did not match the frozen missingness diagnoses.

## Per-stratum counts

| Stratum | v1 action | v2 action | v1 state exact | v2 state exact | terminal v1/v2 |
|---|---:|---:|---:|---:|---:|
| `routing` | 0/4 | 4/4 | 0/4 | 0/4 | 0/0 / 0/0 |
| `pointer_read` | 0/4 | 1/4 | 0/4 | 0/4 | 0/0 / 0/0 |
| `finalize` | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 / 0/4 |
| `abstain` | 4/4 | 4/4 | 0/4 | 0/4 | 0/4 / 0/4 |
| `missingness` | 0/4 | 1/4 | 0/4 | 0/4 | 0/0 / 0/0 |
| `recovery` | 0/4 | 3/4 | 0/4 | 0/4 | 0/0 / 0/0 |
| `adversarial_menu_order` | 1/4 | 2/4 | 0/4 | 0/4 | 0/0 / 0/0 |

## Paired transition tables

### Action correctness (n=28)

| | v2 incorrect | v2 correct |
|---|---:|---:|
| v1 incorrect | 12 | 11 |
| v1 correct | 1 | 4 |

### State exactness (n=28)

| | v2 incorrect | v2 correct |
|---|---:|---:|
| v1 incorrect | 28 | 0 |
| v1 correct | 0 | 0 |

### Terminal correctness (n=8)

| | v2 incorrect | v2 correct |
|---|---:|---:|
| v1 incorrect | 8 | 0 |
| v1 correct | 0 | 0 |

## Frozen gates

### Absolute v2

| Gate | Actual | Frozen threshold | Result |
|---|---|---|---|
| `action_syntax_valid_count` | 28 | `== 28` | PASS |
| `state_syntax_valid_count` | 28 | `== 28` | PASS |
| `action_correct_count` | 15 | `>= 24` | FAIL |
| `state_exact_count` | 0 | `>= 21` | FAIL |
| `end_to_end_terminal_correct_count` | 0 | `>= 7` | FAIL |
| `supported_answer_count` | 0 | `>= 3` | FAIL |
| `correct_abstention_count` | 0 | `== 4` | FAIL |
| `unsupported_required_claims` | 0 | `== 0` | PASS |
| `evaluation_family_or_private_label_exposures` | 0 | `== 0` | PASS |
| `action_correct_per_primary_stratum` | routing=4/4, pointer_read=1/4, finalize=0/4, abstain=4/4, missingness=1/4, recovery=3/4, adversarial_menu_order=2/4 | `>= 3` | FAIL |
| `each_state_field_correct_count` | p_sufficient=12/28, covered_claim_handles=4/28, missing_modalities=3/28, missing_hops=3/28, missingness_cause=2/28, recovery_intent=9/28 | `>= 24` | FAIL |

### Paired v2 minus v1

| Gate | Actual | Frozen threshold | Result |
|---|---:|---|---|
| `action_correct_count_delta` | 10 | `>= 0` | PASS |
| `state_exact_count_delta` | 0 | `>= 4` | FAIL |
| `end_to_end_terminal_correct_count_delta` | 0 | `>= 0` | PASS |
| `unsupported_required_claim_count_delta` | 0 | `<= 0` | PASS |

### Automatic NO_GO conditions

- `artifact_hash_mismatch`: clear
- `constraint_runtime_failure`: clear
- `implementation_worker_accessed_restricted_key`: clear
- `evaluator_labels_changed_after_any_model_output`: clear
- `post_run_tuning`: clear
- `evaluation_family_content_detected`: clear
- `deterministic_answer_substitution`: clear
- `controller_output_mapped_into_answer`: clear

## Decision and authorization boundary

`CONTROLLER_V2_HOLDOUT_NO_GO`

The next excluded r017 controller-v2 competence gate is **not permitted**.

No scientific evaluation family is authorized by this result.
