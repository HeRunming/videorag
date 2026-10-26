# P23_102 Canary2 R22-D repo-wide confidentiality and marker fail-stop

Date: 2026-10-22

Historical note: superseded by R22-E for strict UTF-8 fail-closed handling of
candidate public text files. The R22-D marker fail-stop boundary remains
unchanged.

Decision token:
`P23_102_QUERY_AUTHORING_V2_CANARY2_R22_D_IMPLEMENTATION_READY`

## Public confidentiality boundary

The private selection and identity commitments are unchanged. Public leakage
checking now starts at the repository root and recursively visits text-like
public files rather than relying on a fixed directory list. This includes
root-level `tests*` directories and the public `scripts`, `src`, `mvp`,
`tools`, `tooling`, `docs`, and `data/rehearsal_plan` surfaces, plus any new
public directory created later.

The exclusions are explicit and narrow:

- `data/restricted`;
- repository-control and tool caches such as `.git`, `.agents`, `.codex`,
  `__pycache__`, `.pytest_cache`, and `.ruff_cache`;
- binary, media, model, build, distribution, and virtual-environment
  directories;
- files outside the enumerated text-like suffix/name set;
- text files larger than the fixed scan limit; and
- an enumerated set of generated private-output prefixes.

Allowlisted paths are tested for exact-prefix narrowness. A private token
injected into any non-allowlisted new public directory fails closed. Findings
report paths and token classes only, never token values.

## Attempt-marker durability boundary

Receipt consumption occurs when exclusive marker creation succeeds. The
creation sequence requires:

1. `O_CREAT | O_EXCL`;
2. complete payload write;
3. stream flush;
4. marker-file `fsync`;
5. mode `0600` hardening; and
6. parent-directory `fsync`.

After step 1, no later exception may unlink the marker or make the receipt
reusable. Write, flush, file-`fsync`, chmod, and directory-`fsync` failures
therefore leave the marker inode in place and fail the current execution.
Every later execution using the same receipt is rejected before preflight,
decode, model load, or model call.

A partial or otherwise invalid marker consumes the receipt but does not count
as valid output evidence. Output validation accepts only a complete marker
with the exact schema, permissions, content, path, receipt binding, input
fingerprints, and contract hash.

## Status boundary

R22-D performs no real model execution, creates no authorization, and does not
modify any real output or historical capsule. The remaining gates are an
independent audit of the current commitments and creation of a new independent
authorization receipt.
