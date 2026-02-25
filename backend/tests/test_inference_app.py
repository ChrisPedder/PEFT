"""Tests for backend/inference/app.py — FastAPI endpoints."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import httpx
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Patch the boto3 client before importing app, since it's created at module level
_mock_sagemaker_runtime = MagicMock()

with patch("boto3.client", return_value=_mock_sagemaker_runtime):
    from backend.inference.app import app, get_current_user


# Override the auth dependency for tests that need an authenticated user
_mock_user = {"sub": "test-user-id", "email": "test@example.com", "token_use": "id"}


@pytest.fixture(autouse=True)
def override_auth():
    """Override auth dependency with a mock user for all tests by default."""
    app.dependency_overrides[get_current_user] = lambda: _mock_user
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def mock_sagemaker():
    """Reset and yield the mock sagemaker runtime client."""
    _mock_sagemaker_runtime.reset_mock()
    # Provide a mock exceptions attribute
    _mock_sagemaker_runtime.exceptions = MagicMock()
    _mock_sagemaker_runtime.exceptions.ModelNotReadyException = type(
        "ModelNotReadyException", (Exception,), {}
    )
    with patch.object(app, "state", create=True):
        yield _mock_sagemaker_runtime


@pytest.mark.asyncio
async def test_health_endpoint():
    """GET /api/health returns 200 with status=ok (no auth required)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "endpoint" in data


@pytest.mark.asyncio
async def test_health_endpoint_no_auth():
    """GET /api/health returns 200 even without the auth override (no auth on health)."""
    app.dependency_overrides.clear()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_ask_returns_401_without_auth():
    """POST /api/ask returns 401 when no Authorization header is provided."""
    app.dependency_overrides.clear()  # Remove the mock auth
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/ask",
            json={"question": "test question"},
        )

    assert response.status_code == 401
    assert "authorization" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_ask_returns_401_with_invalid_token():
    """POST /api/ask returns 401 when an invalid JWT is provided."""
    app.dependency_overrides.clear()  # Remove the mock auth
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/ask",
            json={"question": "test question"},
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ask_success(mock_sagemaker):
    """POST /api/ask streams SSE tokens from SageMaker."""
    # Build a mock streaming response in TGI format
    tgi_data = 'data: {"token": {"text": "Hello"}}\ndata: {"token": {"text": " world"}}\ndata: [DONE]\n'
    mock_payload_part = {"PayloadPart": {"Bytes": tgi_data.encode("utf-8")}}

    mock_body = MagicMock()
    mock_body.__iter__ = MagicMock(return_value=iter([mock_payload_part]))

    mock_sagemaker.invoke_endpoint_with_response_stream.return_value = {
        "Body": mock_body,
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("backend.inference.app.sagemaker_runtime", mock_sagemaker):
            response = await client.post(
                "/api/ask",
                json={"question": "What is your policy on education?"},
            )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

    # Parse SSE events from response
    body = response.text
    assert "Hello" in body
    assert "world" in body
    assert "[DONE]" in body


@pytest.mark.asyncio
async def test_ask_model_not_ready(mock_sagemaker):
    """POST /api/ask returns 503 when ModelNotReadyException is raised."""
    ModelNotReadyException = mock_sagemaker.exceptions.ModelNotReadyException
    mock_sagemaker.invoke_endpoint_with_response_stream.side_effect = (
        ModelNotReadyException("Model not ready")
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("backend.inference.app.sagemaker_runtime", mock_sagemaker):
            response = await client.post(
                "/api/ask",
                json={"question": "test question"},
            )

    assert response.status_code == 503
    assert "warming up" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_ask_validation_error(mock_sagemaker):
    """POST /api/ask returns 503 when a ValidationError-type exception occurs."""
    mock_sagemaker.invoke_endpoint_with_response_stream.side_effect = Exception(
        "An error occurred (ValidationError) when calling the InvokeEndpoint operation"
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("backend.inference.app.sagemaker_runtime", mock_sagemaker):
            response = await client.post(
                "/api/ask",
                json={"question": "test question"},
            )

    assert response.status_code == 503
    assert "not available" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_ask_generic_error(mock_sagemaker):
    """POST /api/ask returns 500 on an unexpected exception."""
    mock_sagemaker.invoke_endpoint_with_response_stream.side_effect = Exception(
        "Something totally unexpected"
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("backend.inference.app.sagemaker_runtime", mock_sagemaker):
            response = await client.post(
                "/api/ask",
                json={"question": "test question"},
            )

    assert response.status_code == 500
    assert "SageMaker error" in response.json()["detail"]
