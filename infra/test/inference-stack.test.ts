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

  test("creates SageMaker endpoint config with correct instance type", () => {
    template.hasResourceProperties("AWS::SageMaker::EndpointConfig", {
      ProductionVariants: [
        Match.objectLike({
          InstanceType: "ml.g5.xlarge",
        }),
      ],
    });
  });

  test("creates SageMaker endpoint", () => {
    template.resourceCountIs("AWS::SageMaker::Endpoint", 1);
  });

  test("creates Lambda function with correct memory and timeout", () => {
    template.hasResourceProperties("AWS::Lambda::Function", {
      MemorySize: 512,
      Timeout: 300,
    });
  });

  test("Lambda has SageMaker invoke permissions", () => {
    template.hasResourceProperties("AWS::IAM::Policy", {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: [
              "sagemaker:InvokeEndpoint",
              "sagemaker:InvokeEndpointWithResponseStream",
            ],
            Effect: "Allow",
          }),
        ]),
      },
    });
  });

  test("has scaling target with min=0, max=1", () => {
    template.hasResourceProperties(
      "AWS::ApplicationAutoScaling::ScalableTarget",
      {
        MinCapacity: 0,
        MaxCapacity: 1,
      }
    );
  });

  test("has CfnOutputs for EndpointName and LambdaFunctionUrl", () => {
    template.hasOutput("EndpointName", {});
    template.hasOutput("LambdaFunctionUrl", {});
  });
});
