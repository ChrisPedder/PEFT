import * as cdk from "aws-cdk-lib";
import { Template, Match } from "aws-cdk-lib/assertions";
import { CicdRolesStack } from "../lib/cicd-roles-stack";

describe("CicdRolesStack", () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const stack = new CicdRolesStack(app, "TestCicdRoles", {
      githubRepo: "TestOwner/TestRepo",
    });
    template = Template.fromStack(stack);
  });

  test("creates GitHub OIDC provider", () => {
    template.hasResourceProperties(
      "Custom::AWSCDKOpenIdConnectProvider",
      {
        Url: "https://token.actions.githubusercontent.com",
        ClientIDList: ["sts.amazonaws.com"],
      }
    );
  });

  test("creates five IAM roles", () => {
    const roles = template.findResources("AWS::IAM::Role");
    const roleNames = Object.values(roles)
      .map((r: Record<string, unknown>) => {
        const props = r["Properties"] as Record<string, unknown>;
        return props["RoleName"] as string;
      })
      .filter(Boolean);

    expect(roleNames).toContain("PeftCicdDeployRole");
    expect(roleNames).toContain("PeftCicdScraperRole");
    expect(roleNames).toContain("PeftCicdProcessRole");
    expect(roleNames).toContain("PeftCicdTrainRole");
    expect(roleNames).toContain("PeftCicdUpdateModelRole");
  });

  test("deploy role can assume CDK bootstrap roles", () => {
    template.hasResourceProperties("AWS::IAM::Policy", {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: "sts:AssumeRole",
            Effect: "Allow",
          }),
        ]),
      },
    });
  });

  test("scraper role has Batch SubmitJob scoped to peft resources", () => {
    template.hasResourceProperties("AWS::IAM::Policy", {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Sid: "BatchSubmitScrape",
            Action: "batch:SubmitJob",
            Effect: "Allow",
          }),
        ]),
      },
    });
  });

  test("train role has SageMaker training permissions", () => {
    template.hasResourceProperties("AWS::IAM::Policy", {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Sid: "SageMakerTraining",
            Action: [
              "sagemaker:CreateTrainingJob",
              "sagemaker:DescribeTrainingJob",
            ],
            Effect: "Allow",
          }),
        ]),
      },
    });
  });

  test("update-model role has Bedrock import permissions", () => {
    template.hasResourceProperties("AWS::IAM::Policy", {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Sid: "BedrockImport",
            Action: [
              "bedrock:CreateModelImportJob",
              "bedrock:GetModelImportJob",
            ],
            Effect: "Allow",
          }),
        ]),
      },
    });
  });

  test("roles with PassRole have service condition", () => {
    template.hasResourceProperties("AWS::IAM::Policy", {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Sid: "PassTrainingRole",
            Action: "iam:PassRole",
            Condition: {
              StringEquals: {
                "iam:PassedToService": "sagemaker.amazonaws.com",
              },
            },
          }),
        ]),
      },
    });
  });

  test("has CfnOutputs for all role ARNs", () => {
    template.hasOutput("DeployRoleArn", {});
    template.hasOutput("ScraperRoleArn", {});
    template.hasOutput("ProcessRoleArn", {});
    template.hasOutput("TrainRoleArn", {});
    template.hasOutput("UpdateModelRoleArn", {});
  });
});
