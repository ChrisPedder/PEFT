# Security Review

## Overview

This review covers the PEFT Obama Q&A application — a QLoRA fine-tuned Mistral-7B model served via Amazon Bedrock Custom Model Import, with a TypeScript SPA frontend, FastAPI Lambda proxy, and full CI/CD pipeline on GitHub Actions. The application is deployed across 6 CDK stacks in eu-central-1.

**Overall posture:** The application has a solid foundation (no XSS vectors in the frontend, HTTPS enforced, JWT auth in place) but has significant gaps in infrastructure hardening, dependency security, and CI/CD supply-chain protection. The most critical issues are an unauthenticated Lambda Function URL, a vulnerable JWT library, and script injection in CI/CD workflows.

## Scope

| Layer | Components Reviewed |
|-------|-------------------|
| Infrastructure | 6 CDK stacks: storage, auth, training, inference, frontend, scraper-batch |
| Backend | inference/app.py, Dockerfile, training scripts, scraper, operational scripts |
| Frontend | app.ts, auth.ts, lib.ts, index.html, vite config, package.json |
| CI/CD | 6 GitHub Actions workflows: ci, deploy, scrape, process, train, update-model |

## Findings

### Critical

#### [C-1] Lambda Function URL publicly accessible without authentication

- **Component:** `infra/lib/inference-stack.ts:87`
- **Description:** The Lambda Function URL is configured with `authType: lambda.FunctionUrlAuthType.NONE`. The raw Lambda URL is publicly accessible and exported as a CloudFormation output. Although the FastAPI handler validates JWTs, the function URL itself has zero AWS-level access control.
- **Impact:** Anyone on the internet can invoke the Lambda directly, bypassing CloudFront. Combined with wildcard CORS (C-2), any website can make authenticated cross-origin requests on behalf of logged-in users.
- **Remediation:** Either (a) switch to `AWS_IAM` auth type and use CloudFront OAC to sign requests to the Lambda URL, or (b) if keeping `NONE`, restrict the CORS `allowedOrigins` to the CloudFront domain only and ensure the JWT validation is hardened (see H-1, H-2). At minimum, stop exporting the raw Lambda URL as a stack output.

#### [C-2] Wildcard CORS allows any origin

- **Component:** `backend/inference/app.py:23-28` and `infra/lib/inference-stack.ts:89-93`
- **Description:** Both the FastAPI middleware and the Lambda Function URL CORS configuration use `allow_origins=["*"]`. This permits any website to make cross-origin requests to the API, including requests with the `Authorization` header.
- **Impact:** A malicious website can issue authenticated requests to `/api/ask` on behalf of any logged-in user whose browser visits that page, exfiltrating streaming model responses.
- **Remediation:** Restrict `allow_origins` to the CloudFront distribution domain (e.g. `https://d1tn4j4sanbwt.cloudfront.net`). Load it from an environment variable set during CDK deployment. Also restrict `allow_methods` to `["GET", "POST", "OPTIONS"]` and `allow_headers` to `["Authorization", "Content-Type"]`.

#### [C-3] Unmaintained JWT library (`python-jose`) with known CVEs

- **Component:** `backend/inference/requirements.txt:4`, `backend/inference/app.py:18`
- **Description:** `python-jose` has not been released since 2021 and has two known CVEs: CVE-2024-33663 (algorithm confusion allowing signature bypass) and CVE-2024-33664 (JWT Bomb denial of service via crafted JWE tokens with high compression ratios).
- **Impact:** An attacker could craft malicious JWTs to bypass authentication or cause denial of service on the Lambda.
- **Remediation:** Replace `python-jose` with `PyJWT` (actively maintained, recommended by FastAPI) or `joserfc`. The `jwt.decode` API is nearly identical. Update the Dockerfile requirements and tests accordingly.

#### [C-4] Script injection via unsanitised `workflow_dispatch` inputs

