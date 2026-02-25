import * as cdk from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as sagemaker from "aws-cdk-lib/aws-sagemaker";
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

    // --- SageMaker Endpoint (Inference Components with scale-to-zero) ---

    const endpointExecutionRole = new iam.Role(this, "EndpointRole", {
      roleName: "PeftEndpointExecutionRole",
      assumedBy: new iam.ServicePrincipal("sagemaker.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonSageMakerFullAccess"),
      ],
    });
    props.modelBucket.grantRead(endpointExecutionRole);

    // Endpoint configuration — uses real-time inference with managed auto-scaling
    const endpointConfig = new sagemaker.CfnEndpointConfig(
      this,
      "EndpointConfig",
      {
        endpointConfigName: "peft-obama-endpoint-config",
        productionVariants: [
          {
            variantName: "default",
            instanceType: "ml.g5.xlarge",
            initialInstanceCount: 1, // Min for EndpointConfig; auto-scaling scales to zero after idle
            modelName: "peft-obama-model", // Created after training via CLI
            routingConfig: {
              routingStrategy: "LEAST_OUTSTANDING_REQUESTS",
            },
          },
        ],
      }
    );

    const endpoint = new sagemaker.CfnEndpoint(this, "Endpoint", {
      endpointName: "peft-obama-endpoint",
      endpointConfigName: endpointConfig.endpointConfigName!,
    });
    endpoint.addDependency(endpointConfig);

    // Auto-scaling policy: 0 min, 1 max
    const scalingTarget = new cdk.aws_applicationautoscaling.CfnScalableTarget(
      this,
      "ScalingTarget",
      {
        serviceNamespace: "sagemaker",
        resourceId: `endpoint/peft-obama-endpoint/variant/default`,
        scalableDimension: "sagemaker:variant:DesiredInstanceCount",
        minCapacity: 0,
        maxCapacity: 1,
        roleArn: endpointExecutionRole.roleArn,
      }
    );
    scalingTarget.addDependency(endpoint);

    const scalingPolicy =
      new cdk.aws_applicationautoscaling.CfnScalingPolicy(
        this,
        "ScalingPolicy",
        {
          policyName: "peft-scale-to-zero",
          policyType: "TargetTrackingScaling",
          serviceNamespace: "sagemaker",
          resourceId: `endpoint/peft-obama-endpoint/variant/default`,
          scalableDimension: "sagemaker:variant:DesiredInstanceCount",
          targetTrackingScalingPolicyConfiguration: {
            targetValue: 1.0,
            predefinedMetricSpecification: {
              predefinedMetricType:
                "SageMakerVariantInvocationsPerInstance",
            },
            scaleInCooldown: 600, // 10 min before scaling to zero
            scaleOutCooldown: 60,
          },
        }
      );
    scalingPolicy.addDependency(scalingTarget);

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

    // Allow Lambda to invoke SageMaker endpoint (including streaming)
    lambdaRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "sagemaker:InvokeEndpoint",
          "sagemaker:InvokeEndpointWithResponseStream",
        ],
        resources: [
          `arn:aws:sagemaker:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:endpoint/peft-obama-endpoint`,
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
          SAGEMAKER_ENDPOINT_NAME: "peft-obama-endpoint",
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

    new cdk.CfnOutput(this, "EndpointName", {
      value: endpoint.endpointName!,
    });
    new cdk.CfnOutput(this, "LambdaFunctionUrl", {
      value: this.lambdaFunctionUrl.url,
    });
  }
}
