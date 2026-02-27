# Add Content Security Policy and security headers

**Epic:** Security Hardening

**Points:** 3

## User Story

As a platform operator, I want a Content Security Policy and security headers so that injected scripts cannot execute and common web attacks are mitigated.

## Acceptance Criteria

- [ ] CloudFront returns a `Content-Security-Policy` header on all responses
- [ ] CSP allows `'self'` for scripts, styles, and connections plus the Cognito IDP domain
- [ ] `X-Content-Type-Options: nosniff` is set
- [ ] `X-Frame-Options: DENY` is set
- [ ] `Referrer-Policy: strict-origin-when-cross-origin` is set
- [ ] `Strict-Transport-Security` header is set
- [ ] The frontend continues to work without CSP violations

## Technical Notes

Add a `ResponseHeadersPolicy` to the CloudFront distribution in `infra/lib/frontend-stack.ts`:

```typescript
const responseHeadersPolicy = new cloudfront.ResponseHeadersPolicy(this, "SecurityHeaders", {
  securityHeadersBehavior: {
    contentSecurityPolicy: {
      contentSecurityPolicy: "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' https://cognito-idp.eu-central-1.amazonaws.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
      override: true,
    },
    contentTypeOptions: { override: true },
    frameOptions: {
      frameOption: cloudfront.HeadersFrameOption.DENY,
      override: true,
    },
    referrerPolicy: {
      referrerPolicy: cloudfront.HeadersReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN,
      override: true,
    },
    strictTransportSecurity: {
      accessControlMaxAge: cdk.Duration.days(365),
      includeSubdomains: true,
      override: true,
    },
  },
});
```

Then attach to the default behaviour: `responseHeadersPolicy: responseHeadersPolicy`.

**Important:** The CSP `connect-src` must include the Cognito IDP domain for auth to work. If the `/api/*` behaviour also needs the policy, apply it there too.

Test by opening the frontend and checking the browser console for CSP violations.

## Implementation Subtasks

- [ ] Create `ResponseHeadersPolicy` in `frontend-stack.ts`
- [ ] Attach to default and API behaviours
- [ ] Test frontend works without CSP violations
- [ ] Verify headers appear in browser dev tools
- [ ] Update CDK tests

## Status

~~Todo~~ | ~~In Progress~~ | ~~In Review~~ | **Done**
