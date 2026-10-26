# Source exposure alias manifest v2 supplemental audit

- Final marker: `SOURCE_EXPOSURE_ALIAS_MANIFEST_V2_SUPPLEMENTAL_AUDIT_PASS`
- Date: `2026-10-15`
- Post-freeze eligible files: 54
- Ignored governance/technical artifacts: 54
- Strict supplemental contamination events: 0
- Selected v3.1 commitment/closure exposure hits: 0

## Frozen boundary

- Frozen manifest v2 hash unchanged: `true`
- Frozen ledger v2 hash unchanged: `true`
- All pinned file hashes unchanged: `true`
- Pinned files checked: 2143

The unchanged v2 scanner policy is used. Network, media, semantic annotation bodies, transcripts/captions, and learned payloads are outside the audit boundary. The two supplemental audit outputs are removed after scanning solely to avoid self-referential hashes.

## Added files and classifications

| File or private path commitment | SHA-256 | Classification | Rationale |
|---|---|---|---|
| `data/rehearsal_plan/holoassist_exposure_supplement_v1.json` | `47060b97dbf80e84c9ec4c5f7db07e2e2f841269293e402954321e825c85e890` | `IGNORED_GOVERNANCE_ARTIFACT` | downstream manifest/ledger/audit governance artifact; ignored unless it reveals selected identity routing |
| `data/rehearsal_plan/holoassist_neutral_lineage_preflight_v1.json` | `8f0bab442ac2f2e0c97d6aa797b42428bf09615c6a3ca52d645d858e058264cc` | `IGNORED_GOVERNANCE_ARTIFACT` | downstream manifest/ledger/audit governance artifact; ignored unless it reveals selected identity routing |
| `data/rehearsal_plan/holoassist_opaque_group_commitment_v1.json` | `2b2b39da033e1b9be27901bea2a52bae5163f897844236113baed5bb4871d7ac` | `IGNORED_GOVERNANCE_ARTIFACT` | downstream manifest/ledger/audit governance artifact; ignored unless it reveals selected identity routing |
| `data/rehearsal_plan/untouched_test_group_ledger_v3_1_public_commitment.json` | `0e5b98ef6ec19d8ac5124cce53035eccab3f75955f38e7fe0999ab850ef40f15` | `IGNORED_GOVERNANCE_ARTIFACT` | downstream manifest/ledger/audit governance artifact; ignored unless it reveals selected identity routing |
| `data/rehearsal_plan/untouched_test_group_ledger_v3_public_commitment.json` | `ca4da76893a8bb09467fac1bf7f17e9455a5f9c721af8d6f17734003a77a022e` | `IGNORED_GOVERNANCE_ARTIFACT` | downstream manifest/ledger/audit governance artifact; ignored unless it reveals selected identity routing |
| `data/restricted/holoassist_opaque_group_universe_v1.json` | `bfed01c6cf5d1fb6ac5befb2959dacedeba649aa0d33112338e7eb49ae4bf529` | `IGNORED_GOVERNANCE_ARTIFACT` | custodian-private source-authority governance input; comparison against itself is excluded to avoid a tautological exposure |
| `custodian-private-path:f0a43b8813c7a9eb` | `0308e666e97e2b207782ffc62207ccc71f94c51b4f29ec75f2edf13eb8310e9f` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:345d5b4914f99363` | `a893212854181ae93d2e65e90ea885635b9376a7efb6b507aabb0e229df48f2f` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:7546d1ab915cb0af` | `0a4b678597181ba6593c6e6ef52ff92014dda901870bf9621f202e1d9c5846b1` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:d48594e31ee6a78c` | `398ef254558adff307f4c20b709d3ab78955ab30f4e3e069fbd0c755a2115041` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:27f38a0bec66997b` | `83488fecdcb2d6bd7b5193ab3adb7bc7eb3598639ab02defe8b4e09bbe2975be` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:454b76fc2bd5b9a4` | `dc2263b3812a4f33eb3ab9215f64c3dcbcbd401cc855e3d377f21bf3e13cf540` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:2f2f73e4f5c228e9` | `83785183305aafa78fca4fe916ee16a431dd84c1a921c1c9971e343c9261ea68` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:004f425a66202df2` | `6753f2409ef96d0f1e4976d02e9edbbb1b6fdf2e6df16e939df12c118b3da105` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:8108855729f7bd33` | `1ecaef267cdc49cf14ee7dbed599fabf5442fc77afacc4533b9eea7400af41c9` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:c843a7f434a89081` | `7c59523fa85e7517c8835f6289f03438871b3ee94f72aeb82aa1501999b1a11b` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:beb5a061844d6be0` | `565297253115e20d9a6549f9646a49eda08c3fbba31be16763b1b1a3aee0ccdd` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:ecd4b717147a4245` | `0365f86e3254d9019f796095a87377fd1bf981081085129d61a9f350d3245cc8` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:ff2ca1c1b23b1113` | `08b24348867406098a756cee309137b9c32d84b907812ee48bed2057c57ad169` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:94152ffc8ca0dff7` | `31bf2d6f1d659ee24e0fbc098cbf436a201fb7c2437a679da5c0368520d99a30` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:0e77db892c8c0701` | `a4007313b367210a5819c09975a3ac3ba012c0defac61fdef3f4bcba5dc86ffe` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:aae6c617810ac9c4` | `ffe5dbe58dde57f38fc4cdd3c1cea94acb70d01637602905e83ceaa72a4aa378` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:f1fd0f461260bfd8` | `6e03ef34dffeddbe5499fec35a4a5d29a1392777cca43c1ac44ab0deedac5fc8` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:6df6ce6415d4fbe7` | `ac7d9e677d162ac4097bd6e1c3434509d5ad66827508f288497ca733600958d2` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:31dc1ea10d4c7496` | `3b62076a090837a266fbba49e7f6cba9f189e744c1bbb5ad11041dd536b43638` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:2dadebaf9f8f910f` | `bbc23a3a8a98aba86643707df23105cbcd04438e37d2fd6015d3827438ee9c4b` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:3e92c5a4f9a710a8` | `4bbe2ac0a81f20ad22f0984c2ca6a32d53d9a16c06e0adb67ab0147f1d72b998` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:6a0efb2d857d6806` | `1dbb41f82ab16386c0714636dbb5c74615c88d4b58825d68c6e145cc355de9ec` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:efd296a1cb68e7d6` | `ee27d51293c116917af19e0e640a7815c9e486ef2b058842e74f39ec0510c3af` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:286f5c5481ea9b6a` | `01cb1496bbde8a0035531b26465de36d58af69fbfe64985d72b096d9670e526d` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:26b08378fdc6a6a9` | `6de617d7906650a01ed8c5e4acf302afca917d08cf6d2a502bf4953bda99f9c6` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:ec41650db7703972` | `f8f5043ae0370f4cfbc59c66e2ee4d6c571e983750e439a2c14bcdf0d4972fc2` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:15f16cdfd920641a` | `b7aa0dfb4932ee9cff677c105564b3701169d11d89ceb594b736f3a6bf3e466e` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:77c03b14654d8cb4` | `10c0a5aa5b2f9df20c80389e28e41ba4bbe834fad88e182c302b7bd9832a139d` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:b4228241fcacf1d9` | `c07bed15887728a9b5299720a52084c58806c797e74865b13a6002a90789cc83` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:d735318bbfb39943` | `6b504f7c32b2917b42d646d31abc340a2dc4ed658b33e99b4c6c6aae84756090` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:a5ee71deb61ef510` | `04c340b119665795f51196585341fd701b6397e95bc910dad8d82a6897c0b40f` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:6fcd9b0b98e16b3c` | `82c05ee1ab00e372d83f920d7c4180a27c1f0fd47064bc1d65c966b59445d300` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:23fb320e525aa5a3` | `f1620218297ee193dda8336d09bd75f8ce5faf869980a989dbd22a72f1a7d170` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:41f5225f2639c610` | `a50215472bba79f4d431d64ef4e05d3f82e4d6465fb8c2603a4759450834327e` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:d0c83d6c911eeba4` | `0b74f2135ca9d2caa26324d6522c5dca572ad46ff19d26ba528b8943960c70bb` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:c5ea5242586429cb` | `828996ff1b7f89aa44ca2ba8cca3c062f5b55c0d4af0f4b4de5a6f66449dd746` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:b4a82dfba2536fb2` | `2714ad7cbba6e2450385ff6a4d4d020b2f2e41afebb21b2a483de49006ec478f` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:f6f1868945cc49fe` | `17e918cf892dc72b8c212e97b1f3b7b49292529723cae202a7ee16a6bc3bb7fe` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:b3d31ac7610babcb` | `70d112661ef6b5aa8b5d0e45541cf8a5d2d20d15dca44fbcec4ddac597758ba1` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:89c18c56ed412d01` | `a38c64c2e136c43a1629ba520a7f88441738f445e1d006ac68b9fef16cc915ce` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `custodian-private-path:d2790517c9b42fea` | `9eaccce5d8d64d71d1ad0a00268648350ad4633760c11c267c0394f1b6c296d7` | `IGNORED_GOVERNANCE_ARTIFACT` | technical custody timing metadata; no media or semantic body was opened and this source-authority cache is not a routing exposure |
| `data/restricted/untouched_test_group_ledger_v3_1_private.json` | `11f87b1d3d39c5ca12859b7cb5385eaae923add03075a0bd0984155cf403a149` | `IGNORED_GOVERNANCE_ARTIFACT` | custodian-private source-authority governance input; comparison against itself is excluded to avoid a tautological exposure |
| `data/restricted/untouched_test_group_ledger_v3_private.json` | `d0295fd3081b45054941144f3f15f2499efad3c7e081cad6724e25f2b11b1f68` | `IGNORED_GOVERNANCE_ARTIFACT` | custodian-private source-authority governance input; comparison against itself is excluded to avoid a tautological exposure |
| `docs/review/holoassist_exposure_supplement_v1.md` | `92b944f0fbca104d4519d69a212bf6c5ff2d4ea82b97b60d35a122f3685d26f8` | `IGNORED_GOVERNANCE_ARTIFACT` | downstream review/governance artifact; ignored unless an exact selected identity and semantic-routing category co-occur |
| `docs/review/holoassist_neutral_lineage_preflight_v1.md` | `5d8e0861348ae44b8fc15f3cfeca958645d6340ac0d25edeeee96d7f15857aa4` | `IGNORED_GOVERNANCE_ARTIFACT` | downstream review/governance artifact; ignored unless an exact selected identity and semantic-routing category co-occur |
| `docs/review/holoassist_opaque_group_universe_v1.md` | `40e044201e43fdf7fd686b67af675920e3a2f963836f64f1b257d0f2acb02f54` | `IGNORED_GOVERNANCE_ARTIFACT` | downstream review/governance artifact; ignored unless an exact selected identity and semantic-routing category co-occur |
| `docs/review/untouched_test_group_ledger_v3.md` | `ab5ff629e512a96fcbf797cb735e4ee5396133a9d2949aca96444d914f838717` | `IGNORED_GOVERNANCE_ARTIFACT` | downstream review/governance artifact; ignored unless an exact selected identity and semantic-routing category co-occur |
| `docs/review/untouched_test_group_ledger_v3_1.md` | `3a9e43080a85446818ba82241812b4657613c79d0c3b31eccec974544785e3cd` | `IGNORED_GOVERNANCE_ARTIFACT` | downstream review/governance artifact; ignored unless an exact selected identity and semantic-routing category co-occur |

## Alias-closure and selected-roster result

- v2 alias graph components checked: 163
- Non-selected v2 contaminated closures: 0
- Selected v3.1 contaminated closures: 0
- Selected comparison status: `CLEAR`

No selected identity, alias, private path, salt, or commitment value is published. Only aggregate selected hit counts and status leave the custodian-private comparison boundary.

## Contamination events

None.

`SOURCE_EXPOSURE_ALIAS_MANIFEST_V2_SUPPLEMENTAL_AUDIT_PASS`
