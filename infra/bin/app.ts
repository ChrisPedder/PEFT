#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { StorageStack } from "../lib/storage-stack";
import { TrainingStack } from "../lib/training-stack";
import { AuthStack } from "../lib/auth-stack";
import { InferenceStack } from "../lib/inference-stack";
import { FrontendStack } from "../lib/frontend-stack";
import { ScraperBatchStack } from "../lib/scraper-batch-stack";
import { CicdRolesStack } from "../lib/cicd-roles-stack";

const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION ?? "eu-central-1",
};

// Storage (S3 buckets + IAM roles)
const storageStack = new StorageStack(app, "PeftStorageStack", { env });

// Phase 3: Training resources
const trainingStack = new TrainingStack(app, "PeftTrainingStack", {
  env,
  trainingDataBucket: storageStack.trainingDataBucket,
  modelBucket: storageStack.modelBucket,
});

// Auth (Cognito User Pool)
const authStack = new AuthStack(app, "PeftAuthStack", { env });

// Phase 4: Inference (SageMaker endpoint + Lambda proxy)
const inferenceStack = new InferenceStack(app, "PeftInferenceStack", {
  env,
  modelBucket: storageStack.modelBucket,
  cognitoUserPoolId: authStack.userPool.userPoolId,
  cognitoClientId: authStack.userPoolClientId,
});

// Phase 5: Frontend (CloudFront + S3)
const frontendStack = new FrontendStack(app, "PeftFrontendStack", {
  env,
  lambdaFunctionUrl: inferenceStack.lambdaFunctionUrl,
  cognitoUserPoolId: authStack.userPool.userPoolId,
  cognitoClientId: authStack.userPoolClientId,
});

// Scraper pipeline (AWS Batch on Fargate)
const scraperBatchStack = new ScraperBatchStack(app, "PeftScraperBatchStack", {
  env,
  dataBucket: storageStack.dataBucket,
  trainingDataBucket: storageStack.trainingDataBucket,
});

// CI/CD IAM roles (GitHub OIDC)
const cicdRolesStack = new CicdRolesStack(app, "PeftCicdRolesStack", {
  env,
  githubRepo: "ChrisPedder/PEFT",
});

app.synth();
