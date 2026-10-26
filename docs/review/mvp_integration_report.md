# MVP integration report

**Date:** 2026-09-05  
**Status:** PASS  
**Scope:** Offline synthetic construct-validation demonstration; not a
leaderboard result.

## What was integrated

- Added `scripts/run_mvp.py` with `generate`, `validate`, `run`, and `all`.
- Generation now writes a persisted `backend_index.json`,
  `backend_families.json`, and fail-closed `backend_manifest.json`.
- The index is built from generated timelines, transcripts, audio-event labels,
  and the standalone evidence inventory. Family annotations are used only to
  bind route IDs and validate intervention closure; they do not provide index
  payload or search text.
- Experiment execution requires and loads the persisted backend manifest.
- Agents now run through a blind capability wrapper. They receive question,
  budget/tool metadata, responses, and observations only. They do not receive
  `state_role`, oracle fields, claim/evidence graphs, accepted SESs, or necessity
  groups.
- The evaluator attaches registered claim IDs through a frozen exact-text mapper.
- All emitted trajectories are validated before reporting.

## Reproduction

```bash
python -m pip install -e .
python scripts/run_mvp.py all --probe
PYTHONPATH=src pytest -q tests tests_mvp
python scripts/run_mvp.py all --probe
```

The full suite contains **99 tests** and passed. The complete run produced:

- 4 synthetic sources;
- 8 families;
- 24 matched episodes;
- 4 agents;
- 96 agent trajectories;
- 96/96 schema-valid trajectories.

Observed full-run runtimes were **18.203 seconds** and **18.730 seconds** for
generation, probing, validation, execution, metrics, and report writing on
Python 3.13.11. Test
runtime was approximately 24 seconds with the new full-workflow integration
test included.

## Reproducibility hashes

Two consecutive complete reruns produced identical metadata/result hashes:

| Artifact class | Canonical hash |
|---|---|
| Generation metadata | `sha256:ef31e5bf90703d065281bb03cece86ac50fb9c494cc1b356c4bc1c37c02cd7ab` |
| Frozen backend index | `sha256:25f2c1df58bfcc0eb61d1f53561cb8f1023ee655ab12a22a351806b309c6e223` |
| Frozen backend manifest | `sha256:3766e28aaabe61e05f81d8bb50f77138f7696ad52e41b1db86ae82a658b0aba8` |
| Experiment result | `sha256:f5e50e0c67c5294c682a99deafe21a5e09da49d352d2502b4b9f1ba5fd24a722` |
| Validation result | `sha256:d8d270f53109a7890c15331011c3b187f28b45471c2a3f61bcba71f8ad273cb6` |

The four MP4 hashes also repeated exactly in this environment. The metadata
contract remains portable even though encoded MP4 byte identity is not promised
across codec builds.

## Results

| Agent | CLEAN grounded | BLOCKED grounded | BLOCKED FSR | BLOCKED premature stop | RESTORED grounded | Recovery@Budget | Sufficiency Brier |
|---|---:|---:|---:|---:|---:|---:|---:|
| AlwaysAnswer | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.746 |
| SingleShotRAG | 1.00 | 0.50 | 0.00 | 1.00 | 0.00 | 0.00 | 0.024 |
| ReActHeuristic | 1.00 | 0.50 | 0.00 | 0.50 | 0.50 | 0.50 | 0.020 |
| EvidenceBeliefState | 1.00 | 1.00 | 0.00 | 0.00 | 1.00 | 1.00 | 0.016 |

### Interpretation

- **Equal clean correctness can hide diagnostic differences.** All four systems
  scored 1.00 on CLEAN grounded success, while sufficiency calibration,
  false-sufficiency, premature-stop, and cost differed substantially.
- **BLOCKED exposes false sufficiency and premature stopping.** AlwaysAnswer had
  a 1.00 false-sufficient rate and premature-stop rate. SingleShotRAG avoided
  false sufficiency but still stopped prematurely in every eligible BLOCKED
  episode. ReActHeuristic improved only for typed channel outages; the
  belief-state agent correctly diagnosed and stopped in all BLOCKED episodes.
- **RESTORED separates recovery behavior.** EvidenceBeliefState triggered and
  completed recovery in all families. ReActHeuristic recovered only the four
  channel-outage families. AlwaysAnswer and SingleShotRAG never triggered
  restoration and therefore had zero RESTORED grounded success and
  Recovery@Budget.
- **Failed families/metrics are visible, not hidden.** All CLEAN runs passed.
  AlwaysAnswer failed grounded success in all BLOCKED and RESTORED families.
  SingleShotRAG failed all RESTORED families and four BLOCKED withholding
  families. ReActHeuristic failed the four withholding families in BLOCKED and
  RESTORED. EvidenceBeliefState had no grounded-success failures.

The zero paired restoration gain shown for some agents is expected: it compares
RESTORED with BLOCKED grounded task success, and an agent can earn BLOCKED
success by correctly abstaining yet fail to recover in RESTORED.

## Artifact sizes

The generated corpus plus frozen backend contains approximately **5.52 MB of
file payloads** (about 5.3 MiB by `du`). `mvp/results/latest/` contains
approximately **1.97 MB of file payloads**. Principal result files:

| File | Bytes |
|---|---:|
| `report.json` | 1,858,941 |
| `episode_metrics.csv` | 27,322 |
| `summary.csv` | 33,925 |
| `dashboard.csv` | 690 |
| `report.md` | 1,051 |
| `validation.json` | 33,071 |
| `run_manifest.json` | 9,815 |

## Limitations

1. The sources are 4–8 minute synthetic compatibility fixtures, not public-core
   20–90 minute assets.
2. The policies are symbolic deterministic probes and should not be interpreted
   as model rankings.
3. Registered claim IDs are attached by a frozen exact-text evaluator mapper.
4. Retrieval remains lexical over literal synthetic event labels.
5. Exact MP4 bytes depend on the local codec/toolchain build.
