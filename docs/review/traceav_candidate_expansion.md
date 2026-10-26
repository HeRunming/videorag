# TraceAV candidate expansion review

**Task:** 49  
**Date:** 2026-09-07  
**Mode:** local, metadata-only; network disabled  
**Approval effect:** none; `PROVISIONAL_NOT_APPROVED` and `unknown_hold` are preserved

## Result

No candidate was added. The strict exact-duration shortlist remains **3**:

| Rank | Candidate | Canonical LongVideoBench parent | Exact duration (s) | Split |
|---:|---|---|---:|---|
| 1 | `ccp-008` | `-PgbM2MhcYQ` | 2987.08 | test |
| 2 | `ccp-009` | `-eRimFrm6kQ` | 1540.88 | validation |
| 3 | `ccp-003` | `-7wwfGJXEZg` | 1515.20 | test |

A balanced 4–5 candidate shortlist could not be reached without violating the
required exact-parent, duration, or mapping-lineage gates. No candidate-pool or
funnel row was added.

## Input integrity and copied snapshots

All three parent-provided files matched the required size and SHA-256 before
use and after copying into `data/hf_recon/snapshots/`.

| Task table | Bytes | SHA-256 | Repository snapshot |
|---|---:|---|---|
| environmental sound | 345,889 | `5a5e7af576566093dce69dc6fd8eb9a1c5e2c97d5f3d70211a0b315cdc0b3c46` | `hf_Heinz217_TraceAV-Bench_a_environmental_sound_cc96f31.jsonl` |
| speech context | 457,735 | `ffdea1f5cfde262fa13a634fc11a851531e9c0d70802119d10e9cfee883a3f49` | `hf_Heinz217_TraceAV-Bench_a_speech_context_cc96f31.jsonl` |
| cross-modal matching | 392,687 | `d04dbbba9f4401b804f93bdf9814d17038b11dc58a1b03a5237e4978adbc5ab7` | `hf_Heinz217_TraceAV-Bench_av_cross_modality_matching_cc96f31.jsonl` |

The immutable TraceAV revision is
`cc96f31d1d30b56bd4be02bb660bee394896c288`. The verified
LongVideoBench-Meta revision is
`cdf3444602208c95f453e7683583a077ce38ddbf`.

## Parse and join audit

The three files contained **303 valid JSONL rows** and no parse errors:

| Input | Rows | Unique TraceAV videos | Mapped `lvbench` | Mapped `omnivideobench` | Mapped `videomme` |
|---|---:|---:|---:|---:|---:|
| environmental | 88 | 88 | 12 | 16 | 60 |
| speech | 130 | 121 | 20 | 19 | 91 |
| cross-modal | 85 | 84 | 12 | 13 | 60 |
| **Total** | **303** | **251** | **44** | **48** | **211** |

Every TraceAV `video_id` had an official mapping row. The strict join used the
mapping namespace as part of lineage: only rows marked `source=lvbench` were
eligible to join LongVideoBench-Meta as LongVideoBench parents.

- The 44 `lvbench` rows represented 37 distinct mapped parent IDs.
- **Zero** of those 37 IDs existed in either verified LongVideoBench-Meta table.
- None collided with the current three shortlist parent IDs.
- Consequently, zero rows had an exact duration available under the required
  lineage-preserving join and zero entered ranking/selection.

As a diagnostic only, joining by bare ID while ignoring the official source
namespace found one record: TraceAV `video490`, officially mapped as
`videomme:mOiEOs3ZlT8`. LongVideoBench-Meta also contains that bare ID, but its
exact duration is **12.01 seconds**, outside the 1,200–5,400-second range. This
namespace-crossing coincidence was not treated as LongVideoBench lineage and
would fail duration regardless.

The complete text-only row audit is:

`data/hf_recon/snapshots/traceav_modality_lvb_join_cc96f31d1d30b56bd4be02bb660bee394896c288_cdf3444602208c95f453e7683583a077ce38ddbf.json`

It records input line numbers, mapping rows, parent lookup results, exact
metadata fields when present, task labels, event counts, label diversity,
evidence spans, shortlist collisions, and eligibility outcomes for all rows.

## Ranking and selection rule

Ranking was applied only after these hard gates:

1. official mapping source must be `lvbench`;
2. mapped parent ID must have an exact LongVideoBench-Meta row;
3. exact duration must be 1,200–5,400 seconds inclusive;
4. canonical parent ID must differ from `-PgbM2MhcYQ`, `-eRimFrm6kQ`, and
   `-7wwfGJXEZg`.

Eligible rows would then be ordered by explicit task class, evidence temporal
span, event count/diversity, and source-level modality breadth. Because no row
passed the hard gates, selecting zero additions was preferable to forcing a
fourth candidate.

## Modality interpretation boundary

The upstream labels are explicit and useful for triage:

- `a_speech_context` is a speech-oriented TraceAV task label;
- `a_environmental_sound` is an environmental/non-speech-oriented task label;
- `av_cross_modality_matching` is a cross-modal-oriented task label;
- trajectory entries provide released timestamp ranges and evidence text.

These facts **do not verify AV-TRACE modality necessity**. They do not establish
that an authorized source rendition has an audio stream, that speech is
intelligible, that environmental sound is usable and non-speech, that audio and
vision are jointly necessary, or that no unimodal shortcut exists. Those facts
remain unverified until media is authorized, acquired, probed, and reviewed.

## Coverage hypotheses after expansion attempt

The final three-candidate strict shortlist remains weighted toward
LongVidSearch visual/multi-hop metadata:

- **vision / temporal multi-hop:** plausible metadata leads on all three;
- **speech:** unverified;
- **ambient/non-speech:** unverified;
- **cross-modal necessity:** unverified;
- **far evidence:** plausible from downstream ordinal slices, but source-second
  joins remain unresolved.

Thus the expansion did not improve verified modality coverage. It did improve
the negative evidence: the available TraceAV modality rows cannot supply a
fourth exact-duration LongVideoBench parent at the pinned revisions.

## Safety and provenance confirmation

- No network access was used.
- No video, audio, subtitle payload, or other media was acquired.
- No prohibited payload was acquired.
- Only text annotations, the existing mapping, verified metadata Parquets, and
  a derived text-only JSON audit were read or written.
- Complete-source availability and all media stream facts remain unverified.
- Source-media rights remain `unknown_hold`.
- Every retained shortlist row remains `PROVISIONAL_NOT_APPROVED`.