- **Component:** `.github/workflows/train.yml:47-54`
- **Description:** The `learning_rate` and `instance_type` string inputs are interpolated directly into a shell `run:` block via `${{ inputs.* }}`. Any repository collaborator who can trigger `workflow_dispatch` can inject arbitrary shell commands.
- **Impact:** Arbitrary code execution in the GitHub Actions runner context, which has AWS credentials loaded via OIDC. An attacker could exfiltrate secrets, modify S3 data, or pivot to other AWS services.
- **Remediation:** Pass all inputs through environment variables instead of `${{ }}` interpolation:
  ```yaml
  env:
    INSTANCE_TYPE: ${{ inputs.instance_type }}
  run: python scripts/launch_training.py --instance-type "$INSTANCE_TYPE"
  ```

### High

#### [H-1] JWT audience (`aud`) verification disabled

- **Component:** `backend/inference/app.py:94`
- **Description:** `jwt.decode` is called with `options={"verify_aud": False}`. Any valid ID token from the same Cognito User Pool — regardless of which app client issued it — is accepted.
- **Impact:** If the User Pool gains additional app clients (admin tools, other apps), tokens from those clients grant access to this API. Token scope confusion enables cross-client attacks.
- **Remediation:** Set `options={"verify_aud": True}` and pass `audience=COGNITO_CLIENT_ID` (loaded from an environment variable).

#### [H-2] Internal error details leaked to clients

- **Component:** `backend/inference/app.py:151-153`
- **Description:** The raw boto3/Bedrock exception message is forwarded to the client: `f"Bedrock error: {error_msg}"`. AWS SDK exceptions can contain request IDs, ARNs, account IDs, and IAM role details.
- **Impact:** Information disclosure of internal infrastructure details to attackers.
- **Remediation:** Log the full exception server-side and return a generic message: `"An internal error occurred. Please try again later."`.

#### [H-3] `AmazonSageMakerFullAccess` on IAM roles

- **Component:** `infra/lib/storage-stack.ts:70-72`, `infra/lib/training-stack.ts:27-29`
- **Description:** Two IAM roles use the `AmazonSageMakerFullAccess` managed policy, which grants broad permissions including the ability to create endpoints, notebooks, and modify other SageMaker resources. The role in `storage-stack.ts` appears to be unused (the training stack has its own role).
- **Impact:** A compromised training job or leaked role credentials could create rogue SageMaker notebooks or endpoints, access other S3 buckets, or modify CloudWatch resources.
- **Remediation:** Remove the unused role from `storage-stack.ts`. Replace `AmazonSageMakerFullAccess` on the training role with a scoped-down policy allowing only `sagemaker:CreateTrainingJob`, `sagemaker:DescribeTrainingJob`, `sagemaker:StopTrainingJob`, and related read-only operations.

#### [H-4] Unpinned GitHub Actions across all workflows

- **Component:** All 6 workflow files
- **Description:** Every GitHub Action is pinned to a mutable major version tag (`@v4`, `@v5`) rather than an immutable commit SHA. This includes `actions/checkout`, `actions/setup-python`, `aws-actions/configure-aws-credentials`, and `codecov/codecov-action`.
- **Impact:** A compromised or malicious tag update to any action could execute arbitrary code in the runner, exfiltrating AWS credentials or injecting backdoors.
- **Remediation:** Pin all actions to full commit SHAs: `actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11 # v4.1.1`. Use Dependabot to propose SHA updates.

#### [H-5] Single IAM role used across all CI/CD workflows

- **Component:** deploy.yml, scrape.yml, process.yml, train.yml, update-model.yml
- **Description:** All five AWS-integrated workflows use `secrets.AWS_DEPLOY_ROLE_ARN`, meaning a single OIDC role has permissions for CDK deployments, Batch jobs, SageMaker training, S3 access, and Bedrock imports.
- **Impact:** Compromise of any workflow grants access to all AWS permissions. A scraping workflow vulnerability could be used to deploy infrastructure or import models.
- **Remediation:** Create separate IAM roles per workflow, each scoped to the minimum permissions needed. Constrain each role's OIDC trust policy to the specific workflow file and branch.

#### [H-6] No input validation bounds on API request fields

- **Component:** `backend/inference/app.py:105-108`
- **Description:** The `AskRequest` model has no bounds on `question` length, `max_tokens`, or `temperature`. A user can send multi-megabyte prompts or request `max_tokens: 999999`.
- **Impact:** Cost exhaustion via excessive Bedrock token generation, potential denial of service from oversized requests.
- **Remediation:** Add Pydantic `Field` constraints: `question: str = Field(..., min_length=1, max_length=4000)`, `max_tokens: int = Field(default=512, ge=1, le=4096)`, `temperature: float = Field(default=0.7, ge=0.0, le=2.0)`.

