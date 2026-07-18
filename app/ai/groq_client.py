"""
Shared async client for the Groq Chat Completions API.

All AI features should call call_granite() so the rest of the
application doesn't need to change.
"""
print("Loaded:", __file__)
import asyncio
import logging
import os

import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Configuration
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GENERATION_TIMEOUT = 10.0

API_URL = "https://api.groq.com/openai/v1/chat/completions"


async def call_granite(
    prompt: str,
    *,
    max_new_tokens: int = 300,
    temperature: float = 0.3,
    fallback_text: str = "AI analysis unavailable — check configuration.",
) -> str:
    """
    Send a prompt to Groq and return the generated text.

    Returns fallback_text on any error so callers never
    need to catch exceptions.
    """

    # Read API key every call so .env changes are picked up
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        logger.warning("GROQ_API_KEY is not configured.")
        return fallback_text

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": temperature,
        "max_tokens": max_new_tokens,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
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

        return data["choices"][0]["message"]["content"].strip()

    except asyncio.TimeoutError:
        logger.warning(
            "Groq API timed out after %.1f seconds.",
            GENERATION_TIMEOUT,
        )
        return fallback_text

    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Groq HTTP error %s: %s",
            exc.response.status_code,
            exc.response.text,
        )
        return fallback_text

    except (KeyError, IndexError, TypeError):
        logger.exception("Unexpected Groq response format.")
        return fallback_text

    except Exception as exc:
        logger.exception("Groq call failed: %s", exc)
        return fallback_text