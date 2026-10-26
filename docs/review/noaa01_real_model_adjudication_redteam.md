# NOAA-01 Task 85 independent real-model red-team

**Audit date:** 2026-09-10  
**Scope:** Task 84 authoritative implementation, restricted records, manifests,
model snapshots, media identities, public leakage, persistence, and scientific
claims  
**Stage:** `MACHINE_ADJUDICATED_PROVISIONAL_MVP`  
**Final decision:** **`GO_PROVISIONAL_EPISODE_CONSTRUCTION`**

## Bottom line

Task 84's real local Whisper/AST execution and asset provenance withstand
structural review, but its original scientific labels did not fully withstand
red-team scrutiny. The red-team repaired the authoritative artifacts before
granting the gate:

- accepted/deferred/rejected changed from **7/9/2** to **6/10/2**;
- `noaa01-review-003` was downgraded because the exact interval shows two
  presenters standing and speaking, not the claimed demonstration action;
- all original `likely_necessary` labels (**V=10, S=3, A=1**) were downgraded
  to **V=0, S=0, A=0** because Task 84 had not executed modality-drop
  answerability counterfactuals;
- accepted-window visual claims for `011` and `014` were narrowed to what the
  decoded interval directly supports;
- validation was strengthened for media/model hashes, source-measurement and
  queue identity, decode coverage, stale manifests, fallback provenance, and
  necessity claims.

The remaining six windows are sound enough to construct machine-adjudicated
provisional episodes. This decision does **not** authorize gold annotation,
release, or definitive modality minimality.

## Independently recomputed authoritative counts

| Quantity | Count |
|---|---:|
| Queued/real-ASR/real-AST windows | 18 / 18 / 18 |
| Accepted | 6 |
| Deferred | 10 |
| Rejected | 2 |
| ASR intelligibility-proxy passes | 14 |
| Specific non-speech-event candidates | 1 |
| Meaningful-visual judgments | 11 |
| Candidate question/evidence seeds | 14 |
| `likely_necessary` V / S / A | 0 / 0 / 0 |

Accepted windows:

- `cand-049`: `noaa01-review-004`
- `cand-051`: `noaa01-review-007`, `noaa01-review-011`
- `cand-052`: `noaa01-review-014`, `noaa01-review-016`,
  `noaa01-review-017`

## Accepted-window red-team verdicts

### `noaa01-review-004` — retain accept

The exact interval visibly contains a person in breaking surf. AST's strongest
specific labels support ocean/waves/wind as a clip-level event candidate.
`V+A` is retained as an **episode-construction routing role**, not as a
minimality result. Both V and A necessity remain `uncertain`: the question was
composed after observing the modalities, AST does not localize the event, and
no modality-drop answerability test has run.

### `noaa01-review-007` — retain accept

The opening montage clearly shows a discarded plastic bottle. This is a
supported visual seed, although shallow and title-adjacent. V is a provisional
role; necessity is untested.

### `noaa01-review-011` — retain accept after repair

The interval supports a person walking beside a fence while carrying a large
bag. It does not, by itself, securely show the previously claimed cleanup
action. The seed and description were narrowed accordingly. V remains a role
hypothesis, not a necessity label.

### `noaa01-review-014` — retain accept after repair

The interval shows an aircraft-wing view amid dense storm clouds, with
answer-bearing captions discussing hurricane observations/prediction. The
earlier description of a rotating weather formation was not supported by this
exact interval and was replaced. V necessity remains untested.

### `noaa01-review-016` — retain accept

The visible graphic and speech both support the count of three hurricane
formation factors. This is useful V+S corroboration, but either channel may
duplicate the answer. Both modalities remain `uncertain`, correctly avoiding
a minimality claim.

### `noaa01-review-017` — retain accept

The speech proxy supplies a concise basin-related answer while the visible
webinar layout is not answer-bearing. S is retained as a routing role.
Whisper Tiny output is provisional and partially truncated, so speech
necessity remains `uncertain` pending a modality-drop/answerability check and
later human validation.

## Provenance and implementation findings

Verified independently:

- all 18 queue entries have unique, ordered records with matching candidate,
  basename, interval, source measurement, Task 80 source ID, and queue
  position;
- every record reports one local Whisper execution and one local AST
  execution with the expected model IDs/revisions;
- all 18 audio intervals decode to exactly 128,000 mono 16 kHz samples, with
  complete observed coverage in the independent audit; all have seven video
  observations;
- the three pilot media files match acquisition and authoritative manifest
  sizes/SHA-256 values and passed the prior PyAV media audit;
- all files in both local model snapshots match their local `SHA256SUMS` and
  restricted model manifest inventories;
- authoritative output sizes/hashes and recomputed aggregate counts agree with
  the current manifest;
- Task 83 fallback artifacts are preserved with explicit
  `SUPERSEDED_FALLBACK_PROVENANCE_ONLY`, `authoritative: false`, and
  `superseded_by` markers;
- no full restricted transcript occurs in the reviewed public report/result/
  authorization artifacts;
- no persistent frame, clip, audio, waveform, contact sheet, NumPy media
  derivative, or Task 84/85 temporary inspection artifact remains.

Implementation repairs:

1. Added SHA-256 digest-format, duplicate-entry, exact-file-set, and symlink
   rejection for model snapshots.
2. Added finite-sample and at-least-99.5%-coverage checks to exact audio decode.
3. Added media hash checks against the acquisition manifest and prior decode
   audit.
4. Added queue-to-source-measurement and full queue-to-record identity checks.
5. Added ASR review-ID, sample-count, observation-count, and local execution
   validation.
6. Added manifest aggregate/output/model/fallback identity drift checks.
7. Added explicit `counterfactual_validation`; `likely_necessary` now fails
   closed unless a passing intervention explicitly validates the modality.
8. Corrected ASR token-count wording: these are generated non-special
   tokenizer tokens, not words.
9. Added tests for model bypass metadata, necessity without counterfactual,
   malformed `SHA256SUMS`, record/interval drift, decode drift, public
   transcript leakage, and persistent media derivatives.

## Validation

Completed after the repairs:

```text
python tools/noaa_machine_adjudication.py --validate-existing --repo-root .
VALID; 18 records; decision GO_PROVISIONAL_EPISODE_CONSTRUCTION

pytest -q tests/test_noaa_machine_adjudication.py
22 passed

pytest tests/ -ra
343 passed, 11 subtests passed
```

A repaired deterministic real-model regeneration also completed before final
validation. No further model inference was run after the user's stop request.

## Residual scientific limitations

- Whisper Tiny's confidence proxy is not WER, semantic correctness, or human
  transcription validation.
- AST scores are clip-level, thresholded model outputs; they do not localize an
  event or prove that it is causally needed by a question.
- Visual descriptions/seeds include bounded Codex inspection and are not
  human-reviewed gold.
- Local `SHA256SUMS` prove internal snapshot consistency, but this audit did
  not independently re-fetch or cryptographically attest the remote revision.
- The six accepted items are candidate evidence units, not yet complete
  CLEAN/BLOCKED/RESTORED episodes.
- No sample currently has validated minimal modality necessity. Episode
  construction must execute and persist modality-drop answerability
  counterfactuals before promoting any `likely_necessary` label.

## Gate

**`GO_PROVISIONAL_EPISODE_CONSTRUCTION`**

Proceed with the six repaired windows to provisional episode construction and
protocol testing. Keep all outputs machine-adjudicated and restricted, and do
not restore modality-minimality claims without explicit counterfactual
evidence.
