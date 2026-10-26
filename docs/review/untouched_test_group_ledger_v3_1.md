# Untouched Test Group Ledger v3.1

- Final marker: `UNTOUCHED_TEST_GROUP_LEDGER_V3_1_FROZEN_PRIVATE_READY`
- Identity-free committed conditional groups: **12**
- Dataset lineages: **3 / 3 required**
- Lineage composition: **ASSEMBLY101 7, EPIC 2, HOLOASSIST 3**
- Complete production closures: **12 / 12 required**
- Selected HoloAssist sealed commitments: **3**
- Test construction locked: **true**
- Distribution locked: **true**
- Public identities: **none**

## Decision

**FROZEN_PRIVATE_READY**.

The v3.1 commitment roster contains twelve conditional production closures across Assembly101, EPIC, and HoloAssist. Three HoloAssist commitments replace three frozen v3 commitments by commitment-hash order only.

Historical v3 remains unmodified and retains marker `UNTOUCHED_TEST_GROUP_LEDGER_V3_REPAIR`.

## Commitment-only selection

The repair selected the three lexicographically lowest HoloAssist commitment hashes and removed the three lexicographically highest frozen-v3 group commitment hashes. No identity, title, task, label, transcript, media, timing path, annotation, or semantic field participated.

## HoloAssist conditional boundary

All selected HoloAssist commitments are timing-closed and absent from frozen manifest-v2 identities and the permanent official README example exclusions. Exact video access and exact audio access remain unresolved; every group therefore remains CONDITIONAL.

## Commitments

- Selection-rule commitment: `af7f101137b91949507e8e3e3e29dbbc96f16527d4259df902f6a70d7d9e7bc6`
- Sealed private-roster commitment: `8d36f0c70233c0d3893f2b7b48bf8b1ba1dbb0de005ddded91b68a9b6b12e087`
- Full governance split-lock: `53135211c4a6903078cdea7bef7380fbd37bd6fbeed851f623a75709d8ad8ac2`
- Per-group private commitments: **12**

## Preserved governance

All v3 locks, claims, custodian reveal rules, and replacement policy are preserved exactly. Identities and exact technical timing evidence remain only in the restricted private ledger. The full public governance surface is covered by the recomputed split-lock.

`UNTOUCHED_TEST_GROUP_LEDGER_V3_1_FROZEN_PRIVATE_READY`
