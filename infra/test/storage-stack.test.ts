import * as cdk from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { StorageStack } from "../lib/storage-stack";

describe("StorageStack", () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const stack = new StorageStack(app, "TestStorage");
    template = Template.fromStack(stack);
  });

  test("creates three S3 buckets", () => {
    template.resourceCountIs("AWS::S3::Bucket", 3);
  });

  test("creates IAM role with SageMaker service principal", () => {
    template.hasResourceProperties("AWS::IAM::Role", {
      RoleName: "PeftSageMakerExecutionRole",
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

  test("has expected CfnOutputs", () => {
    template.hasOutput("DataBucketName", {});
    template.hasOutput("ModelBucketName", {});
    template.hasOutput("FrontendBucketName", {});
    template.hasOutput("SageMakerRoleArn", {});
  });

  test("data bucket has lifecycle rule for incomplete uploads (7 days)", () => {
    template.hasResourceProperties("AWS::S3::Bucket", {
      LifecycleConfiguration: {
        Rules: [
          {
            AbortIncompleteMultipartUpload: {
              DaysAfterInitiation: 7,
            },
            Id: "CleanupIncompleteUploads",
            Status: "Enabled",
          },
        ],
      },
    });
  });

  test("model bucket is versioned", () => {
    template.hasResourceProperties("AWS::S3::Bucket", {
      VersioningConfiguration: {
        Status: "Enabled",
      },
    });
  });
});
