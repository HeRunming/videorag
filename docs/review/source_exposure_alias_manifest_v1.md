# Source exposure alias manifest v1

- Final marker: `SOURCE_EXPOSURE_ALIAS_MANIFEST_V1_READY`
- Date: `2026-10-14`
- Scanned files: 2709
- Scanned bytes: 156147814
- Alias closures: 158
- Exposure evidence rows: 1235
- Currently touched closures: 69

## Safety boundary

The generator scans only allowlisted bounded text/JSON/CSV/prompt/log/index/manifest files. It excludes media, model, annotation, and annotations directories and never opens media or semantic annotation bodies.

## Eligibility policy

- Conditional only: `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`.
- Contaminating: `media_acquired`, `media_indexed`, `learned_model_ranked`, `candidate_mined`, `semantic_prompt_exposed`, `human_prescreened`, `annotation_opened`.
- Any contaminating event applies to the full alias closure.

## Event counts

| Event | Evidence rows |
|---|---:|
| `metadata_catalog_only` | 715 |
| `rights/access_preflight` | 166 |
| `failed_zero_byte_probe` | 29 |
| `media_acquired` | 36 |
| `media_indexed` | 60 |
| `learned_model_ranked` | 26 |
| `candidate_mined` | 152 |
| `semantic_prompt_exposed` | 51 |
| `human_prescreened` | 0 |
| `annotation_opened` | 0 |

## Current touched closures