#### [H-7] Unverified binary download in CI

- **Component:** `.github/workflows/ci.yml:63-67`
- **Description:** The `actionlint` binary is downloaded via `curl` from the GitHub Releases `latest` endpoint without checksum verification.
- **Impact:** A compromised `actionlint` release or MITM attack would execute arbitrary code in the CI runner.
- **Remediation:** Pin to a specific version and verify the SHA-256 checksum, or use the official `rhysd/actionlint` action with a pinned SHA.

### Medium

#### [M-1] Cognito User Pool missing MFA enforcement

- **Component:** `infra/lib/auth-stack.ts:12-24`
- **Description:** No MFA configuration is specified. The user pool has `mfa: OFF` by default, and the password policy only requires 8 characters with uppercase and digit (no symbols).
- **Impact:** Accounts are vulnerable to credential stuffing and brute-force attacks.
- **Remediation:** Enable `mfa: cognito.Mfa.OPTIONAL` (or `REQUIRED`) with TOTP. Increase `minLength` to 12 and enable `requireSymbols`.

#### [M-2] `userPassword` auth flow enabled

- **Component:** `infra/lib/auth-stack.ts:29-32`
- **Description:** The `userPassword: true` auth flow sends the user's password in cleartext to the Cognito API. The SRP flow is the secure alternative.
- **Impact:** Passwords visible to application-layer logging, proxies, and AWS CloudTrail.
- **Remediation:** Remove `userPassword: true` and rely solely on `userSrp: true`.

#### [M-3] S3 buckets with `DESTROY` removal policy and `autoDeleteObjects`

- **Component:** `infra/lib/storage-stack.ts:18-61`
- **Description:** All four S3 buckets are configured to be automatically destroyed with all objects deleted on stack deletion.
- **Impact:** Accidental `cdk destroy` permanently deletes all training data, model artifacts, and scraped data.
- **Remediation:** Set `removalPolicy: RETAIN` on `modelBucket` and `trainingDataBucket` at minimum. Enable versioning on all data buckets.

#### [M-4] Dockerfile runs as root

- **Component:** `backend/inference/Dockerfile`
- **Description:** The container does not specify a non-root user, so the process runs as root.
- **Impact:** If an attacker achieves code execution inside the container, they have root privileges.
- **Remediation:** Add `RUN adduser --disabled-password --gecos '' appuser` and `USER appuser`.

#### [M-5] No rate limiting on the API

- **Component:** `backend/inference/app.py`
- **Description:** No rate limiting exists on any endpoint. `/api/ask` calls Bedrock (a billed service) with no per-user or global throttle.
- **Impact:** Denial of service or runaway Bedrock costs from a single authenticated user.
- **Remediation:** Add rate limiting via `slowapi` middleware or CloudFront WAF rate-limit rules.

#### [M-6] No Content Security Policy

- **Component:** `frontend/src/index.html`, `infra/lib/frontend-stack.ts`
- **Description:** No CSP is set via meta tag or CloudFront response headers. Any injected script executes without restriction.
- **Impact:** A future XSS vector would have unrestricted script execution capability.
- **Remediation:** Add a CloudFront `ResponseHeadersPolicy` with `Content-Security-Policy: default-src 'self'; connect-src 'self' https://cognito-idp.eu-central-1.amazonaws.com; frame-ancestors 'none'`. Also add `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`.

#### [M-7] Token storage in localStorage

- **Component:** `frontend/src/auth.ts:21-24` (implicit via `amazon-cognito-identity-js` default)
- **Description:** Cognito tokens (ID, access, refresh) are stored in `localStorage` by default. They persist across tabs and sessions and are accessible to any JavaScript on the same origin.
- **Impact:** A future XSS vulnerability would immediately expose all stored authentication tokens.
- **Remediation:** Pass a custom `Storage` adapter backed by `sessionStorage` or in-memory storage. Document as accepted risk if localStorage is intentional.

#### [M-8] Prompt injection via Mistral control tokens

