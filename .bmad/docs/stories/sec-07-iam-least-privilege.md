# Replace AmazonSageMakerFullAccess with scoped IAM policies

**Epic:** Security Hardening

**Points:** 3

## User Story

As a platform operator, I want IAM roles to follow least-privilege so that a compromised component cannot pivot to unrelated AWS services.

## Acceptance Criteria

- [ ] The unused SageMaker role in `storage-stack.ts` is removed (or scoped down if actually needed)
- [ ] The training role in `training-stack.ts` uses a custom inline policy instead of `AmazonSageMakerFullAccess`
- [ ] The training role only has permissions for: `CreateTrainingJob`, `DescribeTrainingJob`, `StopTrainingJob`, scoped S3 access, scoped ECR access, scoped CloudWatch Logs
- [ ] Bedrock permissions in `scraper-batch-stack.ts` are scoped to the specific model(s) used
- [ ] ECR permissions in `training-stack.ts` are split: `GetAuthorizationToken` on `*`, pull actions scoped to HuggingFace DLC repos
- [ ] CloudWatch Logs resource uses `${AWS::Region}:${AWS::AccountId}` instead of `*:*`
- [ ] Training jobs still work end-to-end after the changes

## Technical Notes

- The role `PeftSageMakerExecutionRole` in `storage-stack.ts` (line 64-73) appears to be dead code — it is exported but no other stack references it. The training stack creates its own `PeftTrainingRole`. Verify before removing.
- For the training role, the needed SageMaker actions are: `sagemaker:CreateTrainingJob`, `sagemaker:DescribeTrainingJob`, `sagemaker:StopTrainingJob`, `sagemaker:AddTags`, `sagemaker:ListTags`.
- The HuggingFace DLC ECR repo is in account `763104351884`. Scope ECR pull to: `arn:aws:ecr:${region}:763104351884:repository/huggingface-pytorch-training`.
- Bedrock actions in scraper-batch-stack should be scoped to: `arn:aws:bedrock:${region}::foundation-model/anthropic.claude-*`.

## Implementation Subtasks

- [ ] Remove or scope down `PeftSageMakerExecutionRole` in `storage-stack.ts`
- [ ] Replace `AmazonSageMakerFullAccess` in `training-stack.ts` with custom inline policy
- [ ] Split ECR policy into `GetAuthorizationToken` (resource `*`) and pull actions (scoped)
- [ ] Scope CloudWatch Logs to current region and account
- [ ] Scope Bedrock permissions in `scraper-batch-stack.ts` to specific model ARN pattern
- [ ] Update CDK tests
- [ ] Run a test training job to verify

## Status

~~Todo~~ | ~~In Progress~~ | ~~In Review~~ | **Done**
