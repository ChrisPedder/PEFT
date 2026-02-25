"""
FastAPI Lambda proxy that forwards requests to the SageMaker streaming endpoint.

Runs inside Lambda via Lambda Web Adapter (LWA) for HTTP compatibility.
Supports SSE streaming from SageMaker invoke_endpoint_with_response_stream.
"""

import json
import os

import boto3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="PEFT Obama Q&A API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ENDPOINT_NAME = os.environ.get("SAGEMAKER_ENDPOINT_NAME", "peft-obama-endpoint")
sagemaker_runtime = boto3.client("sagemaker-runtime")


class AskRequest(BaseModel):
    question: str
    max_tokens: int = 512
    temperature: float = 0.7


@app.get("/api/health")
def health():
    return {"status": "ok", "endpoint": ENDPOINT_NAME}


@app.post("/api/ask")
async def ask(req: AskRequest):
    """
    Forward a question to the SageMaker endpoint and stream the response.
    Uses invoke_endpoint_with_response_stream for token-by-token SSE.
    """
    # Format prompt in Mistral chat template
    prompt = f"<s>[INST] {req.question} [/INST]"

    payload = json.dumps(
        {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": req.max_tokens,
                "temperature": req.temperature,
                "do_sample": True,
                "top_p": 0.9,
                "repetition_penalty": 1.1,
            },
            "stream": True,
        }
    )

    try:
        response = sagemaker_runtime.invoke_endpoint_with_response_stream(
            EndpointName=ENDPOINT_NAME,
            ContentType="application/json",
            Body=payload,
        )
    except sagemaker_runtime.exceptions.ModelNotReadyException:
        raise HTTPException(
            status_code=503,
            detail="Model is warming up (scale-from-zero). Please try again in 3-5 minutes.",
        )
    except Exception as e:
        error_msg = str(e)
        if "ValidationError" in error_msg or "Could not find" in error_msg:
            raise HTTPException(
                status_code=503,
                detail="Model endpoint is not available. It may be scaling up.",
            )
        raise HTTPException(status_code=500, detail=f"SageMaker error: {error_msg}")

    def stream_response():
        """Yield SSE events from SageMaker response stream."""
        event_stream = response["Body"]
        for event in event_stream:
            chunk = event.get("PayloadPart", {}).get("Bytes", b"")
            if chunk:
                text = chunk.decode("utf-8", errors="replace")
                # Parse TGI streaming format
                for line in text.split("\n"):
                    line = line.strip()
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data == "[DONE]":
                            yield "data: [DONE]\n\n"
                            return
                        try:
                            token_data = json.loads(data)
                            token_text = token_data.get("token", {}).get("text", "")
                            if token_text:
                                yield f"data: {json.dumps({'token': token_text})}\n\n"
                        except json.JSONDecodeError:
                            continue
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
