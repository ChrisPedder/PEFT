"""Tests for backend/inference/app.py — FastAPI endpoints with Bedrock."""

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
_mock_bedrock_runtime = MagicMock()

with patch("boto3.client", return_value=_mock_bedrock_runtime):
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
def mock_bedrock():
    """Reset and yield the mock bedrock runtime client."""
    _mock_bedrock_runtime.reset_mock(side_effect=True, return_value=True)
    # Provide a mock exceptions attribute
    _mock_bedrock_runtime.exceptions = MagicMock()
    _mock_bedrock_runtime.exceptions.ThrottlingException = type(
        "ThrottlingException", (Exception,), {}
    )
    with patch.object(app, "state", create=True):
        yield _mock_bedrock_runtime


@pytest.mark.asyncio
async def test_health_endpoint():
    """GET /api/health returns 200 with status=ok (no auth required)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "model_id" in data


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
async def test_ask_success(mock_bedrock):
    """POST /api/ask streams SSE tokens from Bedrock converse_stream."""
    # Build a mock Bedrock converse_stream response
    mock_events = [
        {"contentBlockDelta": {"delta": {"text": "Hello"}}},
        {"contentBlockDelta": {"delta": {"text": " world"}}},
        {"contentBlockStop": {"contentBlockIndex": 0}},
        {"messageStop": {"stopReason": "end_turn"}},
    ]

    mock_bedrock.converse_stream.return_value = {
        "stream": iter(mock_events),
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("backend.inference.app.bedrock_runtime", mock_bedrock):
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
async def test_ask_converse_stream_params(mock_bedrock):
    """POST /api/ask calls converse_stream with correct model ID and message format."""
    mock_bedrock.converse_stream.return_value = {
        "stream": iter([{"messageStop": {"stopReason": "end_turn"}}]),
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("backend.inference.app.bedrock_runtime", mock_bedrock):
            with patch("backend.inference.app.MODEL_ID", "arn:aws:bedrock:eu-central-1:123:imported-model/peft-obama"):
                response = await client.post(
                    "/api/ask",
                    json={"question": "Tell me about healthcare", "max_tokens": 256, "temperature": 0.5},
                )

    assert response.status_code == 200
    call_kwargs = mock_bedrock.converse_stream.call_args[1]
    assert call_kwargs["modelId"] == "arn:aws:bedrock:eu-central-1:123:imported-model/peft-obama"
    assert call_kwargs["messages"] == [
        {"role": "user", "content": [{"text": "Tell me about healthcare"}]}
    ]
    assert call_kwargs["inferenceConfig"]["maxTokens"] == 256
    assert call_kwargs["inferenceConfig"]["temperature"] == 0.5
    assert call_kwargs["inferenceConfig"]["topP"] == 0.9


@pytest.mark.asyncio
async def test_ask_throttling_error(mock_bedrock):
    """POST /api/ask returns 429 when Bedrock throttles the request."""
    ThrottlingException = mock_bedrock.exceptions.ThrottlingException
    mock_bedrock.converse_stream.side_effect = ThrottlingException("Rate exceeded")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("backend.inference.app.bedrock_runtime", mock_bedrock):
            response = await client.post(
                "/api/ask",
                json={"question": "test question"},
            )

    assert response.status_code == 429
    assert "throttled" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_ask_generic_error(mock_bedrock):
    """POST /api/ask returns 500 on an unexpected exception."""
    mock_bedrock.converse_stream.side_effect = Exception(
        "Something totally unexpected"
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("backend.inference.app.bedrock_runtime", mock_bedrock):
            response = await client.post(
                "/api/ask",
                json={"question": "test question"},
            )

    assert response.status_code == 500
    assert "Bedrock error" in response.json()["detail"]


@pytest.mark.asyncio
async def test_ask_stream_skips_non_delta_events(mock_bedrock):
    """Non-contentBlockDelta events are silently skipped in the SSE stream."""
    mock_events = [
        {"contentBlockStart": {"contentBlockIndex": 0}},
        {"contentBlockDelta": {"delta": {"text": "ok"}}},
        {"contentBlockStop": {"contentBlockIndex": 0}},
        {"messageStop": {"stopReason": "end_turn"}},
    ]

    mock_bedrock.converse_stream.return_value = {
        "stream": iter(mock_events),
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("backend.inference.app.bedrock_runtime", mock_bedrock):
            response = await client.post(
                "/api/ask",
                json={"question": "test"},
            )

    assert response.status_code == 200
    body = response.text
    assert "ok" in body
    assert "[DONE]" in body


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
async def test_auth_valid_token_succeeds(mock_bedrock):
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

    mock_bedrock.converse_stream.return_value = {
        "stream": iter([{"messageStop": {"stopReason": "end_turn"}}]),
    }

    with (
        patch("backend.inference.app._get_jwks", return_value=mock_jwks),
        patch("backend.inference.app.jwt.decode", return_value=valid_claims),
        patch("backend.inference.app.bedrock_runtime", mock_bedrock),
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
