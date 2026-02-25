#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { StorageStack } from "../lib/storage-stack";
import { TrainingStack } from "../lib/training-stack";
import { InferenceStack } from "../lib/inference-stack";
import { FrontendStack } from "../lib/frontend-stack";

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
  dataBucket: storageStack.dataBucket,
  modelBucket: storageStack.modelBucket,
});

// Phase 4: Inference (SageMaker endpoint + Lambda proxy)
const inferenceStack = new InferenceStack(app, "PeftInferenceStack", {
  env,
  modelBucket: storageStack.modelBucket,
});

// Phase 5: Frontend (CloudFront + S3)
const frontendStack = new FrontendStack(app, "PeftFrontendStack", {
  env,
  lambdaFunctionUrl: inferenceStack.lambdaFunctionUrl,
});

app.synth();
