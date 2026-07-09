"""
Shared async client for IBM Granite via watsonx.ai — all AI features call
call_granite() so API key setup and timeout/fallback live in one place.

watsonx.ai REST flow
─────────────────────────────────────────────────────────────────────────────
1.  Obtain an IAM bearer token by POST-ing your API key to the IAM token URL.
    The token is cached in module-level state and reused until it expires.
2.  POST to the watsonx.ai text generation endpoint with the bearer token,
    project_id, model_id, and a well-formed prompt.
3.  Parse the first generated text from the response.

Required environment variables (add to your .env file):
    WATSONX_API_KEY     – IBM Cloud API key (from cloud.ibm.com → Manage → Access)
    WATSONX_PROJECT_ID  – watsonx.ai project ID (from watsonx.ai → Manage project)
    WATSONX_URL         – base URL for the watsonx.ai instance, e.g.
                          https://us-south.ml.cloud.ibm.com
    GRANITE_MODEL_ID    – model to use, e.g. ibm/granite-3-3-8b-instruct
                          (defaults to ibm/granite-3-3-8b-instruct if not set)

SDK alternative:  If you install ibm-watsonx-ai (pip install ibm-watsonx-ai)
you can replace the raw HTTP calls below with the ModelInference SDK class.
The REST approach used here has no extra dependencies beyond httpx.
"""

import asyncio
import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

WATSONX_API_KEY    = os.getenv("WATSONX_API_KEY", "")
WATSONX_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID", "")
WATSONX_URL        = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
GRANITE_MODEL_ID   = os.getenv("GRANITE_MODEL_ID", "ibm/granite-3-3-8b-instruct")

IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"
GENERATION_TIMEOUT = 10.0   # seconds — hard cap on every Granite call
CACHE_SLACK_SECONDS = 120   # refresh IAM token this many seconds before expiry

# ── Module-level IAM token cache ─────────────────────────────────────────────

_iam_token: Optional[str] = None
_iam_token_expiry: float = 0.0          # unix timestamp


async def _get_iam_token() -> str:
    """Fetch (or return the cached) IBM IAM bearer token for watsonx.ai auth."""
    global _iam_token, _iam_token_expiry

    if _iam_token and time.time() < (_iam_token_expiry - CACHE_SLACK_SECONDS):
        return _iam_token

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            IAM_TOKEN_URL,
            data={
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey": WATSONX_API_KEY,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        payload = resp.json()

    _iam_token = payload["access_token"]
    _iam_token_expiry = time.time() + payload.get("expires_in", 3600)
    return _iam_token


async def call_granite(
    prompt: str,
    *,
    max_new_tokens: int = 300,
    temperature: float = 0.3,
    fallback_text: str = "AI analysis unavailable — check configuration.",
) -> str:
    """Send prompt to IBM Granite and return the generated text string.

    Returns fallback_text on any error (network, auth, timeout, bad config)
    so callers never need to guard against exceptions from this function.
    """
    if not WATSONX_API_KEY or not WATSONX_PROJECT_ID:
        logger.warning(
            "WATSONX_API_KEY or WATSONX_PROJECT_ID not set — "
            "returning fallback text without calling Granite"
        )
        return fallback_text

    url = f"{WATSONX_URL}/ml/v1/text/generation?version=2023-05-29"

    try:
        token = await asyncio.wait_for(_get_iam_token(), timeout=GENERATION_TIMEOUT)

        payload = {
            "model_id": GRANITE_MODEL_ID,
            "project_id": WATSONX_PROJECT_ID,
            "input": prompt,
            "parameters": {
                "decoding_method": "greedy",
                "max_new_tokens": max_new_tokens,
                "temperature": temperature,
                "stop_sequences": [],
            },
        }

        async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        if results:
            return results[0].get("generated_text", fallback_text).strip()
        return fallback_text

    except asyncio.TimeoutError:
        logger.warning("Granite API call timed out after %.1fs", GENERATION_TIMEOUT)
        return fallback_text
    except httpx.HTTPStatusError as exc:
        logger.warning("Granite HTTP error %s: %s", exc.response.status_code, exc.response.text[:200])
        return fallback_text
    except Exception as exc:  # noqa: BLE001
        logger.warning("Granite call failed: %s", exc)
        return fallback_text