| Closure root | Event types | Alias sample |
|---|---|---|
| `CC4D:P01` | `metadata_catalog_only`, `rights/access_preflight`, `media_acquired`, `media_indexed`, `learned_model_ranked`, `candidate_mined` | `15_46`, `16_20`, `16_35`, `16_42`, `17_43`, `18_27` |
| `CC4D:P02` | `metadata_catalog_only`, `rights/access_preflight`, `media_acquired`, `media_indexed`, `learned_model_ranked`, `candidate_mined` | `10_18`, `10_26`, `10_50`, `12_15`, `12_17`, `12_26` |
| `CC4D:P03` | `metadata_catalog_only`, `rights/access_preflight`, `media_acquired`, `media_indexed`, `learned_model_ranked`, `candidate_mined` | `12_10`, `12_16`, `12_19`, `12_6`, `12_9`, `13_20` |
| `EC-COMMONS-BLOCKCHAIN` | `metadata_catalog_only`, `candidate_mined` | `Commons pageid 126021487 / oldid 1032015587 / SHA-1 53f1de165f9b9c98a6bf1562315fb6ce5a4a61cc`, `EC-COMMONS-BLOCKCHAIN` |
| `EC-COMMONS-WIKIMANIA-2024-OPENING` | `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`, `candidate_mined` | `CommonsFile:Wikimania 2024 - Gdańsk Main Hall - Day 1 - Opening ceremony & Wikimedian of the Year Awards.webm`, `EC-COMMONS-WIKIMANIA-2024-OPENING` |
| `EC-NARA-CITY-UNDER-ICE` | `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`, `candidate_mined` | `EC-NARA-CITY-UNDER-ICE`, `NAID:2569752`, `NARA-BIG-PICTURE-CITY-UNDER-ICE`, `cand-042` |
| `EC-NARA-MEMPHIS-BELLE` | `metadata_catalog_only`, `candidate_mined` | `EC-NARA-MEMPHIS-BELLE`, `NAID:38755`, `cand-031` |
| `EC-NARA-THUNDERBOLT` | `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`, `candidate_mined` | `EC-NARA-THUNDERBOLT`, `NAID:36060`, `NARA-THUNDERBOLT`, `cand-032` |
| `EC-NASA-EXPLORERS-LAUNCH` | `metadata_catalog_only`, `candidate_mined` | `EC-NASA-EXPLORERS-LAUNCH`, `NASA+-nasa-explorers-the-launch`, `NASA:cand-003`, `cand-003` |
| `EC-NASA-MOONBOUND` | `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`, `candidate_mined`, `semantic_prompt_exposed` | `EC-NASA-MOONBOUND`, `EVENT-STABLE:NASA+ post 6979 / content-id 15230 / HLS asset 17905`, `NASA+-moonbound-for-all-humanity`, `NASA:ASSET:17905`, `NASA:CONTENT:15230`, `NASA:POST:6979` |
| `EC-NASA-PATHFINDERS` | `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`, `candidate_mined`, `semantic_prompt_exposed` | `EC-NASA-PATHFINDERS`, `EVENT-STABLE:NASA+ post 2391 / content-id 9199 / HLS asset 11211`, `NASA+ post 2391 / content-id 9199 / HLS asset 11211`, `NASA:ASSET:11211`, `NASA:CONTENT:9199`, `NASA:POST:2391` |
| `EC-NASA-PLANETARY-DEFENDERS` | `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`, `candidate_mined`, `semantic_prompt_exposed` | `EC-NASA-PLANETARY-DEFENDERS`, `EVENT-STABLE:NASA+ post 6604 / content-id 14884 / HLS asset 16899`, `NASA+-planetary-defenders`, `NASA:ASSET:16899`, `NASA:CONTENT:14884`, `NASA:POST:6604` |
| `EC-NASA-TO-THE-RESCUE` | `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`, `candidate_mined`, `semantic_prompt_exposed` | `EC-NASA-TO-THE-RESCUE`, `EVENT-STABLE:NASA+ post 4460 / content-id 13675 / HLS asset 15687`, `NASA+-jpl-to-the-rescue`, `NASA:ASSET:15687`, `NASA:CONTENT:13675`, `NASA:POST:4460` |
| `EC-NOAA-BEACH-BAY-SAFE` | `metadata_catalog_only`, `candidate_mined` | `EC-NOAA-BEACH-BAY-SAFE`, `NOAA-OceanToday-webinar5` |
| `EC-NOAA-SHIPWRECKS` | `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`, `candidate_mined`, `semantic_prompt_exposed` | `EC-NOAA-SHIPWRECKS`, `EVENT-STABLE:NOAA Ocean Today webinar4 / cand-048`, `NOAA-OceanToday-webinar4`, `NOAA:cand-048`, `cand-048` |
| `EC-USGS-SHIFT-CURVES` | `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`, `candidate_mined`, `semantic_prompt_exposed` | `EC-USGS-SHIFT-CURVES`, `EVENT-STABLE:USGS media slug developing-and-applying-shift-curves-using-grsat`, `USGS-media-video-developing-and-applying-shift-curves-using-grsat` |
| `EC-USGS-SIX-ERUPTIONS` | `metadata_catalog_only`, `candidate_mined` | `EC-USGS-SIX-ERUPTIONS`, `USGS-media-video-pubtalk-112023-six-eruptions-two-volcanoes-over-past-three-years` |
| `EPIC:P23` | `metadata_catalog_only`, `rights/access_preflight`, `media_acquired`, `media_indexed`, `learned_model_ranked`, `candidate_mined` | `EPIC:P23`, `P23`, `P23_01`, `P23_02`, `P23_03`, `P23_04` |
| `EPIC:P27` | `metadata_catalog_only`, `rights/access_preflight`, `media_acquired`, `media_indexed`, `learned_model_ranked`, `candidate_mined` | `EPIC:P27`, `P27`, `P27_01`, `P27_02`, `P27_03`, `P27_04` |
| `EPIC:P28` | `metadata_catalog_only`, `rights/access_preflight`, `media_acquired`, `media_indexed`, `learned_model_ranked`, `candidate_mined` | `EPIC:P28`, `P28`, `P28_01`, `P28_02`, `P28_03`, `P28_04` |
| `NAID:12870` | `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`, `candidate_mined` | `NAID:12870`, `NARA-BATTLE-OF-MIDWAY`, `cand-029` |
| `NAID:2569560` | `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`, `candidate_mined` | `NAID:2569560`, `NARA-BIG-PICTURE-NURSES-IN-THE-ARMY`, `cand-040` |
| `NAID:2569665` | `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`, `candidate_mined` | `NAID:2569665`, `NARA-BIG-PICTURE-ARMY-SATELLITES`, `cand-041` |
| `NAID:2569754` | `metadata_catalog_only`, `candidate_mined` | `NAID:2569754`, `cand-043` |
| `NAID:2569758` | `metadata_catalog_only`, `candidate_mined` | `NAID:2569758`, `cand-044` |
| `NAID:35956` | `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`, `candidate_mined` | `NAID:35956`, `NARA-NEGRO-SOLDIER`, `cand-030` |
| `NAID:36073` | `metadata_catalog_only`, `candidate_mined` | `NAID:36073`, `cand-028` |
| `NAID:36074` | `metadata_catalog_only`, `candidate_mined` | `NAID:36074`, `cand-033` |
| `NAID:36075` | `metadata_catalog_only`, `candidate_mined` | `NAID:36075`, `cand-034` |
| `NAID:36076` | `metadata_catalog_only`, `candidate_mined` | `NAID:36076`, `cand-035` |
| `NAID:36077` | `metadata_catalog_only`, `candidate_mined` | `NAID:36077`, `cand-036` |
| `NAID:36078` | `metadata_catalog_only`, `candidate_mined` | `NAID:36078`, `cand-037` |
| `NAID:36079` | `metadata_catalog_only`, `candidate_mined` | `NAID:36079`, `cand-038` |
| `NAID:36080` | `metadata_catalog_only`, `candidate_mined` | `NAID:36080`, `cand-039` |
| `NAID:45017` | `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`, `candidate_mined` | `NAID:45017`, `NARA-PROJECT-GEMINI-BRIDGE-TO-MOON`, `cand-027` |
| `NAID:47292` | `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`, `candidate_mined` | `NAID:47292`, `NARA-APOLLO-11-FOR-ALL-MANKIND`, `cand-026` |
| `NASA:cand-001` | `metadata_catalog_only`, `candidate_mined` | `NASA+-the-flight-of-apollo-11`, `NASA:cand-001`, `cand-001` |
| `NASA:cand-002` | `metadata_catalog_only`, `candidate_mined` | `NASA+-the-birth-of-nasa-documentary`, `NASA:cand-002`, `cand-002` |
| `NASA:cand-006` | `metadata_catalog_only`, `candidate_mined` | `NASA+-hubble-35-years`, `NASA:cand-006`, `cand-006` |
| `NASA:cand-007` | `metadata_catalog_only`, `candidate_mined` | `NASA+-cosmic-dawn`, `NASA:cand-007`, `cand-007` |
| `NASA:cand-008` | `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`, `candidate_mined` | `NASA+-jpl-changing-face-of-mars`, `NASA:cand-008`, `cand-008` |
| `NASA:cand-009` | `metadata_catalog_only`, `candidate_mined` | `NASA+-jpl-stuff-of-dreams`, `NASA:cand-009`, `cand-009` |
| `NASA:cand-010` | `metadata_catalog_only`, `candidate_mined` | `NASA+-jpl-explorer-1`, `NASA:cand-010`, `cand-010` |
| `NASA:cand-011` | `metadata_catalog_only`, `candidate_mined` | `NASA+-jpl-destination-moon`, `NASA:cand-011`, `cand-011` |
| `NASA:cand-012` | `metadata_catalog_only`, `candidate_mined` | `NASA+-jpl-footsteps-of-voyager`, `NASA:cand-012`, `cand-012` |
| `NASA:cand-013` | `metadata_catalog_only`, `candidate_mined` | `NASA+-jpl-pathfinders`, `NASA:cand-013`, `cand-013` |
| `NASA:cand-015` | `metadata_catalog_only`, `candidate_mined` | `NASA+-jpl-mission-to-mars`, `NASA:cand-015`, `cand-015` |
| `NASA:cand-016` | `metadata_catalog_only`, `candidate_mined` | `NASA+-jpl-breaking-point`, `NASA:cand-016`, `cand-016` |
| `NASA:cand-017` | `metadata_catalog_only`, `candidate_mined` | `NASA+-jpl-saving-galileo`, `NASA:cand-017`, `cand-017` |
| `NASA:cand-018` | `metadata_catalog_only`, `candidate_mined` | `NASA+-jpl-hunt-space-rocks`, `NASA:cand-018`, `cand-018` |
| `NASA:cand-019` | `metadata_catalog_only`, `candidate_mined` | `NASA+-jpl-american-rocketeer`, `NASA:cand-019`, `cand-019` |
| `NASA:cand-020` | `metadata_catalog_only`, `candidate_mined` | `NASA+-jpl-whole-new-world`, `NASA:cand-020`, `cand-020` |
| `NASA:cand-021` | `metadata_catalog_only`, `candidate_mined` | `NASA+-and-then-there-was-voyager`, `NASA:cand-021`, `cand-021` |
| `NASA:cand-022` | `metadata_catalog_only`, `candidate_mined` | `NASA-SVS-10233`, `NASA:cand-022`, `cand-022` |
| `NASA:cand-023` | `metadata_catalog_only`, `rights/access_preflight`, `candidate_mined`, `semantic_prompt_exposed` | `NASA-SVS-11205`, `NASA:cand-023`, `cand-023` |
| `NASA:cand-024` | `metadata_catalog_only`, `candidate_mined` | `NASA-SVS-10101`, `NASA:cand-024`, `cand-024` |
| `NASA:cand-025` | `metadata_catalog_only`, `candidate_mined` | `NASA-SVS-10175`, `NASA:cand-025`, `cand-025` |
| `NOAA:cand-045` | `metadata_catalog_only`, `rights/access_preflight`, `media_acquired`, `learned_model_ranked`, `candidate_mined`, `semantic_prompt_exposed` | `NOAA:cand-045`, `cand-045` |
| `NOAA:cand-046` | `metadata_catalog_only`, `rights/access_preflight`, `candidate_mined`, `semantic_prompt_exposed` | `NOAA:cand-046`, `cand-046` |
| `NOAA:cand-047` | `metadata_catalog_only`, `rights/access_preflight`, `media_acquired`, `learned_model_ranked`, `candidate_mined`, `semantic_prompt_exposed` | `NOAA:cand-047`, `cand-047` |
| `NOAA:cand-049` | `metadata_catalog_only`, `rights/access_preflight`, `media_acquired`, `learned_model_ranked`, `candidate_mined`, `semantic_prompt_exposed` | `NOAA:cand-049`, `cand-049` |
| `NOAA:cand-050` | `metadata_catalog_only`, `rights/access_preflight`, `candidate_mined` | `NOAA:cand-050`, `cand-050` |
| `NOAA:cand-051` | `metadata_catalog_only`, `rights/access_preflight`, `media_acquired`, `learned_model_ranked`, `candidate_mined`, `semantic_prompt_exposed` | `NOAA:cand-051`, `cand-051` |
| `NOAA:cand-052` | `metadata_catalog_only`, `rights/access_preflight`, `media_acquired`, `learned_model_ranked`, `candidate_mined`, `semantic_prompt_exposed` | `NOAA:cand-052`, `cand-052` |
| `NOAA:cand-053` | `metadata_catalog_only`, `rights/access_preflight`, `candidate_mined` | `NOAA:cand-053`, `cand-053` |
| `NOAA:cand-054` | `metadata_catalog_only`, `rights/access_preflight`, `candidate_mined`, `semantic_prompt_exposed` | `NOAA:cand-054`, `cand-054` |
| `SG-MIT-RES12-003-L01` | `metadata_catalog_only`, `rights/access_preflight`, `media_acquired`, `media_indexed`, `learned_model_ranked`, `candidate_mined`, `semantic_prompt_exposed` | `SG-MIT-RES12-003-L01`, `repl-mit-res12-003-lecture-1` |
| `SG-OXFORD-QM-001` | `metadata_catalog_only`, `rights/access_preflight`, `media_acquired`, `media_indexed`, `learned_model_ranked`, `candidate_mined`, `semantic_prompt_exposed` | `SG-OXFORD-QM-001`, `repl-oxford-qm-001` |
| `SG-YALE-PHYS200-L01` | `metadata_catalog_only`, `rights/access_preflight`, `media_acquired`, `media_indexed`, `learned_model_ranked`, `candidate_mined`, `semantic_prompt_exposed` | `SG-YALE-PHYS200-L01`, `repl-yale-phys-200-lecture-1` |

