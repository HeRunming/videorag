# Long-video source-data audit

**Verification date:** 2026-09-05  
**Scope:** acquisition planning for an audio-visual, long-video agent benchmark.  
**Important:** this is research and engineering planning, **not legal advice**. Counsel should review the final corpus, agreements, privacy process, and release package.

## Executive decision

No requested academic benchmark is a single, blanket-cleared source of redistributable raw video. Most are excellent **task/annotation precedents** but use copyrighted movies, television, or web videos whose repository license does not clear the media. The safest architecture is therefore dual-track:

1. **Rights-cleared public core:** asset-level verified NASA, NARA, NOAA, Wikimedia Commons, and directly granted media only. A source family is never blanket clearance. This core alone supports primary Pilot-0 conclusions and a public reproducibility package.
2. **External compatibility track:** LongShOTBench, VideoGAIA, TRACE/VES-Bench, TraceAV-Bench, FLARE, LVBench, Video-MME, LongVideoBench, MLVU, MAD, and similar benchmarks, using only officially released artifacts and media access authorized by each source. Release annotations, IDs, timestamps, hashes, and permitted features—not third-party video.

YouTube-derived or ID-dependent corpora (HowTo100M, ActivityNet, YouCook2, QVHighlights, LoVR/LongVideoBench-derived subsets) should be discovery or methodological references, not the sole evaluation backbone. Their legal status is asset-specific, platform access is revocable, and link attrition prevents durable reproduction.

## Method and evidence standard

The inventory uses official project sites, repositories, dataset cards, papers, licenses/agreements, and platform or agency policies. Every CSV row has a primary source URL and the verification date. Counts and duration descriptions are project-reported; where a project does not publish a reliable aggregate, the inventory says to compute it from the versioned release manifest rather than inventing a number.

A repository's software license is **not treated as a license to third-party video**. Likewise, a public URL, dataset download, or Internet Archive item is not treated as permission to redistribute. Raw-media rights are accepted only when an asset-level license, public-domain record, rightsholder permission, or signed agreement supports the intended act.

### Access classes used

| Class | Operational meaning |
|---|---|
| `downloadable_redistributable_raw` | Source-family screening suggests a possible raw-media route, but this is **not clearance**. Acquisition and release require a passing asset manifest with explicit decisions and evidence. |
| `downloadable_annotation_only` | Official annotations/features or possibly media are downloadable, but the project has no blanket right for us to redistribute source video. |
| `link_id_only` | Stable deliverable is metadata/IDs/features; source video remains on a platform or with an uploader. |
| `gated_agreement` | Registration, credentials, data-use agreement, or institutional approval controls access and onward sharing. |
| `unsuitable_too_risky` | Rights, privacy, safety, access, or reproducibility risk is unacceptable. This status should be assigned at the **asset** level during intake; none should enter production. |

## Findings by family

### Benchmark sources that directly inform the target design

- **LoVR**: a long-video text-retrieval corpus with 467 videos and 40,804 time-bounded clips, plus generated clip captions and video descriptions. It is useful for clip/video retrieval and distractor construction, not a human multi-hop QA corpus. Its Hugging Face release improves access but does not remove the need to verify source-video rights.
- **LongVidSearch**: strong multi-hop retrieval/evidence precedent. The current official release reports 3,000 QA pairs over 447 videos, about 26 minutes average, with 2/3/4-hop evidence and released captions/embeddings. Upstream media still require a per-asset provenance map.
- **FLARE**: a highly relevant full-modality retrieval benchmark built from 399 Video-MME videos (10-60 minutes; 225.4 hours), 87,697 clips, and 274,933 queries. Its visual, audio-only, and hard-bimodal cases directly match this project, but upstream Video-MME/source rights remain in force.
- **V-RAGBench**: the official release reports 2,100 query-evidence-answer triplets across 216 Ego4D/EgoLife videos spanning 1-9 hours. It has attractive day-scale retrieval/generation evidence, but the combined EgoLife SLAB/Ego4D terms and privacy burden make it unsuitable for a low-governance pilot.
- **LongShOTBench**: the current official README/dataset card reports 274 videos, about 188 hours, and 3,401 intent-driven questions with weighted rubrics. It is an excellent compatibility set and possible research-only pilot component, but the gated dataset and documented YouTube-cookie workflow require careful terms and source-rights review.
- **VideoGAIA**: 271 model-human co-designed, three-expert-verified tasks for agentic video search and multimodal browsing. The paper license and repository license do not automatically cover source videos or fetched external content.
- **TRACE / VES-Bench**: 348 public long videos and 600 audited questions with jointly necessary evidence intervals and three levels of evidence-coverage strictness. Its released video package is operationally attractive, but separately verify the project's authority to permit onward raw-media redistribution.

