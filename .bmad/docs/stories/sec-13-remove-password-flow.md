# Remove userPassword auth flow from Cognito

**Epic:** Security Hardening

**Points:** 1

## User Story

As a platform operator, I want to disable the plaintext password auth flow so that passwords are only transmitted via the cryptographically secure SRP protocol.

## Acceptance Criteria

- [ ] `userPassword: true` is removed from the Cognito app client auth flows
- [ ] Only `userSrp: true` remains enabled
- [ ] Frontend login continues to work (it already uses SRP via `amazon-cognito-identity-js`)
- [ ] `manage_users.py` still works for admin operations (uses admin APIs, not user auth flows)

## Technical Notes

Change in `infra/lib/auth-stack.ts` lines 29-32:
```typescript
authFlows: {
  userSrp: true,
  // userPassword removed — SRP is the secure alternative
},
```

The `amazon-cognito-identity-js` SDK uses SRP by default (`authenticateUser` with `AuthenticationDetails`), so the frontend should be unaffected. Verify by testing login after deployment.

**Note:** If any scripts use `InitiateAuth` with `USER_PASSWORD_AUTH`, they will break. Check `manage_users.py` — it uses `admin_set_user_password` which is an admin API and unaffected.

## Implementation Subtasks

- [ ] Remove `userPassword: true` from `auth-stack.ts`
- [ ] Deploy and verify frontend login works
- [ ] Update CDK tests

## Status

~~Todo~~ | ~~In Progress~~ | ~~In Review~~ | **Done**
