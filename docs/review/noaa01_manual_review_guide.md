# NOAA-01 restricted manual-review guide

## Scope and boundary

This packet is a first-pass human review workflow for exactly three restricted
NOAA-01 pilot assets: `cand-049`, `cand-051`, and `cand-052`.

The queue contains **18 windows**, six per asset. It balances routing
hypotheses for speech, non-speech audio, visual change, and combined evidence,
and spaces selections across each source timeline. Task 80 measurements and
labels are **routing hypotheses only**. They are not human judgments, gold
labels, evidence-validity findings, or modality-necessity findings.

The blank template contains no completed human answers. Exact intervals and
source identities remain only under `data/restricted/noaa01/`.

## Safety properties

- The server binds to `127.0.0.1` only. It never binds a public interface.
- Media routes are keyed by the three allowlisted candidate IDs. A request
  cannot supply a filesystem path.
- The player receives byte ranges from the original local MP4. The app does not
  decode or write clips, audio, frames, thumbnails, transcripts, contact
  sheets, or waveforms.
- The app has no outbound network integration. Browser requests are same-origin
  requests to the loopback server.
- Queue, template, saved decisions, and exports are restricted files written
  with mode `0600`.
- Responses use `Cache-Control: no-store`; the player also requests no download
  or remote playback controls. Reviewers must not download, screen-record,
  transcribe, or otherwise copy the source media.

## Validate without starting a server

From the repository root:

```bash
python tools/noaa_manual_review_app.py --dry-run
```

This validates the deterministic queue, blank template, exact input identities,
media audit status, allowlist, source files, temporal separation, and category
coverage. The output must say `"listener_started": false`.

To intentionally regenerate the two delivered restricted packet files and then
validate them:

```bash
python tools/noaa_manual_review_app.py --rebuild-packet --dry-run
```

Do not use `--rebuild-packet` after review has begun unless packet regeneration
has been explicitly authorized. It does not overwrite saved decisions, but it
can make an existing decision file incompatible if the frozen queue changes.

## Start a review session

```bash
python tools/noaa_manual_review_app.py
```

Open the loopback URL printed by the command in a browser on the same machine.
To choose another local port:

```bash
python tools/noaa_manual_review_app.py --port 8876
```

Never proxy, tunnel, port-forward, container-publish, or remotely expose this
listener.

## Review procedure

For every queued window:

1. Select the window in queue order.
2. Use **Seek to interval start** or **Replay interval**. Confirm the player
   stops at the routed interval end.
3. Judge the media independently. Do not infer an answer from the displayed
   routing hypothesis.
4. Record:
   - whether media loads and seeks correctly;
   - speech presence and intelligibility;
   - non-speech audio presence and type;
   - meaningful visual information and visual type;
   - a plausible question/evidence seed;
   - candidate modality role;
   - for each of `V`, `S`, and `A`, whether it is potentially necessary,
     merely co-occurring, not selected, or uncertain;
   - whether to keep or adjust the evidence interval;
   - sensitive, distressing, or private-content status;
   - accept, reject, or defer;
   - confidence and notes.
5. Click **Save / resume** before leaving the window.

Use `not_applicable` for speech intelligibility when speech is judged absent.
For modality necessity, use `not_selected` for modalities excluded by the
candidate modality role. “Potentially necessary” is still a review hypothesis;
it is not a completed counterfactual modality-ablation result.

If an interval needs adjustment, enter times on the original asset timeline.
The server rejects reversed, negative, or beyond-duration adjustments.

If sensitive, distressing, or private content may be present, mark it and
prefer `defer` unless the applicable handling policy clearly permits further
use. Do not reproduce sensitive details in notes.

## Resume and export

Saved state is written atomically to:

```text
data/restricted/noaa01/review/noaa01_manual_review_decisions.json
```

Restarting the app loads that file and resumes the queue. The application
rejects state whose packet ID, order, source identity, fields, enums, or
interval bounds do not match the packet.

Click **Export JSON**, or run:

```bash
python tools/noaa_manual_review_app.py --export
```

The deterministic export is:

```text
data/restricted/noaa01/review/noaa01_manual_review_export.json
```

The export preserves queue order, distinguishes complete from partial records,
contains no run timestamp, and therefore produces identical bytes for
identical saved state. It remains restricted and is not a public-release
artifact.

## Stop and verify

Stop the server with `Ctrl-C`. Optionally rerun:

```bash
python tools/noaa_manual_review_app.py --dry-run
```

The dry run validates the delivered packet but does not alter decisions and
does not start a listener.