## Exact local replacement discovery

These are discovery results, not authorization. They are limited to exact locally enumerated metadata groups with no detected contaminating event.

| Closure root | Exact local ID | Basis |
|---|---|---|
| `ASSEMBLY101:9055` | `nusar-2021_action_both_9055-a07_9055_user_id_2021-02-09_092331` | `EXACT_PARTICIPANT_AND_SESSION_LOCALLY_ENUMERATED_IN_AUTHENTICATED_NONSEMANTIC_METADATA` |
| `ASSEMBLY101:9056` | `nusar-2021_action_both_9056-b08a_9056_user_id_2021-02-22_141934` | `EXACT_PARTICIPANT_AND_SESSION_LOCALLY_ENUMERATED_IN_AUTHENTICATED_NONSEMANTIC_METADATA` |
| `ASSEMBLY101:9083` | `nusar-2021_action_both_9083-c03a_9083_user_id_2021-02-16_114344` | `EXACT_PARTICIPANT_AND_SESSION_LOCALLY_ENUMERATED_IN_AUTHENTICATED_NONSEMANTIC_METADATA` |
| `CC4D:P04` | `25_22` | `EXACT_PERSON_ENVIRONMENT_AND_RECORDING_LOCALLY_ENUMERATED_IN_SOURCE_GROUP_INVENTORY` |
| `CC4D:P06` | `16_18` | `EXACT_PERSON_ENVIRONMENT_AND_RECORDING_LOCALLY_ENUMERATED_IN_SOURCE_GROUP_INVENTORY` |
| `CC4D:P07` | `16_23` | `EXACT_PERSON_ENVIRONMENT_AND_RECORDING_LOCALLY_ENUMERATED_IN_SOURCE_GROUP_INVENTORY` |
| `EPIC:P01` | `P01_101` | `EXACT_PARTICIPANT_AND_SESSION_LOCALLY_ENUMERATED_IN_FROZEN_NONSEMANTIC_OFFICIAL_METADATA` |
| `EPIC:P02` | `P02_108` | `EXACT_PARTICIPANT_AND_SESSION_LOCALLY_ENUMERATED_IN_FROZEN_NONSEMANTIC_OFFICIAL_METADATA` |
| `EPIC:P04` | `P04_123` | `EXACT_PARTICIPANT_AND_SESSION_LOCALLY_ENUMERATED_IN_FROZEN_NONSEMANTIC_OFFICIAL_METADATA` |
| `SG-MIT-2-003J-L01` | `repl-mit-2-003j-lecture-1` | `EXACT_LOCAL_REPLACEMENT_METADATA_RECORD` |
| `SG-YALE-HIST202-L01` | `repl-yale-hist-202-lecture-1` | `EXACT_LOCAL_REPLACEMENT_METADATA_RECORD` |

## Required alias checks

- `cand-042`, `EC-NARA-CITY-UNDER-ICE`, and `NAID:2569752` share one evidence-backed closure.
- `P23`, `P23_102`, and all detected P23 derivatives close to `EPIC:P23`.
- CaptainCook4D recording and person/environment aliases close at person level.

`SOURCE_EXPOSURE_ALIAS_MANIFEST_V1_READY`
