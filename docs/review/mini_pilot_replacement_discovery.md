# Mini-pilot replacement discovery

**Date:** 2026-09-22  
**Decision:** `REPLACEMENT_CANDIDATE_POOL_READY_FOR_DOSSIER_PREFLIGHT`  
**Readiness:** metadata candidate pool only; **not acquisition-ready**  
**Evidence mode:** offline finalization from official-source facts supplied in
Task 127; no network, media download, or new route probe

## 1. Result and fail-closed boundary

Task 127 identifies **11 distinct underlying lecture assets** across **11
subject domains** and three official institutional collections:

1. Oxford Podcasts;
2. MIT OpenCourseWare; and
3. Open Yale Courses.

Each underlying lecture is treated as its own candidate source group. Video,
audio, transcript, caption, mirror, excerpt, and alternate-encoding variants
of that lecture do not create additional source groups.

The pool is ready only for Task 128 dossier work. **No candidate is GO for
acquisition, bounded acquisition, processing, or human annotation.** Task 127
did not freeze an exact media object, bind an item license to an exact
rendition, inspect Credits/component exclusions, or perform technical,
privacy, music, and lineage checks.

The concentration caveat is material: the pool has many potential source
groups but only **three producer collections**. If the frozen requirement is
interpreted as four independent producers/collections rather than four
distinct source groups, the decision is **`REPAIR`** and a fourth collection
must be found. If four source groups are sufficient, the discovery threshold
is met at the metadata-candidate level, but eligibility remains zero.

## 2. Ranked pool

| Rank | Candidate source group | Collection | Domain | Supplied duration | Role | Current state |
|---:|---|---|---|---|---|---|
| 1 | Oxford Quantum Mechanics lecture 001 | Oxford Podcasts | quantum physics | 00:44:05 | primary dossier order | Task 128 required; not eligible |
| 2 | Oxford Critical Reasoning: *Fallacies* | Oxford Podcasts | critical reasoning | 01:32:48 | primary dossier order | Task 128 required; not eligible |
| 3 | MIT RES.12-003 Lecture 1: Fluid Dynamics | MIT OCW | fluid dynamics / sediment transport | not provided | primary dossier order | Task 128 required; not eligible |
| 4 | Yale PHYS-200 Lecture 1 | Open Yale Courses | classical mechanics | about 75 minutes, course-level | primary dossier order | Task 128 required; not eligible |
| 5 | MIT 2.003J Dynamics and Control I Lecture 1 | MIT OCW | engineering dynamics/control | not provided | named reserve | Task 128 required; not eligible |
| 6 | Yale HIST-202 Lecture 1 | Open Yale Courses | European history | about 50 minutes, course-level | named reserve | Task 128 required; not eligible |
| 7 | Oxford *D.H. Lawrence 1: Consciousness* | Oxford Podcasts | literary studies | 00:48:28 | additional candidate | Task 128 required; not eligible |
| 8 | MIT STS.042 Lecture 1 | MIT OCW | history of physics / science studies | not provided | additional candidate | Task 128 required; not eligible |
| 9 | MIT 9.13 *The Human Brain* Lecture 1 | MIT OCW | neuroscience | not provided | additional candidate | Task 128 required; not eligible |
| 10 | Yale PHIL-181 Lecture 1 | Open Yale Courses | philosophy / human nature | not provided | additional candidate | Task 128 required; not eligible |
| 11 | Yale PSYC-110 Lecture 1 | Open Yale Courses | introductory psychology | not provided | additional candidate | Task 128 required; not eligible |

The top four follow the requested optimization: usable or plausibly usable
runtime, high likelihood of an official download route, low expected
privacy/music burden, and complementary visual/speech potential. Those are
selection hypotheses, not verified content findings.

One duration issue is already visible. Oxford *Fallacies* is **01:32:48
(5,568 seconds)**, which is 168 seconds above the earlier 5,400-second
source-duration ceiling. Task 128 must resolve that conflict explicitly; the
candidate cannot become eligible through an undocumented relaxation.

No exact duration is assigned where Task 127 did not provide one. The Yale
75-minute and 50-minute descriptions remain course-level approximations, not
exact Lecture 1 measurements. The reported MIT STS.042 range of 85–154 MB is
not allocated to a particular lecture file.

## 3. Official-source observations

### Oxford Podcasts

Task 127 records that official episode pages expose **Download Video,
Download Audio, and Download Transcript**, and that the named episodes carry
episode-level **CC BY-NC-SA 2.0 UK** terms.

Dated official URLs recorded on 2026-09-22:

