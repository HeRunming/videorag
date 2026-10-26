# NARA event-source preflight v1

**Task:** 150  
**Date:** 2026-09-23  
**Decision:** `NARA_EVENT_SOURCE_PREFLIGHT_REPAIR`  
**Mode:** fail-closed finalization after the user ordered all network activity
to stop

## 1. Boundary

The requested live NARA preflight did not complete. The user explicitly
ordered:

> Stop all network activity and finalize immediately. No more discovery.

No network operation was issued after that instruction. Before the stop:

- one bounded search invocation returned no usable source;
- one `curl` request to `https://catalog.archives.gov/id/38294` failed before
  HTTP because the supplied primary proxy could not be resolved inside the
  sandbox;
- the same bounded request was submitted for the required network escalation,
  but the request was interrupted during the approval wait;
- no HTTP response, item page, policy page, API result, digital object,
  manifest, or media bytes were obtained.

Task-150 transfer counts are therefore:

| Measure | Count |
|---|---:|
| Successful evidence-bearing network requests | 0 |
| Successful NARA item snapshots | 0 |
| Successful NARA restriction/use snapshots | 0 |
| Exact NARA digital-object URLs established | 0 |
| Completed HEAD probes | 0 |
| Completed Range probes | 0 |
| Completed manifest probes | 0 |
| Full media downloads | 0 |
| Media payload bytes retained | 0 |

The exact attempt record is saved and hashed at
`data/source_recon/nara_event_sources_v1/network_stop_record.json`.

This report uses prior checked-in metadata only to form an honest repair
queue. It does not relabel prior metadata as Task-150 live evidence.

## 2. Gate and exact counts

`EXACT_PREFLIGHT_READY` requires all of the following for an individual
record:

1. a live-readable exact NARA item and exact catalog ID;
2. item-level use-restriction and specific-use-restriction evidence;
3. an exact NARA digital-object URL, not a guessed route or third-party copy;
4. a successful bounded technical probe supporting video and audio stream
   plausibility;
5. affirmative acquisition, internal-processing, and restricted-annotation
   decisions; and
6. no unresolved critical component, privacy, safety, or soundtrack hold.

No candidate meets that rule.

| Result | Count |
|---|---:|
| Distinct records serialized | 8 |
| `EXACT_PREFLIGHT_READY` | 0 |
| `PREFLIGHT_REPAIR` | 6 |
| `PREFLIGHT_NO_GO` | 2 |
| Non-rejected candidate records | 6 |
| Item-level restriction/use records live verified | 0 |
| Exact NARA digital-object URLs | 0 |
| A/V stream plausibility live verified | 0 |
| Hypothesized capture-format categories | 3 |
| Live-validated capture-format categories | 0 |
| Sources in 30–120 minutes by retained/approximate metadata | 4 |
| Sources in 30–120 minutes live verified in Task 150 | 0 |

The request for at least six non-rejected records is represented by six
`PREFLIGHT_REPAIR` leads. The target of at least two
`EXACT_PREFLIGHT_READY` records was **not met**.

## 3. Candidate ledger

| Candidate | Exact retained catalog ID | Duration evidence | Capture-format hypothesis | Decision | Principal blockers |
|---|---|---|---|---|---|
| *Apollo 11: For All Mankind* | `NAID:47292` | unresolved | mission/event | `PREFLIGHT_REPAIR` | no Task-150 live title/ID, restrictions, object, duration, or stream evidence |
| *The Big Picture: Army Satellites* | `NAID:2569665` | ~28 min, stale/approximate | industrial/lab/process | `PREFLIGHT_REPAIR` | below preferred 30-min floor; no live rights, object, stream, or component evidence |
| *The Big Picture: City Under the Ice* | `NAID:2569752` | unresolved | field operations; maintenance/assembly | `PREFLIGHT_REPAIR` | no live title/local-ID, runtime, restrictions, object, or stream evidence |
| *The Big Picture: Nurses in the Army* | `NAID:2569560` | unresolved | field procedure/training | `PREFLIGHT_REPAIR` | no live rights/object/stream evidence; patient/privacy and dignity review absent |
| *The Negro Soldier* | `NAID:35956` | 40:22 in prior official metadata | mission/event archival film | `PREFLIGHT_REPAIR` | no Task-150 item restrictions or object; propaganda, racist material, music, and sensitivity burden |
| *Thunderbolt* | `NAID:36060` | 44:00 in stale metadata | mission/event archival film | `PREFLIGHT_REPAIR` | title/ID/runtime stale; no rights/object/stream evidence; combat and soundtrack burden |
| *Project Gemini: A Bridge to the Moon* | proposed `NAID:45017` | unresolved | mission/event | `PREFLIGHT_NO_GO` | prior official NARA transcript metadata associates this ID with a different title |
| *The Battle of Midway* | `NAID:12870` | 18:00 in prior official record | mission/event | `PREFLIGHT_NO_GO` | below the frozen 20-minute minimum and preferred 30-minute floor; combat/soundtrack burden |

