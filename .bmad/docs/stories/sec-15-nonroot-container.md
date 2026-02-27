# Run inference container as non-root user

**Epic:** Security Hardening

**Points:** 1

## User Story

As a platform operator, I want the inference Lambda container to run as a non-root user so that container escape vulnerabilities have reduced impact.

## Acceptance Criteria

- [ ] The Dockerfile creates a non-root user and switches to it
- [ ] The application starts successfully under the non-root user
- [ ] The Lambda Web Adapter (LWA) extension works with the non-root user
- [ ] The Docker image builds and deploys successfully

## Technical Notes

Add to `backend/inference/Dockerfile` before the `CMD`:
```dockerfile
RUN adduser --disabled-password --gecos '' --home /app appuser && \
    chown -R appuser:appuser /app
USER appuser
```

The Lambda Web Adapter copies to `/opt/extensions/lambda-adapter` which is owned by root. Lambda extensions run in the same process namespace but are started by the Lambda runtime, so they should work regardless of the app user. Verify by testing after deployment.

If the LWA extension fails, an alternative is to use `--read-only` filesystem and ensure `/tmp` is writable (Lambda provides a writable `/tmp`).

## Implementation Subtasks

- [ ] Add non-root user to Dockerfile
- [ ] Build and test locally
- [ ] Deploy and verify Lambda starts correctly
- [ ] Verify LWA extension works

## Status

~~Todo~~ | ~~In Progress~~ | ~~In Review~~ | **Done**