- **Component:** `backend/inference/app.py:123`
- **Description:** User input is interpolated directly into the Mistral `[INST]` template with no sanitisation. Users can inject `[/INST]`, `</s>`, or other control tokens to break out of the instruction template.
- **Impact:** Users can manipulate model behaviour by injecting control sequences that alter the chat template structure.
- **Remediation:** Strip Mistral control sequences (`[INST]`, `[/INST]`, `<s>`, `</s>`) from user input before constructing the prompt.

#### [M-9] `pip install` without hash checking in CI/CD

- **Component:** `.github/workflows/update-model.yml:36-37`, `ci.yml:25,85`, `train.yml:41`
- **Description:** Multiple workflows install Python packages from PyPI without `--require-hashes` or lockfiles. The `update-model.yml` step runs `pip install boto3 transformers peft accelerate sentencepiece protobuf` with no version pins or verification, with AWS credentials already loaded.
- **Impact:** A typosquatted or compromised PyPI package would execute arbitrary code with AWS credentials.
- **Remediation:** Use pinned versions with hashes in a requirements lockfile.

#### [M-10] Deploy workflow doesn't pin to CI-validated commit

- **Component:** `.github/workflows/deploy.yml`
- **Description:** The deploy workflow is triggered by `workflow_run` but checks out HEAD rather than the specific commit that CI validated. A race condition could deploy an unvalidated commit.
- **Remediation:** Pin checkout to `ref: ${{ github.event.workflow_run.head_sha }}`.

### Low

#### [L-1] Health endpoint leaks model ID

- **Component:** `backend/inference/app.py:111-113`
- **Description:** The unauthenticated `/api/health` endpoint returns the Bedrock model ARN, exposing the AWS account ID and model name.
- **Remediation:** Remove `model_id` from the health response.

#### [L-2] Local-only sign-out

- **Component:** `frontend/src/auth.ts:119-125`
- **Description:** `signOut()` only clears client-side tokens. Stolen refresh tokens remain valid server-side until expiry (default 30 days).
- **Remediation:** Use `currentUser.globalSignOut()` with a local-signout fallback.

#### [L-3] CloudFront missing WAF and access logging

- **Component:** `infra/lib/frontend-stack.ts:58-89`
- **Description:** No WAF WebACL for rate limiting or bot protection. No CloudFront access logging for audit.
- **Remediation:** Attach a WAF WebACL with rate-limiting rules. Enable CloudFront access logging.

#### [L-4] Hardcoded IAM role names prevent multi-environment deployment

- **Component:** Multiple CDK stacks
- **Description:** IAM roles have hardcoded names (e.g. `PeftBedrockImportRole`, `PeftLambdaProxyRole`), preventing deployment of multiple environments to the same account.
- **Remediation:** Remove explicit `roleName` or prefix with a stage variable.

#### [L-5] Legacy OAI instead of OAC for CloudFront-to-S3

- **Component:** `infra/lib/frontend-stack.ts:31`
- **Description:** Uses legacy Origin Access Identity. AWS recommends Origin Access Control (OAC).
- **Remediation:** Migrate to `S3BucketOrigin.withOriginAccessControl()`.

#### [L-6] Missing `persist-credentials: false` on checkout steps

- **Component:** All workflows using `actions/checkout`
- **Description:** The GITHUB_TOKEN is persisted in the local git config, accessible to subsequent steps.
- **Remediation:** Add `persist-credentials: false` to all checkout steps.

#### [L-7] No timeout limits on CI/CD polling loops or jobs

- **Component:** `.github/workflows/scrape.yml`, `process.yml`
- **Description:** `while true` polling loops with no maximum wait time. No `timeout-minutes` on any job.
- **Remediation:** Add maximum iteration counts and `timeout-minutes` to all jobs.

#### [L-8] Cognito User Pool and DynamoDB table with `DESTROY` removal policy

- **Component:** `infra/lib/auth-stack.ts:23`, `infra/lib/training-stack.ts:62-68`
- **Description:** The user pool and metrics table will be permanently deleted on stack destruction.
- **Remediation:** Set `removalPolicy: RETAIN` for production.

#### [L-9] Password passed via CLI argument in manage_users.py

- **Component:** `backend/scripts/manage_users.py:91-92`
- **Description:** Passwords are passed as `--password` CLI arguments, visible in `ps` output and shell history.
- **Remediation:** Read passwords interactively via `getpass.getpass()` or from stdin.

