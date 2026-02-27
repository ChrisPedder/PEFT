# Enable MFA on Cognito User Pool

**Epic:** Security Hardening

**Points:** 2

## User Story

As a platform operator, I want users to have multi-factor authentication so that compromised passwords alone cannot grant account access.

## Acceptance Criteria

- [ ] MFA is enabled on the Cognito User Pool (at least `OPTIONAL`, ideally `REQUIRED`)
- [ ] TOTP (authenticator app) is supported as a second factor
- [ ] Password policy is strengthened: minimum 12 characters, symbols required
- [ ] Frontend handles MFA challenge flow (TOTP setup + verification)
- [ ] Existing users can enrol in MFA

## Technical Notes

CDK changes in `infra/lib/auth-stack.ts`:
```typescript
mfa: cognito.Mfa.OPTIONAL, // or REQUIRED
mfaSecondFactor: { sms: false, otp: true },
passwordPolicy: {
  minLength: 12,
  requireUppercase: true,
  requireDigits: true,
  requireSymbols: true,
},
```

Frontend changes: The `amazon-cognito-identity-js` SDK handles MFA challenges via `authenticateUser` callback. The `onSuccess` callback receives a session; a new `mfaSetup` or `totpRequired` callback provides the TOTP secret or prompts for a code. The frontend needs a new UI section for:
1. TOTP setup (display QR code / secret, verify first code)
2. TOTP verification during login

**Warning:** Changing MFA to `REQUIRED` will lock out existing users who haven't enrolled. Use `OPTIONAL` first and migrate users, or handle the `MFA_SETUP` challenge in the frontend.

## Implementation Subtasks

- [ ] Update Cognito User Pool config in `auth-stack.ts` (MFA + password policy)
- [ ] Add TOTP setup UI to frontend (QR code display, verification input)
- [ ] Handle `SOFTWARE_TOKEN_MFA` challenge in `auth.ts` sign-in flow
- [ ] Handle `MFA_SETUP` challenge for first-time MFA enrolment
- [ ] Update `manage_users.py` if needed for MFA admin operations
- [ ] Test with existing and new users
- [ ] Update CDK tests

## Status

Todo | In Progress | In Review | **Done**
