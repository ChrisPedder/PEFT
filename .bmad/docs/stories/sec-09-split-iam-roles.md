# Create separate IAM roles for each CI/CD workflow

**Epic:** Security Hardening

**Points:** 8

## User Story

As a platform operator, I want each CI/CD workflow to use a dedicated IAM role with minimum permissions so that compromise of one workflow does not grant access to all AWS resources.

## Acceptance Criteria

- [ ] Separate IAM OIDC roles exist for: deploy, scrape, process, train, update-model
- [ ] Each role's trust policy constrains the OIDC `sub` claim to the specific workflow file and branch
- [ ] Each role's permissions are scoped to only what that workflow needs
- [ ] Separate GitHub secrets exist for each role ARN
- [ ] All workflows work end-to-end with their scoped roles

## Technical Notes

Proposed role separation:

| Workflow | Role | Key Permissions |
|----------|------|-----------------|
| deploy.yml | `PeftDeployRole` | CloudFormation, IAM, Lambda, S3, CloudFront, ECR, Cognito, DynamoDB, SageMaker (for CDK) |
| scrape.yml | `PeftScraperRole` | Batch:SubmitJob, Batch:DescribeJobs, S3 read on data bucket |
| process.yml | `PeftProcessRole` | Batch:SubmitJob, Batch:DescribeJobs, S3 read/write on data + training buckets |
| train.yml | `PeftTrainRole` | SageMaker:CreateTrainingJob, SageMaker:Describe*, S3 read on training data, S3 write on model artifacts |
| update-model.yml | `PeftUpdateModelRole` | S3 read on model artifacts, Bedrock:CreateModelImportJob, Bedrock:GetModelImportJob, IAM:PassRole (for Bedrock import role), Lambda:UpdateFunctionConfiguration |

Each trust policy should include:
```json
"Condition": {
  "StringEquals": {
    "token.actions.githubusercontent.com:sub": "repo:ChrisPedder/PEFT:ref:refs/heads/main",
    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
  }
}
```

Consider defining these roles in a new CDK stack (`CicdRolesStack`) or via CloudFormation/Terraform separately from the application stacks.

## Implementation Subtasks

- [ ] Design permissions for each role
- [ ] Create IAM roles (CDK stack or CloudFormation)
- [ ] Configure OIDC trust policies with workflow-specific conditions
- [ ] Add separate GitHub secrets for each role ARN
- [ ] Update each workflow to reference its own secret
- [ ] Test each workflow end-to-end
- [ ] Remove the old single `AWS_DEPLOY_ROLE_ARN` secret

## Status

Todo | In Progress | In Review | **Done**
