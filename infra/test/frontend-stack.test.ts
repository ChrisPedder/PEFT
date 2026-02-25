import * as cdk from "aws-cdk-lib";
import { Template, Match } from "aws-cdk-lib/assertions";
import { StorageStack } from "../lib/storage-stack";
import { InferenceStack } from "../lib/inference-stack";
import { FrontendStack } from "../lib/frontend-stack";

describe("FrontendStack", () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const storageStack = new StorageStack(app, "TestStorage");
    const inferenceStack = new InferenceStack(app, "TestInference", {
      modelBucket: storageStack.modelBucket,
      cognitoUserPoolId: "us-east-1_testpool",
    });
    const stack = new FrontendStack(app, "TestFrontend", {
      lambdaFunctionUrl: inferenceStack.lambdaFunctionUrl,
      cognitoUserPoolId: "us-east-1_testpool",
      cognitoClientId: "test-client-id",
    });
    template = Template.fromStack(stack);
  });

  test("creates S3 bucket for frontend", () => {
    template.hasResourceProperties("AWS::S3::Bucket", {
      BucketName: Match.objectLike({
        "Fn::Join": Match.anyValue(),
      }),
    });
  });

  test("creates CloudFront distribution", () => {
    template.resourceCountIs("AWS::CloudFront::Distribution", 1);
  });

  test("CloudFront has /api/* behavior", () => {
    template.hasResourceProperties("AWS::CloudFront::Distribution", {
      DistributionConfig: Match.objectLike({
        CacheBehaviors: Match.arrayWith([
          Match.objectLike({
            PathPattern: "/api/*",
          }),
        ]),
      }),
    });
  });

  test("has CfnOutput for DistributionUrl", () => {
    template.hasOutput("DistributionUrl", {});
  });
});
