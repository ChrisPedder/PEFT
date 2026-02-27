# Harden S3 bucket removal policies and enable versioning

**Epic:** Security Hardening

**Points:** 2

## User Story

As a platform operator, I want critical S3 buckets to be protected from accidental deletion so that training data and model artifacts are not permanently lost.

## Acceptance Criteria

- [ ] `modelBucket` and `trainingDataBucket` have `removalPolicy: RETAIN`
- [ ] `autoDeleteObjects` is removed from retained buckets
- [ ] Versioning is enabled on `dataBucket` and `trainingDataBucket`
- [ ] Lifecycle rules expire old versions after 90 days to control costs
- [ ] CDK deploy succeeds without errors

## Technical Notes

Changes in `infra/lib/storage-stack.ts`:

For `modelBucket` (already has `versioned: true`):
- Change `removalPolicy: cdk.RemovalPolicy.DESTROY` to `cdk.RemovalPolicy.RETAIN`
- Remove `autoDeleteObjects: true`

For `trainingDataBucket`:
- Change `removalPolicy: cdk.RemovalPolicy.DESTROY` to `cdk.RemovalPolicy.RETAIN`
- Remove `autoDeleteObjects: true`
- Set `versioned: true`

For `dataBucket`:
- Set `versioned: true`
- Optionally retain (less critical since data can be re-scraped)

Add lifecycle rules:
```typescript
lifecycleRules: [
  {
    noncurrentVersionExpiration: cdk.Duration.days(90),
  },
],
```

**Note:** Changing `removalPolicy` from `DESTROY` to `RETAIN` means `cdk destroy` will leave the bucket in the account. The `autoDeleteObjects` custom resource Lambda will also be removed. This is the intended behaviour for production data.

## Implementation Subtasks

- [ ] Update `modelBucket` removal policy and remove autoDeleteObjects
- [ ] Update `trainingDataBucket` removal policy, enable versioning
- [ ] Enable versioning on `dataBucket`
- [ ] Add lifecycle rules for version expiration
- [ ] Update CDK tests
- [ ] Deploy and verify

## Status

~~Todo~~ | ~~In Progress~~ | ~~In Review~~ | **Done**
