import * as cdk from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as ecr_assets from "aws-cdk-lib/aws-ecr-assets";
import { Construct } from "constructs";
import * as path from "path";

interface InferenceStackProps extends cdk.StackProps {
  modelBucket: s3.IBucket;
  cognitoUserPoolId: string;
}

export class InferenceStack extends cdk.Stack {
  public readonly lambdaFunctionUrl: lambda.FunctionUrl;

  constructor(scope: Construct, id: string, props: InferenceStackProps) {
    super(scope, id, props);

    // --- Bedrock Custom Model Import Role ---

    const bedrockImportRole = new iam.Role(this, "BedrockImportRole", {
      roleName: "PeftBedrockImportRole",
      assumedBy: new iam.ServicePrincipal("bedrock.amazonaws.com"),
    });

    // Allow Bedrock to read model artifacts from S3
    props.modelBucket.grantRead(bedrockImportRole);

    // --- Lambda Proxy (FastAPI via Lambda Web Adapter) ---

    const lambdaRole = new iam.Role(this, "LambdaProxyRole", {
      roleName: "PeftLambdaProxyRole",
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaBasicExecutionRole"
        ),
      ],
    });

    // Allow Lambda to invoke Bedrock imported models
    lambdaRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
        ],
        resources: [
          `arn:aws:bedrock:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:imported-model/*`,
        ],
      })
    );

    const dockerImage = new ecr_assets.DockerImageAsset(
      this,
      "LambdaImage",
      {
        directory: path.join(__dirname, "../../backend/inference"),
      }
    );

    const proxyFunction = new lambda.DockerImageFunction(
      this,
      "ProxyFunction",
      {
        functionName: "peft-inference-proxy",
        code: lambda.DockerImageCode.fromEcr(dockerImage.repository, {
          tagOrDigest: dockerImage.imageTag,
        }),
        role: lambdaRole,
        memorySize: 512,
        timeout: cdk.Duration.minutes(5),
        environment: {
          BEDROCK_MODEL_ID: "", // Set after running import_to_bedrock.py
          AWS_LWA_INVOKE_MODE: "RESPONSE_STREAM",
          COGNITO_USER_POOL_ID: props.cognitoUserPoolId,
          COGNITO_REGION: cdk.Aws.REGION,
        },
      }
    );

    // Lambda Function URL (streaming mode for SSE passthrough)
    this.lambdaFunctionUrl = proxyFunction.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      invokeMode: lambda.InvokeMode.RESPONSE_STREAM,
      cors: {
        allowedOrigins: ["*"],
        allowedMethods: [lambda.HttpMethod.POST, lambda.HttpMethod.GET],
        allowedHeaders: ["content-type", "authorization"],
      },
    });

    new cdk.CfnOutput(this, "BedrockImportRoleArn", {
      value: bedrockImportRole.roleArn,
    });
    new cdk.CfnOutput(this, "LambdaFunctionUrl", {
      value: this.lambdaFunctionUrl.url,
    });
  }
}
