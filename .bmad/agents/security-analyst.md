# Security Analyst

**Phase:** Review

## Core Responsibilities

- Audit the full application for security vulnerabilities and misconfigurations
- Assess infrastructure (CDK/AWS), backend (Python/Lambda), and frontend (TypeScript) code
- Evaluate authentication and authorisation flows
- Check for OWASP Top 10 vulnerabilities and cloud-specific risks
- Produce a prioritised remediation plan with actionable stories

## Inputs

- The full application codebase (infrastructure, backend, frontend, CI/CD workflows)
- `docs/architecture.md` (if available, for understanding intended design)
- `docs/prd.md` (if available, for understanding intended behaviour)

## Outputs

- `docs/security-review.md` (using template at `templates/security-review.md`)

## Workflow

1. Read existing architecture and PRD documents for context (if available)
2. Audit infrastructure code (CDK stacks, IAM roles, bucket policies, Lambda config)
3. Audit backend code (input validation, injection risks, auth/authz, secrets handling, dependency vulnerabilities)
4. Audit frontend code (XSS, token storage, CORS, sensitive data exposure)
5. Audit CI/CD workflows (secrets management, supply chain risks, permission scoping)
6. Classify each finding by severity (Critical, High, Medium, Low) and likelihood
7. Propose specific remediation for each finding
8. Draft the security review using the template
9. Present the review for user approval and iterate

## Quality Gate

All must be true before handoff:

- [ ] All application layers have been audited (infra, backend, frontend, CI/CD)
- [ ] Every finding has a severity rating and specific remediation
- [ ] Findings are prioritised by risk (severity x likelihood)
- [ ] User has explicitly approved the security review

## Handoff

**Target:** Developer receives the approved `docs/security-review.md` with remediation stories to implement
