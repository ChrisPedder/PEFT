# Stop leaking internal error details to clients

**Epic:** Security Hardening

**Points:** 1

## User Story

As a platform operator, I want error responses to be generic so that internal infrastructure details are not exposed to attackers.

## Acceptance Criteria

- [ ] The generic exception handler in `/api/ask` returns a fixed message without the raw exception text
- [ ] JWT error messages return `"Invalid token"` without the specific `JWTError` message
- [ ] The `/api/health` endpoint no longer returns the model ID
- [ ] Full exception details are logged server-side (via `print` or `logging`)
- [ ] Tests are updated for the new error message format

## Technical Notes

Changes in `backend/inference/app.py`:

1. Line 151-153: Change to `raise HTTPException(status_code=500, detail="An internal error occurred")` and `print(f"Bedrock error: {e}")` for server-side logging.
2. Line 102: Change to `raise HTTPException(status_code=401, detail="Invalid token")`.
3. Lines 111-113: Change health response to `{"status": "ok"}` without `model_id`.

## Implementation Subtasks

- [ ] Replace generic exception handler with fixed error message + server-side logging
- [ ] Replace JWT error handler with generic message + server-side logging
- [ ] Remove `model_id` from health endpoint response
- [ ] Update tests for new response formats

## Status

~~Todo~~ | ~~In Progress~~ | ~~In Review~~ | **Done**