## Remediation Plan

| Priority | ID | Finding | Effort | Story |
|----------|-----|---------|--------|-------|
| 1 | C-1 | Lambda Function URL unauthenticated | M | `stories/sec-01-lambda-url-auth.md` |
| 2 | C-2 | Wildcard CORS | S | `stories/sec-02-cors-lockdown.md` |
| 3 | C-3 | Replace python-jose | M | `stories/sec-03-replace-python-jose.md` |
| 4 | C-4 | Script injection in train.yml | S | `stories/sec-04-ci-script-injection.md` |
| 5 | H-1 | JWT audience verification | S | `stories/sec-05-jwt-audience.md` |
| 6 | H-2 | Error detail leakage | S | `stories/sec-06-error-messages.md` |
| 7 | H-3 | SageMaker full access IAM | M | `stories/sec-07-iam-least-privilege.md` |
| 8 | H-4 | Pin GitHub Actions to SHA | M | `stories/sec-08-pin-actions.md` |
| 9 | H-5 | Separate CI/CD IAM roles | L | `stories/sec-09-split-iam-roles.md` |
| 10 | H-6 | Input validation bounds | S | `stories/sec-10-input-validation.md` |
| 11 | H-7 | Pin actionlint download | S | `stories/sec-11-pin-actionlint.md` |
| 12 | M-1 | Enable MFA on Cognito | S | `stories/sec-12-cognito-mfa.md` |
| 13 | M-2 | Remove userPassword auth flow | S | `stories/sec-13-remove-password-flow.md` |
| 14 | M-3 | S3 removal policy hardening | S | `stories/sec-14-s3-retention.md` |
| 15 | M-4 | Non-root Dockerfile | S | `stories/sec-15-nonroot-container.md` |
| 16 | M-5 | Rate limiting | M | `stories/sec-16-rate-limiting.md` |
| 17 | M-6 | Content Security Policy | M | `stories/sec-17-csp-headers.md` |
| 18 | M-7 | Token storage review | S | `stories/sec-18-token-storage.md` |
| 19 | M-8 | Prompt injection sanitisation | S | `stories/sec-19-prompt-sanitisation.md` |
| 20 | M-9 | Pin CI pip installs | M | `stories/sec-20-pin-pip-deps.md` |
| 21 | M-10 | Pin deploy checkout SHA | S | `stories/sec-21-deploy-sha.md` |

## Positive Observations

- **No XSS vectors in frontend**: Consistent use of `textContent` over `innerHTML` throughout the codebase. No `eval`, `document.write`, or unsafe DOM APIs.
- **HTTPS enforced**: CloudFront uses `REDIRECT_TO_HTTPS` for all behaviours.
- **JWT validation in place**: The Lambda proxy validates Cognito JWTs with issuer checking and key rotation via JWKS.
- **No hardcoded secrets**: No API keys, passwords, or credentials found in any source files.
- **Strict TypeScript**: `tsconfig.json` has `"strict": true` enabled.
- **Clean frontend dependency surface**: Only one runtime dependency (`amazon-cognito-identity-js`).
- **S3 server-side encryption**: Buckets use `S3_MANAGED` encryption by default.
- **Model bucket versioning**: `modelBucket` has versioning enabled.
- **Self-signup disabled**: Cognito user pool correctly disables self-registration.

## Out of Scope / Future Considerations

- **Penetration testing**: This is a static code review. Dynamic testing (fuzzing, network probing) was not performed.
- **AWS account-level security**: IAM account settings, CloudTrail configuration, GuardDuty, and Security Hub are outside the scope of this codebase review.
- **Model security**: Adversarial attacks on the fine-tuned model (data poisoning, model extraction) were not assessed.
- **Third-party dependency deep audit**: CVE scanning was limited to known issues in directly imported packages. A full SCA (Software Composition Analysis) tool like Snyk or Trivy should be run regularly.
- **Secrets rotation**: No assessment was made of how frequently AWS credentials, Cognito secrets, or OIDC roles are rotated.
- **Disaster recovery**: Backup and recovery procedures for S3 data, DynamoDB, and Cognito user pools were not assessed.
