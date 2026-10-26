# Security Policy

## Supported surface

Until a formal public release is approved, security fixes are prioritized for
the current default branch and the public-release tooling. Historical local
artifacts, restricted data, third-party models, and internal orchestration
records are not public distribution surfaces.

## Reporting a vulnerability or sensitive exposure

Do **not** open a public issue for:

- leaked credentials, tokens, private keys, cookies, or authorization records;
- internal proxy/domain or infrastructure details;
- participant or reviewer identity exposure;
- restricted media, model, dataset, private ledger, or untouched-test leakage;
- a vulnerability that could expose local files or execute untrusted content.

Use GitHub's private vulnerability reporting feature if it is enabled for the
repository. If it is not enabled, contact the repository owner or organizational
security contact through an already established private channel and ask for a
secure reporting route. Do not attach sensitive payloads until that route is
confirmed.

Include a concise description, affected revision or file, reproduction steps
using synthetic data where possible, impact, and suggested mitigation. Remove
live secrets and personal data from logs and screenshots.

## If a secret or restricted artifact is exposed

1. Stop sharing the material publicly.
2. Revoke or rotate the credential through its provider; deleting a file is not
   sufficient.
3. Quarantine the affected release or artifact.
4. Preserve only the minimum private incident evidence needed for response.
5. Review repository history, release archives, CI logs, caches, mirrors, and
   downstream copies.
6. Notify the relevant data-rights, privacy, or security owner when restricted
   data or participant information is involved.

The public audit in `scripts/audit_public_release.py` is a preventive control,
not a substitute for provider-side secret scanning, history review, dependency
security review, or incident response.
