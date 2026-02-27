import * as cdk from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
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

    // Import bucket created by StorageStack (avoids cyclic cross-stack reference)
    const frontendBucket = s3.Bucket.fromBucketName(
      this,
      "FrontendBucket",
      `peft-frontend-${cdk.Aws.ACCOUNT_ID}`
    );

    // Origin Access Identity for CloudFront → S3
    const oai = new cloudfront.OriginAccessIdentity(this, "OAI");

    // Grant OAI read access via bucket policy (can't use grantRead on imported bucket)
    new s3.CfnBucketPolicy(this, "FrontendBucketPolicy", {
      bucket: frontendBucket.bucketName,
      policyDocument: new iam.PolicyDocument({
        statements: [
          new iam.PolicyStatement({
            actions: ["s3:GetObject"],
            resources: [`${frontendBucket.bucketArn}/*`],
            principals: [
              new iam.CanonicalUserPrincipal(
                oai.cloudFrontOriginAccessIdentityS3CanonicalUserId
              ),
            ],
          }),
        ],
      }),
    });

    // Lambda Function URL origin with OAC (SigV4 signed requests)
    const lambdaOrigin = origins.FunctionUrlOrigin.withOriginAccessControl(
      props.lambdaFunctionUrl
    );

    // Security response headers
    const responseHeadersPolicy = new cloudfront.ResponseHeadersPolicy(
      this,
      "SecurityHeaders",
      {
        securityHeadersBehavior: {
          contentSecurityPolicy: {
            contentSecurityPolicy:
              "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' https://cognito-idp.eu-central-1.amazonaws.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
            override: true,
          },
          contentTypeOptions: { override: true },
          frameOptions: {
            frameOption: cloudfront.HeadersFrameOption.DENY,
            override: true,
          },
          referrerPolicy: {
            referrerPolicy:
              cloudfront.HeadersReferrerPolicy
                .STRICT_ORIGIN_WHEN_CROSS_ORIGIN,
            override: true,
          },
          strictTransportSecurity: {
            accessControlMaxAge: cdk.Duration.days(365),
            includeSubdomains: true,
            override: true,
          },
        },
      }
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
        responseHeadersPolicy,
      },
      additionalBehaviors: {
        "/api/*": {
          origin: lambdaOrigin,
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
    // prune: false so this deployment doesn't delete assets uploaded by DeployFrontend
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
      prune: false,
    });

    new cdk.CfnOutput(this, "DistributionUrl", {
      value: `https://${this.distribution.distributionDomainName}`,
      description: "CloudFront distribution URL",
    });
  }
}
