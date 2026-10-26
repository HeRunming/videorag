# P23_102 Canary2 R22-F complete public-surface scan

Date: 2026-10-22

Decision token:
`P23_102_QUERY_AUTHORING_V2_CANARY2_R22_F_IMPLEMENTATION_READY`

## Public scan repair

R22-F removes the suffix allowlist and the 8 MiB text ceiling from the public
confidentiality gate. The scanner recursively considers every regular file
under the repository root. It first applies only narrow path exclusions:

- `data/restricted`;
- repository-control directories `.git`, `.agents`, and `.codex`;
- explicitly named cache/build/environment prefixes;
- three exact synthetic-media fixture prefixes; and
- the existing exact generated-private-output prefixes.

Every remaining regular file is opened and read in chunks. Raw bytes are
scanned for every forbidden private token, including files classified as
binary by an explicit known-binary suffix/name or exact binary-media prefix.
Token matching carries overlap across chunk boundaries. No file is skipped
because of size.

Files not explicitly classified as binary undergo incremental strict UTF-8
decoding regardless of suffix. Unknown-suffix UTF-8 files therefore enter the
text scan. Decode failure is `PUBLIC_SURFACE_UNDECODABLE_TEXT`. Valid UTF-8
containing NUL, C0 controls other than tab/newline/carriage return, DEL, or C1
controls fails as `PUBLIC_SURFACE_BINARY_CONTROL_BYTES`.

Directory traversal, stat, open, and read errors are recorded by path and fail
closed. Reports expose counts for all regular files, raw-scanned files,
UTF-8-validated files, binary-classified files, restricted exclusions,
policy exclusions, and failures. They never expose private token values.

The canonical policy is
`av-trace.canary2-public-surface-scan/2.0`; plan, public commitment, private
governance ledger, plan status, and preflight bind its semantic hash.

## Frozen boundaries

Selection algorithm/version, role commitments, one-run limit,
no-redraw/no-runtime-fallback rules, and one-shot marker behavior are
unchanged. R22-F performs no real model execution, creates no authorization,
and modifies no real output or historical capsule.

## Remaining gate

Implementation readiness does not authorize execution. The remaining gates
are an independent audit of the current R22-F commitments and creation of a
new independent authorization receipt.
