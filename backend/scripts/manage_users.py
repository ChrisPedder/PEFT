#!/usr/bin/env python3
"""CLI tool to manage Cognito users for the PEFT app.

Usage:
    python manage_users.py create --email user@example.com --password Pass123!
    python manage_users.py reset-password --email user@example.com --password NewPass!
    python manage_users.py list
    python manage_users.py delete --email user@example.com
"""

import argparse
import sys

import boto3


def find_user_pool_id(client, pool_name: str = "peft-user-pool") -> str:
    """Find the User Pool ID by name."""
    paginator = client.get_paginator("list_user_pools")
    for page in paginator.paginate(MaxResults=60):
        for pool in page["UserPools"]:
            if pool["Name"] == pool_name:
                return pool["Id"]
    raise SystemExit(f"Error: User pool '{pool_name}' not found.")


def create_user(client, pool_id: str, email: str, password: str) -> None:
    """Create a user and set a permanent password (skips FORCE_CHANGE_PASSWORD)."""
    client.admin_create_user(
        UserPoolId=pool_id,
        Username=email,
        UserAttributes=[
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
        ],
        MessageAction="SUPPRESS",
    )
    client.admin_set_user_password(
        UserPoolId=pool_id,
        Username=email,
        Password=password,
        Permanent=True,
    )
    print(f"Created user: {email}")


def reset_password(client, pool_id: str, email: str, password: str) -> None:
    """Reset a user's password."""
    client.admin_set_user_password(
        UserPoolId=pool_id,
        Username=email,
        Password=password,
        Permanent=True,
    )
    print(f"Password reset for: {email}")


def list_users(client, pool_id: str) -> None:
    """List all users in the pool."""
    paginator = client.get_paginator("list_users")
    users_found = False
    for page in paginator.paginate(UserPoolId=pool_id):
        for user in page["Users"]:
            users_found = True
            email = ""
            for attr in user.get("Attributes", []):
                if attr["Name"] == "email":
                    email = attr["Value"]
                    break
            status = user.get("UserStatus", "UNKNOWN")
            enabled = user.get("Enabled", False)
            print(f"  {email:40s}  status={status:30s}  enabled={enabled}")
    if not users_found:
        print("  (no users)")


def delete_user(client, pool_id: str, email: str) -> None:
    """Delete a user."""
    client.admin_delete_user(
        UserPoolId=pool_id,
        Username=email,
    )
    print(f"Deleted user: {email}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Manage PEFT Cognito users")
    sub = parser.add_subparsers(dest="command", required=True)

    create_p = sub.add_parser("create", help="Create a new user")
    create_p.add_argument("--email", required=True)
    create_p.add_argument("--password", required=True)

    reset_p = sub.add_parser("reset-password", help="Reset a user's password")
    reset_p.add_argument("--email", required=True)
    reset_p.add_argument("--password", required=True)

    sub.add_parser("list", help="List all users")

    del_p = sub.add_parser("delete", help="Delete a user")
    del_p.add_argument("--email", required=True)

    args = parser.parse_args(argv)
    client = boto3.client("cognito-idp")
    pool_id = find_user_pool_id(client)

    if args.command == "create":
        create_user(client, pool_id, args.email, args.password)
    elif args.command == "reset-password":
        reset_password(client, pool_id, args.email, args.password)
    elif args.command == "list":
        list_users(client, pool_id)
    elif args.command == "delete":
        delete_user(client, pool_id, args.email)


if __name__ == "__main__":
    main()