- `https://podcasts.ox.ac.uk/`
- `https://podcasts.ox.ac.uk/001-introduction-quantum-mechanics-probability-amplitudes-and-quantum-states`

The exact episode landing URLs for *Fallacies* and *D.H. Lawrence 1:
Consciousness* are intentionally not guessed. Task 128 must locate and archive
them, then bind each license statement to the exact video, audio, and
transcript objects and inspect all slides, figures, marks, music, and other
components.

### MIT OpenCourseWare

Task 127 records official course pages, **Download Course**, MIT OCW Creative
Commons terms, and the fact that third-party exclusions apply. It also records
RES.12-003 lecture videos; STS.042 lecture 1 and other 85–154 MB lecture
files; 2.003J Dynamics and Control I video lectures; and 9.13 *The Human
Brain* lecture videos.

Dated official URLs recorded on 2026-09-22:

- `https://ocw.mit.edu/courses/res-12-003-fluid-motions-sediment-transport-and-current-generated-sedimentary-structures-fall-2006/`
- `https://ocw.mit.edu/courses/sts-042-einstein-oppenheimer-feynman-physics-in-the-20th-century-fall-2020/`
- `https://ocw.mit.edu/courses/2-003sc-engineering-dynamics-fall-2011/resources/lecture-videos/`
- `https://ocw.mit.edu/courses/9-13-the-human-brain-spring-2019/`
- `https://ocw.mit.edu/pages/privacy-and-terms-of-use/`

A course download control is not proof of a particular lecture-media object.
Task 128 must identify the exact first-party lecture route and separately
classify every excluded slide, photograph, figure, film/news clip, reading,
software screen, mark, and other component.

### Open Yale Courses

Task 127 records that official pages say lectures can be downloaded as video,
audio, and transcript without registration. Most Yale-owned content is
described as **CC BY-NC-SA 3.0**, while third-party material identified
through Credits is excluded.

Dated official URLs recorded on 2026-09-22:

- `https://oyc.yale.edu/physics/phys-200/lecture-1`
- `https://oyc.yale.edu/history/hist-202/lecture-1`
- `https://oyc.yale.edu/philosophy/phil-181/lecture-1`
- `https://oyc.yale.edu/psychology/psyc-110/lecture-1`
- `https://oyc.yale.edu/terms`

Task 128 must archive the exact lecture and Credits pages, establish which
components are Yale-owned, and bind the license to the exact downloadable
objects. Classroom audience, demonstrations, images, marks, and likenesses
remain review items.

## 4. Task 128 dossier gate

Every candidate must independently pass all of the following before any
acquisition:

1. archive the exact official episode/lecture/course, license, terms, and
   Credits pages with date, byte count, and SHA-256;
2. establish the earliest underlying lecture asset and collapse alternate
   encodings, audio, transcripts, captions, mirrors, excerpts, and derivatives
   into one source group;
3. extract and allowlist only exact official first-party media/transcript
   routes—never an inferred URL or third-party mirror;
4. freeze redirects, final host, size, MIME, ETag or immutable identity,
   Last-Modified where available, and byte-range behavior;
5. verify exact duration, complete synchronized A/V, codecs, time base, and
   object identity under a separately authorized bounded technical check;
6. bind item-level license terms to the exact rendition and affirm processing
   and human-annotation authority;
7. inspect slides, figures, photographs, readings, software screens,
   film/news excerpts, marks, music, audience content, and every other
   third-party component or Credits exclusion;
8. inspect minors, personal information, sensitive examples, audience privacy,
   and safety concerns;
9. check mirrors, duplicates, lineage, and all development-source
   fingerprints; and
10. issue an explicit per-source GO/REPAIR/NO_GO dossier decision.

General availability, a course download, a Creative Commons collection
policy, a transcript, or an institutional host is not enough. Exact
item/component clearance and exact technical identity are mandatory.

## 5. Decision

**`REPLACEMENT_CANDIDATE_POOL_READY_FOR_DOSSIER_PREFLIGHT`**

This means that Task 128 has a ranked pool to investigate. It does **not**
mean that any asset may be downloaded. Current acquisition eligibility is
**0/11**.

Primary Task 128 order:

1. Oxford Quantum Mechanics lecture 001;
2. Oxford Critical Reasoning *Fallacies*;
3. MIT RES.12-003 Lecture 1: Fluid Dynamics; and
4. Yale PHYS-200 Lecture 1.

Named reserves:

1. MIT 2.003J Dynamics and Control I Lecture 1; and
2. Yale HIST-202 Lecture 1.

If four independent producers/collections are frozen rather than four source
groups, stop with **`REPAIR`** despite this ranking and discover a fourth
producer/collection before claiming pool sufficiency.
