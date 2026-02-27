# Enable JWT audience verification

**Epic:** Security Hardening

**Points:** 1

## User Story

As a platform operator, I want JWT tokens to be validated against the specific app client ID so that tokens from other Cognito clients cannot be used.

## Acceptance Criteria

- [ ] `jwt.decode` in `app.py` verifies the `aud` claim against the Cognito app client ID
- [ ] A `COGNITO_CLIENT_ID` environment variable is added to the Lambda function
- [ ] Tokens issued for a different client ID are rejected with 401
- [ ] Tests cover the audience verification path

## Technical Notes

- Add `COGNITO_CLIENT_ID` env var to `inference-stack.ts` Lambda environment (value: `authStack.userPoolClientId`)
- In `app.py`, read `COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "")` and pass to `jwt.decode`:
  ```python
  claims = jwt.decode(token, key, algorithms=["RS256"], issuer=issuer, audience=COGNITO_CLIENT_ID)
  ```
- Remove `options={"verify_aud": False}`
- If migrating to PyJWT (sec-03), handle this in the same PR

## Implementation Subtasks

- [ ] Add `COGNITO_CLIENT_ID` env var to Lambda in `inference-stack.ts`
- [ ] Read env var in `app.py` and pass as `audience` to `jwt.decode`
- [ ] Remove `options={"verify_aud": False}`
- [ ] Add test for token with wrong audience being rejected
- [ ] Update CDK tests if needed

## Status

~~Todo~~ | ~~In Progress~~ | ~~In Review~~ | **Done**
