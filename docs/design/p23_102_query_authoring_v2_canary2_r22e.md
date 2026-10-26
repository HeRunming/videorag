# P23_102 Canary2 R22-E UTF-8 fail-closed public scan

Date: 2026-10-22

Historical note: superseded by R22-F for all-regular-file raw scanning,
suffix-independent UTF-8 validation, binary control-byte rejection, no size
ceiling, and fail-closed I/O handling.

Decision token:
`P23_102_QUERY_AUTHORING_V2_CANARY2_R22_E_IMPLEMENTATION_READY`

## Public confidentiality repair

R22-E preserves the R22-D repository-wide public-surface scope and its narrow
exclusions. For every candidate public text-suffix/name file within the size
limit, the scanner now:

1. reads the original bytes;
2. scans those bytes for every forbidden private token encoded as UTF-8;
3. reports any byte-level token match as
   `PUBLIC_SURFACE_PRIVATE_LEAKAGE`; and
4. strictly decodes the same bytes as UTF-8, reporting any decode failure as
   `PUBLIC_SURFACE_UNDECODABLE_TEXT`.

The decode check is mandatory even when no private token is present. A
text-suffix file with a binary prefix is therefore not silently reclassified
or skipped. No lossy or byte-dropping error strategy is permitted. Findings
continue to expose only paths and classifications, never private token values.

The scanner still excludes `data/restricted`, caches, repository metadata,
enumerated generated private outputs, oversized candidate text, and true
model/media/binary surfaces. Files outside the enumerated public text
suffix/name set remain out of scope.

## Frozen boundaries

Selection algorithm/version, selected commitments, role priority, one-run
limit, no-redraw/no-runtime-fallback rules, and one-shot marker semantics are
unchanged. R22-E performs no real model execution, creates no authorization,
and modifies no real output or historical capsule.

## Remaining step

The remaining gates are an independent audit of the current R22-E commitments
and creation of a new independent authorization receipt.
