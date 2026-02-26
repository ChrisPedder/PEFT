import * as cdk from "aws-cdk-lib";
import { Template, Match } from "aws-cdk-lib/assertions";
import { StorageStack } from "../lib/storage-stack";
import { InferenceStack } from "../lib/inference-stack";

describe("InferenceStack", () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const storageStack = new StorageStack(app, "TestStorage");
    const stack = new InferenceStack(app, "TestInference", {
      modelBucket: storageStack.modelBucket,
      cognitoUserPoolId: "us-east-1_testpool",
    });
    template = Template.fromStack(stack);
  });

  test("creates Bedrock import role with bedrock.amazonaws.com principal", () => {
    template.hasResourceProperties("AWS::IAM::Role", {
      RoleName: "PeftBedrockImportRole",
      AssumeRolePolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Principal: {
              Service: "bedrock.amazonaws.com",
            },
            Effect: "Allow",
          }),
        ]),
      },
    });
  });

  test("creates Lambda function with correct memory and timeout", () => {
    template.hasResourceProperties("AWS::Lambda::Function", {
      MemorySize: 512,
      Timeout: 300,
    });
  });

  test("Lambda has Bedrock invoke permissions", () => {
    template.hasResourceProperties("AWS::IAM::Policy", {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: [
              "bedrock:InvokeModel",
              "bedrock:InvokeModelWithResponseStream",
            ],
            Effect: "Allow",
          }),
        ]),
      },
    });
  });

  test("has CfnOutputs for BedrockImportRoleArn and LambdaFunctionUrl", () => {
    template.hasOutput("BedrockImportRoleArn", {});
    template.hasOutput("LambdaFunctionUrl", {});
  });
});
