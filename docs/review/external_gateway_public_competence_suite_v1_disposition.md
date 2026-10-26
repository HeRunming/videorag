# External-gateway public-fictional competence suite v1 disposition

**Date:** 2026-10-12  
**Disposition:** **NO-GO; retired; execution permanently forbidden**  
**Replacement:** v2 frozen as `REPAIR_NOT_AUTHORIZED`

## Binding disposition

The independent red-team findings are accepted as binding. The v1 artifact,
tool, and evaluator are historical evidence only. They must never be used to
render a production prompt, call a gateway/model, score a competence run, arm
a ledger, or support a technical/scientific claim.

V1 remains on disk only because this task forbids editing historical
artifacts. Its presence is not authorization.

## Why v1 is not repairable in place

The rejected design combined public packets and the private evaluator key in
one artifact, exposed stratum metadata publicly, used target-revealing wording
and regular action positions, admitted deterministic public heuristics, and
had permissive semantic checks vulnerable to target substrings and
overinclusive diagnosis. Its submission contract also trusted declarations
that were not sufficiently bound to raw prompt/output provenance, and its
evaluation path did not provide strong one-shot replay prevention.

The binding attack set includes:

- public-only heuristic recovery of targets;
- contradictory text containing an accepted target substring;
- all-ones/overinclusive diagnosis;
- forged runner declarations;
- repeated evaluation;
- public/private leakage;
- runner schema mismatch; and
- undercounting malformed or missing required claims.

Because these defects affect the freeze boundary and evaluation semantics, v1
is not eligible for execution with a patch or operational exception.

## V2 response

V2 is implemented only in new `*_v2` files. It:

- separates public and private artifacts;
- removes labels, strata, and target metadata from the public file;
- freezes 48 diverse opaque randomized cases;
- requires all public-only baselines to fail;
- uses exact normalized allowlists and contradiction-aware scoring;
- conservatively charges malformed/missing claims;
- requires exclusive/coherent diagnosis;
- audits exact, near, and rendered-prompt overlap;
- binds raw prompt/output hashes and full model/provider/runtime provenance;
- forbids substitution;
- provides exclusive atomic one-shot receipt semantics; and
- emits only `PUBLIC_FICTIONAL_TECHNICAL_ROW_GO/NO_GO`.

## Current authorization decision

Local `0600` permissions are established for the private file, but no secure
independent sealing/delivery workflow is available in this environment.
Therefore v2 is frozen for review but execution remains:

`PUBLIC_FICTIONAL_TECHNICAL_ROW_NO_GO`

Neither v1 nor v2 currently supports H2 or scientific competence.

