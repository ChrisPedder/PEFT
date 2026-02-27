# Pin deploy workflow checkout to CI-validated commit SHA

**Epic:** Security Hardening

**Points:** 1

## User Story

As a platform operator, I want the deploy workflow to check out the exact commit that CI validated so that a race condition cannot deploy an untested commit.

## Acceptance Criteria

- [ ] `deploy.yml` checkout step uses `ref: ${{ github.event.workflow_run.head_sha }}`
- [ ] `persist-credentials: false` is set on checkout
- [ ] The deploy workflow still triggers correctly after CI passes on main

## Technical Notes

Change in `.github/workflows/deploy.yml`:

```yaml
- uses: actions/checkout@<sha>
  with:
    ref: ${{ github.event.workflow_run.head_sha }}
    persist-credentials: false
```

This ensures the deploy runs against the exact commit that CI validated, closing the TOCTOU (time-of-check-to-time-of-use) window.

Also add `persist-credentials: false` to all other workflow checkout steps (see L-6 in the security review).

## Implementation Subtasks

- [ ] Update `deploy.yml` checkout to use `workflow_run.head_sha`
- [ ] Add `persist-credentials: false` to all checkout steps across all workflows
- [ ] Verify deploy workflow triggers and succeeds

## Status

~~Todo~~ | ~~In Progress~~ | ~~In Review~~ | **Done**
