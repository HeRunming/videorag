# Rehearsal asset packet review

**Review date:** 2026-09-06  
**Owner:** human-review packet preparation  
**Scope:** official-source metadata, rights evidence, acquisition-path triage, and reviewer instructions for the first real-video rehearsal  
**Not in scope:** media acquisition, playback inspection, annotation, legal approval, or Gate A approval  
**Legal posture:** not legal advice

## Executive outcome

**Gate A remains NO-GO.** Ten candidates were packaged for review. All ten draft manifests are fail-closed with `audit.gate_status = unknown_hold`; all substantive rights decisions remain `unknown_hold`; no media bytes were acquired.

The shortlist intentionally includes:

- 4 NASA items: two SVS records with official download controls and two NASA+ items with strong expected technical value but no verified transfer route;
- 3 NOAA Ocean Today items: strong expected field/webinar value but no verified non-platform acquisition path;
- 3 Wikimedia Commons items: direct repository files, but revision/source-chain and license or public-domain review remain incomplete.

There are no NARA shortlist items because the available official catalog evidence was not sufficient to conservatively verify exact item metadata, affirmative federal-work/public-domain status, and an authorized acquisition path for this packet.

## Deliverable inventory

- `data/rehearsal_review/shortlist.csv`
- `data/rehearsal_review/packets/cand-*.json` — ten complete review packets
- `data/rehearsal_review/reviewer_checklist.md`
- `data/rehearsal_review/selection_rationale.md`

Each packet contains:

1. official landing-page and rights-evidence findings as of 2026-09-06;
2. acquisition-path classification;
3. likely media-backed suitability and fallback IDs;
4. unanswered questions grouped by acquisition, processing, transcript, derivative, annotation, raw redistribution, components/likeness/music/marks, privacy, withdrawal, and technical review;
5. a schema-shaped draft acquisition manifest with no approvals.

## Material corrections since the 2026-09-05 pool audit

- `cand-055` Commons duration is currently reported as **39:14**, not 1:00:56; it is retained only as a fallback.
- `cand-056` Commons duration is **51:07**.
- `cand-057` Commons duration is **1:24:03** and the file page explicitly reports that license review is still needed.
- `cand-061` Commons duration is **1:29:35**, leaving only 25 seconds below the 90-minute maximum.
- `cand-062` Commons duration is **1:06:21**, but it remains excluded because the topic and likely depictions concern children.
- `cand-059` Commons duration is **1:21:15**, but it remains excluded because Indigenous-cultural and slide/image review burdens are avoidable for this rehearsal.

These are metadata corrections only. Exact duration must still be confirmed by probing authorized acquired bytes.

## Acquisition-path findings

### Documented official file/download path, still held

- NASA SVS: `cand-022`, `cand-023`
- Wikimedia Commons: `cand-056`, `cand-057`, `cand-061`

“Documented” means the official item page exposes a repository download mechanism. It does **not** mean rights are cleared. Each exact rendition, revision, license/status, attribution chain, and component scope must be frozen before transfer.

### No verified acquisition path

- NASA+: `cand-003`, `cand-004`
- NOAA Ocean Today: `cand-048`, `cand-051`, `cand-052`

The institutional landing pages are valid discovery/identity evidence. They do not authorize extraction of an embedded stream. These candidates may advance only through an official direct download, platform-authorized API/export, or rightsholder delivery.

## Rights and ethics findings

- NASA and NOAA family-level guidance is useful but cannot clear music, contractor/partner footage, slides, marks, or people.
- Recent Commons imports may state a Creative Commons license while also remaining in “license review needed”; those claims are treated as unresolved.
- Public-event or public-official status does not eliminate likeness, contextual-integrity, or sensitive-content review.
- Raw redistribution is a separate required decision. If it is not affirmatively allowed, the item cannot enter the public core.
- Every packet includes withdrawal, quarantine, deletion, replacement, and benchmark-version questions because the project freeze checklist requires an operational lifecycle policy.

## Scientific and technical constraint

The scientific Go/No-Go permits only a conditional small rehearsal after engineering blockers are closed. Rights clearance alone is insufficient. Before annotation:

- `inspect_clip` must use decoded registered media;
- audio and transcript observations must have real provenance;
- corrupt/inconsistent media must fail validation;
- agents must cross a leakage-resistant serialization/process boundary;
- source-level retrieval, distractors, validator trajectories, complete metrics, and balanced restoration triggers must be implemented.

Any eventual media inspection should be rejection-oriented and should measure actual family yield, rights-review time, privacy burden, annotation time, alternative-evidence search, validation, adjudication, and repair.

## Conditional selection recommendation

Review `cand-061`, `cand-056`, and `cand-023` first because they combine official repository paths with complementary domains. Review `cand-048` next for field/ambient value, but only if NOAA supplies an authorized transfer. Consider `cand-003` as an optional fifth only if NASA supplies authorized delivery and component rights are tractable.

This is a conditional ordering, not an approval. If direct-path candidates prove too speech/narration heavy, do not compensate by scraping embedded sources; seek documented rightsholder delivery or use a cleared fallback.

## Reviewer sign-off table

| Candidate | Rights/legal | Acquisition/data | Privacy/ethics | Technical after Gate A | Final status |
|---|---|---|---|---|---|
| `cand-061` | pending | pending | pending | prohibited until Gate A | `unknown_hold` |
| `cand-056` | pending | pending | pending | prohibited until Gate A | `unknown_hold` |
| `cand-023` | pending | pending | pending | prohibited until Gate A | `unknown_hold` |
| `cand-022` | pending | pending | pending | prohibited until Gate A | `unknown_hold` |
| `cand-003` | pending | pending | pending | prohibited until Gate A | `unknown_hold` |
| `cand-048` | pending | pending | pending | prohibited until Gate A | `unknown_hold` |
| `cand-051` | pending | pending | pending | prohibited until Gate A | `unknown_hold` |
| `cand-052` | pending | pending | pending | prohibited until Gate A | `unknown_hold` |
| `cand-004` | pending | pending | pending | prohibited until Gate A | `unknown_hold` |
| `cand-057` | pending | pending | pending | prohibited until Gate A | `unknown_hold` |

## Required next action

Assign named rights, acquisition, and privacy reviewers. They must capture immutable official evidence, answer every packet question, replace placeholder hashes, and record item/component decisions. Only then may a formal Gate A owner consider transfer. No packet created here passes Gate A.
