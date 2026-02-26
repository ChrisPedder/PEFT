import * as cdk from "aws-cdk-lib";
import { Template, Match } from "aws-cdk-lib/assertions";
import { StorageStack } from "../lib/storage-stack";
import { ScraperBatchStack } from "../lib/scraper-batch-stack";

describe("ScraperBatchStack", () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const storageStack = new StorageStack(app, "TestStorage", {
      env: { account: "123456789012", region: "eu-central-1" },
    });
    const stack = new ScraperBatchStack(app, "TestScraperBatch", {
      env: { account: "123456789012", region: "eu-central-1" },
      dataBucket: storageStack.dataBucket,
      trainingDataBucket: storageStack.trainingDataBucket,
    });
    template = Template.fromStack(stack);
  });

  test("creates Fargate compute environment", () => {
    template.hasResourceProperties("AWS::Batch::ComputeEnvironment", {
      ComputeResources: {
        MaxvCpus: 4,
      },
    });
  });

  test("creates job queue", () => {
    template.hasResourceProperties("AWS::Batch::JobQueue", {
      JobQueueName: "peft-scraper-job-queue",
    });
  });

  test("creates scrape job definition", () => {
    template.hasResourceProperties("AWS::Batch::JobDefinition", {
      JobDefinitionName: "peft-scrape-speeches",
      Type: "container",
      Timeout: { AttemptDurationSeconds: 21600 },
    });
  });

  test("creates process job definition", () => {
    template.hasResourceProperties("AWS::Batch::JobDefinition", {
      JobDefinitionName: "peft-process-speeches",
      Type: "container",
      Timeout: { AttemptDurationSeconds: 14400 },
    });
  });

  test("task role has S3 and Bedrock permissions", () => {
    template.hasResourceProperties("AWS::IAM::Policy", {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: ["bedrock:Converse", "bedrock:InvokeModel"],
            Effect: "Allow",
          }),
        ]),
      },
    });
  });

  test("has CfnOutput for JobQueueName", () => {
    template.hasOutput("JobQueueName", {});
  });

  test("has CfnOutput for ScrapeJobDefinitionArn", () => {
    template.hasOutput("ScrapeJobDefinitionArn", {});
  });

  test("has CfnOutput for ProcessJobDefinitionArn", () => {
    template.hasOutput("ProcessJobDefinitionArn", {});
  });

  test("process container has DATA_BUCKET and TRAINING_DATA_BUCKET env vars", () => {
    template.hasResourceProperties("AWS::Batch::JobDefinition", {
      JobDefinitionName: "peft-process-speeches",
      ContainerProperties: {
        Environment: Match.arrayWith([
          Match.objectLike({ Name: "DATA_BUCKET" }),
          Match.objectLike({ Name: "TRAINING_DATA_BUCKET" }),
        ]),
      },
    });
  });
});
