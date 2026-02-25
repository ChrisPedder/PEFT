import * as cdk from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as iam from "aws-cdk-lib/aws-iam";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

interface TrainingStackProps extends cdk.StackProps {
  trainingDataBucket: s3.IBucket;
  modelBucket: s3.IBucket;
  /** @deprecated Kept temporarily to avoid breaking the CloudFormation cross-stack export. Remove after one deploy. */
  dataBucket?: s3.IBucket;
}

/**
 * Resources for SageMaker training jobs.
 * The actual training job is launched via CLI/SDK, not as a CDK resource
 * (training jobs are one-shot, not long-lived infrastructure).
 */
export class TrainingStack extends cdk.Stack {
  public readonly trainingRole: iam.Role;

  constructor(scope: Construct, id: string, props: TrainingStackProps) {
    super(scope, id, props);

    // IAM role for SageMaker training jobs
    this.trainingRole = new iam.Role(this, "TrainingRole", {
      roleName: "PeftTrainingRole",
      assumedBy: new iam.ServicePrincipal("sagemaker.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonSageMakerFullAccess"),
      ],
    });

    // Grant access to training data and model buckets
    props.trainingDataBucket.grantRead(this.trainingRole);
    props.modelBucket.grantReadWrite(this.trainingRole);

    // Allow pulling HuggingFace containers from ECR
    this.trainingRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "ecr:GetAuthorizationToken",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
        ],
        resources: ["*"],
      })
    );

    // Allow CloudWatch logging
    this.trainingRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ],
        resources: ["arn:aws:logs:*:*:log-group:/aws/sagemaker/*"],
      })
    );

    new dynamodb.Table(this, "TrainingMetrics", {
      tableName: "peft-training-metrics",
      partitionKey: { name: "job_id", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "timestamp", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    new cdk.CfnOutput(this, "TrainingRoleArn", {
      value: this.trainingRole.roleArn,
    });

    // Temporary: keep cross-stack reference alive so CloudFormation can
    // migrate the import in one deploy.  Remove after the next deploy.
    if (props.dataBucket) {
      new cdk.CfnOutput(this, "DeprecatedDataBucketRef", {
        value: props.dataBucket.bucketArn,
        description: "Temporary — remove after one successful deploy",
      });
    }
  }
}
