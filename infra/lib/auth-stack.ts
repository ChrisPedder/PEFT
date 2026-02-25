import * as cdk from "aws-cdk-lib";
import * as cognito from "aws-cdk-lib/aws-cognito";
import { Construct } from "constructs";

export class AuthStack extends cdk.Stack {
  public readonly userPool: cognito.UserPool;
  public readonly userPoolClientId: string;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    this.userPool = new cognito.UserPool(this, "UserPool", {
      userPoolName: "peft-user-pool",
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      passwordPolicy: {
        minLength: 8,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: false,
      },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const appClient = this.userPool.addClient("WebClient", {
      userPoolClientName: "peft-web-client",
      generateSecret: false,
      authFlows: {
        userSrp: true,
        userPassword: true,
      },
    });

    this.userPoolClientId = appClient.userPoolClientId;

    new cdk.CfnOutput(this, "UserPoolId", {
      value: this.userPool.userPoolId,
    });
    new cdk.CfnOutput(this, "UserPoolClientId", {
      value: appClient.userPoolClientId,
    });
    new cdk.CfnOutput(this, "CognitoRegion", {
      value: cdk.Aws.REGION,
    });
  }
}
