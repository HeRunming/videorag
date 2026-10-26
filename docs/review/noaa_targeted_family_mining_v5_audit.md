# NOAA targeted family mining v5 audit

**Date:** 2026-10-12  
**Decision:** `NOAA_TARGETED_FAMILY_MINING_V5_READY`  
**Artifact class:** development-only machine-expert provisional mining  
**Human semantic review performed:** no  
**Media downloaded or decoded by this miner:** no  
**Network used:** no  
**Accepted SES / H tier / Gate-A credit created:** no / no / no

## 1. Scope and boundary

This task implemented a deterministic, local-only targeted miner for the
pilot-v4 shortages identified by pilot-v5 prospecting:

- `V+S`;
- `V+S+A`;
- coherent far/separated multi-hop families.

The miner prioritizes the exact NOAA sources in this order:

1. `cand-049`;
2. `cand-047`;
3. `cand-051`;
4. `cand-045`;
5. `cand-052`.

The generated registry is
`data/restricted/noaa_targeted_family_candidates_v5_dev/candidate_registry.json`.
It is permanently development-only and future-test-ineligible. Every claim,
question, answer, profile, and evidence role is a machine-expert hypothesis
requiring fresh authorized human review.

## 2. Local evidence inspected

The implementation binds and hashes already-local artifacts only:

- the complete NOAA Scale-1A timeline index;
- segment and observation manifests;
- complete quality-gated ASR and learned visual/ambient records represented by
  the index and checkpoint lineages;
- exact NOAA media audit and source hashes;
- the prior development candidate registry;
- prior machine-review records;
- the pilot-v5 targeted prospecting plan.

No source MP4 is opened by the miner. Visual and audio handles are exact index
record IDs and timestamps, not newly decoded observations. Ambient model labels
are used only to route or reject prospects; they never establish sound identity.

## 3. Ranked result

| Rank | Source | Provisional status | Target | Evidence-center separation | Decision |
|---:|---|---|---|---:|---|
| 1 | `cand-049` | `REPAIR` | `V+S`, far/multi | 177 s | Dynamic wave-entry plus later rescue instruction is plausible, but repeated rescue animations, speech-only sufficiency, visible `911`, captions, and OCR remain open. The rejected ambient-surf routes are explicitly excluded. |
| 2 | `cand-047` | `KEEP` | `V+S`, far/multi | 195 s | A hands-on ocean-zone model and later twilight-zone explanation form a coherent lead. Poll text, model labels, spoken construction, and small-object visibility require closure. |
| 3 | `cand-051` | `KEEP` | `V+S`, far/multi | 324 s | A field trash-collection result and later public-database explanation form a collection-to-data-use chain. Narration, app screens, captions, and recurrence remain high risks. |
| 4 | `cand-045` | `REJECT` | attempted `V+S` | 57 s | Presentation, website, slide, and OCR routes dominate. Dynamic non-text visual work is not established. |
| 5 | `cand-052` | `REJECT` | attempted `V+S` / far | 899 s | The known factor graphic duplicates narration/OCR, and aircraft footage is separately captioned or described. Distance does not create a coherent necessary composition. |

`KEEP` means “retain for authorized human prescreen,” not accepted evidence.
`REPAIR` means a promising lead has material unresolved substitution or
coherence defects. `REJECT` means the inspected local evidence should not be
used for the targeted shortage.

## 4. V+S+A outcome

The honest local result is **zero `V+S+A` candidates**.

No exact local evidence establishes all three of:

1. dynamic non-text visual work;
2. substantive non-duplicative speech work;
3. a concrete, temporally localizable, source-world non-speech event carrying
   an independent answer component.

The miner therefore does not promote surf, music, footsteps, generic handling,
water, animal, wind, or other AST predictions into ambient facts. It recommends
separately approved acquisition of audio-rich procedural sources or
prospectively narrowing/removing the `V+S+A` target if authorized acquisition
does not produce survivors.

## 5. Hard-constraint audit

The implementation and validator enforce:

- no human-validation wording or completed human-review flag;
- zero accepted SES count;
- no H tier;
- no Gate-A credit or GO;
- profiles marked as targets/hypotheses rather than forced necessity labels;
- `V+S` candidates require exact vision and speech handles;
- any `V+S+A` candidate would require exact vision, speech, and ambient handles;
- far candidates require at least 120 seconds between evidence centers,
  multi-hop structure, and an explicit coherence hypothesis;
- all evidence intervals stay within exact source duration;
- all `asr.*` and `seg.*` references exist in the complete index;
- `cand-049` explicitly excludes both `DEV-F09-SURF-AUDIO-PROPERTY` and
  `noaa01-r004-surf-av`;
- no duplicate/OCR route is restored as independent dynamic vision;
- no network, download, or media decode is performed;
- canonical JSON and nested payload hashes make output deterministic.

## 6. Validation and execution

Commands used:

```text
python tools/noaa_targeted_family_mining_v5.py
python tools/noaa_targeted_family_mining_v5.py --check
pytest -q tooling/tests/test_noaa_targeted_family_mining_v5.py
ruff check tools/noaa_targeted_family_mining_v5.py tooling/tests/test_noaa_targeted_family_mining_v5.py
```

The tests cover deterministic regeneration, checked-in registry equality,
source priority, status accounting, honest `V+S+A` zero, far/multi invariants,
known `cand-049` exclusions, exact-handle validation, and rejection of invented
Gate-A or triple-modal credit.

## 7. Next scientific action

If annotation authority is established, run source-uniform human prescreen on
the three retained leads without exposing their target labels as outcomes.
Reviewers must search full-source repeats, captions, polls, slides, OCR, chat,
speech derivatives, and embedded-clip lineage before authoring. If the retained
leads collapse to speech-only or duplicate routes, do not preserve quotas by
relabeling. Acquire suitable audio-rich sources or preregister a narrower pilot.

`NOAA_TARGETED_FAMILY_MINING_V5_READY`
