# VES exact discovery stream-preflight plan

Date: 2026-09-09  
Repository: `buaaplay/VES-Bench`  
Immutable revision: `b1cdbb370ad866090e6fec82ccb9e699b10edbc7`

## Decision

**Ready for a later bounded ISO-BMFF stream/container preflight over exactly
10 closed VES objects.**

This is a discovery plan, not a duration-qualified candidate pool. Task 70
remains unchanged and fail-closed:

- the VES Parquet has no item-level whole-video duration column;
- the duration-qualified candidate pool remains empty;
- the Task 70 long-stream plan remains blocked with zero objects;
- no selected discovery object is currently known to satisfy the
  1,200–5,400 second duration gate.

For every selected object:

```text
actual_duration: UNRESOLVED_PENDING_BOUNDED_CONTAINER_PREFLIGHT
audio_track: UNRESOLVED_PENDING_BOUNDED_CONTAINER_PREFLIGHT
evidence_extent_is_duration: false
```

The later bounded preflight—not metadata evidence—must establish actual
container duration and declared audio/video tracks.

## Exact metadata basis

The plan reuses the exact offline snapshots validated in Task 70:

| Artifact | Exact identity |
|---|---|
| Parquet repository path | `VES-Bench.parquet` |
| Local Parquet | `data/hf_recon/snapshots/hf_buaaplay_VES-Bench_b1cdbb3_VES-Bench.parquet` |
| Parquet size | `422415` bytes |
| Parquet SHA-256 | `be2dca2e9e7561ca9606291fd22f86c0a54eea353fac8c8ac3cf964b4c612376` |
| Parquet blob ID | `74c9e646c04f2a9923d3de0ffe017d9f62a1fbe2` |
| API snapshot | `data/hf_recon/snapshots/hf_api_buaaplay_VES-Bench.json` |
| API size | `79549` bytes |
| API SHA-256 | `a1f844b2f6632e4e8a01038342239854338c9ca85e21ea9e3642cef486a69c6a` |

The 600 metadata rows join one-to-one to 348 exact MP4 sibling objects by
exact metadata `video_path` and API `rfilename`. The discovery tool does not
open a network connection and does not read an MP4 body.

## Selection method

Selection is deterministic and uses the following hierarchy:

1. seed both metadata sources, `ego4d` and `youtube`;
2. cover the three observed task profiles:
   event-counting-only, temporal-ordering-only, and dual-task;
3. cover all three metadata-derived modality-role hypotheses;
4. spend remaining slots on previously unseen topic hypotheses;
5. within each diversity requirement, prefer the greatest maximum evidence
   endpoint, then greater evidence interval coverage;
6. use object size only as a late deterministic tie-break, never as the sole
   or primary selection basis.

After the diverse set is selected, ranks are ordered primarily by decreasing
maximum evidence endpoint.

The evidence-extent preference is only a triage heuristic: observing
benchmark evidence later in a video raises the chance that the object is long,
but cannot prove that its whole-video duration is at least 1,200 seconds. The
largest endpoint in the complete metadata is `1080.0` seconds, and it remains
an evidence timestamp rather than a duration.

## Frozen ten-object set

| Rank | Dataset | Task profile | Max evidence endpoint (s) | Topic hypothesis | Modality hypothesis | Exact path |
|---:|---|---|---:|---|---|---|
| 1 | ego4d | event counting + temporal ordering | 1080.0 | technology/science | environmental/non-speech | `videos/30805f57-8f23-4d41-91a0-19d248a62c1d.mp4` |
| 2 | youtube | event counting + temporal ordering | 1010.0 | animals/nature | environmental/non-speech | `videos/nP5efbYfBPU.mp4` |
| 3 | ego4d | event counting + temporal ordering | 790.0 | retail/daily life | environmental/non-speech | `videos/43f87662-2d38-447b-ba72-0eb7a9daebf1.mp4` |
| 4 | youtube | event counting + temporal ordering | 759.0 | history/news | mixed A/V | `videos/0yKvPsqOtT0.mp4` |
| 5 | ego4d | event counting + temporal ordering | 708.0 | outdoors/travel | mixed A/V | `videos/4b5a1000-66ba-4ebb-8ca0-daf0772c1697.mp4` |
| 6 | youtube | event counting + temporal ordering | 685.0 | home/DIY | mixed A/V | `videos/_Pbquj-6MVc.mp4` |
| 7 | youtube | event counting + temporal ordering | 640.0 | food/cooking | environmental/non-speech | `videos/Pf1hNFndi60.mp4` |
| 8 | youtube | event counting only | 632.72 | sports/performance | mixed A/V | `videos/awHc8IySU-I.mp4` |
| 9 | youtube | event counting + temporal ordering | 600.0 | sports/performance | speech-heavy | `videos/x8zGsWuu-e0.mp4` |
| 10 | youtube | temporal ordering only | 576.0 | animals/nature | mixed A/V | `videos/wUnEDnAYTpE.mp4` |

The result contains:

- 3 `ego4d` objects and 7 `youtube` objects;
- both requested evidence tasks and all three task profiles;
- 8 distinct topic hypotheses;
- all 3 modality-role hypotheses;
- 10 unique paths, blob IDs, and SHA-256 values.

The JSON plan records the exact byte size, blob ID, SHA-256, metadata evidence
rows, per-row evidence extent, and object-level maximum evidence endpoint for
every entry.

## Authorization boundary

The plan authorizes only:

```text
BOUNDED_ISO_BMFF_RANGE_PREFLIGHT_FOR_THE_TEN_EXACT_OBJECTS_ONLY
```

It does not authorize:

- a complete-object response or complete-object range;
- full media acquisition or download;
- processing;
- annotation;
- publication or release.

All those authorization arrays are empty, and every object repeats false
per-object flags for acquisition, processing, annotation, and release.
Rights remain `UNKNOWN_HOLD`.

The parent may adapt `tools/hf_audio_stream_preflight.py` to use this closed
allowlist and bounded range budgets. Any discovered duration or track result
must be written as a preflight result; it must not be inferred from the
evidence timestamps in this plan.

## Files and validation

- Generator: `tools/ves_discovery_preflight_plan.py`
- Plan: `data/acquisition_preflight/ves_discovery_stream_preflight_plan.json`
- Tests: `tests/test_ves_discovery_preflight_plan.py`

Focused tests cover deterministic selection, source/task/topic/modality
diversity, exact sibling identities, evidence-row provenance, no duration
conflation, no wildcard, bounded-only authority, and preservation of Task
70's empty duration-qualified pool.
