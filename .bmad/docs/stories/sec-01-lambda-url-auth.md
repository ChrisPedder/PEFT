# Restrict Lambda Function URL access

**Epic:** Security Hardening

**Points:** 5

## User Story

As a platform operator, I want the Lambda Function URL to be inaccessible to the public internet so that only CloudFront can invoke the inference proxy.

## Acceptance Criteria

- [ ] The raw Lambda Function URL returns 403 when called directly without IAM auth
- [ ] Requests routed through CloudFront continue to work end-to-end
- [ ] The Lambda Function URL is no longer exported as a plaintext CloudFormation output (or is removed from outputs entirely)
- [ ] CORS `allowedOrigins` on the Function URL is restricted to the CloudFront domain

## Technical Notes

Two approaches:

**Option A — IAM auth + CloudFront OAC (preferred):**
- Change `authType` to `lambda.FunctionUrlAuthType.AWS_IAM` in `infra/lib/inference-stack.ts:87`
- Add a CloudFront Origin Access Control (OAC) for the Lambda URL origin so CloudFront signs requests with SigV4
- Grant `lambda:InvokeFunctionUrl` to the CloudFront OAC in the Lambda resource policy
- This requires CDK v2.130+ for `origins.FunctionUrlOrigin` with OAC support

**Option B — Keep NONE auth, harden app-level controls:**
- Keep `AuthType.NONE` but restrict CORS origins to the CloudFront domain only
- Add an `Origin` or `Referer` header check in the FastAPI middleware
- Less secure than Option A but simpler

The CloudFront distribution is defined in `frontend-stack.ts` and the Lambda URL origin is configured there at line 70. The origin currently uses `HttpOrigin` — switching to OAC would require using `FunctionUrlOrigin` instead.

## Implementation Subtasks

- [ ] Change `authType` to `AWS_IAM` in `inference-stack.ts`
- [ ] Add CloudFront OAC for the Lambda URL origin in `frontend-stack.ts`
- [ ] Grant `lambda:InvokeFunctionUrl` to CloudFront in the Lambda resource policy
- [ ] Restrict `allowedOrigins` on the Function URL to the CloudFront domain
- [ ] Remove or restrict the `LambdaFunctionUrl` CfnOutput
- [ ] Update CDK tests
- [ ] Verify end-to-end via CloudFront after deployment

## Status

Todo | In Progress | In Review | **Done**