The eight catalog IDs above are exact strings retained in the prior local
candidate registry. Only prior audit status is claimed. Task 150 did not
independently revalidate any of them live.

## 4. Capture-format result

The six held leads span three **hypothesized** formats:

1. mission/event documentary or archival event record;
2. industrial/laboratory/process material;
3. field operations, maintenance, assembly, or procedural training.

No wildlife/environment record was established before the stop. No category
was live validated, and no media was inspected. The labels therefore provide
queue organization only; they are not evidence of actual capture composition.

## 5. Rights-first findings

NARA custody, a catalog URL, or a downloadable digital copy is not a warranty
that a whole record or every embedded component is public domain. This
preflight requires item-level restriction/use evidence and a separate
component review.

For all six held candidates, the following remain unresolved:

- exact `useRestriction` and `specificUseRestriction` values;
- affirmative federal-work/public-domain basis or documented permission;
- contractor, partner, donor, foreign, newsreel, or stock footage;
- score, incidental music, or other copyrighted audio;
- marks, endorsement, faces, voices, publicity, and privacy;
- exact acquisition authority for the catalog-described digital object;
- project authorization for ML processing and restricted annotation;
- artifact-specific public-release authority.

Additional fail-closed risks apply:

- *Nurses in the Army*: medical privacy, dignity, patients, and bystanders;
- *The Negro Soldier*: racist imagery/language, propaganda framing, community
  review, and reviewer safety;
- *Thunderbolt*: combat casualties or gore, foreign footage, and soundtrack
  provenance;
- *City Under the Ice* and *Army Satellites*: military/contractor components
  and possible historical security context.

No general NARA policy is treated as item-level clearance. No holding is
declared public domain in this task.

## 6. Technical and semantic result

No exact NARA digital-object URL was established, so no legitimate object
HEAD, Range, manifest, or container probe was possible. Consequently, all of
the following remain unknown for every held candidate:

- object length, MIME, ETag, and Last-Modified;
- Range behavior;
- duration from the actual digital object;
- video and audio stream counts and codecs;
- timestamps, time bases, and A/V synchronization plausibility.

Titles and prior descriptions suggest dynamic process or mission visuals for
the six held records. Machinery, launch, equipment, hospital/training, or
aircraft sounds may occur. These are metadata hypotheses only. Narration,
captions, diagrams, propaganda framing, and editorial music are substantial
shortcut or masking risks. No semantic suitability finding is made.

## 7. Separate decisions

The fail-closed decision is uniform because item-level and technical evidence
is missing:

| Decision plane | Task-150 decision |
|---|---|
| Acquisition | `NOT_AUTHORIZED` |
| Internal processing | `NOT_AUTHORIZED` |
| Restricted human annotation | `NOT_AUTHORIZED` |
| Raw-media release | `NOT_AUTHORIZED` |
| Clip/frame/audio release | `NOT_AUTHORIZED` |
| Transcript release | `NOT_AUTHORIZED` |
| Annotation/evaluator release | `NOT_AUTHORIZED` |
| Derived feature/embedding release | `NOT_AUTHORIZED` |

The `HOLD` values inside individual repair dossiers identify what could be
reconsidered after evidence repair. They confer no current authorization.

## 8. Evidence

Small Task-150 evidence:

| Path | Bytes | SHA-256 |
|---|---:|---|
| `data/source_recon/nara_event_sources_v1/network_stop_record.json` | 2,307 | `a9772655e1f9ae8b9dd7f2058b0351f211757fabe26aa37ccbfcca7cd3ed6a34` |

The dossier also pins hashes for the prior local candidate registry,
top-30 queue, Task-143 event-source dossier, candidate-pool review, and
license-risk register. Those files support provenance for the repair queue,
not a live-readiness finding.

## 9. Next action

No acquisition, processing, annotation, or release action is authorized while
the network stop remains in force.

If the user later reauthorizes live work, the minimum repair order is:

1. verify *City Under the Ice* and *Army Satellites* first as the lower-combat
   process/field leads;
2. verify *Apollo 11: For All Mankind* as the mission/event lead;
3. retain *Nurses in the Army* only if medical privacy and dignity can be
   managed;
4. consider *The Negro Soldier* and *Thunderbolt* only after elevated
   sensitivity, violence, component, and soundtrack review;
5. capture exact item restriction/use fields and exact NARA digital-object
   URLs before any media request;
6. use only bounded HEAD, manifest, or small Range probes, aborting if Range
   is ignored.

Final decision: `NARA_EVENT_SOURCE_PREFLIGHT_REPAIR`
