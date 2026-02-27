import * as cdk from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as iam from "aws-cdk-lib/aws-iam";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

interface TrainingStackProps extends cdk.StackProps {
  trainingDataBucket: s3.IBucket;
  modelBucket: s3.IBucket;
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

    // IAM role for SageMaker training jobs (least-privilege, no managed policy)
    this.trainingRole = new iam.Role(this, "TrainingRole", {
      roleName: "PeftTrainingRole",
      assumedBy: new iam.ServicePrincipal("sagemaker.amazonaws.com"),
    });

    // SageMaker training actions only
    this.trainingRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "sagemaker:CreateTrainingJob",
          "sagemaker:DescribeTrainingJob",
          "sagemaker:StopTrainingJob",
          "sagemaker:AddTags",
          "sagemaker:ListTags",
        ],
        resources: [
          `arn:aws:sagemaker:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:training-job/peft-*`,
        ],
      })
    );

    // Grant access to training data and model buckets
    props.trainingDataBucket.grantRead(this.trainingRole);
    props.modelBucket.grantReadWrite(this.trainingRole);

    // ECR: GetAuthorizationToken requires resource "*"
    this.trainingRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["ecr:GetAuthorizationToken"],
        resources: ["*"],
      })
    );

    // ECR: Pull actions scoped to HuggingFace DLC repos
    this.trainingRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
        ],
        resources: [
          `arn:aws:ecr:${cdk.Aws.REGION}:763104351884:repository/huggingface-pytorch-training`,
        ],
      })
    );

    // CloudWatch logging scoped to current region and account
    this.trainingRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ],
        resources: [
          `arn:aws:logs:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:log-group:/aws/sagemaker/*`,
        ],
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
  }
}
