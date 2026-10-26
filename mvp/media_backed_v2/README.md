# AV-TRACE media-backed MVP v2

This non-normative integration closes the three engineering gaps identified by
the MVP reviews: citable observations are decoded from registered MP4 bytes,
all four agents execute over the JSONL subprocess boundary, and premature-stop
eligibility is taken from the certified validator denominator.

## Run

```bash
PYTHONPATH=src python scripts/run_media_backed_mvp.py
PYTHONPATH=src pytest -q tests tests_mvp tests_media tests_agent_runtime tests_validation tests_media_pipeline
```

Outputs are written only to `mvp/results/media_backed_v2/`; prior result
folders are not modified.

## Data flow

1. `mvp/generated/full/backend_manifest.json` is verified, including the frozen
   source MP4 hashes and original control-plane index.
2. `mvp/validator/generated/dataset_certificate.json` is schema checked,
   self-hash checked against the v2 trust anchor, recomputed from all validator
   artifacts, and bound to the live backend, family snapshots, and
   `premature_stop_denominator.json`.
3. `av_trace_media_pipeline.indexing` scans each MP4 on a fixed 2-second grid,
   merges adjacent equal decoded detections, re-decodes proposed intervals, and
   builds a frozen lexical index. Searchable text/content comes only from
   decoded pixels or waveform samples. Family evidence is consulted afterward
   only for evaluator-private `(asset, modality, interval)` route binding.
4. Search uses that frozen media-derived index. `inspect_clip`,
   `read_transcript`, and ambient observations decode the registered MP4 at
   call time and never serve content from timeline, transcript, evidence, or
   family JSON.
5. Each agent/family/state run gets a fresh backend and a fresh subprocess.
   The evaluator reconstructs and validates the normative trajectory.
6. Metrics use the existing state endpoints and common-endpoint paired
   restoration gain, plus certified premature-stop eligibility.

## Intervention and trigger coverage

The eight certified main families retain their original status triggers and
cover both `necessity_group_withholding` and `modality_channel_outage`. The
certified validator case under `mvp/validator/generated/cases/fixed_call/` is
run separately for all four agents. It is clearly reported as a fixed-call
integration fixture and is not mixed into the main 96-episode estimands.

## Mutation experiments

The run compares original MP4s with the three checked-in mutations:

- blanked visual interval `syn_source_01` 24–30 s;
- muted ambient interval `syn_source_02` 38–44 s;
- speech symbol changed in `syn_source_01` 72–78 s.

For every agent, the affected family's decoded observation changes or
vanishes and its supported answer fails. A same-source unrelated family is
also rerun and must preserve semantic observations, answer, and support.
Because mutation fixtures re-encode a whole MP4, byte hashes and incidental
codec/OCR details are not required to remain identical outside the target;
semantic task observations are.

## Synthetic-specific perception outputs

The following outputs remain specific to the procedural fixtures:

- central single-object shape/color recognition over a fixed screen layout;
- closed-vocabulary recognition of burned-in uppercase captions and counters;
- a six-symbol tonal speech codec, explicitly not natural-speech ASR;
- handcrafted waveform classes for pulse trains, motor hum, and confirmation
  chime;
- display phrases such as “operator says” or “inspector says,” deterministically
  projected from decoded symbols for compatibility with the existing agents.

Evidence IDs, claims, SES membership, necessity groups, intervention state, and
correct answers are evaluator-private and are not perception outputs.

## Checked-in run

`mvp/results/media_backed_v2/report.json` records 96/96 valid main
trajectories, four fixed-call trajectories, 24 mutation trajectories, complete
17/17 media/evidence coverage, and 3/3 passing mutation contracts. The semantic
result hash is
`sha256:bcb3b5eb7458abd132a1939d53f043aef615a98c2f462bc3bc6b2573f2844a01`.
Two complete same-environment reruns produced identical report, run-manifest,
and artifact-hash-map files.
