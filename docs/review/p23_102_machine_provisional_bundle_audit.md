# P23_102 MACHINE-PROVISIONAL bundle audit

**Audit date:** 2026-10-14  
**Decision:** `P23_102_MACHINE_PROVISIONAL_BUNDLE_READY`

## Scope and ownership

This audit covers only:

- `tools/p23_102_machine_provisional_bundle.py`
- `tooling/tests/test_p23_102_machine_provisional_bundle.py`
- `data/restricted/epic_p23_102_machine_provisional_families_v1/`
- this audit document

No existing file was modified. The builder does not open media, load or run a
model, or access a network.

## Authorized inputs

The builder consumes:

1. the repaired registry at
   `data/restricted/epic_p23_102_family_mining_v1_dev/candidate_registry.json`;
2. the six verified-index artifacts under
   `data/restricted/epic_p23_102_full_timeline_index_v1/`;
3. the public exogenous restoration-v2 protocol; and
4. the public P23_102 acquire/ground/act rehearsal configuration.

It verifies the repaired registry self-hash, every candidate self-hash, pinned
input file hashes, source and index bindings, and the development-only
governance fields before conversion.

## Conversion result

Only structurally valid input leads were converted:

| Item | Count |
|---|---:|
| REPAIR-status machine-provisional families | 20 |
| Exact evidence handles | 56 |
| Provisional route groups | 20 |
| Mechanism-specific interventions | 40 |
| C/B/R/N state surfaces | 160 |
| Accepted families | 0 |
| Accepted SESs | 0 |
| H tiers | 0 |
| Gate-A claims | 0 |
| V+S machine leads | 0 |
| V+S+A machine leads | 0 |

All converted families retain:

- source status `REPAIR`;
- exact integer-microsecond index handles;
- the `V+A` hypothesis and
  `HYPOTHESIS_NOT_MODALITY_NECESSITY` boundary;
- local/far and one-hop/multi-hop labels;
- recurrence checks and substitution risks;
- source-uniform human-prescreen requirement; and
- unfilled question, answer, and atomic-claim templates.

No answer template was semantically completed. Answer, support, route
completeness, and necessity semantics are explicitly labeled provisional and
not human validated.

## Rehearsal-path artifacts

The required files exist with the expected statuses:

| Artifact | Status |
|---|---|
| `family_registry.json` | `MACHINE_PROVISIONAL_FROZEN` |
| `evidence_registry.json` | `MACHINE_PROVISIONAL_EVIDENCE_FROZEN` |
| `intervention_manifest.json` | `MECHANISM_SPECIFIC_FROZEN` |
| `state_surface_manifest.json` | `FROZEN` |
| `source_split_manifest.json` | `P23_DEVELOPMENT_ONLY_SOURCE_DISJOINT_FROM_EVALUATION` |
| `leakage_gate.json` | `PASS` |

The evidence registry carries the rehearsal's required phrase, “all accepted
SESs discovered under the frozen saturation protocol,” only as a compatibility
field with `asserted: false`. This is necessary because the bundle has zero
accepted SESs and makes no saturation claim.

## Intervention and state-surface checks

Each family has both:

- `SILENT_ROUTE_WITHHOLDING`; and
- `EXPLICIT_CHANNEL_OUTAGE`.

Each intervention has C/B/R/N surfaces. The R/N surfaces use exogenous
restoration-v2 with zero-based action index 4, after four completed
action/response cycles and before the fifth model decision. R and N contain
the same neutral checkpoint object and public inputs through the event. Only R
restores the registered provisional route after the checkpoint.

Exposure validation enforces:

- C: route available initially and afterward;
- B: route unavailable throughout;
- R: unavailable initially, available only after the checkpoint; and
- N: unavailable initially and after the byte-identical checkpoint.

Private family, route, intervention, arm, support-mapping, and restoration
fields are marked non-model-visible. Search pointers are not citations; public
observation acquisition remains required before citation.

## Source split and leakage boundary

`P23_102` is marked development-only, excluded from evaluation, and
future-test-ineligible. Any future test use requires fresh normal-mode
regeneration.

The leakage gate records that no semantic annotations, private human labels,
human prescreen, answer keys, accepted SES labels, H-tier labels, Gate-A
adjudications, evaluation outcomes, raw media, model runs, or network inputs
entered this bundle.

## Deterministic hashes

| Artifact | Canonical payload SHA-256 |
|---|---|
| `family_registry.json` | `sha256:b0fa6136438999f350ae992f053e4fda31b00cdd8730a118a3c5a6cb2e75c443` |
| `evidence_registry.json` | `sha256:568e0eaf60d64929a88bc45bb2271674279464adfa2bdb16b1b4f585dfd9008c` |
| `intervention_manifest.json` | `sha256:5a3699a2298b97536bdfa9e2b9a9584702cabce22ad03a4ec08045ad3ec1bcf0` |
| `state_surface_manifest.json` | `sha256:4f7f0797e518b8d2264ed07fabd15ef6f5458f5f6710cc5e888e58b791e98862` |
| `source_split_manifest.json` | `sha256:9a22096d721ec19fb463e6dfe81a7bf1de5100c6561cfd8c0856ea783b12e241` |
| `leakage_gate.json` | `sha256:f129b3db04104d7aa45d54d670e2bd8560d1b8d10e0b002807526b1b8361f8f4` |

The non-leakage bundle content hash is
`sha256:c197b3ab4f71cfb761cac1df9f1203241a756963b820ef2d61f5f989acc84caf`.

## Validation commands

```bash
python tools/p23_102_machine_provisional_bundle.py --mode check
pytest -q tooling/tests/test_p23_102_machine_provisional_bundle.py
ruff check tools/p23_102_machine_provisional_bundle.py \
  tooling/tests/test_p23_102_machine_provisional_bundle.py
```

Results:

- deterministic committed-bundle check: passed;
- focused pytest suite: `8 passed`;
- Ruff: `All checks passed!`;
- restricted bundle directory mode: `0700`;
- restricted JSON file modes: `0600`.

`P23_102_MACHINE_PROVISIONAL_BUNDLE_READY`
