# Validator trajectory implementation report

**Date:** 2026-09-06  
**Implementation version:** `1.0.0`

## Scope

The validator layer adds independently linked, machine-verifiable evidence for
the synthetic MVP without changing normative specifications or existing
`av_trace` / `av_trace_mvp` packages.

## Implemented controls

- Versioned schemas cover validator identity, trajectory linkage, SES
  demonstration, leave-one-out minimality, `BLOCKED` insufficiency,
  `RESTORED` recovery, decision-point route feasibility, the denominator
  bundle, and the final certificate.
- Every one of the eight synthetic families has two validator identities and
  six normative trajectories: two each for `CLEAN`, `BLOCKED`, and `RESTORED`.
- Validator A uses search followed by chronological observation. Validator B
  uses direct interval observation in reverse chronological order. These are
  distinct permitted plans while sharing only evaluator-private frozen graph
  annotations.
- Both validators acquire accepted SES evidence in `CLEAN` and `RESTORED`.
  Both remain insufficient in `BLOCKED` and assign the maximum cause
  probability to source evidence being inaccessible.
- Every accepted SES has a satisfiability record and a complete leave-one-out
  result. The alternative-route family records both accepted SESs.
- Link records bind trajectory hash, family hash and annotation version,
  backend version and manifest hash, index version and hash, source manifest
  hash, and intervention manifest hash.
- Certification checks no author/validator overlap, distinct validator
  independence groups, exact block/restoration, trigger activation, normative
  trajectory validity, and route cost/step arithmetic.
- Missing, malformed, hash-mismatched, or logically inconsistent proof
  artifacts produce a `FAIL` certificate and a nonzero certification CLI exit.

## Premature-stop denominator

`premature_stop_denominator.json` enumerates route templates and feasibility at
validator decision points. The separate metrics adapter recomputes the tested
trajectory's final remaining budget and observed evidence, then applies only
the pre-certified route templates. It never treats a tested system's unused
status call or attempted action history as proof that a route exists.

The adapter returns:

- `premature_stop_eligible`;
- `premature_stop`;
- certified feasible route IDs;
- final remaining steps and cost;
- the denominator artifact ID.

## Trigger coverage

The generated eight-family corpus remains unchanged and exercises
`get_channel_status` restoration. A separate validator-only fixture derived
from `syn_f08_count_status` changes only the restoration trigger to
`fixed_call_index=0` and supplies two passing RESTORED trajectories. This
provides both required trigger cases without mutating source dataset artifacts.

## Reproduction

```bash
PYTHONPATH=src python scripts/generate_validator_trajectories.py
PYTHONPATH=src python scripts/certify_mvp_dataset.py
PYTHONPATH=src pytest -q tests_validation
```

The implementation is metadata-backed, like the current MVP. It certifies the
fixed backend protocol and its declared routes; it does not claim media-decoding
or general audiovisual reasoning validity.

