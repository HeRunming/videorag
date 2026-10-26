# Source-family notes for the Pilot-0 candidate pool

**Prepared:** 2026-09-05  
**Purpose:** metadata-only discovery notes, not legal conclusions or Gate A evidence.

## Cross-family selection logic

The pool favors recordings that are 20–90 minutes, contain continuous audiovisual material, and appear to have multiple separated phases, demonstrations, mission stages, presentation sections, or Q&A. Those structures are promising for minimal sufficient evidence sets, necessity groups, modality-channel outages, and natural failure/restoration episodes. Actual suitability cannot be established from metadata; it requires an authorized media inspection after Gate A.

The top-30 target mix is 12 NASA, 6 NARA, 4 NOAA, and 8 Commons records. It intentionally spans spaceflight, astronomy, Earth science, ocean science, engineering, archival history, computing, archaeology, law, and public events. The queue is not a recommendation to acquire all 30 and does not imply equal feasibility.

## NASA

### Why retained

NASA has the strongest concentration of mission chronology, engineering procedures, archival operations audio, interviews, visual demonstrations, and recurring failure/recovery narratives. Official NASA+ and Scientific Visualization Studio landing pages often provide useful duration, description, transcript, chapter, or download metadata.

### Main unresolved issues

- NASA hosting is not conclusive proof that every component is a U.S. federal work.
- Jet Propulsion Laboratory productions may implicate Caltech, contractors, international partners, and separate production rights.
- ESA/CSA imagery, launch-provider footage, news clips, archival stills, documentary music, stock footage, and interview releases need component-level review.
- NASA names, insignia, mission patches, and participant likenesses require mark/endorsement/publicity treatment even where copyright is not the main barrier.
- An embedded stream is not an authorized acquisition path by itself. Use only an official direct download/export documented in the eventual manifest.
- NASA SVS records can contain unusually explicit music and contributor credits; these are warnings, not automatic exclusions.

### Priority candidates

`The Flight of Apollo 11`, `NASA Explorers: The Launch`, and the JPL rescue/failure documentaries are especially promising for separated event evidence and restoration questions. `The World Avoided` and the Hubble candidates diversify toward Earth science and astronomy but may depend more heavily on narration/music than natural ambient audio.

### Fallback logic

Prefer another NASA-authored program on the same mission or a NARA federal record with an affirmative public-domain basis. Do not fall back to a YouTube mirror.

## NARA

### Why retained

NARA offers durable catalog identifiers, long government films, and historical recordings with distinct sequences. Apollo/Gemini and selected `The Big Picture` records could supply operational or procedural audio-visual evidence beyond contemporary studio-style documentaries.

### Main unresolved issues

- NARA custody, a catalog page, or a downloadable digital copy is not a warranty of copyright status.
- Require an affirmative federal-work/public-domain basis or written permission and inspect the catalog's exact use-restriction fields.
- Many films include foreign newsreels, contractor footage, donated material, music, stock footage, or people whose rights are not resolved by federal copyright status.
- War-era records may contain death, violence, racist imagery/language, propaganda, or sensitive depictions. These should be retained only if benchmark value clearly exceeds the review and participant-safety burden.
- Several series-level discovery IDs should be reconfirmed against the live catalog title, local identifier, duration, and restriction statement before they advance.

### Priority candidates

`Apollo 11: For All Mankind`, `Project Gemini: A Bridge to the Moon`, and the less combat-centered `The Big Picture` medical/engineering records are preferred. Combat-heavy `Why We Fight` titles are mostly reserve holds and should not be used merely to fill quotas.

### Fallback logic

For spaceflight, use the corresponding NASA official item. For Arctic/engineering topics, use a NOAA or NASA science/operations program. If the rights note is missing or ambiguous, reject rather than infer clearance.

## NOAA

### Why retained

The official Ocean Today webinar pages expose long, chaptered educational programs with speech, guest explanations, underwater or weather visuals, and often non-speech field/ROV/surf audio. Chaptering suggests useful temporal segmentation without obtaining caption bytes.

### Main unresolved issues

- Confirm the recording is NOAA-produced rather than merely hosted, linked, or embedded by NOAA.
- Many programs feature NASA/JPL, WHOI, university, sanctuary, museum, and other guest or expedition-partner contributions.
- Supplied clips, 360-degree video, charts, music, photographs, trademarks, and speaker releases may have separate terms.
- Confirm an official downloadable/export path. A YouTube-hosted recording remains `metadata_only_hold` unless NOAA provides a separately authorized route.
- The NOAA disclaimer and general federal-work principles do not replace item-level credit and component review.

### Priority candidates

`Shipwrecks and Sanctuaries`, `Get Into Your Sanctuary`, `Trash Talk`, and `Climate Alive! Wild Weather` offer domain and modality diversity. `Ocean Worlds` is scientifically rich but has heavier partner-rights complexity.

### Fallback logic

Switch among official Ocean Today programs with the same duration/modality pattern, or use NASA Earth-science material. Never use arbitrary copies on third-party channels.

## Wikimedia Commons

### Why retained

Commons can provide explicit reusable licenses and domain diversity, particularly public lectures, community events, computing history, and educational presentations. Long recordings often contain visual slides, demonstrations, room sound, and Q&A separated in time.

### Required pinning before review can advance

For each file, capture:

1. exact canonical file title and page ID;
2. exact revision ID (`oldid`) reviewed;
3. original file SHA-256 after an authorized Gate A transfer;
4. license name/version, author, source, attribution text, and share-alike requirements;
5. the uploader's authority and the full source chain;
6. separate treatment of recording, slides, screenshots, music, quotations, software interfaces, venue content, and identifiable audience members.

Every Commons row is therefore `metadata_only_hold` until revision pinning is complete. A current file-page license badge is not enough, and category membership is not rights evidence.

### Main content risks

- Public lectures can incorporate copyrighted slides, website screenshots, film clips, readings, or data visualizations.
- Ceremonies and conferences may contain music, performances, audience imagery, or materials not covered by the event recording license.
- Topics involving children, bullying, health, Indigenous history, or online abuse require additional privacy/sensitivity review.
- License laundering and mistaken uploader claims remain possible even on an official Commons file page.

### Priority candidates

Lectures with clear structure and limited third-party media are preferred over ceremonies with music. Computing meetups offer ambient/device audio but introduce trademarks and software-screen rights. A revision-pinned equivalent file is the normal fallback.

## Direct grants

No direct-grant asset was placed in the pool because no public, asset-specific grant covering the required acquisition, editing, ML evaluation, derivative/transcript publication, and raw redistribution scope was identified during this metadata pass. A future grant should be added only with a stable public grant record and the named rightsholder's authority over all embedded components.

## YouTube and other embedded platforms

An official institutional page may point to or embed YouTube. Such a record can support discovery, but it cannot become an acquisition candidate merely because the video is viewable. Unless the institution supplies a separate authorized download/export route and explicit rights basis, keep the row at `metadata_only_hold`. No generic downloader, cookie workflow, stream URL, or raw platform-media URL belongs in these deliverables.

## Recommendation to the rights reviewer

The 2026-09-05 independent audit left no row at `candidate_review`: all surviving records are `metadata_only_hold`, and four pool records are rejected. Start with top-30 rows whose `verification_result` is `verified` or `verified_with_corrections`, but do not transfer media until the acquisition manifest can record affirmative, evidence-backed decisions. Review series concentration early: selecting many JPL documentaries, NARA propaganda films, NOAA webinars, or Wikimania sessions could violate source-disjointness in spirit even if URLs differ. Keep at least a 20% cleared replacement reserve after item-level review.
