# Pin actionlint download with checksum verification

**Epic:** Security Hardening

**Points:** 1

## User Story

As a platform operator, I want third-party binary downloads in CI to be pinned and checksum-verified so that a compromised release cannot execute arbitrary code.

## Acceptance Criteria

- [ ] `actionlint` is downloaded at a pinned version (not `latest`)
- [ ] The downloaded tarball is verified against a known SHA-256 checksum
- [ ] The CI lint step still passes

## Technical Notes

Current code in `.github/workflows/ci.yml` lines 63-67 dynamically resolves `latest`:
```bash
curl -sL "https://github.com/rhysd/actionlint/releases/latest/download/actionlint_$(curl -sL ...)/..."
```

Replace with:
```bash
ACTIONLINT_VERSION="1.7.7"
ACTIONLINT_CHECKSUM="<sha256>"
curl -sL "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz" -o actionlint.tar.gz
echo "${ACTIONLINT_CHECKSUM}  actionlint.tar.gz" | sha256sum --check
tar xz -C "$HOME/.local/bin" actionlint < actionlint.tar.gz
```

Look up the latest version and checksum from the [actionlint releases page](https://github.com/rhysd/actionlint/releases).

## Implementation Subtasks

- [ ] Look up latest stable actionlint version and SHA-256
- [ ] Update the install step in `ci.yml` with pinned version + checksum
- [ ] Verify the lint step passes

## Status

~~Todo~~ | ~~In Progress~~ | ~~In Review~~ | **Done**