### Common long-video and temporal datasets

- **Best controlled academic sources:** Ego4D, EgoLife, EPIC-KITCHENS-100/EPIC-SOUNDS, Assembly101, HD-EPIC, and Ego-Exo4D offer centrally managed access, rich timestamps, and real audio. Their chief drawbacks are agreements, privacy, large size, and usually no onward raw redistribution. Note that the current Ego-Exo4D access page describes a license covering research and commercial use, but redistribution and package-specific restrictions still control.
- **Best long-duration but copyrighted sources:** MAD and MovieNet provide feature-film duration and rich language/temporal annotations. They are useful annotation precedents or internal experiments where lawful access exists, but raw movie redistribution is not viable.
- **Best existing compatibility benchmarks:** TraceAV-Bench has 578 videos, 339.5 hours and explicit multi-hop audiovisual trajectories; FLARE offers audio-only and hard-bimodal retrieval; LVBench has a manageable 103 videos and about 68-minute average duration; Video-MME has 900 videos and explicit audio/subtitle evaluation; LongVideoBench provides time-aware subtitles at larger scale; MLVU has diverse tasks and durations to two hours. Their media rights are heterogeneous.
- **Useful but too short as primary sources:** NExT-QA/NExT-GQA, QVHighlights, TVQA clips, ActivityNet, and much of YouCook2. Their taxonomies, timestamp schemas, subtitle grounding, and saliency labels remain valuable.
- **Scale-first, low-durability web corpora:** HowTo100M and YouTube-derived ActivityNet/YouCook2/QVHighlights provide speech and diversity, but ID attrition, uploader copyright, platform restrictions, noisy captions, and unsafe content make them poor foundations for reproducible evaluation.

### Rights-cleared and stable fallbacks

- **NASA official media:** top pilot source for long mission broadcasts, briefings, documentaries, speech, ambient audio, and event logs. Select only NASA-produced assets; exclude or separately clear credited third-party material, music, marks, and likeness uses.
- **US National Archives:** top full-benchmark fallback for historical films and long government recordings. Not all NARA holdings are public domain; the catalog rights/restriction record is mandatory evidence.
- **NOAA:** useful for briefings, field science, expeditions, weather, and ambient sound. Apply the same item-level government/third-party review.
- **Wikimedia Commons:** the broadest practical open-license pool. Pin the file page ID and revision, capture the exact license, author, attribution, source, and hash, and guard against license laundering.
- **Internet Archive:** accept only authoritative institutional collections or items with independently credible public-domain/open-license provenance. Archive hosting and uploader metadata alone are insufficient.

## Ranked Pilot shortlist

The pilot should optimize for rights clarity, audio presence, long duration, timestampability, and manageable intake. The table ranks discovery sources only; it does not authorize transfer.

| Rank | Source | Proposed pilot use | Why | Blocking conditions |
|---:|---|---|---|---|
| 1 | NASA official media | 15-20 long broadcasts/documentaries | Public-sector provenance, long AV, speech plus ambient mission audio, event logs, stable official pages | Asset-level third-party credit, logo/endorsement, likeness review |
| 2 | Wikimedia Commons verified files | 10-15 lectures, documentaries, performances without restrictive music, or public events | Explicit file licenses and raw redistribution path; broad domains | Revision-pinned license validation and attribution/share-alike automation |
| 3 | NARA unrestricted/public-domain records | 10-15 historical films or complete recordings | Durable catalog IDs and potential raw redistribution | Catalog restriction review; donor/music/privacy issues |
| 4 | Direct creator/institution grants | Fill public-core gaps | A written grant can cover exact acquisition, processing, annotation, transcript, derivative, and raw-release uses | Grant must cover included audio/music, identifiable people, territory, and onward release |
| 5 | EPIC-KITCHENS-100, TRACE/VES-Bench, or TraceAV-Bench | Compatibility cases only | Useful evidence and modality precedents | Raw media remains on hold unless separately cleared; results are unpooled |
| 6 | LVBench or LongShOTBench | Compatibility evaluation only, not public raw-media core | Genuinely long duration and strong task/rubric coverage | Resolve asset provenance; publish annotations/IDs only unless cleared |

**Pilot gate:** every selected item has usable original audio and is 20–90 minutes; target median is at least 40 minutes. Each public-core item must have a passing 0.2.0 manifest with explicit acquisition, processing, derivative-release, annotation-release, transcript-release, and raw-media-release decisions before annotation begins. `unknown_hold` never passes. Current cleared count is 0 until real reviewed records exist.

## Ranked Full Benchmark shortlist

