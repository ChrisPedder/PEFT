import * as cdk from "aws-cdk-lib";
import { Template, Match } from "aws-cdk-lib/assertions";
import { AuthStack } from "../lib/auth-stack";

describe("AuthStack", () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const stack = new AuthStack(app, "TestAuth");
    template = Template.fromStack(stack);
  });

  test("creates Cognito User Pool with self-signup disabled", () => {
    template.hasResourceProperties("AWS::Cognito::UserPool", {
      UserPoolName: "peft-user-pool",
      Policies: Match.objectLike({
        PasswordPolicy: Match.objectLike({
          MinimumLength: 8,
          RequireUppercase: true,
          RequireNumbers: true,
        }),
      }),
    });
  });

  test("User Pool uses email as sign-in alias", () => {
    template.hasResourceProperties("AWS::Cognito::UserPool", {
      UsernameAttributes: ["email"],
    });
  });

  test("creates App Client without secret", () => {
    template.hasResourceProperties("AWS::Cognito::UserPoolClient", {
      ClientName: "peft-web-client",
      GenerateSecret: false,
      ExplicitAuthFlows: Match.arrayWith([
        "ALLOW_USER_PASSWORD_AUTH",
        "ALLOW_USER_SRP_AUTH",
      ]),
    });
  });

  test("has CfnOutputs for UserPoolId, UserPoolClientId, and CognitoRegion", () => {
    template.hasOutput("UserPoolId", {});
    template.hasOutput("UserPoolClientId", {});
    template.hasOutput("CognitoRegion", {});
  });
});
