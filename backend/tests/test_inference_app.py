"""Tests for backend/inference/app.py — FastAPI endpoints."""

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import httpx
import pytest_asyncio
from jose import jwt as jose_jwt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Patch the boto3 client before importing app, since it's created at module level
_mock_sagemaker_runtime = MagicMock()

with patch("boto3.client", return_value=_mock_sagemaker_runtime):
    from backend.inference.app import app, get_current_user, _get_jwks


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
    _mock_sagemaker_runtime.reset_mock(side_effect=True, return_value=True)
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


# --- JWKS and JWT validation tests ---


@pytest.mark.asyncio
async def test_get_jwks_fetches_and_caches():
    """_get_jwks fetches JWKS from Cognito and caches the result."""
    import backend.inference.app as app_module

    app_module._jwks_cache = None
    app_module._jwks_cache_time = 0

    mock_jwks = {"keys": [{"kid": "key-1", "kty": "RSA"}]}
    with patch("backend.inference.app.http_requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            json=MagicMock(return_value=mock_jwks),
            raise_for_status=MagicMock(),
        )
        result = _get_jwks()
        assert result == mock_jwks
        assert mock_get.call_count == 1

        # Second call should use cache
        result2 = _get_jwks()
        assert result2 == mock_jwks
        assert mock_get.call_count == 1

    app_module._jwks_cache = None
    app_module._jwks_cache_time = 0


@pytest.mark.asyncio
async def test_get_jwks_refetches_after_ttl():
    """_get_jwks refetches after cache TTL expires."""
    import backend.inference.app as app_module

    mock_jwks = {"keys": [{"kid": "key-1"}]}
    app_module._jwks_cache = {"keys": [{"kid": "old"}]}
    app_module._jwks_cache_time = time.time() - 7200  # Expired

    with patch("backend.inference.app.http_requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            json=MagicMock(return_value=mock_jwks),
            raise_for_status=MagicMock(),
        )
        result = _get_jwks()
        assert result == mock_jwks
        assert mock_get.call_count == 1

    app_module._jwks_cache = None
    app_module._jwks_cache_time = 0


@pytest.mark.asyncio
async def test_auth_kid_not_found():
    """Returns 401 when token kid doesn't match any JWKS key."""
    app.dependency_overrides.clear()

    token = jose_jwt.encode(
        {"sub": "user", "token_use": "id"},
        "secret",
        algorithm="HS256",
        headers={"kid": "nonexistent-kid"},
    )

    mock_jwks = {"keys": [{"kid": "different-kid", "kty": "RSA"}]}
    with patch("backend.inference.app._get_jwks", return_value=mock_jwks):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/ask",
                json={"question": "test"},
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 401
    assert "key not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_auth_invalid_token_use():
    """Returns 401 when token_use is not 'id'."""
    app.dependency_overrides.clear()

    token = jose_jwt.encode(
        {"sub": "user", "token_use": "access"},
        "secret",
        algorithm="HS256",
        headers={"kid": "test-kid"},
    )

    mock_jwks = {"keys": [{"kid": "test-kid", "kty": "oct", "k": "c2VjcmV0"}]}
    with (
        patch("backend.inference.app._get_jwks", return_value=mock_jwks),
        patch(
            "backend.inference.app.jwt.decode",
            return_value={"sub": "user", "token_use": "access"},
        ),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/ask",
                json={"question": "test"},
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 401
    assert "token_use" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_auth_jwt_decode_error():
    """Returns 401 when jwt.decode raises JWTError."""
    app.dependency_overrides.clear()

    from jose import JWTError

    token = jose_jwt.encode(
        {"sub": "user"},
        "secret",
        algorithm="HS256",
        headers={"kid": "test-kid"},
    )

    mock_jwks = {"keys": [{"kid": "test-kid", "kty": "oct", "k": "c2VjcmV0"}]}
    with (
        patch("backend.inference.app._get_jwks", return_value=mock_jwks),
        patch(
            "backend.inference.app.jwt.decode",
            side_effect=JWTError("Signature verification failed"),
        ),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/ask",
                json={"question": "test"},
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 401
    assert "invalid token" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_auth_valid_token_succeeds(mock_sagemaker):
    """A valid JWT with correct kid and token_use=id passes auth."""
    app.dependency_overrides.clear()

    token = jose_jwt.encode(
        {"sub": "user", "token_use": "id"},
        "secret",
        algorithm="HS256",
        headers={"kid": "test-kid"},
    )

    valid_claims = {"sub": "user", "token_use": "id", "email": "user@test.com"}
    mock_jwks = {"keys": [{"kid": "test-kid", "kty": "oct", "k": "c2VjcmV0"}]}

    tgi_data = "data: [DONE]\n"
    mock_body = MagicMock()
    mock_body.__iter__ = MagicMock(
        return_value=iter([{"PayloadPart": {"Bytes": tgi_data.encode()}}])
    )
    mock_sagemaker.invoke_endpoint_with_response_stream.return_value = {
        "Body": mock_body
    }

    with (
        patch("backend.inference.app._get_jwks", return_value=mock_jwks),
        patch("backend.inference.app.jwt.decode", return_value=valid_claims),
        patch("backend.inference.app.sagemaker_runtime", mock_sagemaker),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/ask",
                json={"question": "test"},
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_stream_malformed_json(mock_sagemaker):
    """Malformed JSON in SSE stream is skipped without error."""
    tgi_data = 'data: {not valid json}\ndata: {"token": {"text": "ok"}}\ndata: [DONE]\n'

    mock_body = MagicMock()
    mock_body.__iter__ = MagicMock(
        return_value=iter([{"PayloadPart": {"Bytes": tgi_data.encode()}}])
    )
    mock_sagemaker.invoke_endpoint_with_response_stream.return_value = {
        "Body": mock_body
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("backend.inference.app.sagemaker_runtime", mock_sagemaker):
            response = await client.post(
                "/api/ask",
                json={"question": "test"},
            )

    assert response.status_code == 200
    body = response.text
    assert "ok" in body
    assert "[DONE]" in body