| Rank | Source family | Target role | Rationale |
|---:|---|---|---|
| 1 | NASA + NARA + NOAA verified assets | Redistributable long-form backbone | Stable institutional provenance; scalable long recordings; public raw-media package feasible for selected assets |
| 2 | Wikimedia Commons verified CC/public-domain media | Domain diversification | Explicit licenses, international topics, lectures/events/documentaries; high per-item diligence but good release feasibility |
| 3 | Assembly101 and EPIC-KITCHENS/EPIC-SOUNDS | External compatibility partition | Dense timestamps, mistakes, actions, and ambient audio; raw-media rights and access remain package-specific |
| 4 | Ego4D / Ego-Exo4D selected agreement-compliant subset | Hard egocentric research partition | Long naturalistic evidence and rich labels; privacy/governance and storage limit scale |
| 5 | TRACE/VES-Bench + TraceAV-Bench + LongVidSearch + LongShOTBench | External compatibility suites | Evidence intervals, multi-hop trajectories, retrieval and rubric-based evaluation without republishing media |
| 6 | FLARE + LVBench + Video-MME + LongVideoBench + MLVU | Breadth and modality compatibility | Audio-only/bimodal retrieval, long duration, subtitles and task diversity, but heterogeneous rights |
| 7 | MAD / MovieNet | Annotation-design reference and optional internal-only evaluation | Excellent movie-scale temporal language; raw media cannot form a public benchmark |

**Do not use as sole full-benchmark sources:** HowTo100M, ActivityNet, YouCook2, QVHighlights, or arbitrary YouTube crawling. They may supplement discovery only after a separate platform-compliant acquisition decision and asset-level permission review.

## Acquisition and reproducibility plan

1. **Freeze a candidate manifest before media transfer.** Record canonical URL, source identifier/revision, publisher, access class, upstream dataset IDs, duration estimate, and fallback mapping.
2. **Rights gate.** Save the exact license/grant/terms version and URL, dated
   snapshot hash, licensor/rightsholder, copyright basis, acquisition authority,
   processing authority, and explicit derivative, annotation, transcript, and
   raw-media release decisions, plus commercial-use scope, attribution,
   share-alike, embedded-component review, agreement ID, reviewer, and date.
3. **Privacy/safety gate.** Screen faces, voices, minors, private spaces, precise locations, medical/sexual/violent content, copyrighted music, and identity data. Human-review all public-release items.
4. **Authorized acquisition only.** Use the official dataset downloader, official direct download, platform-authorized API/export, or rightsholder delivery. Do not use a generic downloader merely because a URL resolves.
5. **Integrity and media probe.** Compute SHA-256, byte size, source headers, perceptual video hash, audio fingerprint, duration, codecs, frame rate, channels, sample rate, subtitle tracks, and tool versions.
6. **Immutable originals, reproducible derivatives.** Keep the original object read-only. Version preprocessing containers, commands, ASR model, shot/audio event detectors, frame sampling, and time-base conversions. Hash every artifact.
7. **Timestamp contract.** Store all evidence in seconds from original media start, plus source time base, and retain mappings through transcode/trimming. Prefer no editorial trimming; if unavoidable, store edit decision lists.
8. **Link-rot defense.** For redistributable items, archive exact source bytes and rights evidence. For non-redistributable items, retain IDs, hashes/fingerprints, metadata snapshots, permitted features, transcript/annotation hashes, and a pre-approved replacement asset with equivalent duration/domain/modalities.
9. **Release separation.** Build distinct packages: `(a)` raw media permitted for redistribution, `(b)` annotations/transcripts/features permitted for redistribution, `(c)` IDs and acquisition scripts/instructions, `(d)` internal-only restricted assets. Never let a broad repository license blur these packages.
10. **Withdrawal process.** Support quarantine, deletion, source withdrawal, replacement, and versioned benchmark mappings without silently changing test semantics.

The machine-enforced record is `acquisition_manifest_schema.json`. One JSON record should exist per original asset, not per clip. Clips, questions, evidence spans, distractors, transcripts, and features refer back to that immutable `asset_id` and source time base.

## Deferred distractor design

Distractor insertion is deferred until after Pilot-0. If later approved, prefer distractors from within the same rights-cleared long recording: repeated speakers, visually similar scenes, recurring objects, repeated procedures, and semantically similar speech at distant times. Cross-video distractors add licensing and leakage complexity. Annotation should store every positive evidence interval, the minimum sufficient evidence set, plausible hard-negative intervals, modality needed (visual, speech, non-speech audio, subtitle), and annotator disagreement. Existing sources contribute patterns:

