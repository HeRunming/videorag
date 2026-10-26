# Manifest-to-episode provenance bridge fix

**Date:** 2026-09-07  
**Scope:** DXA-014, DXA-018, DXA-025 and associated provenance/gate findings  
**Network/media access:** none

## Result

The repository now has an implemented, versioned verified-asset bridge between
the frozen acquisition manifest and the frozen episode-family source shape.
The existing JSON schemas were not weakened or changed.

The bridge resolves:

- **DXA-014:** acquired hashes, verified streams, transformations, and
  source-time mappings now have an executable conversion and validation path;
- **DXA-018:** acquisition, annotation, public-core release, and restricted
  external compatibility are explicit gate profiles; public-core status is not
  inferred from `acquisition_approved`;
- **DXA-025:** episode identity must resolve through the exact manifest asset
  ID, immutable revision, complete manifest hash, canonical upstream namespace,
  upstream asset ID, and upstream revision.

## API

The implementation is in `src/av_trace_data/provenance.py`.

### `VerifiedAssetRecord`

An immutable dataclass wrapper for bridge JSON version `1.0.0`. The serialized
record contains:

1. `canonical_upstream`: namespace, asset ID, revision;
2. `lineage`: original/derived status, hashed parents, relation, and
   source-time mappings;
3. `manifest`: asset ID, revision, and canonical JSON SHA-256;
4. `acquired_asset`: exact-vs-derived relationship, artifact reference,
   acquired content hash, and duration;
5. `streams`: verified video/audio and any other episode-visible streams,
   hashes, durations, roles, parents, and transformation IDs;
6. `transformations`: input/output streams, tool/version, parameter hash, and
   source-time mapping;
7. `access`: separate technical-access, rights-status, and episode-access-class
   objects.

### Validation and conversion

- `validate_verified_asset_record(record, manifest, gate=None, registry=None)`
  validates the bridge and exact manifest reference. With no explicit gate,
  `episode_access_class` selects either `public_core_release` or
  `external_compatibility_unpooled`.
- `episode_source_from_verified_asset(record, manifest, registry=None)` returns
  exactly the existing `episode_schema.json` source object. It raises
  `ProvenanceBridgeError` unless every normative bridge and selected-gate
  invariant passes.
- `validate_episode_provenance(family, manifest, record, registry=None)` checks
  source identity/content/streams and every evidence unit's stream,
  transformation, interval, and source-time mapping.
- `validate_family(..., verified_asset=record)` optionally invokes the full
  bridge. Existing callers remain source compatible.

The public exports are available from `av_trace_data`.

## Explicit gate profiles

`src/av_trace/manifest.py` now defines:

- `acquisition`;
- `annotation`;
- `public_core_release`;
- `external_compatibility_unpooled`.

The old `PUBLIC_RELEASE` attribute and `public_release` string remain accepted
as a backward-compatible profile with the same requirements as
`public_core_release`.

Key distinctions:

- acquisition requires allowed acquisition and processing but does not imply
  annotation or release;
- public core requires `public_release_approved`, all six named decisions
  allowed, an explicit `approved_for_public_release` bridge rights status, and
  `public_core_redistributable`;
- compatibility permits restricted/non-public release decisions when
  annotation is allowed, but requires `restricted_compatibility` and remains
  unpooled.

## Fail-closed invariants

Conversion and validation reject:

- missing, malformed, unknown, or conflicting canonical identity;
- a wrong manifest asset ID, revision, or whole-manifest hash;
- missing acquired or stream hashes;
- an unregistered derivative or mismatched derivative hash;
- absent verified video/audio streams;
- unresolved stream, parent-stream, or transformation IDs;
- evidence stream hashes that differ from verified stream hashes;
- intervals outside the acquired asset or stream duration;
- transformed or derived intervals not covered by an auditable source-time
  mapping;
- unknown/conflicting/unavailable technical access;
- unknown/conflicting/prohibited or gate-insufficient rights status;
- contradictory rights status and episode access class;
- attempts to use restricted compatibility assets under public-core gates.

The three access concepts are intentionally orthogonal. No crosswalk invents a
rights decision from technical accessibility.

## Tests

Added:

- `tests_data/fixtures/positive_verified_asset.json`;
- `tests_data/test_provenance_bridge.py`;
- focused manifest tests for public-core separation and restricted
  compatibility;
- semantic integration coverage for episode stream tampering.

Adversarial coverage includes:

- tampered stream hash;
- missing stream hash;
- wrong manifest revision;
- unresolved canonical identity;
- missing transformation mapping;
- derived interval outside parent mapping;
- invalid evidence interval;
- acquisition-only manifest presented as public core;
- restricted compatibility asset presented to a public-core gate;
- conflicting rights and technical-access states.

Validation run:

```text
PYTHONPATH=src pytest -q tests_data/test_provenance_bridge.py tests/test_manifest.py tests/test_semantic.py
53 passed
```

Additional regression commands completed:

```text
PYTHONPATH=src pytest -q tests_data/test_selection_manifests.py tests_data/test_download.py
19 passed
```

A combined `tests tests_data` run was also attempted. All core/bridge tests passed;
one pre-existing `tests_data/test_cli.py` case failed because the current download
planner now requires explicit positive item and total byte caps. That behavior is
outside this task's allowed implementation files and was not weakened.

## Remaining steps before real annotation

1. Produce one bridge record per exact acquired rendition from real probe and
   hashing output; metadata-only candidate records cannot populate it.
2. Freeze and store the canonical acquisition-manifest JSON bytes/hash used by
   each bridge record.
3. Verify all stream hashes and durations against the exact local media bytes.
4. Register every derived media/transcript route and review its source-time
   mapping over the full interval range used by evidence.
5. Obtain explicit asset-level rights decisions and choose either public-core
   or restricted compatibility; do not infer the class from access mechanics.
6. Run complete-source alternative-evidence review, privacy/safety review, and
   the remaining backend/trajectory certification required for annotation and
   freeze.

## Architecture follow-up owned elsewhere

`docs/engineering/upstream_ingestion_architecture.md` was intentionally not
edited. Its owner should later document:

- the `VerifiedAssetRecord` 1.0.0 handoff after acquisition/probing;
- canonical whole-manifest hashing;
- the separation of technical access, rights status, and episode access class;
- original/derived lineage and source-time mapping requirements;
- explicit public-core versus external-compatibility gate selection.
