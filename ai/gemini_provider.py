"""Official Google GenAI SDK provider for Peachy.

Implements Gemini Flash multimodal queries with:
- Direct client.models.generate_content() calls (no chat wrapper overhead)
- AFC (Automatic Function Calling) explicitly disabled
- Image optimization via Pillow (downscale long side > 2048 px, never upscale)
- Secure runtime API key reading through get_gemini_api_key()
- Strict error mapping to typed ProviderError exceptions
- Manual multi-turn conversation history management
"""

from __future__ import annotations

import io
import logging
import os
from typing import Any, List, Optional

import httpx
from PIL import Image

from google import genai
from google.genai import errors, types

from ai.provider import (
    AnswerResult,
    BaseAIProvider,
    BlockedError,
    EmptyResponseError,
    InvalidKeyError,
    MissingKeyError,
    NetworkError,
    ProviderError,
    RateLimitedError,
    TimeoutError,
    UnknownError,
)
from config.settings import load_settings

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = (
    "You are Peachy, a concise screen assistant. Answer the user's question about the image. "
    "If there is no question, work out what the content is and give the most useful short response: "
    "multiple choice -> the correct option first, then one or two lines why; "
    "code or error -> cause and fix; "
    "chart or table -> the key takeaway; "
    "foreign language -> translation. "
    "Be short by default and detailed only when asked. "
    "If text is blurry or cut off, say exactly what you cannot read. "
    "Never invent text that is not visible. Use simple markdown."
)

MAX_IMAGE_LONG_SIDE = 2048
REQUEST_TIMEOUT_MS = 45000  # google-genai HttpOptions timeout is in milliseconds


def get_gemini_api_key() -> Optional[str]:
    """Retrieve the Gemini API key strictly from the environment variable.

    Security Rule: The value returned by this function MUST NEVER be printed,
    logged, echoed, or persisted to files or tests.
    """
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        key = key.strip()
    return key if key else None


def prepare_image(image_bytes: bytes, max_long_side: int = MAX_IMAGE_LONG_SIDE) -> bytes:
    """Prepare image for Gemini API.

    Downscales only if the long side is over 2048 px. Never upscales.
    Returns standard PNG bytes.
    """
    with Image.open(io.BytesIO(image_bytes)) as img:
        # Convert RGBA / palette images to RGB if needed, or preserve RGBA for PNG
        w, h = img.size
        long_side = max(w, h)
        if long_side > max_long_side:
            scale = max_long_side / float(long_side)
            new_w = max(1, round(w * scale))
            new_h = max(1, round(h * scale))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        out_buf = io.BytesIO()
        img.save(out_buf, format="PNG")
        return out_buf.getvalue()


class GeminiProvider(BaseAIProvider):
    """Gemini multimodal provider utilizing the official google-genai SDK.

    Uses client.models.generate_content() directly with explicit AFC disabled,
    rather than the chats wrapper, for lower latency and predictable behaviour.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        client: Optional[genai.Client] = None,
    ):
        self._model = model
        self._api_key = api_key
        self._client = client

    def get_model_name(self) -> str:
        """Resolve model name prioritizing env var PEACHY_MODEL over settings."""
        env_model = os.environ.get("PEACHY_MODEL")
        if env_model:
            return env_model.strip()
        if self._model:
            return self._model
        return load_settings().model

    def _get_client(self) -> genai.Client:
        """Get or initialize the Google GenAI SDK client."""
        if self._client is not None:
            return self._client

        api_key = self._api_key or get_gemini_api_key()
        if not api_key:
            raise MissingKeyError()

        return genai.Client(api_key=api_key)

    def ask(
        self,
        image_png: Optional[bytes],
        question: str,
        history: Optional[List[Any]] = None,
    ) -> AnswerResult:
        """Submit a question and optional image to Gemini.

        Uses client.models.generate_content() directly with the full contents
        list (history + current turn) for lower latency. AFC is disabled.
        """
        client = self._get_client()
        model_name = self.get_model_name()

        # Build the current user turn's parts
        user_parts: List[types.Part] = []
        if image_png:
            prep_bytes = prepare_image(image_png)
            user_parts.append(types.Part.from_bytes(data=prep_bytes, mime_type="image/png"))

        q_text = question.strip() if question else ""
        if not q_text:
            q_text = "Explain this screen"
        user_parts.append(types.Part.from_text(text=q_text))

        # Build the full contents list: history + current user turn
        contents: List[types.Content] = []
        if history:
            contents.extend(history)
        contents.append(types.Content(role="user", parts=user_parts))

        # Config: system instruction, timeout, AFC explicitly disabled
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True,
            ),
        )

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )

            # Check for safety blocks
            if not response.candidates:
                raise EmptyResponseError()

            candidate = response.candidates[0]
            if candidate.finish_reason:
                reason = str(candidate.finish_reason).upper()
                if any(b in reason for b in ["SAFETY", "BLOCKLIST", "PROHIBITED"]):
                    raise BlockedError()

            text = response.text
            if not text or not text.strip():
                raise EmptyResponseError()

            # Build updated history: previous history + user turn + model turn
            new_history = list(contents)
            new_history.append(types.Content(
                role="model",
                parts=[types.Part.from_text(text=text.strip())],
            ))

            return AnswerResult(text=text.strip(), history=new_history)

        except errors.APIError as err:
            code = getattr(err, "code", None)
            msg = str(getattr(err, "message", str(err))).lower()

            if code in (401, 403) or (
                code == 400 and any(k in msg for k in ["api_key", "invalid", "key not valid", "api key"])
            ):
                raise InvalidKeyError(original_error=err) from err
            if code == 429 or "resource_exhausted" in msg or "quota" in msg:
                raise RateLimitedError(original_error=err) from err
            if code in (408, 504) or "deadline" in msg or "timed out" in msg:
                raise TimeoutError(original_error=err) from err
            if code in (500, 502, 503) or "unavailable" in msg:
                raise NetworkError(original_error=err) from err

            raise UnknownError(message=f"Gemini API error ({code}): {err.message}", original_error=err) from err

        except httpx.TimeoutException as err:
            raise TimeoutError(original_error=err) from err

        except (httpx.NetworkError, ConnectionError, OSError) as err:
            raise NetworkError(original_error=err) from err

        except ProviderError:
            raise

        except Exception as err:
            raise UnknownError(message=f"Unexpected error: {str(err)}", original_error=err) from err
