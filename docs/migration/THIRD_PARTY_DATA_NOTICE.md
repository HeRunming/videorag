# Third-party data, media, model, and annotation notice

**As of:** 2026-10-23  
**Status:** boundary notice; not a complete attribution file and not legal
advice.

AV-TRACE research materials reference third-party datasets, media, annotations,
models, metadata, and services. Those artifacts retain their own terms. Their
availability to a researcher or their mention in code/documentation does not
mean that they may be redistributed in a public GitHub repository.

## Public repository boundary

The public repository must not contain:

- acquired raw or transformed third-party audio/video;
- dataset archives or payloads requiring registration, agreement, or restricted
  research access;
- model weights or checkpoints;
- credentials, cookies, authorization or approval receipts;
- private labels, participant identities, untouched-test identities, raw
  attempts, or private governance ledgers;
- dense derivatives that substitute for restricted source content unless
  separately reviewed and expressly permitted.

Public code may describe an acquisition or processing interface, but users must
obtain artifacts themselves from the authorized source and comply with the
applicable terms.

## EPIC and other research-only/gated sources

EPIC-KITCHENS/EPIC-SOUNDS materials are treated here as restricted,
research-bound development inputs. Project records use an **"EPIC CC BY-NC /
source-specific terms"** shorthand for relevant components; that shorthand is
not a file-level clearance. The exact artifact and current official terms must
be checked before each use. **No EPIC raw media or restricted derivative is
part of the public GitHub release.**

The same fail-closed approach applies to Ego4D/Ego-Exo4D, Assembly101,
CaptainCook4D, licensed benchmark sources, and any source requiring an access
agreement or having uncertain onward-redistribution rights.

This noncommercial/research boundary applies to the applicable third-party
artifact. It must not be copied onto original AV-TRACE code as though it were a
software license.

## Government, public, and openly licensed sources

Government provenance, a public URL, or a Creative Commons label is not a
blanket clearance. Item-level review still must cover credited third-party
material, trademarks, endorsement, privacy/publicity, exact license version,
attribution, modification notices, and redistribution scope.

## Required release record

For each third-party artifact actually included in a future public package,
record at minimum:

- artifact path and version/hash;
- upstream source and rightsholder/licensor;
- exact license or grant and version;
- access and redistribution decision;
- required attribution and modification notice;
- privacy/safety review where people or voices are present;
- reviewer and decision date.

If those facts are missing or ambiguous, exclude the artifact. See
`docs/data/license_risk_register.md` for the project's broader rights and
privacy risk framework.
