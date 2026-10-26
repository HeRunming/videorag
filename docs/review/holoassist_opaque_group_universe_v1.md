# HoloAssist opaque group universe v1

**Final decision: `HOLOASSIST_OPAQUE_GROUP_UNIVERSE_REPAIR`**

Finalized offline on **October 15, 2026**, immediately after the stop
instruction. The interrupted Hugging Face API request produced no retained
response or header artifact, and no further network request was made.

## Sealed result

- Sealed opaque groups: **6**
- Required minimum: **6**
- Groups with both technical-file names present: **6**
- Groups with bounded `VideoMp4Timing.txt` bodies fetched: **0**
- Timing-closed groups with computed duration/frame count: **0**
- Video/audio objects downloaded or inspected: **0**
- Annotation or media files downloaded: **0**

Recording identities, folder paths, technical-file paths, and per-group
lineage are confined to the mode-`0600` restricted JSON. This review and the
public commitment reveal only counts, source lineage hashes/revision,
cryptographic commitments, and the decision.

## Construction and exclusions

The universe was derived from the locally retained Hugging Face metadata
snapshot. It contained 4,222 technical path entries: 2,111 timing-file names
and 2,111 pose-file names. A group is rooted at the normalized leading base
recording identity. Every folder variant carrying date/device/task suffixes is
merged under that base root; this is the conservative collision rule.

The four README examples were permanently excluded. The implementation also
regex-extracted recording identities from the locally retained project README
without parsing or retaining semantic fields, and unioned those identities
with the explicit exclusion set. Selection then used a frozen salted SHA-256
rank over path, available OID/size metadata, and timing/pose presence only.
No semantic token influenced ranking.

## Evidence and limitations

The source snapshot pins Hugging Face dataset revision
`7ad9269e82503f677cb4ec64d77a460d0790a6c4`. The mirror metadata declares
`apache-2.0` and reports the dataset as not gated, while official project
evidence declares `CDLA-Permissive-2.0`; the discrepancy is preserved rather
than resolved.

The retained 1,000-entry HF tree page supplied exact paths, OIDs, sizes, and
types where available; those values are recorded only in the sealed file.
The larger HF info snapshot supplied technical filenames but no OID/size for
those sibling entries. The interrupted live API request left no completed
artifact, so missing OIDs/sizes were not invented.

No bounded timing text was successfully fetched before the stop. Therefore no
selected group has defensible frame count or duration evidence. Presence of a
timing filename is not treated as timing closure. Likewise, no video/audio
claim is made because no object or stream evidence was obtained.

## Why REPAIR

The count threshold is met, but the required technical timing closure is not:
**0 of 6** selected groups have parsed timing bodies. The honest final marker
is therefore:

**`HOLOASSIST_OPAQUE_GROUP_UNIVERSE_REPAIR`**
