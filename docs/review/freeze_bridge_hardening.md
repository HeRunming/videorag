# Promotion/freeze and verified-asset bridge hardening

**Date:** 2026-09-07  
**Scope:** Task 36; `NEW-001`, `NEW-005`, remaining `DXA-014`, and directly
related freeze/certification controls  
**Network/download activity:** none

## Outcome

Metadata reconnaissance remains capable of recording unresolved revisions.
Promotion, freeze, and real-media semantic validation now fail closed unless
their immutable source evidence is present.

## Implemented controls

### Shared immutable revision validation

`src/av_trace_data/models.py` defines the reusable
`immutable_revision`, `is_immutable_revision`, and
`require_immutable_revision` API. Promotion and the verified-asset bridge use
the same definition.

Accepted immutable forms:

- full 40-hex Git/Hugging Face object IDs;
- full 64-hex object IDs;
- explicitly typed object-store `versionId:` or `generation:` values.

Rejected at promotion/freeze:

- `main`, `master`, `HEAD`, and `latest`;
- short hashes;
- ref expressions and compound display strings;
- unresolved/placeholder values.

The `NormalizedCandidate` reconnaissance model intentionally remains
permissive so unresolved observations can be serialized and reviewed.

### Selection states and snapshot bindings

Selection artifacts now distinguish:

1. reconnaissance candidates (`NormalizedCandidate`);
2. selected exploratory candidates;
3. freeze-ready/executable candidates.

Every selection records:

- `selection_state`;
- `freezeable`;
- `executable`;
- `non_freezeable_reasons`.

An empty snapshot map produces
`exploratory_non_freezeable_candidate`. Freeze-ready state requires valid
`provider:repository@immutable_revision` snapshot keys and complete coverage
for every selected candidate. The download-plan boundary independently
rechecks nonempty bindings and source coverage.

### Mandatory real-media bridge

`validate_family(..., media_mode="real")` emits `PROV-005` when no
verified-asset record is supplied. This blocks the prior consistent
stream-hash-tampering bypass: internally consistent episode/evidence hashes
are not external evidence.

The explicit `synthetic_testing` mode preserves project-owned procedural
fixture workflows. Default mode inference recognizes only the existing,
narrow synthetic rights declarations; all other families default to real.

The bridge now rejects mutable/short/compound canonical revisions, lineage
parent revisions, manifest source revisions, and manifest revisions.

The certification CLI defaults to `--mode real`, verifies each indexed
family's `verified_asset_path` and `verified_asset_hash`, and only then runs
the existing validator-bundle certifier. Existing synthetic certification
requires the explicit `--mode synthetic-testing` option.

## Focused adversarial coverage

Added tests cover:

- `main`, short hashes, and compound revisions at promotion and bridge gates;
- empty snapshot bindings marked non-freezeable/non-executable;
- real-media family validation without a verified asset;
- consistent source/evidence stream-hash tampering without bridge evidence;
- explicit synthetic-only compatibility.

## Adapter documentation follow-up

Task 37 owns `docs/engineering/data_adapter.md`. It should document:

- the shared immutable-revision forms;
- selection `freezeable`/`executable` state fields;
- the exact `provider:repository@revision` snapshot-key format and coverage
  requirement;
- the distinction between reconnaissance acceptance and promotion/freeze
  rejection.

## Test results

Focused command:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m pytest \
  tests/test_semantic.py \
  tests_data/test_selection_manifests.py \
  tests_data/test_provenance_bridge.py \
  tests_mvp/test_synthetic_data.py \
  tests_data/test_download.py \
  tests_data/test_download_security.py \
  -q -o addopts=''
```

Result:

```text
98 passed, 31 subtests passed in 5.29s
```

The exact full-suite result is recorded below after final execution.

## Remaining limitations

- No real verified-asset records were added; real-media certification is
  therefore expected to fail closed until such evidence exists.
- Immutable object-store support is syntactic (`versionId:`/`generation:`).
  Provider-specific existence and immutability still require externally
  acquired evidence.
- This task did not change adapter/download implementation or source facts,
  rights decisions, or rehearsal rankings.
