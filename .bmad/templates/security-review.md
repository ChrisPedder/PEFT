# Security Review

## Overview

Brief summary of the application, scope of the review, and overall security posture.

## Scope

| Layer | Components Reviewed |
|-------|-------------------|
| Infrastructure | _e.g. CDK stacks, IAM roles, S3 policies, Lambda config_ |
| Backend | _e.g. inference API, training scripts, scraper_ |
| Frontend | _e.g. auth flow, token handling, API calls_ |
| CI/CD | _e.g. GitHub Actions workflows, secrets, permissions_ |

## Findings

### Critical

_Findings that could lead to immediate compromise or data breach._

#### [C-1] Finding title

- **Component:** _affected file or resource_
- **Description:** _what the vulnerability is_
- **Impact:** _what an attacker could do_
- **Remediation:** _specific fix with code or config changes_

### High

_Findings that could lead to significant security impact with moderate effort._

#### [H-1] Finding title

- **Component:** _affected file or resource_
- **Description:** _what the vulnerability is_
- **Impact:** _what an attacker could do_
- **Remediation:** _specific fix with code or config changes_

### Medium

_Findings that represent defence-in-depth gaps or could be chained with other issues._

#### [M-1] Finding title

- **Component:** _affected file or resource_
- **Description:** _what the vulnerability is_
- **Impact:** _what an attacker could do_
- **Remediation:** _specific fix with code or config changes_

### Low

_Minor findings, best-practice recommendations, and hardening suggestions._

#### [L-1] Finding title

- **Component:** _affected file or resource_
- **Description:** _what the issue is_
- **Remediation:** _suggested improvement_

## Remediation Plan

| Priority | ID | Finding | Effort | Story |
|----------|-----|---------|--------|-------|
| 1 | C-1 | _title_ | _S/M/L_ | _link to story file_ |
| 2 | H-1 | _title_ | _S/M/L_ | _link to story file_ |

## Positive Observations

_Things the application does well from a security perspective._

## Out of Scope / Future Considerations

_Areas not covered in this review, or longer-term security improvements to consider._
