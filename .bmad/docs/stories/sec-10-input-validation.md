# Add input validation bounds on API request fields

**Epic:** Security Hardening

**Points:** 1

## User Story

As a platform operator, I want API request fields to have validated bounds so that users cannot cause cost exhaustion or denial of service via oversized requests.

## Acceptance Criteria

- [ ] `question` field has a maximum length of 4000 characters and minimum of 1
- [ ] `max_tokens` is bounded between 1 and 4096
- [ ] `temperature` is bounded between 0.0 and 2.0
- [ ] Requests exceeding bounds return 422 with a clear validation error
- [ ] Tests cover boundary validation

## Technical Notes

Update `AskRequest` in `backend/inference/app.py`:

```python
from pydantic import BaseModel, Field

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    max_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
```

Pydantic + FastAPI will automatically return 422 for out-of-bounds values.

## Implementation Subtasks

- [ ] Update `AskRequest` model with `Field` constraints
- [ ] Add tests for boundary values (max question length, max_tokens extremes, etc.)
- [ ] Verify 422 response format matches frontend error handling

## Status

~~Todo~~ | ~~In Progress~~ | ~~In Review~~ | **Done**
