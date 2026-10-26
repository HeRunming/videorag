---
pretty_name: AV-TRACE
license: apache-2.0
task_categories:
  - video-question-answering
  - visual-question-answering
language:
  - en
tags:
  - long-video
  - audio-visual
  - retrieval-augmented-generation
  - agents
  - benchmark
  - evidence-grounding
  - research-in-progress
---

# AV-TRACE

AV-TRACE is a research project for diagnosing evidence acquisition, grounded
generation, insufficiency recognition, stopping, and recovery in agentic
long-video audiovisual RAG.

## Current release status

This Hugging Face repository,
`blackBOX25I47/videorag`, is a **metadata-only, pre-benchmark research
release**. It does not currently contain a validated benchmark corpus or
redistributed source videos.

As of 2026-10-23:

```text
H1 families = 0
H2 families = 0
Gate A = REPAIR
scientific episodes = 0
```

The repository therefore must not be described as a finished benchmark,
human-gold dataset, or completed learned-agent evaluation.

## What this repository contains

- project-authored research-state and migration metadata;
- public-safe provenance, policy, and reconstruction manifests;
- the post-migration CVPR work queue;
- integrity hashes for the corresponding public code snapshot;
- third-party data and redistribution notices.

## What this repository does not contain

- raw or clipped third-party video/audio;
- EPIC-KITCHENS, CaptainCook4D, LongVideoBench, lecture, or NOAA payloads;
- model weights;
- dense private indexes or source-substitutive features;
- private reviewer identities, test-source identities, labels, or ledgers;
- credentials, authorization receipts, runtime attempts, or gateway output.

The absence of these files is intentional. A public or private Hugging Face
repository does not override source licenses, consent, privacy, annotation
authority, or redistribution restrictions.

## Scientific scope

AV-TRACE uses the diagnostic stack:

```text
Acquire -> Ground -> Act
```

and the matched states:

```text
CLEAN / BLOCKED / RESTORED / NO_TRIGGER
```

The intended final corpus target is at least 60
`H2_HUMAN_ADJUDICATED_SATURATION_AUDITED` families from at least 30 source
groups, including at least 12 untouched test groups. These targets have not
yet been achieved.

## Code

The public code repository is intended for:

```text
https://github.com/HeRunming/videorag
```

Project-authored code and documentation are licensed under Apache-2.0.
Third-party assets retain their own terms.

## Data access and reconstruction

Where source-specific use is authorized, users should obtain third-party
media and model assets directly from their official upstream locations at the
pinned identities described in the manifests. AV-TRACE does not grant access
to or redistribution rights for those assets.

## Citation

No paper citation is frozen yet. Please cite the eventual AV-TRACE paper and
release version once they are available. Until then, reference this repository
as a research-in-progress metadata release.

## Responsible use

Do not use project metadata to reconstruct private identities, bypass source
access controls, infer untouched evaluation sources, or redistribute
restricted media. Report licensing, privacy, or security concerns through the
project repository's security contact.
