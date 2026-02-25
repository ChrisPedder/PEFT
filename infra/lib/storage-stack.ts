import * as cdk from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as iam from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";

export class StorageStack extends cdk.Stack {
  public readonly dataBucket: s3.Bucket;
  public readonly modelBucket: s3.Bucket;
  public readonly frontendBucket: s3.Bucket;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Raw + processed training data
    this.dataBucket = new s3.Bucket(this, "SpeechDataBucket", {
      bucketName: `peft-speech-data-${cdk.Aws.ACCOUNT_ID}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      versioned: false,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      lifecycleRules: [
        {
          id: "CleanupIncompleteUploads",
          abortIncompleteMultipartUploadAfter: cdk.Duration.days(7),
        },
      ],
    });

    // Trained model weights / artifacts
    this.modelBucket = new s3.Bucket(this, "ModelArtifactsBucket", {
      bucketName: `peft-model-artifacts-${cdk.Aws.ACCOUNT_ID}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

    // Static frontend assets (served by CloudFront)
    this.frontendBucket = new s3.Bucket(this, "FrontendBucket", {
      bucketName: `peft-frontend-${cdk.Aws.ACCOUNT_ID}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

    // SageMaker execution role with access to data and model buckets
    const sagemakerRole = new iam.Role(this, "SageMakerExecutionRole", {
      roleName: "PeftSageMakerExecutionRole",
      assumedBy: new iam.ServicePrincipal("sagemaker.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonSageMakerFullAccess"),
      ],
    });

    this.dataBucket.grantReadWrite(sagemakerRole);
    this.modelBucket.grantReadWrite(sagemakerRole);

    // Outputs
    new cdk.CfnOutput(this, "DataBucketName", {
      value: this.dataBucket.bucketName,
    });
    new cdk.CfnOutput(this, "ModelBucketName", {
      value: this.modelBucket.bucketName,
    });
    new cdk.CfnOutput(this, "FrontendBucketName", {
      value: this.frontendBucket.bucketName,
    });
    new cdk.CfnOutput(this, "SageMakerRoleArn", {
      value: sagemakerRole.roleArn,
    });
  }
}
