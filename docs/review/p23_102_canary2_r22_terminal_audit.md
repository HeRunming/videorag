# P23_102 Canary2 R22 terminal audit

**Date:** October 23, 2026  
**Decision:** `R22_SCIENTIFIC_NO_GO_PERMANENT_R23_REQUIRED`  
**Status:** terminal; R22 is consumed and permanently closed

## Terminal disposition

R22 used its single authorized attempt. The atomic attempt marker exists and
the fail-closed capsule preserves the run evidence. Therefore:

- R22 must never be rerun;
- the consumed receipt must never be reused;
- no reserve may be substituted, redrawn, or selected as an R22 fallback;
- no replay of retained outputs may be installed as an R22 success; and
- any future execution must be preregistered and authorized as **R23, a new
  experiment**, not as an R22 retry.

This disposition is permanent. A repair to code or validation logic cannot
restore the consumed R22 opportunity.

## What actually caused the top-level exception

The recorded top-level error is
`COMPOSITION_COMPONENT_LOCAL_BINDING_INVALID:1`. Deterministic reconstruction
from the retained 13 raw attempts locates the exception in the
`far_continuity_anaphora` selected role, component 1.

The retained sentence says:

> A kitchen with a pot on the stove and a table with various items on it.

The component-local validator treated `it` as unresolved continuity language.
That is an implementation defect: `it` has the explicit sentence-local
antecedent `a table`. There is no cross-component bridge in this sentence.

This exception must not be described as a failure of factor identity,
clip/media binding, or accepted-output provenance. Reconstructing the accepted
factor manifest and all final rows from the sealed subset, prompt manifest, and
retained raw attempts gives:

- exact binding/provenance: **PASS**;
- accepted factors: **13**;
- bound final rows: **26**; and
- cross-factor fill or substitution detected: **false**.

The reconstructed manifest payload is sealed as
`sha256:6577877038c23a7a87a2dbde92b3b11ca8dff1c3d3cc33d0fedcdc7491f27594`.

## Independent scientific NO-GO

Correcting the validator defect would not make R22 scientifically acceptable.
A deterministic, no-model reconstruction of the retained outputs exposes
independent blocking collisions:

1. **Three exact duplicate query pairs.**
2. **The corresponding three same-kind near-collision records**, each with
   Jaccard `1.0`.
3. **Two directional family-compositional records** for one cross-family pair,
   each with Jaccard `0.92592593`, above the frozen threshold `0.92`.
4. **One cross-family ambient semantic-tuple duplicate.** The tuple auditor's
   narrow fail-closed rule blocks same-family tuple duplicates, so this item is
   recorded as a global cross-family collision rather than its own narrow
   tuple-gate failure. It nevertheless corroborates the exact ambient lexical
   duplicate and cannot be silently rewritten or retried.

Thus the scientific conclusion does not depend on the validator bug:
**R22 is a SCIENTIFIC NO-GO even under a hypothetical bug-fixed replay of the
already retained outputs.**

No embedding, ASR, retrieval, or scoring model was run for this terminal
audit. The conclusion above uses only retained output text, deterministic
derivation, exact hashes, and the frozen lexical threshold.

## Execution accounting and integrity

The retained failure runtime and capsule establish:

| Item | R22 value |
|---|---:|
| authoring calls | 13 |
| exact target clip decodes | 5 |
| schema-only repairs | 0 |
| ASR calls | 0 |
| retrieval/scoring | 0 / not executed |
| network requests | 0 |
| process exit code | 2 |

Integrity checks pass:

- marker mode is `0600`;
- marker content and SHA-256 match the sealed contract;
- receipt SHA-256 matches the sealed contract;
- every file in the failure capsule's preserved-file manifest matches its
  recorded byte count and SHA-256;
- the failure directory remains present;
- no successful output directory was installed;
- ephemeral clip arrays are absent; and
- raw model evidence remains retained in the real failure capsule.

The marker, authorization receipt, and real failure capsule were not modified
by this audit.

## R21 and R22 remain separate

R21 remains a separate historical report. Its fail-closed outcome recorded
`DUPLICATE_OR_LEXICAL_COLLISION`, `EMBEDDING_COLLISION`, and
`FAR_FAMILY_SEMANTIC_CONTRACT`. R22 does not overwrite, relabel, or replace
those findings. Conversely, the R22 terminal finding is based on the R22
attempt and its independently reconstructed retained outputs.

## Identity boundary

Public termination permits disclosure of the **selected** reserve identities,
but this owner-facing audit intentionally uses the selected role/commitment
labels:

- `local_v15_structure`;
- `far_vocalization_asr_ambiguity`; and
- `far_continuity_anaphora`.

No unselected reserve identity is published here or in the public terminal
JSON. Restricted detail may retain selected identifiers required for exact
audit binding.

## Seal checklist

| Role | SHA-256 |
|---|---|
| R22 attempt marker | `216a620f72b741b277c996f242f39f6fe2b6524f8e595f2e181a2f4643cfdf20` |
| R22 authorization receipt | `3b7e39ed594c18864de37469ebfebe6b97df4fd8268b44127aea3952cfb2b720` |
| R22 failure capsule | `6a14a169fd11c3dcb117b0a2237fd853963b12b116c21c50aaa6482ec3127a11` |
| R22 retained raw attempts | `d517a54125f85355d3eef8b77e710d80f2d3a361e2094dc86164238eb1d9b5ad` |
| R22 failed runtime | `0d2b1d66a90e119173c237548224522465195a5b870dfe381234bed67513cf47` |
| Parent authoring source bound by R22 | `ba84ba2a26810da99f4a8fb184bf740e675dcd9fe42b21dfa708e1e70de2df60` |
| Canary2 wrapper source bound by R22 | `39d30102807feb9fe9c906df2c85a3e2a95277311089ce4149ed7be2428eefbe` |
| R21 failure capsule, separate history | `a591f1a9937dfc3fa0a58a10b091069a12fd07dc494c70a5687ead916ec04ffc` |
| R21 failed audit, separate history | `f42d88aac03abafe88274ec9be5589006013c6c6db916889b6a86124313f1b0d` |

Machine-readable public disposition:
`data/rehearsal_plan/p23_102_canary2_r22_terminal_public.json`.

Restricted detailed audit:
`data/restricted/p23_102_canary2_r22_terminal_detailed_audit.json`.

## Final decision

`R22_SCIENTIFIC_NO_GO_PERMANENT_R23_REQUIRED`

R22 is permanently closed. R23, if pursued, must be a separately
preregistered, separately selected, separately authorized experiment with no
reuse of the R22 receipt and no characterization as an R22 retry.
