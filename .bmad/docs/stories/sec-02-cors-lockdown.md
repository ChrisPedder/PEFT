# Lock down CORS to CloudFront domain only

**Epic:** Security Hardening

**Points:** 2

## User Story

As a platform operator, I want CORS restricted to my frontend domain so that malicious websites cannot make cross-origin requests to the API.

## Acceptance Criteria

- [ ] `allow_origins` in FastAPI middleware is set to the CloudFront distribution domain (not `"*"`)
- [ ] `allowedOrigins` on the Lambda Function URL CORS config matches the CloudFront domain
- [ ] `allow_methods` is restricted to `["GET", "POST", "OPTIONS"]`
- [ ] `allow_headers` is restricted to `["Authorization", "Content-Type"]`
- [ ] The CloudFront domain is loaded from an environment variable (not hardcoded)
- [ ] Cross-origin requests from other domains are rejected by the browser

## Technical Notes

- Add a `CORS_ALLOWED_ORIGIN` environment variable to the Lambda function in `inference-stack.ts`
- Set it to the CloudFront distribution domain: `https://${distribution.distributionDomainName}`
- This creates a cross-stack dependency from InferenceStack to FrontendStack — consider passing the origin as a prop or using SSM parameter store
- Alternatively, if doing sec-01 (IAM auth), the CORS on the Function URL becomes less critical since only CloudFront can invoke it
- Update `backend/inference/app.py` to read `CORS_ALLOWED_ORIGIN` from env and use it in the middleware

## Implementation Subtasks

- [ ] Add `CORS_ALLOWED_ORIGIN` env var to Lambda in `inference-stack.ts`
- [ ] Update `app.py` to read origin from env and configure CORS middleware
- [ ] Restrict `allow_methods` and `allow_headers` in `app.py`
- [ ] Update Lambda Function URL CORS in `inference-stack.ts`
- [ ] Update tests in `test_inference_app.py`

## Status

~~Todo~~ | ~~In Progress~~ | ~~In Review~~ | **Done**
