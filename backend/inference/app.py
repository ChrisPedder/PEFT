"""
FastAPI Lambda proxy that forwards requests to a Bedrock imported model.

Runs inside Lambda via Lambda Web Adapter (LWA) for HTTP compatibility.
Supports SSE streaming via the Bedrock Converse API.
"""

import json
import logging
import os
import re
import time

import boto3
from botocore.config import Config
import requests as http_requests
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import jwt
from jwt.exceptions import PyJWTError
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

app = FastAPI(title="PEFT Obama Q&A API")

RATE_LIMIT = os.environ.get("RATE_LIMIT", "10/minute")


def _get_user_id(request: Request) -> str:
    """Extract user sub from JWT for per-user rate limiting, fall back to IP."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            claims = jwt.decode(auth[7:], options={"verify_signature": False})
            sub = claims.get("sub")
            if sub:
                return sub
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=_get_user_id)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    from fastapi.responses import JSONResponse

    retry_after = exc.detail if hasattr(exc, "detail") else "60"
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
        headers={"Retry-After": str(retry_after)},
    )


CORS_ALLOWED_ORIGIN = os.environ.get("CORS_ALLOWED_ORIGIN", "*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[CORS_ALLOWED_ORIGIN],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "")
COGNITO_REGION = os.environ.get("COGNITO_REGION", "eu-central-1")

bedrock_runtime = boto3.client(
    "bedrock-runtime",
    config=Config(retries={"total_max_attempts": 10, "mode": "standard"}),
)

# JWKS cache
_jwks_cache: dict | None = None
_jwks_cache_time: float = 0
_JWKS_CACHE_TTL = 3600  # 1 hour

# Mistral control tokens to strip from user input
_CONTROL_TOKENS = re.compile(r"\[/?INST\]|</?s>", re.IGNORECASE)


def _sanitise_prompt(text: str) -> str:
    """Strip Mistral control sequences from user input."""
    return _CONTROL_TOKENS.sub("", text).strip()


def _get_jwks() -> dict:
    """Fetch and cache the Cognito JWKS."""
    global _jwks_cache, _jwks_cache_time
    if _jwks_cache and (time.time() - _jwks_cache_time) < _JWKS_CACHE_TTL:
        return _jwks_cache
    jwks_url = (
        f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/"
        f"{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
    )
    resp = http_requests.get(jwks_url, timeout=5)
    resp.raise_for_status()
    _jwks_cache = resp.json()
    _jwks_cache_time = time.time()
    return _jwks_cache


def get_current_user(request: Request) -> dict:
    """Validate the JWT from the Authorization header and return user claims."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid authorization header"
        )

    token = auth_header[7:]
    try:
        # Decode header to find the key id
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="Invalid token header")

        jwks = _get_jwks()
        key_data = None
        for k in jwks.get("keys", []):
            if k["kid"] == kid:
                key_data = k
                break
        if not key_data:
            raise HTTPException(status_code=401, detail="Token signing key not found")

        # Convert JWK dict to an RSA public key object for PyJWT
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)

        issuer = (
            f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
        )
        decode_options: dict = {}
        decode_kwargs: dict = {
            "algorithms": ["RS256"],
            "issuer": issuer,
        }
        if COGNITO_CLIENT_ID:
            decode_kwargs["audience"] = COGNITO_CLIENT_ID
        else:
            decode_options["verify_aud"] = False

        claims = jwt.decode(
            token,
            public_key,
            options=decode_options,
            **decode_kwargs,
        )

        if claims.get("token_use") != "id":
            raise HTTPException(status_code=401, detail="Invalid token_use")

        return claims
    except PyJWTError as e:
        logger.warning("JWT validation failed: %s", e)
        raise HTTPException(status_code=401, detail="Invalid token")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    max_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/ask")
@limiter.limit(RATE_LIMIT)
async def ask(
    request: Request, req: AskRequest, _user: dict = Depends(get_current_user)
):
    """
    Forward a question to the Bedrock imported model and stream the response
    via the Converse API.
    """
    clean_question = _sanitise_prompt(req.question)
    if not clean_question:
        raise HTTPException(
            status_code=400, detail="Question is empty after sanitisation"
        )

    try:
        response = bedrock_runtime.converse_stream(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": clean_question}]}],
            inferenceConfig={
                "maxTokens": req.max_tokens,
                "temperature": req.temperature,
                "topP": 0.9,
            },
        )
    except bedrock_runtime.exceptions.ModelNotReadyException:
        raise HTTPException(
            status_code=503,
            detail="Model is warming up. Please try again in a minute.",
        )
    except bedrock_runtime.exceptions.ThrottlingException:
        raise HTTPException(
            status_code=429,
            detail="Request throttled. Please try again shortly.",
        )
    except Exception as e:
        logger.error("Bedrock invocation failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again later.",
        )

    def stream_response():
        """Yield SSE events from Bedrock Converse streaming response."""
        for event in response["stream"]:
            if "contentBlockDelta" in event:
                text = event["contentBlockDelta"]["delta"].get("text", "")
                if text:
                    yield f"data: {json.dumps({'token': text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
