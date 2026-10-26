# LVB-01 restricted real-media visual + subtitle-proxy rehearsal

**Run date:** 2026-09-09  
**Scope:** internal engineering rehearsal using **video plus subtitle proxy**  
**Engineering decision:** **GO**  
**Scientific decision:** **NO-GO beyond protocol mechanics**

## Boundary

This run is limited to video and a subtitle text proxy. The five audited MP4
files contain no audio streams. Subtitle JSON is handled only as a source-level
text proxy; it is not called audio, speech-waveform retrieval, ASR, or ambient
evidence.
No benchmark answers, gold answers, final annotations, frames, or subtitle text
were written by the rehearsal.

The authoritative preconditions remain:

- `docs/review/lvb01_download_media_audit.md`
- `docs/review/lvb01_post_download_decision.md`
- `data/rehearsal_plan/lvb01_verified_asset_status.csv`

## Implementation

The implementation consists of:

- `src/av_trace_real_rehearsal/adapter.py`
  - verifies the frozen-plan and acquisition-manifest digests bound by the
    media audit;
  - verifies the authoritative status overlay before every payload open;
  - permits only the five audit-bound video/subtitle pairs;
  - rejects symlinks, non-regular files, permissive payload modes, size drift,
    and SHA-256 drift;
  - decodes requested source-time frames in memory and returns only timing,
    geometry, and decode status;
  - searches ordered subtitle proxy cues but returns no subtitle strings;
  - uses symmetric windows around cue start times and ignores point-like cue
    ends as speech-span evidence.
- `src/av_trace_real_rehearsal/protocol.py`
  - derives four provisional route probes per asset;
  - constructs matched `CLEAN`, `BLOCKED`, and `RESTORED` definitions;
  - runs direct/single-shot, subtitle-first, visual-first, and
    sufficiency-aware recovery baselines;
  - records source-time citations and non-content diagnostics.
- `tools/run_lvb01_visual_subtitle_rehearsal.py`
- `tests/test_lvb01_visual_subtitle_rehearsal.py`

Learned semantic visual retrieval was unavailable and was not imitated. The
visual route is explicitly a deterministic inspection baseline: candidate
source times are derived from real ordered subtitle timing, then actual video
frames are sought and decoded at those times. This demonstrates protocol and
media-access behavior, not semantic visual localization quality.

## Automatically derived rehearsal set

The runner generated 20 provisional tasks:

- 5 assets;
- 4 routes per asset:
  - visual-only;
  - subtitle-proxy-only;
  - video to subtitle-proxy;
  - subtitle-proxy to video.

Each task is marked `PROVISIONAL_REHEARSAL_ONLY`,
`final_benchmark_annotation=false`, and
`semantic_visual_retrieval=UNAVAILABLE_NOT_FAKED`.

For each asset, a deterministic rare-token subtitle cue supplied an internal
inspection coordinate and an in-memory query. The persisted task contains only
the cue index and times. Neither query tokens nor cue text are persisted.

## Matched states and perturbations

All baselines used the same task, tool budget, answer surface, available
channel declaration, and intervention definition across state variants.

- `CLEAN`: the registered video window and subtitle-proxy route are available.
- `BLOCKED`: either the task video window or the subtitle-proxy route is
  withheld.
- `RESTORED`: starts identically to `BLOCKED`; the exact withheld route is
  restored after the recovery agent observes the controlled access failure.

The missing audio stream is not used as an intervention.

Every asset received controlled retrieval perturbations in the recovery
baseline:

- wrong deterministic video candidate window; and/or
- partial subtitle-proxy result with the target cue withheld from that call.

All five assets had a subsequent recovery attempt.

## Executed workload and results

The restricted result is:

`data/restricted/lvb01/rehearsal/lvb01_visual_subtitle_rehearsal.json`

It is mode `0600` inside a mode `0700` directory. Its SHA-256 after the final
run is:

`a3ce3a43121054e5c676ad8038e72d6670ae3b066a3e86cb763b1595aefeffe1`

The final run contains:

