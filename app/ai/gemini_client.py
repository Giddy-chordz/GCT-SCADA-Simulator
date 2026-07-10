"""
Shared async client for Google Gemini REST API.

All AI features should call call_granite() so the rest of the
application doesn't need to change.

"""

import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)


# Configuration


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

GENERATION_TIMEOUT = 10.0

API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


async def call_granite(
    prompt: str,
    *,
    max_new_tokens: int = 300,
    temperature: float = 0.3,
    fallback_text: str = "AI analysis unavailable — check configuration.",
) -> str:
    """
    Send a prompt to Gemini and return the generated text.

    Returns fallback_text on any error so callers never
    need to catch exceptions.
    """

    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is not configured.")
        return fallback_text

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_new_tokens,
        },
    }

    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT) as client:
            response = await client.post(
                API_URL,
                json=payload,
                headers=headers,
            )

            response.raise_for_status()
            data = response.json()

        return (
            data["candidates"][0]
            ["content"]["parts"][0]
            ["text"]
            .strip()
        )

    except asyncio.TimeoutError:
        logger.warning(
            "Gemini API timed out after %.1f seconds.",
            GENERATION_TIMEOUT,
        )
        return fallback_text

    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Gemini HTTP error %s: %s",
            exc.response.status_code,
            exc.response.text[:500],
        )
        return fallback_text

    except (KeyError, IndexError, TypeError):
        logger.warning("Unexpected Gemini response format.")
        return fallback_text

    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini call failed: %s", exc)
        return fallback_text