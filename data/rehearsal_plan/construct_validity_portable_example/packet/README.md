# AV-TRACE deferred construct-validity packet

This packet is an unfilled assignment. It is **not human review** and contains
no human-gold labels.

## Offline workflow

1. Copy the entire packet directory and the referenced source media to a
   reviewer workstation. If `media/` is present, verify it against
   `packet_manifest.json`.
2. Before distributing any role directory, update
   `coordinator/source_exposure_ledger.json` with every known prior exposure,
   assign real pseudonymous reviewer IDs in
   `coordinator/reviewer_assignments.json`, validate source-group conflicts,
   and freeze the assignment ledger. The generated blank draft is deliberately
   not distributable.
3. Preserve the blind alternative finder's packet until their full-source
   search is finished; do not disclose the machine-preferred SES first.
4. Give each person only their directory under `reviewer_packets/<family>/`;
   never give the blind finder the coordinator directory or another role's
   packet.
5. Edit that role's `form.json`; set `completion_status` to `completed`, fill
   every required field, and do not alter IDs or assignment provenance.
6. Validators must not read one another's decisions before submission.
7. The adjudicator acts only after all four pre-adjudication role forms are
   complete.
8. Freeze adjudication, then give the saturation auditor only their directory
   and the source. Never disclose accepted/preferred SESs, machine ranks, or
   validator/adjudicator decisions.
9. Append each actual packet exposure to the source exposure ledger. Copy the
   packet back and run `tools/construct_validity_import.py`.

Only the importer may derive H1/H2 status. Manually typing a human tier into a
machine registry is invalid.
