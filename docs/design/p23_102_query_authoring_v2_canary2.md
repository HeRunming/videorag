# P23_102 query authoring v2 Canary2

Date: 2026-10-22

Decision token:
`P23_102_QUERY_AUTHORING_V2_CANARY2_R22_F_IMPLEMENTATION_READY`

## Current scope

Canary2 is a fail-closed three-role, bounded-clip, thirteen-query authoring
wrapper over `tools/p23_102_query_authoring_v2.py`. R22-F preserves the frozen
selection commitments while exposing only opaque roles, aggregate counts, and
cryptographic bindings on public surfaces.

Private selection identities, full rankings, exclusions, intervals, evidence
handles, and risk tuples are intentionally omitted from this public design.
The detailed governance and binding contract is specified in
`docs/design/p23_102_query_authoring_v2_canary2_r22f.md`.

This status is implementation readiness only. It does not authorize or attest
execution, run a model, decode media, create a receipt, change a historical
capsule, perform retrieval, or make a scientific claim.

## Selection and governance

The selection implementation:

- reconstructs the local anchor from the sealed v1.5 structural reference;
- ranks far candidates from the frozen bundle and speech diagnostics;
- filters exposure by family/hash/private ID/clip/handle, positive interval
  overlap, and boundary or shared-speech-chunk aliasing;
- applies vocalization role priority before continuity role priority;
- enforces distinct selected roles and exactly five clips;
- uses canonical tie hashes;
- fails closed on input drift or a missing candidate; and
- permits no runtime fallback or redraw.

The private ledger is mode `0600` and carries the complete proof. The public
commitment carries only algorithm/version, counts, non-identifying input
hashes, the private canonical commitment, and one-run/no-redraw policy.
The tool extracts private-token classes from the ledger and recursively
considers every regular file below the repository root. After narrow
restricted/repository/cache/generated-output exclusions, every remaining file
is raw-byte scanned in chunks, with overlap for cross-chunk token matches and
no size ceiling. Explicit binary files are still raw-scanned; only their UTF-8
decode may be omitted. Every other file, including unknown suffixes and files
larger than 8 MiB, receives incremental strict UTF-8 validation. NUL and
forbidden control characters fail closed. Traversal, stat, open, and read
errors also fail closed. The report publishes only paths, codes, policy
version/hash, and aggregate counts—never private token values.

## Retained R22-A behavior

Canary2 continues to inherit:

- exact ordinal description projection for far-family local-clause binding;
- independent ordered visual and ambient coverage validation;
- the ambient semantic-tuple duplicate early gate;
- no automatic rewrite, synonym substitution, retry, or ordinal masking;
- constrained structured ambient generation;
- exact accepted-factor provenance;
- separate video-only visual and audio-only ambient factors; and
- text-only family composition.

The initial factor budget remains five visual calls, five ambient calls, and
three composition calls. A factor may receive at most one content-preserving
schema-only repair where the parent contract permits it. The default future
output remains:

`data/restricted/p23_102_query_authoring_v2_canary2_run_v1`

## Execution and validation boundary

Execution requires a separately created exact schema-v3 authorization receipt.
The receipt, future contract, fingerprints, and plan bind the private ledger
hash, private canonical commitment, public commitment hash, selection
algorithm/version, exact selected structural hashes, code, bundle, diagnostics,
model snapshots, media, subset, prompts, and fixed output path.

Old receipts are invalid. Validation can establish deterministic integrity and
current-input authorization, but it does not establish an execution transcript
or external attestation.

After receipt and exact-input validation, but before media decode, model load,
or model call, execution derives the output, failure-capsule, and attempt-marker
paths from the authorization ID. Existing output, capsule, or marker causes
`CANARY_ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED`. The first process atomically
creates a mode-`0600` marker with `O_EXCL`; concurrent or later processes cannot
reuse the receipt. Marker creation requires complete write, flush, file
`fsync`, mode hardening, and parent-directory `fsync`. Once `O_EXCL` succeeds,
any later failure retains the marker inode—even if partial or invalid—and the
receipt remains consumed. Partial or invalid markers never validate as
successful output evidence. Failure retains marker plus capsule when capsule
construction is reached, and success retains marker plus output. Preflight may
report path clearance but never creates the marker. The output contract and
validator bind the marker path, content, and hash.

## Remaining step

The remaining steps are independent audit of the frozen commitments and
creation of a new independent authorization receipt. No real model run is part
of R22-F implementation readiness.
