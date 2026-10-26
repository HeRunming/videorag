# NOAA-01 restricted audiovisual content reconnaissance

**Reconnaissance date:** 2026-09-09  
**Decision:** **CONDITIONAL_GO**

## Executive finding

The exact five authorized NOAA-01 assets passed the fail-closed input gate and
were sampled with a frozen deterministic policy. The run produced
**120** bounded in-memory measurements
(90 coarse and 30 adaptive) and
selected **30** restricted candidate windows. No extracted frame,
audio, clip, contact sheet, waveform, or transcript was persisted.

The reconnaissance found provisional speech-proxy routing candidates in
**5/5** assets, non-speech-priority
routing candidates in
**5/5**, and meaningful
visual-change routing candidates in
**5/5**. Candidate-table
counts include **25** `V+S`,
**12** `V+A`, and
**12** `V+S+A` routing hypotheses. These selected-shortlist
counts are intentionally enriched by the selection policy and are not corpus
prevalence estimates.

## Capability and important limitation

PyAV, NumPy, SciPy, Torch, torchaudio, transformers, and OpenCV were locally
available. External `ffprobe`, `ffmpeg`, OCR tooling, and local speech-model
weights were absent. A bounded attempt to obtain the pinned
`openai/whisper-tiny.en` revision could not resolve the approved proxy, and no
model artifact was retained. The completed scan used deterministic acoustic
proxies; this implementation did not execute ASR and generated no transcript or
textual ASR snippet.

Consequently, the handcrafted score supports only review routing. It does not
establish speech presence or intelligibility. The overlapping non-speech score
does not identify an audio event. Human listening is required before annotation
or benchmark construction.

## Frozen sampling and measurements

- Window length: **8 seconds**
- Coarse grid: **18 windows per asset**, inclusive of
  beginning and near-end coverage
- Adaptive expansion: at most **6 windows per
  asset** around the highest coarse transitions and neighboring active-audio or
  visual-change signals
- Audio: mono 16 kHz in memory, aligned to the requested window with coverage
  recorded; floating full-scale RMS/peak (not per-window normalized), 20 ms
  silence ratio, zero-crossing rate, spectral centroid/flatness, and
  autocorrelation-based voiced/harmonicity proxies computed on active frames
- Video: at most **9** in-memory grayscale frames per window;
  consecutive-frame difference, scene-cut count, entropy, edge density, and
  brightness
- OCR: unavailable and not used
- Randomness: none

Observed measurements are stored separately from inferred candidate statuses.
Thresholds and the full policy are recorded in the restricted manifest.

## Feasibility answers

- All five assets contain intelligible speech:
  **not machine-verified**. Speech-proxy candidates occur in
  **5/5**, but intelligibility
  requires human listening because no ASR model was available.
- Assets with non-speech-priority routing candidates:
  **5/5**
- Assets with meaningful visual-change routing candidates:
  **5/5**
- Selected `V+S` routing hypotheses: **25**
- Selected `V+A` routing hypotheses: **12**
- Selected `V+S+A` routing hypotheses: **12**
- Assets with routing signals separated by at least two minutes:
  **5/5**
- Ambient/non-speech recommendation:
  **smaller_diagnostic_slice**
- First manual pilot: `cand-049`, `cand-051`, `cand-052`

## Decision and boundary

**CONDITIONAL_GO**

This is a candidate-reconnaissance layer only. It does not make a gold evidence
label, final benchmark annotation, transcript publication, or minimal modality
necessity claim. `V`, `S`, `A`, and their combinations are review-routing
hypotheses only: they mean that fixed proxy signals crossed provisional
thresholds, not that those modalities are present, relevant, jointly required,
or minimally necessary. Human review must verify content, speech
intelligibility, non-speech sound identity, evidence relevance, temporal
boundaries, and whether any modality is actually necessary.

Detailed timestamps, hashes, and window-level metadata remain under
`data/restricted/noaa01/recon/`.
