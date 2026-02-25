import * as cdk from "aws-cdk-lib";
import * as batch from "aws-cdk-lib/aws-batch";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as ecr_assets from "aws-cdk-lib/aws-ecr-assets";
import * as iam from "aws-cdk-lib/aws-iam";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";
import * as path from "path";

interface ScraperBatchStackProps extends cdk.StackProps {
  dataBucket: s3.IBucket;
  trainingDataBucket: s3.IBucket;
}

export class ScraperBatchStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: ScraperBatchStackProps) {
    super(scope, id, props);

    const vpc = new ec2.Vpc(this, "BatchVpc", {
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        {
          name: "Public",
          subnetType: ec2.SubnetType.PUBLIC,
        },
      ],
    });

    const securityGroup = new ec2.SecurityGroup(this, "BatchSecurityGroup", {
      vpc,
      description: "Security group for scraper Batch jobs",
      allowAllOutbound: true,
    });

    // Fargate compute environment
    const computeEnv = new batch.FargateComputeEnvironment(
      this,
      "ComputeEnv",
      {
        vpc,
        vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
        securityGroups: [securityGroup],
        maxvCpus: 4,
      }
    );

    const jobQueue = new batch.JobQueue(this, "JobQueue", {
      jobQueueName: "peft-scraper-job-queue",
      computeEnvironments: [
        { computeEnvironment: computeEnv, order: 1 },
      ],
    });

    // Docker image (build context = backend/, Dockerfile = scraper/Dockerfile)
    const image = new ecr_assets.DockerImageAsset(this, "ScraperImage", {
      directory: path.join(__dirname, "../../backend"),
      file: "scraper/Dockerfile",
    });

    // IAM execution role (ECR pull + CloudWatch)
    const executionRole = new iam.Role(this, "ExecutionRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AmazonECSTaskExecutionRolePolicy"
        ),
      ],
    });

    // IAM task role (S3, Bedrock, STS)
    const taskRole = new iam.Role(this, "TaskRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
    });

    props.dataBucket.grantReadWrite(taskRole);
    props.trainingDataBucket.grantReadWrite(taskRole);

    taskRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["bedrock:Converse", "bedrock:InvokeModel"],
        resources: ["*"],
      })
    );

    taskRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["sts:GetCallerIdentity"],
        resources: ["*"],
      })
    );

    // Scrape job definition
    const scrapeJobDef = new batch.EcsJobDefinition(this, "ScrapeJobDef", {
      jobDefinitionName: "peft-scrape-speeches",
      timeout: cdk.Duration.hours(2),
      container: new batch.EcsFargateContainerDefinition(
        this,
        "ScrapeContainer",
        {
          image: ecs.ContainerImage.fromEcrRepository(
            image.repository,
            image.imageTag
          ),
          cpu: 1,
          memory: cdk.Size.gibibytes(2),
          executionRole,
          jobRole: taskRole,
          assignPublicIp: true,
          environment: {
            DATA_BUCKET: props.dataBucket.bucketName,
          },
          command: [
            "sh",
            "-c",
            "python -m scraper.scrape_speeches --bucket $DATA_BUCKET && python -m scraper.upload_to_s3",
          ],
        }
      ),
    });

    // Process job definition
    const processJobDef = new batch.EcsJobDefinition(this, "ProcessJobDef", {
      jobDefinitionName: "peft-process-speeches",
      timeout: cdk.Duration.hours(4),
      container: new batch.EcsFargateContainerDefinition(
        this,
        "ProcessContainer",
        {
          image: ecs.ContainerImage.fromEcrRepository(
            image.repository,
            image.imageTag
          ),
          cpu: 1,
          memory: cdk.Size.gibibytes(2),
          executionRole,
          jobRole: taskRole,
          assignPublicIp: true,
          environment: {
            DATA_BUCKET: props.dataBucket.bucketName,
            TRAINING_DATA_BUCKET: props.trainingDataBucket.bucketName,
          },
          command: [
            "sh",
            "-c",
            [
              "aws s3 cp s3://$DATA_BUCKET/raw/speeches.jsonl scraper/data/raw_speeches.jsonl",
              "python -m scraper.clean_and_format",
              "aws s3 cp scraper/data/training_data.jsonl s3://$TRAINING_DATA_BUCKET/training_data.jsonl",
            ].join(" && "),
          ],
        }
      ),
    });

    // Outputs
    new cdk.CfnOutput(this, "JobQueueName", {
      value: jobQueue.jobQueueName,
    });
    new cdk.CfnOutput(this, "ScrapeJobDefinitionArn", {
      value: scrapeJobDef.jobDefinitionArn,
    });
    new cdk.CfnOutput(this, "ProcessJobDefinitionArn", {
      value: processJobDef.jobDefinitionArn,
    });
  }
}
