# AV-TRACE validator artifacts

This directory is the non-normative implementation layer for independent
validator trajectories, SES/minimality proofs, exact blocking/restoration
proofs, and the system-independent premature-stop denominator.

Generate and certify the checked-in synthetic bundle:

```bash
PYTHONPATH=src python scripts/generate_validator_trajectories.py
PYTHONPATH=src python scripts/certify_mvp_dataset.py
PYTHONPATH=src pytest -q tests_validation
```

## Layout

- `generated/artifact_index.json` links every family and proof artifact.
- `generated/identities/` contains role/conflict attestations.
- `generated/families/<family>/trajectories/` contains two validator
  trajectories for each of `CLEAN`, `BLOCKED`, and `RESTORED`.
- `generated/families/<family>/proofs/` contains SES, leave-one-out,
  `BLOCKED`, and `RESTORED` proofs.
- `generated/families/<family>/feasible_routes.json` records a certified route,
  remaining steps, and remaining cost at every validator decision point.
- `generated/premature_stop_denominator.json` is the system-independent
  denominator source consumed by `av_trace_validation.metrics_adapter`.
- `generated/cases/fixed_call/` provides the fixed-call restoration case; the
  primary eight families retain their generated status triggers.
- `generated/dataset_certificate.json` is the fail-closed freeze certificate.

Validator artifacts are evaluator-private. Tested agents must not receive graph,
route, intervention, or oracle fields. The adapter consumes the frozen route
templates after a tested trajectory has finished and does not infer eligibility
from the tested system's tool choices.

