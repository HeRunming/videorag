# AV-TRACE MVP fixed backend

This backend is an offline, deterministic Pilot-0 implementation. It exposes only:

`search_visual`, `search_speech`, `search_ambient_audio`, `inspect_clip`,
`read_transcript`, `get_channel_status`, and `finalize`.

## Frozen artifacts

`mvp/generated/backend_manifest.json` is the entry point when generated data is
present. Its format is `mvp/schemas/backend_manifest_schema.json` version `1.0.0`.
The manifest freezes:

- backend, tool-API, and index versions;
- exact tool costs;
- lexical ranking/tokenizer and tie breakers;
- the canonical-JSON SHA-256 of every JSON artifact;
- the index hash and record count.

Loading fails closed for a missing artifact, schema mismatch, path traversal,
hash mismatch, version mismatch, cost mismatch, or record-count mismatch.

For compatibility with the sibling synthetic generator, `load_generated()` also
recognizes its documented `corpus_index.json`, `families/`, `timelines/`,
`evidence/`, `transcripts/`, and `audio_events/` layout (including the default
`mvp/generated/full` and `mvp/generated/quick` directories). The adapter builds
one canonical in-memory index and rebinds only the family backend/index metadata
to that derived frozen index; question, graph, interventions, budgets, and source
records are not changed.

The one required index artifact is:

```json
{
  "schema_version": "1.0.0",
  "format": "av_trace_mvp.index.v1",
  "records": [
    {
      "record_id": "alarm_speech_1",
      "family_id": "syn_alarm",
      "asset_id": "asset_alarm",
      "modality": "speech",
      "interval": {"start_s": 100.0, "end_s": 110.0},
      "payload": {"text": "A pressure drop caused the warning."},
      "search_text": "pressure drop warning alarm",
      "preview": "A pressure drop caused the warning.",
      "route_evidence_ids": ["e_speech"],
      "is_distractor": false,
      "speaker": "operator",
      "transcript_sources": ["asr"]
    }
  ]
}
```

`family_id` and `asset_id` may be `null` for shared distractors. Every
answer-bearing or derived record must enumerate **all** `route_evidence_ids`.
A record with no evidence route is accepted only when explicitly marked
`is_distractor: true`. This makes necessity-group withholding transitive over
declared derived leaks rather than merely hiding one preferred clip.

Search is case-folded Unicode alphanumeric lexical overlap. Rankings are stable:
score descending, start/end time ascending, then stable result ID. Search pointers
are non-citable. Clip/transcript observations are immutable and carry a canonical
payload hash.

## State semantics

- `CLEAN` starts with the family's clean evidence and channels.
- `BLOCKED` applies exactly one declared necessity-group withholding or one
  declared modality channel outage.
- `RESTORED` starts exactly as `BLOCKED`. A registered fixed call index or
  `get_channel_status` action reverses exactly that operation.

Channel outages return `channel_unavailable` and a typed
`<CHANNEL>_CHANNEL_UNAVAILABLE` error. Backend-reaching failures are charged.
A call that would exceed the budget returns zero-cost `budget_exhausted`, after
which only `finalize` is accepted.

`inspect_clip` charges once per request and accumulates the exact requested
duration in `backend.inspected_duration_s`. The same duration is recorded in each
returned clip observation payload, because the frozen trajectory schema does not
currently provide a top-level duration field.

## Running an episode

Create a JSON array of schema-valid action envelopes ending in `finalize`, then:

```bash
python scripts/run_mvp_episode.py \
  --generated-root mvp/generated \
  --family-id syn_alarm \
  --state-role RESTORED \
  --script actions.json \
  --output trajectory.json
```

The runner uses logical timestamps derived from the replay seed, not wall time,
and writes payload, response, intervention-manifest, backend-manifest, and
trajectory hashes through the existing normative schemas and validators.

Tests intentionally build temporary indexes/manifests and do not require sibling
generated files or network/model access.
