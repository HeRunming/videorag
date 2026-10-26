# P23_102 Canary2 R22-C public-boundary and one-shot governance

Date: 2026-10-22

Historical note: superseded by R22-D for repository-wide public scanning and
post-`O_EXCL` marker persistence. This file remains a record of the R22-C
boundary.

Decision token:
`P23_102_QUERY_AUTHORING_V2_CANARY2_R22_C_IMPLEMENTATION_READY`

## Public boundary

Public repository surfaces contain only opaque role descriptions, aggregate
counts, and cryptographic commitments. The restricted ledger remains the sole
location for fresh selected identities, unselected reserves, private evidence
handles, interval literals, ranking tuples, and exposure identifiers.

The implementation derives classified token literals at runtime from the
restricted ledger and scans:

- `tools`
- `tooling/tests`
- `docs`
- `data/rehearsal_plan`

Restricted/private artifacts and generated caches are excluded. Historical
identities that were public before R22 may be exempted only by ledger
classification. Findings report paths and token classes, never token values.

## Pre-execution one-shot rule

For a valid schema-v3 authorization receipt, the tool derives three paths from
the authorization ID: final output, failure capsule, and external attempt
marker. If any exists, execution fails immediately with
`CANARY_ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED`.

The first execution atomically creates the attempt marker with `O_CREAT |
O_EXCL`, mode `0600`, after receipt/input validation and before any media
decode, model load, or model call. The marker records the authorization ID,
receipt hash, fingerprint commitment, governance commitments, fixed output
path, and start time.

- failure retains marker plus failure capsule;
- success retains marker plus sealed output;
- the same receipt can never be rerun;
- two concurrent processes cannot both consume one receipt;
- preflight reports clearance only and creates no marker; and
- output validation verifies marker content, path, and hash against the
  contract and current trusted inputs.

## Status boundary

R22-C performs no real model execution, creates no authorization, and modifies
no real output or historical capsule. Remaining gates are independent audit of
the commitments and creation of a new independent authorization receipt.
