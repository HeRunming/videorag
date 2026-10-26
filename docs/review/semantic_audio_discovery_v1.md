# Task193 — Semantic-audio discovery v1 scientific audit

**Date:** 2026-10-10  
**Decision:** `SEMANTIC_AUDIO_DISCOVERY_READY`  
**Classification:** `MACHINE_EXPERT_PROVISIONAL_DEVELOPMENT_ONLY`

## Executive finding

Task193 completed an isolated, source-time CLAP search across the complete
timelines of:

- EPIC `P27_101` and `P28_103`;
- CaptainCook4D `16_20`, `15_29`, and `26_22`.

The search used the exact frozen local model:

```text
laion/clap-htsat-unfused@
8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a
```

It embedded **1,932** overlapping 8-second windows at 4-second stride over
**7,733.30 seconds** of source time. The prospectively frozen vocabulary has
**43 concepts**: 28 concrete target sounds, 7 generic controls, and 8
distractors.

The scientific audit retains **10 machine-expert provisional audio-bearing
leads**:

| Profile | Exact count |
|---|---:|
| A | 2 |
| V+A | 8 |
| S+A | 0 |
| V+S+A | 0 |
| Total retained audio-bearing leads | 10 |

The two A leads are:

1. `15_29`, 832-876 s: three distinct blender/food-processor motor bursts;
2. `16_20`, 676-748 s: three distinct clusters of tonal appliance-like alerts.

Eight V+A leads cover wrapper opening, peeling/scraping, chopping, water onset,
stirring/whisking, microwave completion timing, and utensil rinsing.

`READY` means the learned discovery, direct machine review, recurrence audit,
and provisional lead accounting are complete and reproducible. It does **not**
mean human semantic acceptance, H-tier assignment, modality necessity,
minimality, Gate-A eligibility, or scientific pilot execution.

## Inputs and semantic firewall

### Read and honored

- Tasks 103-105: Wave-R CLAP implementation, red-team, and final audit;
- Task153: semantic A/V source-prescreen boundaries;
- Tasks164 and 189: exact complete timeline and source bindings;
- Tasks167 and 191: prior development-only authoring boundaries and known
  audio false-positive risks;
- Task192: current pilot-v3 matrix and its ambient-audio shortfall;
- exact local source MP4s and canonical full-timeline manifests/indexes.

### Not used for retrieval

The discovery build did not read:

- EPIC action, narration, or EPIC-SOUNDS semantic annotations;
- CaptainCook4D action, step, recipe, procedure, or error annotations;
- prior Q/A text, answers, candidate labels, family IDs, or evidence labels.

The retrieval allowlist is serialized in `source_bindings.json`. Direct prior
candidate records were consulted only after the independent retrieval and
bounded review had produced provisional facts, for matrix comparison and
cross-modal-substitute auditing.

## Frozen vocabulary and retrieval method

`vocabulary.json` was materially written before CLAP model load and before
source waveform decoding. It includes concrete kitchen/procedure sounds such
as:

- running water and dish washing;
- chopping;
- peeling/scraping and grating;
- wrapper tearing and plastic rustling;
- container, jar, bottle, and can opening;
- liquid and dry-food pouring;
- sizzling/frying;
- stirring and whisking;
- utensil, dish, pot, and lid impacts;
- appliance beeps, microwave operation, and blender operation;
- cupboard, freezer, and drawer movement;
- footsteps, spraying, egg cracking, and knife sharpening.

Generic controls include speech, music, room tone, silence, generic kitchen
activity, handling noise, and steady hum. Distractors include dogs, birds,
traffic, rain, wind, keyboards, applause, and power tools.

Each concept used three text prompts. Prompt embeddings were normalized,
mean-pooled, and normalized again. Every source window was decoded from the
original MP4 to mono 48 kHz float32, padded only at terminal boundaries, and
embedded with CLAP. Float16 vectors are persisted; scoring is replayed in
float32 cosine space. Every result includes:

- source-scoped rank;
- within-source descriptive z-score;
- target similarity;
- margin over the maximum generic-control similarity;
- waveform and spectral statistics.

No semantic threshold was fitted from source annotations.

## Coverage and direct review

| Source | Duration (s) | 8 s windows |
|---|---:|---:|
| P27_101 | 1,360.20 | 340 |
| P28_103 | 1,825.16 | 456 |
| 16_20 | 1,930.90 | 482 |
| 15_29 | 1,292.82 | 323 |
| 26_22 | 1,324.22 | 331 |
| **Total** | **7,733.30** | **1,932** |

