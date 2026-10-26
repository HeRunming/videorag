# Pilot-v5 candidate integration audit

**Date:** 2026-10-12  
**Decision:** `PILOT_V5_CANDIDATE_MATRIX_REPAIR`  
**Artifact class:** provisional development-lead integration planning only  
**Human review performed:** no  
**Gate A or test eligibility created:** no

## 1. Executive decision

The deterministic integration preserves all 12 pilot-v4 slots and overlays
exactly three retained NOAA v5 development leads:

| Development slot | Candidate | Source group | Retained status | Target | Hop / span |
|---|---|---|---|---|---|
| `PV5-DEV-NOAA47-01` | `NOAA-V5-047-OCEAN-MODEL-TWILIGHT` | `cand-047` | `KEEP` | V+S | multi / far |
| `PV5-DEV-NOAA51-01` | `NOAA-V5-051-TRASH-TRIP-DATA` | `cand-051` | `KEEP` | V+S | multi / far |
| `PV5-DEV-NOAA49-01` | `NOAA-V5-049-WAVE-ENTRY-RESCUE` | `cand-049` | `REPAIR` | V+S | multi / far |

The overlay is additive inventory only. It does not replace a v4 slot, merge a
new NOAA source into `cand-052`, or count one candidate twice. The v5 statuses
remain exactly `KEEP`, `KEEP`, and `REPAIR`.

Both retained-lead coverage views provisionally close the **V+S** and
**multi-hop** inventory shortages. Neither closes the **far** shortage:

| Coverage view | Added leads | V+S | Multi-hop | Far | V+S+A |
|---|---:|---:|---:|---:|---:|
| Conservative `KEEP` only | 2 | 2 / 2, inventory gap closed | 7 / 6, inventory gap closed | 3 / 6, short 3 | 0 / 2, short 2 |
| Optimistic `KEEP` + `REPAIR` | 3 | 3 / 2, inventory gap closed | 8 / 6, inventory gap closed | 4 / 6, short 2 | 0 / 2, short 2 |

These are not accepted credits. No retained lead has human semantic review,
an accepted SES, an H tier, Gate-A credit, or future-test eligibility.

The honest matrix decision is **REPAIR**. Retained leads improve planning
coverage but cannot directly close an exact Pivot-v2 roster.

## 2. Frozen baseline and delta method

The generator reads only:

1. `data/rehearsal_plan/pilot_v4_candidate_matrix.json`; and
2. `data/restricted/noaa_targeted_family_candidates_v5_dev/candidate_registry.json`.

The v4 baseline remains:

- 12 candidate slots;
- six source groups;
- two slots per source group;
- profile hypotheses: 6 V, 2 S, 2 A, 2 V+A, 0 V+S, 0 V+S+A;
- hop hypotheses: 7 one-hop and 5 multi-hop;
- temporal hypotheses: 11 near/local and 1 far/separated.

For each scenario, the generator adds only the retained lead's target profile,
hop, temporal class, and distinct source group. It does not subtract or
replace any baseline record. This produces transparent deltas:

- conservative: +2 V+S, +2 multi, +2 far, +2 source groups;
- optimistic: +3 V+S, +3 multi, +3 far, +3 source groups.

The matrix binds both inputs by SHA-256, binds every retained lead to its
candidate payload hash, and hashes the complete generated matrix canonically.

## 3. Why provisional coverage is not a valid 12-slot matrix

Direct addition fails the frozen source/slot constraints:

1. conservative inventory would have 14 candidates and eight source groups;
2. optimistic inventory would have 15 candidates and nine source groups;
3. each newly added NOAA source group supplies only one retained lead, not the
   required two candidates per source group;
4. `cand-052` is already the presentation-wrapped NOAA group in v4, so adding
   two or three more presentation-wrapped NOAA groups exceeds the cap of two;
5. an exact roster change would require explicit source-group replacement and
   a complete two-candidate package for every admitted group.

The integration therefore does not silently assign the new leads to v4 slots.
If a retained NOAA source is later admitted, the complete six-group roster
must be redesigned prospectively and the displaced source/slots must be named.

## 4. Shortage conclusions

### V+S

