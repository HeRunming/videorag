# Independent red-team of NOAA-01 content reconnaissance

**Review date:** 2026-09-10  
**Task 80 decision reviewed:** `CONDITIONAL_GO`  
**Task 81 decision:** **`GO_HUMAN_WINDOW_REVIEW`**

## Executive finding

Task 80 is operationally useful as a **restricted candidate-window routing
pass**, but several original names were scientifically stronger than the
measurements support. No ASR or audio-event recognizer was available. The
handcrafted acoustic scores therefore cannot establish intelligible speech,
speech presence, ambient sound, or a specific non-speech event. Likewise,
`V+A` and `V+S+A` are not modality-necessity findings.

I made narrow corrections to Task 80 code, tests, restricted outputs, and public
reports:

1. renamed speech statuses to `strong_speech_proxy`,
   `speech_proxy_candidate`, and `below_speech_proxy_threshold`;
2. renamed `credible_candidate` to `non_speech_priority_candidate`;
3. described `V`, `S`, `A`, and combinations explicitly as **review-routing
   hypotheses only**;
4. described shortlist family counts as selection-biased, not prevalence;
5. fixed audio extraction to align samples to the requested timeline, flush the
   resampler, zero-fill uncovered timeline positions, and record coverage;
6. changed misleading `*_normalized` amplitude names to `*_full_scale`;
7. excluded silent spectral frames from autocorrelation/spectral aggregation;
8. made capability reporting explicit that ASR is not executed even if model files happen to exist;
9. removed stale hard-coded test totals from the generated Task 80 result.

After the fix, the scan was rerun. The operational counts still are **120
measurements** (90 coarse, 30 adaptive) and **30 shortlisted windows** (six per
asset). The shortlist remains suitable for a bounded human review, provided
reviewers treat every label as provisional and adjudicate actual content.

## What survives, and what does not

### Counts that survive scrutiny

- Authorized assets scanned: **5/5**.
- Measurements: **120** = **90 coarse + 30 adaptive**.
- Candidate shortlist: **30**, exactly **6 per asset**.
- Speech-proxy routing coverage: **5/5 assets**.
- Visual-change routing coverage: **5/5 assets**.
- Non-speech-priority routing coverage at the baseline thresholds: **5/5
  assets**.
- Selected shortlist routing counts: `V+S` **25**, `V+A` **12**, and `V+S+A`
  **12**.
- First pilot ranking: **cand-049, cand-051, cand-052**.
- Ambient/non-speech remains a **smaller diagnostic slice**, not a headline
  benchmark dimension.

### Counts or claims that must be downgraded or renamed

- “Speech-bearing” becomes **speech-proxy routing candidate**.
- “Intelligible speech candidates in all five” remains **not machine verified**;
  no count of intelligible assets survives without listening.
- “Credible non-speech audio” becomes **non-speech-priority routing candidate**.
  The baseline 5/5 count is threshold-dependent and fell to **3/5** in part of
  the reasonable sensitivity grid.
- “Plausible episode opportunities” becomes **selected review-routing
  hypotheses**. The values 25/12/12 are counts inside a deliberately enriched
  30-window shortlist, not prevalence estimates and not evidence counts.
- “Temporally separated evidence” becomes **temporally separated routing
  signals**. No evidence relevance was established.
- `V+A` and `V+S+A` do not mean both modalities are necessary, jointly
  informative, or even semantically relevant.

## Methodology audit

### Audio units, windowing, and silence

PyAV decodes/resamples the first audio stream to mono 16 kHz floating
full-scale samples. These amplitudes are not normalized per window; peaks may
slightly exceed 1.0, so the prior field name `peak_absolute_normalized` was
misleading. It is now `peak_absolute_full_scale`, with the analogous RMS rename.

The original implementation concatenated whole resampled frames after seeking
and truncated the result to 128,000 samples. That admitted a small amount of
pre-window audio and, where the source contained timestamp gaps, silently
returned fewer than eight seconds. The corrected implementation places samples
using resampled timestamps, flushes the resampler, zero-fills uncovered
positions, and records both decoded and covered sample counts. All output arrays
now contain exactly 128,000 positions. Coverage is complete in **96/120**
windows; the minimum observed timeline coverage is **0.9085625**. This should be
understood as source/timestamp coverage, not decoder failure.