- 5 assets;
- 20 provisional tasks;
- 240 runs = 20 tasks × 3 states × 4 baselines;
- 100% timestamp-citation validity over all runs;
- zero unsupported-claim proxies over all runs;
- matched intervention definitions for every task.

### Recovery baseline

For the 40 `CLEAN` or `RESTORED` recovery-agent runs:

| Metric | Result |
|---|---:|
| Evidence acquisition success | 1.000000 |
| Recovery after perturbation | 1.000000 |
| Premature stop | 0.000000 |
| Timestamp citation validity | 1.000000 |
| Unsupported-claim proxy | 0.000000 |
| Mean tool calls | 2.875000 |
| Mean video seconds inspected | 1.500000 |
| Mean route switches | 0.500000 |

For the 20 terminal `BLOCKED` recovery-agent runs:

| Metric | Result |
|---|---:|
| Evidence acquisition success | 0.000000 |
| Recovery after perturbation | 0.000000 |
| Premature stop | 0.000000 |
| Timestamp citation validity | 1.000000 |
| Unsupported-claim proxy | 0.000000 |

Here `premature_stop=0` in `BLOCKED` means the recovery policy attempted the
registered route, observed the access failure, and stopped with an
`insufficient` protocol verdict rather than asserting sufficiency.

### Deterministic baselines across all states

| Baseline | Evidence success | Premature stop | Mean calls | Video seconds | Route switches |
|---|---:|---:|---:|---:|---:|
| Direct/single-shot | 0.166667 | 0.833333 | 1.000000 | 0.750000 | 0.000000 |
| Subtitle-first | 0.333333 | 0.666667 | 1.333333 | 0.583333 | 0.333333 |
| Visual-first | 0.333333 | 0.666667 | 1.333333 | 0.750000 | 0.333333 |
| Recovery agent | 0.666667 | 0.000000 | 2.750000 | 1.416667 | 0.500000 |

The recovery aggregate includes deliberately impossible terminal `BLOCKED`
runs, so its overall evidence-success rate is two thirds by construction.

## Privacy and integrity checks

- Source video/subtitle payloads were opened read-only and were not modified.
- No derived image or media file was created.
- Persisted frame diagnostics contain no pixels, image hashes, or content
  features.
- Persisted subtitle diagnostics contain no text or query terms.
- A post-run scan found zero verbatim subtitle lines in the report.
- The runner printed only counts, scope, status, and its restricted output
  path.
- Fail-closed tests cover payload hash/size drift and non-allowlisted access.

## Validation

```text
pytest -q tests/test_lvb01_visual_subtitle_rehearsal.py
7 passed

python tools/run_lvb01_visual_subtitle_rehearsal.py
strict_engineering_go=true

pytest -q
144 passed
```

## Strict Go / No-Go

### Engineering GO

The rehearsal shows that, on all five real long-video byte streams, the
implementation can:

1. verify acquisition/audit/status bindings before opening payloads;
2. seek and decode frames at requested source times;
3. search ordered subtitle proxies using conservative start-centered windows;
4. execute visual-only, subtitle-proxy-only, and both route-switch directions;
5. instantiate matched video/subtitle-proxy `CLEAN`, `BLOCKED`, and `RESTORED`
   states;
6. recover after controlled wrong-window, partial-result, and access-block
   failures;
7. cite source-time evidence;
8. avoid premature sufficient finalization in the recovery baseline.

### Scientific NO-GO beyond those mechanics

This run does **not** establish:

- learned semantic visual retrieval quality;
- benchmark answer accuracy or final annotation validity;
- modality necessity for any LongVideoBench question;
- retrieval from raw speech or any audio waveform;
- ambient or non-speech audio behavior;
- genuine audiovisual routing, synchronization, or recovery;
- subtitle fidelity to unavailable source audio;
- rights, privacy, redistribution, or public-release eligibility;
- generalization beyond these five restricted files and deterministic probes.

The correct conclusion is therefore:

**GO for the demonstrated restricted video + subtitle-proxy engineering
protocol; NO-GO for audiovisual, benchmark-scientific, or release claims.**
