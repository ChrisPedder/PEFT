# Pin all GitHub Actions to commit SHAs

**Epic:** Security Hardening

**Points:** 3

## User Story

As a platform operator, I want GitHub Actions pinned to immutable commit SHAs so that a compromised action cannot execute arbitrary code in my CI/CD pipelines.

## Acceptance Criteria

- [ ] Every `uses:` reference in all 6 workflow files uses a full 40-character commit SHA
- [ ] Each SHA has a version comment (e.g. `# v4.1.1`)
- [ ] Dependabot or Renovate is configured to propose SHA updates for Actions
- [ ] All workflows still pass after pinning

## Technical Notes

Actions to pin across all workflow files:
- `actions/checkout@v4` → look up latest v4.x SHA
- `actions/setup-python@v5` → look up latest v5.x SHA
- `actions/setup-node@v4` → look up latest v4.x SHA
- `aws-actions/configure-aws-credentials@v4` → look up latest v4.x SHA
- `codecov/codecov-action@v5` → look up latest v5.x SHA

Format: `uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11 # v4.1.1`

To find SHAs: `git ls-remote --tags https://github.com/actions/checkout | grep 'v4\.'`

Add a `.github/dependabot.yml` with:
```yaml
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

## Implementation Subtasks

- [ ] Look up current commit SHAs for all 5 action references
- [ ] Update `ci.yml`
- [ ] Update `deploy.yml`
- [ ] Update `scrape.yml`
- [ ] Update `process.yml`
- [ ] Update `train.yml`
- [ ] Update `update-model.yml`
- [ ] Add `.github/dependabot.yml` for GitHub Actions updates
- [ ] Verify all workflows pass

## Status

~~Todo~~ | ~~In Progress~~ | ~~In Review~~ | **Done**
