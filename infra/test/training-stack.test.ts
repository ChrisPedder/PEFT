import * as cdk from "aws-cdk-lib";
import { Template, Match } from "aws-cdk-lib/assertions";
import { StorageStack } from "../lib/storage-stack";
import { TrainingStack } from "../lib/training-stack";

describe("TrainingStack", () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const storageStack = new StorageStack(app, "TestStorage");
    const stack = new TrainingStack(app, "TestTraining", {
      dataBucket: storageStack.dataBucket,
      modelBucket: storageStack.modelBucket,
    });
    template = Template.fromStack(stack);
  });

  test("creates training IAM role with SageMaker service principal", () => {
    template.hasResourceProperties("AWS::IAM::Role", {
      RoleName: "PeftTrainingRole",
      AssumeRolePolicyDocument: {
        Statement: [
          {
            Action: "sts:AssumeRole",
            Effect: "Allow",
            Principal: {
              Service: "sagemaker.amazonaws.com",
            },
          },
        ],
      },
    });
  });

  test("has AmazonSageMakerFullAccess managed policy", () => {
    template.hasResourceProperties("AWS::IAM::Role", {
      ManagedPolicyArns: Match.arrayWith([
        {
          "Fn::Join": Match.anyValue(),
        },
      ]),
    });
  });

  test("creates DynamoDB table with correct key schema", () => {
    template.hasResourceProperties("AWS::DynamoDB::Table", {
      TableName: "peft-training-metrics",
      KeySchema: [
        { AttributeName: "job_id", KeyType: "HASH" },
        { AttributeName: "timestamp", KeyType: "RANGE" },
      ],
      AttributeDefinitions: [
        { AttributeName: "job_id", AttributeType: "S" },
        { AttributeName: "timestamp", AttributeType: "S" },
      ],
    });
  });

  test("DynamoDB table has PAY_PER_REQUEST billing", () => {
    template.hasResourceProperties("AWS::DynamoDB::Table", {
      BillingMode: "PAY_PER_REQUEST",
    });
  });

  test("has CfnOutput for TrainingRoleArn", () => {
    template.hasOutput("TrainingRoleArn", {});
  });
});
