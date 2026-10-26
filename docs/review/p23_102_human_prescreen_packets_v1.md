# P23_102 human prescreen packets v1

Date: 2026-10-14

## Scope

This review covers the deterministic construction of one source-level
prescreen packet and twenty neutral lead forms for `P23_102`. The only inputs
are:

- the repaired candidate registry at
  `data/restricted/epic_p23_102_family_mining_v1_dev/candidate_registry.json`;
- the six verified-index JSON artifacts under
  `data/restricted/epic_p23_102_full_timeline_index_v1/`.

The builder verifies the registry and candidate self-hashes, the registry's
pinned input hashes, the index bindings, and each timestamp handle's exact
range in the verified index. It does not open media, semantic annotations, or
human review data.

## Output

The packet is committed at:

`data/rehearsal_plan/p23_102_human_prescreen_packets_v1/`

It contains:

- `source_prescreen_packet.json`: common source-level instructions;
- `lead_forms/`: twenty blank forms, one per repaired input lead;
- `source_exposure_ledger.json`: one blank exposure ledger for source group
  `P23`;
- `synthetic_calibration_examples.json`: fictional calibration scenarios only;
- `artifact_manifest.json`: deterministic input, file, and package hashes;
- `README.md`: operator-facing usage notes.

Every artifact that carries a distribution flag sets
`distribution_authorized=false`. All derivatives originating from a P23 source
are assigned to the single `P23` source group.

## Neutral review surface

Each lead form exposes only:

- an opaque lead identifier and form identifier;
- exact timestamp handles with available modalities;
- neutral visual and ambient-audio inspection hypotheses;
- recurrence, substitution, OCR/text, duplicate, source-world-audio,
  far-coherence, and alternative-route checks;
- the choices `RETAIN_FOR_AUTHORING`, `REPAIR_AND_RECHECK`, and `REJECT`;
- a free-rationale field.

The forms omit generation state, numerical metrics, ordering information,
selection limits, hidden answer material, experimental assignments, private
labels, source candidate identifiers, human identities, observations, and
completed choices. The opaque filenames and lead identifiers are derived from
hashes and do not convey source ordering or review preference.

## Exposure and import boundaries

The committed source exposure ledger is blank. A completed import must:

1. represent every one of the twenty opaque lead IDs exactly once;
2. bind every response to the committed blank-form hash;
3. complete all seven checks and one allowed prescreen choice;
4. provide a non-empty free rationale;
5. remain identity-free and set every distribution flag to `false`;
6. include at least one timezone-aware P23 source or derivative exposure event;
7. keep every P23 derivative in source group `P23`.

The import validator records no authoring output and makes no acceptance, tier,
or eligibility finding.

## Validation

Run:

```text
ruff check tools/p23_102_human_prescreen_packets.py tooling/tests/test_p23_102_human_prescreen_packets.py
pytest -q tooling/tests/test_p23_102_human_prescreen_packets.py
python tools/p23_102_human_prescreen_packets.py --mode check
python tools/p23_102_human_prescreen_packets.py --mode audit
```

The test suite checks deterministic regeneration, committed byte equality,
hashes, exact twenty-lead coverage, timestamp preservation, blank forms and
ledger, fictional-only calibration examples, source-group handling, forbidden
surface removal, absence of identities and completed choices, and fail-closed
import behavior.

Completion token:

`P23_102_HUMAN_PRESCREEN_PACKETS_READY`
