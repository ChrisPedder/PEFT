import * as cdk from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

export class StorageStack extends cdk.Stack {
  public readonly dataBucket: s3.Bucket;
  public readonly trainingDataBucket: s3.Bucket;
  public readonly modelBucket: s3.Bucket;
  public readonly frontendBucket: s3.Bucket;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Raw scraped speeches
    this.dataBucket = new s3.Bucket(this, "SpeechDataBucket", {
      bucketName: `peft-speech-data-${cdk.Aws.ACCOUNT_ID}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      lifecycleRules: [
        {
          id: "CleanupIncompleteUploads",
          abortIncompleteMultipartUploadAfter: cdk.Duration.days(7),
        },
        {
          id: "ExpireOldVersions",
          noncurrentVersionExpiration: cdk.Duration.days(90),
        },
      ],
    });

    // Processed training data (clean_and_format output)
    this.trainingDataBucket = new s3.Bucket(this, "TrainingDataBucket", {
      bucketName: `peft-training-data-${cdk.Aws.ACCOUNT_ID}`,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      lifecycleRules: [
        {
          id: "CleanupIncompleteUploads",
          abortIncompleteMultipartUploadAfter: cdk.Duration.days(7),
        },
        {
          id: "ExpireOldVersions",
          noncurrentVersionExpiration: cdk.Duration.days(90),
        },
      ],
    });

    // Trained model weights / artifacts
    this.modelBucket = new s3.Bucket(this, "ModelArtifactsBucket", {
      bucketName: `peft-model-artifacts-${cdk.Aws.ACCOUNT_ID}`,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      lifecycleRules: [
        {
          id: "ExpireOldVersions",
          noncurrentVersionExpiration: cdk.Duration.days(90),
        },
      ],
    });

    // Static frontend assets (served by CloudFront)
    this.frontendBucket = new s3.Bucket(this, "FrontendBucket", {
      bucketName: `peft-frontend-${cdk.Aws.ACCOUNT_ID}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

    // Outputs
    new cdk.CfnOutput(this, "DataBucketName", {
      value: this.dataBucket.bucketName,
    });
    new cdk.CfnOutput(this, "TrainingDataBucketName", {
      value: this.trainingDataBucket.bucketName,
    });
    new cdk.CfnOutput(this, "ModelBucketName", {
      value: this.modelBucket.bucketName,
    });
    new cdk.CfnOutput(this, "FrontendBucketName", {
      value: this.frontendBucket.bucketName,
    });
  }
}
