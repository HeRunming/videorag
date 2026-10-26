# P23_102 Canary2 R22-B one-shot reserve governance

Date: 2026-10-22

Decision token:
`P23_102_QUERY_AUTHORING_V2_CANARY2_R22_B_IMPLEMENTATION_READY`

## Scope and status

R22-B replaces the failed R21 far roles under a frozen, deterministic,
one-shot governance rule while retaining the previously exposed local anchor.
The resulting five-clip set is **one exposed anchor plus two fresh reserves**.
The complete set must not be described as untouched or as a replication set.

This change is implementation readiness only. It does not run a model, decode
media, create authorization, modify a real output, replace a historical
failure capsule, run retrieval, or make scientific claims.

## Deterministic selection

Selection version `2.0` uses algorithm
`r22b_one_shot_reserve_selection`. It reconstructs the result from:

- the frozen machine-provisional structural bundle;
- the frozen speech diagnostics;
- the sealed v1.5 local reference;
- the R21 failure-evidence hashes; and
- the private exposure and anti-alias ledger.

It does not accept a hard-coded family key as proof. The local anchor must
match the sealed v1.5 structural hash exactly. Far candidates are ranked from
machine diagnostics, with canonical hash tie-breaking. Exposure filtering
rejects matches by family key, structural hash, private family ID, clip key,
private evidence handle, positive interval overlap, and boundary/shared-speech
chunk. The role order is vocalization first and continuity second, with
distinct-family enforcement. Missing candidates or any drift fails closed.

The private ledger contains the complete ranking, exclusions, risk tuples,
tie hashes, selected private identities, and source hashes. The public
commitment contains only the algorithm/version, aggregate counts, source
artifact hashes that do not reveal reserve identities, the private canonical
commitment, and the one-run/no-redraw/no-runtime-fallback policy.

## One-shot governance

- replacement generation: 1
- maximum replacements: 2
- run-attempt limit: 1
- redraw after output: forbidden
- fallback after output: forbidden
- runtime fallback: forbidden
- human selection: not performed
- retrieval-assisted selection: not performed
- future-output-assisted selection: not performed

An additional eligible family may appear only in the private ranking proof;
it is not a runtime fallback.

## Bindings and authorization invalidation

The Canary2 plan, future execution contract, input fingerprints, and
authorization schema bind:

- the private ledger file SHA-256;
- the private canonical commitment SHA-256;
- the public commitment file SHA-256;
- selection algorithm and version;
- selected structural hashes;
- bundle, speech-index, v1.5 reference, and R21 evidence hashes; and
- the existing exact code, model, media, subset, prompt, and output bindings.

Authorization schema v3 is exact-key validated. Receipts from schema v2 or
earlier are invalid.

## Retained authoring contract

The selected subset remains exactly three families, five clips, and thirteen
initial factor calls: five visual, five ambient, and three composition. The
R22-A exact ordinal description binding and same-family ambient tuple
duplicate early gate remain active. The default future output remains
`data/restricted/p23_102_query_authoring_v2_canary2_run_v1`; historical
capsules are unchanged.

## Remaining gate

After implementation checks pass, the remaining steps are an independent
audit of the frozen private/public commitments and creation of a new,
independent schema-v3 authorization receipt. No prior receipt is reusable.
