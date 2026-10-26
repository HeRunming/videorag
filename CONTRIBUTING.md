# Contributing to AV-TRACE

AV-TRACE is a research prototype with a strict separation between public
source material and restricted research inputs. Contributions are welcome only
when that separation is preserved.

## Before opening a change

1. Do not add real media, dataset payloads, model weights, checkpoints,
   credentials, tokens, authorization receipts, private review ledgers,
   raw attempts, failure capsules, or internal orchestration logs/prompts/results.
2. Do not assume that a dataset, model, annotation, or media license applies to
   the repository's code. Keep code licensing and third-party artifact rights
   separate.
3. Use synthetic or deliberately minimal fixtures. A public URL, a repository
   badge, or research access does not by itself grant redistribution rights.
4. Avoid machine-specific absolute paths, internal proxy/domain names, private
   governance identifiers, participant identities, and unpublished test-set
   identities.
5. Never place a live secret in an example, test, issue, pull request, or
   terminal transcript.

Public design plans may live under `data/rehearsal_plan/`, but execution
attempts and private governance records in that tree remain excluded. The
release boundary is documented in
`docs/migration/github_release_boundary.md`.

## Local checks

Run the model-free public-release audit before proposing a release:

```bash
python scripts/audit_public_release.py --check \
  --json-output /tmp/av-trace-public-release-audit.json
```

The audit does not use Git state and does not modify the repository except when
you explicitly request a JSON report path. A failing audit is expected while
the repository-level code license decision remains unresolved; all other
findings should be reviewed and removed, redacted, excluded, or documented in
a narrow allowlist with a concrete reason.

Run focused tests for modified components and, when practical:

```bash
pytest -q
```

## Pull requests

Describe:

- the scientific or engineering purpose;
- the files and release surfaces affected;
- test commands and results;
- any third-party code, data, model, media, or annotation dependency;
- the applicable license or terms evidence and whether redistribution is
  actually permitted;
- known limitations, negative results, and fail-closed behavior.

Do not weaken gates or rewrite negative results as successes. Do not include
restricted evidence merely to make a test reproducible; replace it with a
synthetic fixture or provide a separately documented, authorized acquisition
procedure.

## Issues

Use issues for public, nonsensitive bug reports and design discussion. Do not
post secrets, credentials, private access records, participant information,
restricted dataset details, unpublished test identities, or exploitable
security findings. Follow `SECURITY.md` for private disclosure.
