# Reviewed candidate conversion boundary

**Version:** 1.0  
**Date:** 2026-09-07  
**Scope:** local metadata only

## Boundary

The snapshot importer emits
`metadata_reconnaissance_inspection`. That artifact is intentionally not
selectable. A signed `reviewed_candidate_decision` must bind its complete
`inspection_sha256` and explicitly select exact imported `record_id` values.
Only `convert_reviewed_candidates.py` turns that pair into a
`reviewed_candidate_inspection` containing `NormalizedCandidate` records.

```text
metadata_reconnaissance_inspection
  + reviewed_candidate_decision
  + local reviewer registry
  -> reviewed_candidate_inspection
```

Conversion is not acquisition, annotation, or release approval. Every output
states:

- `network_access_performed: false`;
- `contains_media: false`;
- `acquisition_authorization: none`;
- `annotation_authorization: none`; and
- `release_authorization: none`.

The existing selection CLI continues to reject raw importer output even if a
`candidates` member is injected into it.

## Reviewer decision 1.0

`REVIEWER_DECISION_SCHEMA` is published by
`av_trace_data.reviewed_conversion`. The versioned object contains:

- the exact complete importer `inspection_sha256`;
- `selected_source_record_ids`, with no duplicates;
- one or more candidate decisions whose source-record union must exactly equal
  that selected set;
- resolved provider, repository, immutable revision, source identity, lineage,
  duration, duration provenance, tri-state video/audio/speech/ambient facts,
  license resolution, technical access, and media-rights state in each
  candidate;
- per-claim evidence references;
- immutable local reviewer-evidence entries;
- reviewer ID, authorized role, UTC timestamp, expiry, exact attestation; and
- an HMAC-SHA-256 signature verified against a local reviewer registry.

The registry and signature are an offline trust mechanism. The CLI accepts
only regular local files, rejects URLs and symlinks, and contains no network
client.

## Claim evidence

Every top-level candidate field and the separate `duration_provenance` object
must have at least one evidence reference:

- `kind: imported_record` cites a selected imported `record_id` and a JSON
  pointer within that exact record; or
- `kind: reviewer_evidence` cites a separate evidence entry and a JSON pointer
  within its `claims` object.

The referenced value must exactly equal the reviewed claim. Consequently,
changing a modality assertion, identity, duration, revision, access state, or
license resolution without changing its evidence fails conversion. Reviewer
evidence used for freeze-ready output must carry a valid self-hash over the
complete entry excluding `evidence_sha256`.

Unknown fields are not normalized into new semantics. They are retained in
the output's preservation sections, raw reviewed-decision copy, selected
imported-record and source-file copies, or candidate review metadata.

## Freeze readiness

The decision chooses `output_mode: exploratory` or `freeze_ready`.

Exploratory conversion retains unknown tri-state facts and unresolved states
and explicitly emits `freeze_ready: false` with reasons.

Freeze-ready conversion fails unless:

- the importer artifact was promoted and its complete self-hash verifies;
- every selected record exists exactly once;
- candidate repository identity agrees with every selected source record;
- every candidate revision is a supported immutable revision;
- source identity and all four tri-state media facts are resolved;
- duration is positive and has cited provenance;
- license evidence is consistently resolved, complete, and observed at an
  immutable revision;
- technical access fields are resolved;
- media-rights state is not `unknown_hold`;
- reviewer evidence is hash-bound; and
- the signed reviewer decision is recognized, current, and exactly attested.

`snapshot_sha256` in the converted inspection is the complete importer
artifact hash. `select_rehearsal_candidates.py` therefore carries the exact
reconnaissance snapshot binding into `source_snapshots`.

## CLI

```bash
PYTHONPATH=src python scripts/convert_reviewed_candidates.py \
  --inspection local-importer-inspection.json \
  --decision local-reviewer-decision.json \
  --reviewer-registry local-reviewer-registry.json \
  --output reviewed-candidate-inspection.json \
  --as-of 2026-09-07T12:00:00Z
```

`--as-of` is optional operationally and is useful for deterministic review
reproduction. The default maximum decision age is 30 days; expiry is also
mandatory and independently enforced.