Silence is measured in non-overlapping 20 ms frames using full-scale RMS below
0.003. The active gate is an OR over RMS >= 0.008, peak >= 0.04, or active-frame
ratio >= 0.35. Every measured window passes that permissive gate; consequently,
it does not discriminate within this corpus. Even when all three activity
thresholds are raised by 50%, the measured statuses and selected shortlist are
unchanged.

Spectral centroid and flatness use a 512-sample Hann window and 256-sample hop.
The periodicity features use normalized autocorrelation over lags corresponding
to 70–400 Hz. The implementation now skips frames below the silence threshold
and subtracts the frame mean before spectral/autocorrelation calculations.
Even so, this is a crude periodicity proxy, not a speech classifier: after the
fix, 117/120 measured windows cross the baseline speech-proxy threshold.

### Video frame selection and visual calculations

The video pass seeks backward to a keyframe and targets nine inclusive times
from window start through start + 8 seconds. It selects the first decoded frame
at or later than target minus 50 ms. Across the stored run, **119 windows have
nine frames and one near-end window has eight**. Target timing error ranges from
-0.050 to +0.504 seconds; the median error is about -0.031 seconds. Consecutive
intervals have median spacing about 1.001 seconds, but range from 0.467 to 1.514
seconds because frame timestamps are irregular.

Frames are converted to grayscale, aspect-preservingly downscaled to at most
192 pixels on the long side, and compared using mean absolute pixel difference
scaled by 1/255. Entropy is Shannon entropy over the 256-bin grayscale
histogram; edge density is the fraction of pixels marked by Canny(100, 200);
brightness is mean gray value divided by 255. A “scene cut” is a sampled-pair
difference >= 0.12. Since only eight adjacent pairs are observed, this is a
coarse visual-change indicator and must not be interpreted as semantic visual
evidence.

### Coarse and adaptive coverage

The coarse grid has 18 deterministic inclusive start positions from 0 to
`duration - 8`, giving beginning and near-end coverage but sparse temporal
coverage in long assets.

All **30 adaptive intervals are genuinely additional**: none overlaps any
coarse 8-second interval for the same asset. They are not exact duplicate
windows. However, adaptive allocation is concentrated: **27/30** were selected
as neighbors of a high non-speech-proxy or scene-cut signal and only **3/30** as
transition midpoints. There are **9 symmetric flank pairs** around the same
coarse region. This is acceptable for boundary/context review, but it is local
redundancy and should not be mistaken for 30 independent phenomena.

### Candidate selection balance and bias

The selector guarantees up to six windows per asset and first attempts one
speech-proxy, one non-speech-priority, and one visual-change candidate per
asset when available. It then fills by a weighted score with an adaptive bonus.
The resulting shortlist is balanced by asset (**6 each**) and contains no
unsupported forced category: a category is selected only if a window actually
crosses its threshold. But the shortlist is deliberately category-enriched and
adaptive-heavy (**22 adaptive, 8 coarse**).

Therefore the selected counts cannot estimate corpus frequency. At baseline,
all 30 selected windows carry `S`, whereas 117/120 measured windows cross the
speech-proxy threshold; 14 selected windows carry `A`, versus 18/120 measured
windows at baseline; and 25 selected windows carry `V`, versus 49/120 measured
windows. Reporting only the selected 30 exaggerates the apparent concentration
of multimodal routing signals.

## Scientific-claim audit

### Speech and intelligibility

The speech score is a weighted combination of periodicity, autocorrelation
strength, proximity to a fixed zero-crossing rate, low spectral flatness, and
activity ratio. Those features can prioritize voiced or harmonic audio, but
cannot establish language, lexical content, or intelligibility. Music, tones,
noise mixtures, and recording characteristics can cross the same thresholds.
The red-team therefore accepts **5/5 assets with speech-proxy candidates**, but
rejects any machine claim that all five contain intelligible speech.

### Non-speech audio and ambient sound

The non-speech score is not an audio-event classifier. It is also coupled to the
speech-strong threshold because a window is eligible only when its speech score
is below that threshold. Raising the speech-strong threshold from 0.68 to 0.73
increases non-speech-priority windows from 18 to 31; lowering it to 0.63 reduces
them to 11 and reduces asset coverage to 3/5. That behavior confirms the label
must be “non-speech-priority candidate,” not “credible non-speech audio.”

