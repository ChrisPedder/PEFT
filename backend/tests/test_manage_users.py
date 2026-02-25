"""Tests for backend/scripts/manage_users.py — Cognito user management CLI."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.scripts.manage_users import (
    find_user_pool_id,
    create_user,
    reset_password,
    list_users,
    delete_user,
    main,
)


@pytest.fixture
def mock_cognito():
    """Return a mock cognito-idp client."""
    client = MagicMock()
    # Set up paginator for list_user_pools
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {
            "UserPools": [
                {"Id": "us-east-1_abc123", "Name": "peft-user-pool"},
                {"Id": "us-east-1_other", "Name": "other-pool"},
            ]
        }
    ]
    client.get_paginator.return_value = paginator
    return client


class TestFindUserPoolId:
    def test_finds_pool_by_name(self, mock_cognito):
        pool_id = find_user_pool_id(mock_cognito, "peft-user-pool")
        assert pool_id == "us-east-1_abc123"

    def test_raises_when_not_found(self, mock_cognito):
        with pytest.raises(SystemExit, match="not found"):
            find_user_pool_id(mock_cognito, "nonexistent-pool")


class TestCreateUser:
    def test_creates_user_and_sets_password(self, mock_cognito):
        create_user(mock_cognito, "pool-id", "user@test.com", "Pass123!")

        mock_cognito.admin_create_user.assert_called_once_with(
            UserPoolId="pool-id",
            Username="user@test.com",
            UserAttributes=[
                {"Name": "email", "Value": "user@test.com"},
                {"Name": "email_verified", "Value": "true"},
            ],
            MessageAction="SUPPRESS",
        )
        mock_cognito.admin_set_user_password.assert_called_once_with(
            UserPoolId="pool-id",
            Username="user@test.com",
            Password="Pass123!",
            Permanent=True,
        )


class TestResetPassword:
    def test_resets_password(self, mock_cognito):
        reset_password(mock_cognito, "pool-id", "user@test.com", "NewPass!")

        mock_cognito.admin_set_user_password.assert_called_once_with(
            UserPoolId="pool-id",
            Username="user@test.com",
            Password="NewPass!",
            Permanent=True,
        )


class TestListUsers:
    def test_lists_users(self, mock_cognito, capsys):
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {
                "Users": [
                    {
                        "Attributes": [{"Name": "email", "Value": "a@test.com"}],
                        "UserStatus": "CONFIRMED",
                        "Enabled": True,
                    },
                    {
                        "Attributes": [{"Name": "email", "Value": "b@test.com"}],
                        "UserStatus": "FORCE_CHANGE_PASSWORD",
                        "Enabled": True,
                    },
                ]
            }
        ]
        mock_cognito.get_paginator.return_value = paginator

        list_users(mock_cognito, "pool-id")
        output = capsys.readouterr().out
        assert "a@test.com" in output
        assert "b@test.com" in output
        assert "CONFIRMED" in output

    def test_shows_no_users_message(self, mock_cognito, capsys):
        paginator = MagicMock()
        paginator.paginate.return_value = [{"Users": []}]
        mock_cognito.get_paginator.return_value = paginator

        list_users(mock_cognito, "pool-id")
        output = capsys.readouterr().out
        assert "no users" in output


class TestDeleteUser:
    def test_deletes_user(self, mock_cognito):
        delete_user(mock_cognito, "pool-id", "user@test.com")

        mock_cognito.admin_delete_user.assert_called_once_with(
            UserPoolId="pool-id",
            Username="user@test.com",
        )


class TestMain:
    @patch("backend.scripts.manage_users.boto3")
    def test_create_command(self, mock_boto3, mock_cognito):
        mock_boto3.client.return_value = mock_cognito

        main(["create", "--email", "new@test.com", "--password", "Pass123!"])

        mock_cognito.admin_create_user.assert_called_once()
        mock_cognito.admin_set_user_password.assert_called_once()

    @patch("backend.scripts.manage_users.boto3")
    def test_list_command(self, mock_boto3, mock_cognito, capsys):
        mock_boto3.client.return_value = mock_cognito
        # Set up list_users paginator
        list_paginator = MagicMock()
        list_paginator.paginate.return_value = [{"Users": []}]

        # get_paginator is called twice: once for find_user_pool_id, once for list_users
        pool_paginator = MagicMock()
        pool_paginator.paginate.return_value = [
            {"UserPools": [{"Id": "us-east-1_abc123", "Name": "peft-user-pool"}]}
        ]
        mock_cognito.get_paginator.side_effect = [pool_paginator, list_paginator]

        main(["list"])

        output = capsys.readouterr().out
        assert "no users" in output

    @patch("backend.scripts.manage_users.boto3")
    def test_delete_command(self, mock_boto3, mock_cognito):
        mock_boto3.client.return_value = mock_cognito

        main(["delete", "--email", "del@test.com"])

        mock_cognito.admin_delete_user.assert_called_once()
