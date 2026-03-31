"""
bedrock_client.py — Reusable AWS Bedrock client wrapper.
Provides lazy-initialized clients for both LLM and embedding calls.
"""

# This __future__ import allows us to use type hints for classes defined later in the same file.
from __future__ import annotations

import os
import json
import logging
from collections.abc import Generator

# lru_cache is used for memoization to cache the results of function calls.
# This is useful for functions that are called multiple times with the same arguments.
from functools import lru_cache

import boto3


logger = logging.getLogger(__name__)

AWS_REGION = os.getenv("AWS_REGION", "eu-west-3")
LLM_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0")


@lru_cache(maxsize=1)
def get_bedrock_client():
    """Return a Bedrock client."""
    return boto3.client("bedrock-runtime", region_name=AWS_REGION)

def invoke_llm(
    user_prompt: str,
    system_prompt: str,
    max_tokens: int = 1024,
    temperature: float = 0.1,
    
) -> Generator[str, None, str]:
    """Invoke the LLM with the given prompt."""
    client = get_bedrock_client()
    
    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
    }
    if system_prompt:
        request_body["system"] = system_prompt
    
    response = client.invoke_model_with_response_stream(
        modelId=LLM_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(request_body),
    )

    full_text = []

    for event in response["body"]:
        raw = event.get("chunk", {}).get("bytes")
        if not raw:
            continue

        chunk = json.loads(raw)
        event_type = chunk.get("type")

        if event_type == "content_block_delta":
            # This is the actual text token arriving
            delta = chunk.get("delta", {})
            if delta.get("type") == "text_delta":
                text = delta.get("text", "")
                full_text.append(text)
                yield text

        elif event_type == "message_stop":
            # Stream is done — log stop reason if useful
            stop_reason = chunk.get("amazon-bedrock-invocationMetrics", {})
            logger.debug(f"Stream complete. Metrics: {stop_reason}")

    return "".join(full_text)