Twenty-four top or diagnostic intervals were directly decoded for bounded
machine review. Review used:

- waveform envelopes and event peaks;
- spectral centroid, flux, band fractions, and spectrogram summaries;
- transient and silence statistics;
- bounded source frames decoded in memory.

Temporary waveform, spectrogram, and contact-sheet material was removed.
Repository outputs contain no WAV, audio clip, frame, spectrogram image, or
other media derivative.

## Retained provisional audio facts

### A leads

#### 1. `15_29` 832-876 s — three blender bursts

CLAP's `blender_processor` ranks 1-8 are concentrated in one 828-880 s
cluster, with top margins over generic controls of 0.353-0.519. The waveform
and spectrogram contain three separated sustained motor blocks. Bounded frames
show operation of a countertop blender before the participant returns to the
pan.

**Answer-bearing audio fact:** the appliance runs in **three separate
bursts**. Sparse frames identify the appliance but do not reliably carry the
complete pulse count. No substantive quality-passing speech overlaps.

**Profile:** `A`, provisional.

#### 2. `16_20` 676-748 s — three tonal alert clusters

The top seven `appliance_beep` ranks form three separated clusters:
676-692 s, 708-720 s, and 736-748 s. Spectrogram inspection shows repeated,
stable horizontal tonal stacks rather than broadband utensil impacts.
Bounded frames show continuing food preparation but do not expose a clear
emitting appliance.

**Answer-bearing audio fact:** there are **three distinct alert-tone
clusters** in the bounded span.

**Profile:** `A`, provisional. Human listening must confirm that these are
environmental appliance alerts rather than an unseen source or recording
artifact.

### V+A leads

1. **P27_101 1288-1301 s — wrapper opening.**  
   Wrapper tearing ranks 1-3 and plastic rustling ranks 1-3 in the same
   cluster. An irregular broadband crinkle/tear pattern accompanies
   two-handed package manipulation after freezer retrieval. Audio
   distinguishes active opening from mere carrying, but vision also shows the
   manipulation.

2. **P28_103 196-224 s — potato peeling/scraping.**  
   High-frequency repeated scraping supports an abrasive preparation action.
   CLAP also calls it grating, so bounded vision is required to identify the
   potato and handheld peeler.

3. **P28_103 1116-1132 s — chopping.**  
   Chopping ranks 1-3; a regular impulse train coincides with repeated knife
   motion on the blue board.

4. **P28_103 258-271 s — running-water onset.**  
   The waveform transitions into sustained broadband faucet noise as frames
   move from board preparation to sink work. Water is highly recurrent.

5. **16_20 508-524 s — chopping tomatoes.**  
   Chopping ranks 2-3 with a clear separated impulse train and matching knife
   motion.

6. **16_20 584-604 s — vigorous stirring/whisking.**  
   Stirring ranks 1-4, whisking ranks 1-4, and utensil impacts rank 1-3 in one
   concentrated cluster. Audio supplies vigor, rhythm, and continuity; vision
   identifies the bowl action.

7. **26_22 916-925 s — microwave completion transition.**  
   Microwave operation ranks 1 and 3. A steady hum ends before a sharp
   door/handling transient; frames show microwave opening and mug retrieval.
   Vision fully substitutes for the main action, while audio adds completion
   timing.

8. **26_22 456-464 s — red-utensil rinse.**  
   Running water ranks 1-2, dish washing ranks 2-3, and liquid pouring ranks
   1-2. Audio establishes active water flow; vision identifies the small red
   utensil.

## Rejected or repaired semantic interpretations

Direct review rejected six important retrieval interpretations:

1. **P27_101 384-420 s, "sizzling/frying": rejected.**  
   Frames show washing/rinsing dishes at the sink. This is a strong
   broadband-water substitute for frying.

2. **P28_103 1408-1448 s, "sizzling/frying": rejected.**  
   The rain-like/frying texture is strong, but frames do not support active
   frying. This confirms the Task167 false-positive warning.

3. **15_29 656-676 s, "running water": rejected.**  
   Frames remain on pan and recipe interaction, not faucet use.

4. **15_29 684-712 s, "microwave operation": rejected.**  
   Frames show pan/recipe work; beep scores are below the generic-control
   maximum.

5. **26_22 1216-1240 s, "wrapper tearing": not answer-bearing.**  
   Package handling is visible, but the acoustic texture is not distinctive
   enough to establish a nonduplicated wrapper-opening fact.