Ambient sound must remain a diagnostic slice. Human reviewers should identify
whether a routed window actually contains environmental sound, music, effects,
silence/gaps, or speech mixtures before it is used for any benchmark dimension.

### Routing-family labels and selected counts

`V+S`, `V+A`, and `V+S+A` mean only that the corresponding proxy thresholds
co-occurred in a sampled window. They do not establish modality necessity or
minimality. The baseline selected counts are **25, 12, and 12**, respectively,
but across the 243-scenario threshold grid their ranges are:

- `V+S`: **23–25**;
- `V+A`: **8–21**;
- `V+S+A`: **6–21**.

These variations, plus the quota/enrichment policy, make them useful workload
routing statistics only.

## Threshold sensitivity and pilot robustness

The restricted sensitivity artifact recomputes classifications and candidate
selection from the existing measurements only; it decodes no additional media.
It includes one-at-a-time checks plus a **243-scenario factorial grid** over
speech candidate thresholds 0.50/0.55/0.60, speech-strong thresholds
0.63/0.68/0.73, non-speech-priority thresholds 0.53/0.58/0.63, and 0.8/1.0/1.2
multipliers on activity and visual scales.

Across all 243 scenarios:

- speech-proxy asset coverage remains **5/5**;
- visual-change asset coverage remains **5/5**;
- non-speech-priority asset coverage ranges **3/5–5/5**;
- overlap with the baseline 30-window shortlist ranges **22–30 windows**;
- the ordered first pilot remains **cand-049, cand-051, cand-052 in 243/243
  scenarios**.

The pilot recommendation is therefore robust to the tested perturbations. The
non-speech/ambient headline is not.

## Determinism

- Random sampling is absent.
- A pure replay of all stored inferences, adaptive starts, and candidate
  selection matched exactly.
- Independent re-decoding of beginning, middle, and near-end windows for all
  five assets (15 windows total) was byte-for-byte equal at the normalized
  measurement/inference level before the implementation correction.
- The corrected full 120-window scan was rerun twice; output measurements and
  candidates were byte-identical across those two runs (the manifest is
  expected to change only if referenced output hashes or code-produced content
  changes).

## Validation

- Focused Task 80 tests: **11 passed**.
- Default `tests/` suite: **321 passed**.
- Candidate, manifest, and sensitivity JSON artifacts parse successfully.
- The deterministic full rerun produced the same measurement, candidate,
  public-review, and Task 80 result hashes on the immediately repeated run.

## Safety and provenance

- The authorization remains active only for the exact five restricted assets
  and prohibits public transcripts, persistent media derivatives, gold labels,
  and modality-necessity claims.
- Restricted metadata files are mode 0600. Public Task 80 and Task 81 reports
  contain no timestamps, source-media hashes, frame data, audio data,
  transcripts, URL tokens, or signed URLs.
- No extracted frame, clip, waveform, contact sheet, or transcript exists in
  the reconnaissance output directory.
- Frozen authoritative input hashes remain exact:
  - plan: `241a476b503a198eafe208485206385f755cd57756f924e769ce8a37d1d1f6fd`;
  - acquisition manifest: `92b7a1ff740d79a4253071018dc18cc3cb41570ccc62dfb08ff2a9c1c48fe2a1`;
  - media audit: `b8c743f48ad328cda46be2ea2569759da95262b404e3f3647eef2d9c2e2efde9`;
  - authorization: `ab0d524d192eb1aea46c53d38fed01660b4d7cf4231ac712402057b945dddde9`.
- All five source-media sizes and SHA-256 values still match the acquisition
  manifest. Source files were not modified.

## Decision

**`GO_HUMAN_WINDOW_REVIEW`**

Proceed with a small human review of the 30 restricted windows, starting with
cand-049, cand-051, and cand-052. Reviewers must verify actual speech and
intelligibility, identify any non-speech event, assess visual semantic content,
and test modality necessity. Do not use the shortlist counts as prevalence or
as evidence that an ambient-audio benchmark dimension is ready.