The two `KEEP` leads are enough to cover the numerical shortage of two. The
`REPAIR` lead provides an optimistic reserve. Closure remains provisional
because dynamic visual work, speech non-duplication, repeated routes, captions,
polls/OCR, source coherence, and rights all require human review.

### Multi-hop

V4 has five multi-hop hypotheses. Either coverage view adds at least two
far/multi leads, so the numerical inventory exceeds the target of six. This is
not permission to force a multi-hop label if human review collapses a lead.

### Far/separated

V4 has one far hypothesis. The `KEEP`-only view reaches three and remains
short by three. The optimistic view reaches four and remains short by two.
Thus retained NOAA leads cannot close the far shortage by themselves.

### V+S+A

V+S+A remains honestly unsupported. None of the retained leads has a concrete,
localizable, source-world non-speech event carrying a non-duplicative answer
component. Surf, music, score, footsteps, handling, water, generic ambience,
AST labels, and simple co-occurrence remain ineligible for triple-modal credit.

## 5. Exact next wave

### Wave 0 — human prescreen of retained exact-source leads

Run only after source/component human-annotation authority is affirmative:

1. `PV5-HP-047`: prescreen `PV5-DEV-NOAA47-01` first. Close model labels,
   spoken construction, poll text/results, captions, recurrence, small-object
   visibility, and embedded-clip lineage.
2. `PV5-HP-051`: prescreen `PV5-DEV-NOAA51-01` first. Close narration,
   app-screen/map/OCR, captions, recurrence, and embedded field-clip lineage.
3. `PV5-HP-049-REPAIR`: keep a separate repair lane for
   `PV5-DEV-NOAA49-01`. Preserve both rejected surf-route exclusions and group
   the repeated rescue animations and speech. Reject if speech/OCR alone
   answers the complete claim or if the separated clauses are incoherent.

No Wave-0 outcome automatically replaces a v4 slot.

### Wave 1 — new audio-rich source acquisition

Acquire for the two exact triple-modal far/multi target cells:

- `B08`: one rights-ready, non-presentation, audio-rich source group with
  independent dynamic V, substantive S, and concrete answer-bearing A;
- `B12`: a source-disjoint group from another production lineage meeting the
  same requirements.

Each acquired group also needs a second defensible candidate before it can
satisfy the exact two-candidates-per-source rule.

These two far/multi acquisitions would fill the optimistic far remainder of
two. Under conservative `KEEP`-only coverage, they raise far inventory from
three to five, so acquire or author one additional coherent multi/far prospect
(`FAR-KEEP-ONLY-01`) without forcing its modality profile.

### Wave 2 — prospective target narrowing

Narrow only after documented acquisition failure and before roster selection:

1. if `B08` and `B12` acquisition is NO_GO, freeze an addendum that explicitly
   reduces/removes V+S+A and names replacement profiles; never relabel a
   retained NOAA lead as V+S+A;
2. if fewer than six coherent far prospects remain, freeze a revised far
   target and near/far balance prospectively;
3. if retained V+S leads pass semantics but cannot fit source constraints,
   either redesign the complete six-source roster with two candidates per
   admitted NOAA group or acquire non-presentation V+S sources for `B02` and
   `B11`.

## 6. Validation

The implementation provides validators for:

- deterministic regeneration and checked-in equality;
- exact preservation of all v4 slot IDs, profile statuses, and dispositions;
- exact retained identity and `KEEP`/`REPAIR` status preservation;
- no slot-ID collision, source merge, replacement, or double counting;
- conservative and optimistic delta/shortage accounting;
- explicit failure of exact source-group/slot constraints;
- V+S+A honest zero;
- no human decision, accepted SES, H tier, Gate-A credit, or test eligibility;
- exact next-wave routing; and
- canonical payload hashes.

Commands:

```text
python tools/pilot_v5_candidate_integration.py
python tools/pilot_v5_candidate_integration.py --check
pytest -q tooling/tests/test_pilot_v5_candidate_integration.py
ruff check tools/pilot_v5_candidate_integration.py tooling/tests/test_pilot_v5_candidate_integration.py
```

`PILOT_V5_CANDIDATE_MATRIX_REPAIR`
