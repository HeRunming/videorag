# Adapter semantics fix

**Date:** 2026-09-07  
**Scope:** Task 30 adapter-side corrections for DXA-001, DXA-008, DXA-009,
DXA-010, DXA-023, DXA-027, DXA-028, and directly corresponding red-team
findings.

## Changes

### Release identity

- Corrected the four audited dataset IDs:
  `debugger123/LoVR-benchmark`, `AnonymousFLARE/FLARE`,
  `MBZUAI/longshot-bench`, and `buaaplay/VES-Bench`.
- Changed LongVidSearch to its audited dataset release
  `Fishiing/LongVidSearch`.
- Kept code repositories in separate configuration fields. A code repository
  is no longer used as a dataset release locator.
- Represented V-RAGBench as protocol-only and EgoLife, Ego4D, and
  OmniVideoBench as manual-resolution sources. The generic adapter refuses
  candidate inspection for those states.

### Reconnaissance uncertainty

- `has_video`, `has_audio`, `has_speech`, and `has_ambient_audio` are now
  tri-state (`true`, `false`, or `null`).
- Inspection defaults absent modality facts to unknown.
- Default AV selection rejects verified absence and holds unknown with
  different reason codes.
- Manifest drafting refuses any unknown normative media field, so unknown
  speech or ambient audio cannot silently become false.

### License evidence and rights isolation

- Replaced the mandatory singular license with zero-or-more
  `LicenseEvidence` records and `consistent`, `unresolved`, or `conflicting`
  resolution status.
- Missing and conflicting evidence are representable reconnaissance outcomes.
- Draft manifests no longer copy a release/card license into the normative
  asset-level grant slot. They use an explicit unresolved-evidence placeholder,
  hash the full reconnaissance evidence, and retain `unknown_hold` decisions.

### Identity and deduplication

- Added required semantics for upstream namespace, upstream asset ID, and
  identity resolution status.
- Added optional parent dataset/asset fields and typed lineage relations.
- Removed fallback from upstream identity to dataset-local source ID.
- Selection builds lineage components and deduplicates connected records, exact
  checksums, and fingerprints.
- Tests cover FLARE/Video-MME,
  LongVidSearch/LoVR/LongVideoBench, and
  TraceAV/mapped-upstream relationships.
- Unresolved identity remains unresolved and is held by default.

### Access taxonomy

- Added an explicit lossless crosswalk from audited technical access status to
  access gate and payload state.
- Kept technical access, media rights, and episode access class independent.
- Unknown statuses and contradictory access overrides fail closed.

### Fixtures

- Replaced the misleading LoVR fixture with an explicitly synthetic,
  schema-faithful reconnaissance fixture. It does not assert direct MP4 access,
  transcripts, verified audio, settled license, or resolved item lineage.
- Added clearly synthetic verified-AV and TraceAV mapping fixtures for behavior
  tests.
- Converted the missing-license fixture into a valid zero-evidence unresolved
  case.

## Migration

Inspection and selection serialization versions are now `2.0`.

New candidate writers must emit:

- `license_evidence` and `license_resolution_status`;
- `technical_access_status`, `access_gate`, `payload_state`, and
  `media_rights_status`;
- `upstream_namespace`, `upstream_asset_id`, and
  `identity_resolution_status`;
- optional parent identity and lineage relation.

Safe legacy reading remains available:

- a singular legacy `license` object becomes one unresolved evidence record;
- a legacy `access_mode` becomes `legacy_unresolved:<value>`;
- an unnamespaced legacy `upstream_id` is retained only as unresolved metadata
  and is not exposed as a canonical identity.

This compatibility path intentionally prevents old records from passing the
default identity/access selection requirements by accident.

## Tests

Required command:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
python -m pytest tests_data -q -o addopts=''
```

Result on 2026-09-07 after the implementation: **60 passed, 21 subtests
passed**.

Coverage added for:

- audited release IDs and separate code provenance;
- protocol-only/manual adapter refusal;
- tri-state round-trip and unknown-audio selection hold;
- zero and conflicting license evidence;
- prevention of release-license inheritance into asset rights;
- namespaced identity and legacy unnamespaced hold;
- three required cross-source lineage chains;
- technical-access crosswalk validation;
- fail-closed manifest drafting for every unknown media field.

## Remaining limitations

- The adapters still consume local JSON snapshots; they do not perform live
  source discovery or network validation.
- Full immutable-revision and URL/host controls remain downstream concerns and
  are tested separately; no transfer backend is authorized here.
- Source-specific parsers for V-RAGBench, EgoLife, Ego4D, OmniVideoBench, and
  complex benchmark tables are not implemented. Their registry states are
  explicit rather than pretending generic coverage.
- A lineage edge is only as trustworthy as its reviewed source mapping.
  Selection does not infer unseen relationships. Hash/fingerprint comparison
  remains supplemental and content probing requires separately authorized
  acquisition.
- The normative manifest schema requires Boolean media assertions. Therefore a
  reconnaissance candidate with any unknown stream field cannot produce a
  schema-valid draft until asset-level verification supplies those facts.
- No adapter evidence creates asset-level rights approval or public-core
  eligibility.
