import * as cdk from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { Construct } from "constructs";
import * as path from "path";

interface FrontendStackProps extends cdk.StackProps {
  lambdaFunctionUrl: lambda.FunctionUrl;
  cognitoUserPoolId: string;
  cognitoClientId: string;
}

export class FrontendStack extends cdk.Stack {
  public readonly distribution: cloudfront.Distribution;

  constructor(scope: Construct, id: string, props: FrontendStackProps) {
    super(scope, id, props);

    // S3 bucket for static frontend assets
    const frontendBucket = new s3.Bucket(this, "FrontendBucket", {
      bucketName: `peft-frontend-${cdk.Aws.ACCOUNT_ID}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

    // Origin Access Identity for CloudFront → S3
    const oai = new cloudfront.OriginAccessIdentity(this, "OAI");
    frontendBucket.grantRead(oai);

    // Parse the Lambda Function URL domain
    const lambdaUrlDomain = cdk.Fn.select(
      2,
      cdk.Fn.split("/", props.lambdaFunctionUrl.url)
    );

    // CloudFront distribution
    this.distribution = new cloudfront.Distribution(this, "Distribution", {
      defaultRootObject: "index.html",
      defaultBehavior: {
        origin: new origins.S3Origin(frontendBucket, {
          originAccessIdentity: oai,
        }),
        viewerProtocolPolicy:
          cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
      },
      additionalBehaviors: {
        "/api/*": {
          origin: new origins.HttpOrigin(lambdaUrlDomain, {
            protocolPolicy: cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
          }),
          viewerProtocolPolicy:
            cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy:
            cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
        },
      },
      errorResponses: [
        {
          httpStatus: 404,
          responsePagePath: "/index.html",
          responseHttpStatus: 200,
          ttl: cdk.Duration.seconds(0),
        },
      ],
    });

    // Deploy built frontend assets to S3
    new s3deploy.BucketDeployment(this, "DeployFrontend", {
      sources: [
        s3deploy.Source.asset(path.join(__dirname, "../../frontend/dist")),
      ],
      destinationBucket: frontendBucket,
      distribution: this.distribution,
      distributionPaths: ["/*"],
    });

    // Deploy runtime auth config (fetched by frontend at load time)
    new s3deploy.BucketDeployment(this, "DeployConfig", {
      sources: [
        s3deploy.Source.jsonData("config.json", {
          cognitoUserPoolId: props.cognitoUserPoolId,
          cognitoClientId: props.cognitoClientId,
          cognitoRegion: cdk.Aws.REGION,
        }),
      ],
      destinationBucket: frontendBucket,
      distribution: this.distribution,
      distributionPaths: ["/config.json"],
    });

    new cdk.CfnOutput(this, "DistributionUrl", {
      value: `https://${this.distribution.distributionDomainName}`,
      description: "CloudFront distribution URL",
    });
  }
}
