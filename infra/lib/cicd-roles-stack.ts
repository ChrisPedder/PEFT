import * as cdk from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";

interface CicdRolesStackProps extends cdk.StackProps {
  /** GitHub owner/repo, e.g. "ChrisPedder/PEFT" */
  githubRepo: string;
}

/**
 * Creates per-workflow IAM OIDC roles for GitHub Actions CI/CD.
 * Each role has minimum permissions scoped to what the workflow actually does.
 */
export class CicdRolesStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: CicdRolesStackProps) {
    super(scope, id, props);

    const { githubRepo } = props;

    // GitHub OIDC provider
    const oidcProvider = new iam.OpenIdConnectProvider(
      this,
      "GitHubOidc",
      {
        url: "https://token.actions.githubusercontent.com",
        clientIds: ["sts.amazonaws.com"],
      }
    );

    const oidcCondition = {
      StringEquals: {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
      },
      StringLike: {
        "token.actions.githubusercontent.com:sub": `repo:${githubRepo}:*`,
      },
    };

    const githubPrincipal = new iam.FederatedPrincipal(
      oidcProvider.openIdConnectProviderArn,
      oidcCondition,
      "sts:AssumeRoleWithWebIdentity"
    );

    // ---------------------------------------------------------------
    // Deploy Role — CDK deploy (assumes CDK bootstrap roles)
    // ---------------------------------------------------------------
    const deployRole = new iam.Role(this, "DeployRole", {
      roleName: "PeftCicdDeployRole",
      assumedBy: githubPrincipal,
      maxSessionDuration: cdk.Duration.hours(1),
    });

    deployRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "AssumeBootstrapRoles",
        actions: ["sts:AssumeRole"],
        resources: [
          `arn:aws:iam::${cdk.Aws.ACCOUNT_ID}:role/cdk-*`,
        ],
      })
    );

    // ---------------------------------------------------------------
    // Scraper Role — submit and monitor Batch scrape jobs
    // ---------------------------------------------------------------
    const scraperRole = new iam.Role(this, "ScraperRole", {
      roleName: "PeftCicdScraperRole",
      assumedBy: githubPrincipal,
      maxSessionDuration: cdk.Duration.hours(1),
    });

    scraperRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "BatchSubmitScrape",
        actions: ["batch:SubmitJob"],
        resources: [
          `arn:aws:batch:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:job-queue/peft-*`,
          `arn:aws:batch:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:job-definition/peft-scrape-*`,
        ],
      })
    );

    scraperRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "BatchDescribe",
        actions: ["batch:DescribeJobs"],
        resources: ["*"],
      })
    );

    // ---------------------------------------------------------------
    // Process Role — submit and monitor Batch process jobs
    // ---------------------------------------------------------------
    const processRole = new iam.Role(this, "ProcessRole", {
      roleName: "PeftCicdProcessRole",
      assumedBy: githubPrincipal,
      maxSessionDuration: cdk.Duration.hours(1),
    });

    processRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "BatchSubmitProcess",
        actions: ["batch:SubmitJob"],
        resources: [
          `arn:aws:batch:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:job-queue/peft-*`,
          `arn:aws:batch:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:job-definition/peft-process-*`,
        ],
      })
    );

    processRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "BatchDescribe",
        actions: ["batch:DescribeJobs"],
        resources: ["*"],
      })
    );

    // ---------------------------------------------------------------
    // Train Role — launch and monitor SageMaker training jobs
    // ---------------------------------------------------------------
    const trainRole = new iam.Role(this, "TrainRole", {
      roleName: "PeftCicdTrainRole",
      assumedBy: githubPrincipal,
      maxSessionDuration: cdk.Duration.hours(2),
    });

    trainRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "SageMakerTraining",
        actions: [
          "sagemaker:CreateTrainingJob",
          "sagemaker:DescribeTrainingJob",
        ],
        resources: [
          `arn:aws:sagemaker:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:training-job/peft-*`,
        ],
      })
    );

    trainRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "PassTrainingRole",
        actions: ["iam:PassRole"],
        resources: [
          `arn:aws:iam::${cdk.Aws.ACCOUNT_ID}:role/PeftTrainingRole`,
        ],
        conditions: {
          StringEquals: {
            "iam:PassedToService": "sagemaker.amazonaws.com",
          },
        },
      })
    );

    trainRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "S3TrainingData",
        actions: ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
        resources: [
          `arn:aws:s3:::peft-training-data-${cdk.Aws.ACCOUNT_ID}`,
          `arn:aws:s3:::peft-training-data-${cdk.Aws.ACCOUNT_ID}/*`,
          `arn:aws:s3:::peft-model-artifacts-${cdk.Aws.ACCOUNT_ID}`,
          `arn:aws:s3:::peft-model-artifacts-${cdk.Aws.ACCOUNT_ID}/*`,
        ],
      })
    );

    trainRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "DynamoDBMetrics",
        actions: ["dynamodb:PutItem"],
        resources: [
          `arn:aws:dynamodb:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:table/peft-training-metrics`,
        ],
      })
    );

    trainRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "StsIdentity",
        actions: ["sts:GetCallerIdentity"],
        resources: ["*"],
      })
    );

    // ---------------------------------------------------------------
    // Update-Model Role — merge adapter, import to Bedrock
    // ---------------------------------------------------------------
    const updateModelRole = new iam.Role(this, "UpdateModelRole", {
      roleName: "PeftCicdUpdateModelRole",
      assumedBy: githubPrincipal,
      maxSessionDuration: cdk.Duration.hours(2),
    });

    updateModelRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "S3ModelArtifacts",
        actions: [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
        ],
        resources: [
          `arn:aws:s3:::peft-model-artifacts-${cdk.Aws.ACCOUNT_ID}`,
          `arn:aws:s3:::peft-model-artifacts-${cdk.Aws.ACCOUNT_ID}/*`,
        ],
      })
    );

    updateModelRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "BedrockImport",
        actions: [
          "bedrock:CreateModelImportJob",
          "bedrock:GetModelImportJob",
        ],
        resources: ["*"],
      })
    );

    updateModelRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "PassBedrockImportRole",
        actions: ["iam:PassRole"],
        resources: [
          `arn:aws:iam::${cdk.Aws.ACCOUNT_ID}:role/PeftBedrockImportRole`,
        ],
        conditions: {
          StringEquals: {
            "iam:PassedToService": "bedrock.amazonaws.com",
          },
        },
      })
    );

    updateModelRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "DynamoDBMetrics",
        actions: ["dynamodb:PutItem"],
        resources: [
          `arn:aws:dynamodb:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:table/peft-training-metrics`,
        ],
      })
    );

    updateModelRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "StsIdentity",
        actions: ["sts:GetCallerIdentity"],
        resources: ["*"],
      })
    );

    // ---------------------------------------------------------------
    // Outputs — role ARNs to set as GitHub secrets
    // ---------------------------------------------------------------
    new cdk.CfnOutput(this, "DeployRoleArn", {
      value: deployRole.roleArn,
      description: "Set as GitHub secret AWS_DEPLOY_ROLE_ARN",
    });
    new cdk.CfnOutput(this, "ScraperRoleArn", {
      value: scraperRole.roleArn,
      description: "Set as GitHub secret AWS_SCRAPER_ROLE_ARN",
    });
    new cdk.CfnOutput(this, "ProcessRoleArn", {
      value: processRole.roleArn,
      description: "Set as GitHub secret AWS_PROCESS_ROLE_ARN",
    });
    new cdk.CfnOutput(this, "TrainRoleArn", {
      value: trainRole.roleArn,
      description: "Set as GitHub secret AWS_TRAIN_ROLE_ARN",
    });
    new cdk.CfnOutput(this, "UpdateModelRoleArn", {
      value: updateModelRole.roleArn,
      description: "Set as GitHub secret AWS_UPDATE_MODEL_ROLE_ARN",
    });
  }
}