- TRACE/VES-Bench and LongVidSearch: evidence selection and multi-hop retrieval;
- TraceAV-Bench and LongShOTBench: multi-hop audiovisual trajectories and long-form reasoning;
- LoVR and FLARE: clip/video retrieval, audio-only and hard-bimodal distractors;
- NExT-GQA and QVHighlights: explicit interval/saliency schemas;
- TVQA and LongVideoBench: time-aware subtitle grounding;
- EPIC-SOUNDS: non-speech audio events;
- Assembly101/EPIC-KITCHENS: repeated procedural stages and mistakes.

## Storage and preprocessing planning

These are illustrative scaling assumptions, not a Pilot-0 budget and not quotes.
Actual storage, compute, retention, backup, and labor must be recomputed from the
selected 20–30-asset manifest and the 12-family rehearsal.

### Assumptions

- Average source duration: illustrative **60 minutes/video** within the frozen
  20–90-minute Pilot-0 range.
- Stored source/mezzanine: **8 Mb/s video + 192 kb/s audio**, about **3.7 GB/hour** (decimal), rounded to **4 GB/video**.
- Audio extraction: 16 kHz mono PCM, about **0.115 GB/hour**.
- Sampled visual representations: 1 frame every 2 seconds as JPEG/AVIF plus indexes, budget **0.5 GB/hour**.
- Embeddings, ASR words/timestamps, shot/audio-event metadata, QA and indexes: **0.4 GB/hour**.
- Working overhead and duplicate-safe staging: **1.5×** the sum of source plus derived artifacts.
- GPU preprocessing per video-hour: ASR **0.15-0.6 GPU-h**, visual/audio embeddings **0.3-1.2 GPU-h**, detectors/indexing **0.1-0.4 GPU-h**; total **0.55-2.2 GPU-h/hour**. CPU demux/probe/QA: **0.5-1.5 CPU-h/hour**.
- Human rights/privacy verification: **20-60 minutes/item** before annotation, more for ambiguous archival items. Annotation labor is excluded because question design depth varies dramatically.

### Illustrative capacity outside the frozen Pilot-0 count

| Source videos | Source hours | Source media | Derived artifacts | Provisioned working storage (1.5×) | GPU preprocessing | CPU preprocessing | Rights/privacy intake |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 20 | 20 h | ~80 GB | ~20 GB | ~0.15 TB | 11-44 GPU-h | 10-30 CPU-h | pending rehearsal |
| 30 | 30 h | ~120 GB | ~31 GB | ~0.23 TB | 17-66 GPU-h | 15-45 CPU-h | pending rehearsal |
| 300 | 300 h | ~1.2 TB | ~0.30 TB | ~2.3 TB | 165-660 GPU-h | 150-450 CPU-h | 100-300 person-h |
| 1,000 | 1,000 h | ~4.0 TB | ~1.0 TB | ~7.5 TB | 550-2,200 GPU-h | 500-1,500 CPU-h | 333-1,000 person-h |

Duration sensitivity is approximately linear: a two-hour average doubles storage and compute; a 30-minute average halves them. High-resolution egocentric multi-view sources can exceed these estimates several-fold. Retaining only compressed source files can reduce storage, while a lossless or visually transparent mezzanine can increase it substantially.

### Cost model rather than false precision

Use current institutional rates at execution time:

- `GPU cost = GPU-hours × approved GPU instance rate`;
- `CPU cost = CPU-hours × approved CPU rate`;
- `object storage = provisioned TB-month × storage rate`;
- `egress = released/downloaded TB × provider egress rate`;
- `human review = person-hours × loaded reviewer rate`.

Do not commit a dollar figure before the final codec/duration sample, cloud region, reserved/spot policy, and transcription model are chosen.

## Go/no-go controls

A source asset is **no-go** if any acquisition, processing, derivative-release, annotation-release, transcript-release, or raw-media-release decision is `unknown_hold` at the relevant gate; if authority evidence is missing; if an agreement bars the intended use; if high-risk personal data is unmitigated; or if reproducibility depends on an unarchived third-party link with no approved replacement. Legal facts and project risk judgments are recorded separately in the risk register.

## Primary-source index

The inventory CSV is the row-level source index. High-level policy sources used in decisions include:

- YouTube Terms of Service: https://www.youtube.com/static?template=terms
- Ego4D official portal/license workflow: https://ego4d-data.org/
- NASA media usage guidance: https://www.nasa.gov/nasa-brand-center/images-and-media/
- NARA motion-picture research and catalog guidance: https://www.archives.gov/research/motion-pictures
- Wikimedia Commons reuse policy: https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia
- Internet Archive Terms: https://archive.org/about/terms.php

All were checked on 2026-09-05. Terms can change; re-verify them immediately before acquisition and release.
