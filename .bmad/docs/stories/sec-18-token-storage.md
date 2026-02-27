# Review and harden token storage strategy

**Epic:** Security Hardening

**Points:** 2

## User Story

As a platform operator, I want authentication tokens stored as securely as possible so that a future XSS vulnerability does not expose long-lived credentials.

## Acceptance Criteria

- [ ] Token storage strategy is explicitly chosen (not relying on SDK default)
- [ ] If using localStorage, this is documented as an accepted risk
- [ ] If switching to sessionStorage or in-memory, tokens clear on tab close / refresh
- [ ] Refresh token lifetime is reviewed and set to an appropriate duration
- [ ] Sign-out clears all stored tokens

## Technical Notes

`amazon-cognito-identity-js` accepts a custom `Storage` option:

```typescript
userPool = new CognitoUserPool({
  UserPoolId: config.cognitoUserPoolId,
  ClientId: config.cognitoClientId,
  Storage: window.sessionStorage, // tokens cleared on tab close
});
```

Options:
1. **`sessionStorage`**: Cleared when tab closes. Users must re-login per session. More secure.
2. **`In-memory`**: Cleared on any navigation/refresh. Most secure but worst UX.
3. **`localStorage`** (current default): Persists across sessions. Most convenient but tokens accessible to XSS.

Recommendation: Switch to `sessionStorage` as a pragmatic middle ground. Combined with CSP (sec-17) and the existing XSS-safe DOM practices, the risk is well-mitigated.

Also review refresh token expiry in Cognito — the default is 30 days which is long. Consider reducing to 7 days or less.

## Implementation Subtasks

- [ ] Pass explicit `Storage: window.sessionStorage` to `CognitoUserPool` in `auth.ts`
- [ ] Test login/logout flow (tokens should clear on tab close)
- [ ] Review and adjust Cognito refresh token expiry in `auth-stack.ts`
- [ ] Update tests

## Status

**Todo** | In Progress | In Review | Done