6. **16_20 1088-1108 s, "chopping": no new audio lead.**  
   Frames show mixed onion stirring/handling, and the existing visual
   onion-pan formulation is cleaner.

These failures are scientifically important: high CLAP similarity alone is
not treated as a semantic fact.

## Recurrence and substitutes

- **Water is recurrent** in every kitchen source. It is suitable for temporal
  localization and transition facts but generally not for A-only object
  questions.
- **Chopping and stirring recur** within sources. Questions must bind the
  local food, vessel, state, or immediate sequence.
- **Wrapper opening** is strongest at P27 1284-1324 s but has weaker same-source
  alternatives; the question must bind it to the freezer-retrieved item.
- **Microwave-like and beep-like sounds recur**, especially in `26_22`.
  Appliance identity and local sequence need bounded visual correlation.
- **Broadband water/rain-like spectra substitute for sizzling**, producing
  confident but semantically wrong retrievals.
- Canonical speech provides no substantive overlapping answer route for any
  retained fact. Across these five sources, the only quality-passing chunks are
  non-substantive "Mm-hmm." utterances at P28 630-660 s and `15_29` 180-210 s.

## Exact pilot-matrix repair

Task192 currently records:

```text
V=10, S=2, A=0, V+S=0, V+A-or-S+A=0, V+S+A=0
```

If trained-human listening confirms the two A facts and the two preferred V+A
facts, replace four existing visual slots rather than adding slots:

- **A (2):**
  - `15_29` blender three-burst count;
  - `16_20` three alert-tone clusters.
- **V+A (2):**
  - `P27_101` freezer-item wrapper opening;
  - `P28_103` potato peeling with repeated scraping.

The resulting prospective profile accounting would be:

```text
V=6, S=2, A=2, V+S=0, V+A-or-S+A=2, V+S+A=0
```

This repairs the A and V+A-or-S+A rows only. It does **not** repair:

- `V+S` shortfall: 2;
- `V+S+A` shortfall: 2;
- hop or temporal balance;
- human Task153, recurrence closure, accepted SES, or Gate-A requirements.

Fresh normal-mode records are required. Existing Task192 records must not be
relabelled in place.

## Artifact and reproducibility audit

Primary restricted artifacts:

```text
data/restricted/semantic_audio_discovery_v1/vocabulary.json
data/restricted/semantic_audio_discovery_v1/source_bindings.json
data/restricted/semantic_audio_discovery_v1/window_index.json
data/restricted/semantic_audio_discovery_v1/clap_embeddings.npz
data/restricted/semantic_audio_discovery_v1/rankings.json
data/restricted/semantic_audio_discovery_v1/machine_review_packets.json
data/restricted/semantic_audio_discovery_v1/provisional_audio_facts.json
data/restricted/semantic_audio_discovery_v1/build_manifest.json
```

The implementation is isolated in:

```text
scripts/build_semantic_audio_discovery_v1.py
scripts/review_semantic_audio_discovery_v1.py
scripts/finalize_semantic_audio_discovery_v1.py
```

Validation completed:

- exact CLAP repo/revision and all nine allowlisted model files checked;
- all five exact source hashes recomputed;
- 1,932 finite normalized 512-dimensional audio vectors built;
- 43 text vectors built from the frozen vocabulary;
- 24 review intervals decoded from original MP4s;
- all persisted outputs set to mode 0600 and directory to 0700;
- temporary Task193 extraction/review files removed;
- no persisted media derivatives found;
- JSON self-hashes and cross-artifact bindings written;
- all three Task193 scripts pass `py_compile`.

## Limitations and scientific boundary

- CLAP retrieval is a discovery instrument, not semantic ground truth.
- No human listened to or accepted these events.
- Machine waveform/spectrogram inspection can support event structure but
  cannot replace trained-human semantic listening.
- No H tiers, modality necessity, minimality, accepted SES, Gate-A status, or
  scientific intervention claim is made.
- All retained facts and matrix repairs remain development-only and
  future-test-ineligible.
- Public release and redistribution are not authorized.

## Final decision

`SEMANTIC_AUDIO_DISCOVERY_READY`

The discovery and audit are complete enough to hand the two A and eight V+A
leads to trained-human review. `REPAIR` is not selected because the requested
learned search, direct review, recurrence/substitute audit, exact lead
accounting, and pilot repair recommendation were completed. `NO_GO` is not
selected because two plausible A-only and eight plausible V+A leads survived
the machine-expert audit.

