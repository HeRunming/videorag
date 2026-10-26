# NOAA-01 real-A/V MVP Go/No-Go review


**Stage:** `MACHINE_ADJUDICATED_PROVISIONAL_MVP`  
**Human reviewed:** `false`  
**Gold annotation:** `false`

This is a bounded 18-window protocol/construct-validity MVP over three long
NOAA videos. The four baselines are deterministic protocol-level policies, not
learned VLM/LLM systems. No SOTA or model-quality claim is supported.

## Scope

- Families: 6
- Source assets: 3
- Reviewed source windows in frozen index: 18
- Main trajectories: 72 (6 families × 3 states × 4 policies)
- Valid trajectories: 72
- No-trigger controls: 12

## Resolved intervention failures

- `noaa01-r004-surf-av`: After ambient restoration the lexical ranker selected a same-source ambient distractor instead of binding the audio result to the already observed visual interval. Repair: Use policy-visible exact timestamps for cross-modal binding after the registered channel-status trigger; the restored ambient route is then reacquired from the original MP4. Verified: `true`.
- `noaa01-r016-three-factors-vs`: After speech restoration the lexical ranker preferred a North-Atlantic distractor over the speech observation co-timed with the acquired graphic. Repair: Use the same policy-visible temporal-binding rule to select the co-timed speech observation after restoration, without exposing evaluator route IDs. Verified: `true`.

## Protocol checks

- Original MP4 identity is checked against its registered SHA-256; a cached
  digest is reused only while device/inode/size remain unchanged.
- Every citable observation decodes its exact source-time interval with PyAV.
- No frame, audio, or clip derivative is persisted.
- CLEAN/BLOCKED/RESTORED invariants and no-trigger controls passed:
  `true`.
- Agents receive only question, tools, budget, and opaque search/observation
  results; evaluator-private support routes and state labels are absent.

## Metric boundary

Evidence, answer, and citation metrics are hypothesis-conditioned on two
deterministic validators. Modality Recall is `null` because no modality
necessity is human-validated. Recovery is `null` for direct and single-shot
policies. Supported-Claim Rate now uses asserted public claim slots and their
claim-specific citations; empty abstentions are ineligible. Success@Budget
requires a valid, in-budget, fully supported finalization. Premature Stop uses
an evaluator-private feasibility certificate at the actual final decision
point. Every aggregate row carries `LOW_N_DESCRIPTIVE_PILOT`; all results are
descriptive and prohibit inference.

## Policy boundary

`react-recovery` is a reactive search/reformulation policy.
`evidence-sufficiency` follows a separate controller path, maintains an
explicit public-slot coverage belief, checks channel state when evidence is
weak or missing, avoids further search for supported slots, and abstains when
its visible evidence remains insufficient. These are deterministic protocol
probes, not learned agents.

## Decisions

- `ENGINEERING_GO`
- `PROVISIONAL_SCIENTIFIC_INCONCLUSIVE`
- `FINAL_BENCHMARK_NOT_YET_VALIDATED`

The engineering decision concerns executable plumbing only. The provisional
scientific decision cannot establish benchmark validity, and final validation
still requires human evidence/counterfactual review, broader data, release
review, and genuine learned baselines.
