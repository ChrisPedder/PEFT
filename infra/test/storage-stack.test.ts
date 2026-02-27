import * as cdk from "aws-cdk-lib";
import { Template, Match } from "aws-cdk-lib/assertions";
import { StorageStack } from "../lib/storage-stack";

describe("StorageStack", () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const stack = new StorageStack(app, "TestStorage");
    template = Template.fromStack(stack);
  });

  test("creates four S3 buckets", () => {
    template.resourceCountIs("AWS::S3::Bucket", 4);
  });

  test("has expected CfnOutputs", () => {
    template.hasOutput("DataBucketName", {});
    template.hasOutput("TrainingDataBucketName", {});
    template.hasOutput("ModelBucketName", {});
    template.hasOutput("FrontendBucketName", {});
  });

  test("data bucket has lifecycle rule for incomplete uploads (7 days)", () => {
    template.hasResourceProperties("AWS::S3::Bucket", {
      LifecycleConfiguration: {
        Rules: Match.arrayWith([
          Match.objectLike({
            AbortIncompleteMultipartUpload: {
              DaysAfterInitiation: 7,
            },
            Id: "CleanupIncompleteUploads",
            Status: "Enabled",
          }),
        ]),
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
