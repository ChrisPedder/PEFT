# Add rate limiting to the inference API

**Epic:** Security Hardening

**Points:** 3

## User Story

As a platform operator, I want per-user rate limiting on the inference API so that individual users cannot cause cost exhaustion or denial of service.

## Acceptance Criteria

- [ ] Rate limiting is applied to `/api/ask` (the Bedrock-invoking endpoint)
- [ ] Rate limits are per-user (based on JWT `sub` claim)
- [ ] Exceeding the rate limit returns 429 with a `Retry-After` header
- [ ] Rate limit is configurable via environment variable
- [ ] Tests cover rate limit enforcement

## Technical Notes

Two approaches:

**Option A — Application-level (`slowapi`):**
- Add `slowapi` to requirements.txt
- Configure per-user rate limit (e.g. 10 requests/minute) keyed on JWT `sub`
- Pros: Simple, per-user, visible in application logs
- Cons: Only applies to this Lambda; resets on cold start

**Option B — CloudFront WAF:**
- Attach an AWS WAF WebACL to the CloudFront distribution
- Add a rate-based rule (e.g. 100 requests/5 minutes per IP)
- Pros: Applies before Lambda invocation (saves cost), persistent across cold starts
- Cons: IP-based not user-based, requires WAF subscription

Recommended: Implement both. WAF for coarse IP-based protection, `slowapi` for fine-grained per-user limits.

For `slowapi`:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

def get_user_id(request: Request) -> str:
    # Extract from JWT or fall back to IP
    ...

limiter = Limiter(key_func=get_user_id)
app.state.limiter = limiter

@app.post("/api/ask")
@limiter.limit("10/minute")
async def ask(...):
```

## Implementation Subtasks

- [ ] Add `slowapi` to `requirements.txt`
- [ ] Configure per-user rate limiter in `app.py`
- [ ] Add `RATE_LIMIT` env var (default: `10/minute`)
- [ ] Add tests for rate limit enforcement
- [ ] (Optional) Add WAF WebACL to CloudFront in `frontend-stack.ts`

## Status

Todo | In Progress | In Review | **Done**
