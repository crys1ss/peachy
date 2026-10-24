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
from config.key_storage import get_api_key
from config.settings import load_settings

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = (
    "You are Peachy, an ultra-direct, concise screen utility. Answer the user's question about the image with zero conversational filler, preamble, pleasantries, or sycophancy (never say 'Sure!', 'Here is...', 'Hope this helps', or 'Certainly'). Give the direct answer immediately: "
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
    """Retrieve the Gemini API key following lookup order: keyring, then environment."""
    return get_api_key()


def test_connection(api_key: Optional[str] = None, model: Optional[str] = None) -> tuple[bool, str]:
    """Test API connection with a small call, returning (success, message)."""
    key = api_key or get_api_key()
    if not key:
        return False, MissingKeyError.DEFAULT_MESSAGE

    try:
        client = genai.Client(api_key=key)
        test_model = model or load_settings().model
        client.models.generate_content(
            model=test_model,
            contents="Say hi in 1 word",
            config=types.GenerateContentConfig(
                http_options=types.HttpOptions(timeout=10000),
            ),
        )
        return True, "API Key is valid!"
    except errors.APIError as exc:
        code = getattr(exc, "code", None)
        if code in (400, 401, 403) or "API_KEY_INVALID" in str(exc) or "PERMISSION_DENIED" in str(exc):
            return False, InvalidKeyError.DEFAULT_MESSAGE
        if code == 429 or "RESOURCE_EXHAUSTED" in str(exc):
            return False, RateLimitedError.DEFAULT_MESSAGE
        return False, f"API error: {exc.message if hasattr(exc, 'message') else str(exc)}"
    except (httpx.TimeoutException, errors.ClientError):
        return False, "Connection timed out. Please check your network."
    except httpx.NetworkError:
        return False, NetworkError.DEFAULT_MESSAGE
    except Exception as exc:
        return False, f"Error: {exc}"


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


FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-lite-latest"]


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
        answer_length: str = "short",
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

        system_instruction = SYSTEM_INSTRUCTION
        if answer_length == "detailed":
            system_instruction += " Provide a detailed, thorough explanation with in-depth context and clear steps."

        # Config: system instruction, timeout, AFC explicitly disabled
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True,
            ),
        )

        models_to_try = [model_name]
        for fallback in FALLBACK_MODELS:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        for idx, current_model in enumerate(models_to_try):
            try:
                response = client.models.generate_content(
                    model=current_model,
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

                if idx > 0:
                    logger.info("Primary model %s unavailable; successfully responded using fallback model %s", model_name, current_model)

                # Build updated history: previous history + user turn + model turn
                new_history = list(contents)
                new_history.append(types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=text.strip())],
                ))

                return AnswerResult(text=text.strip(), history=new_history)

            except (BlockedError, EmptyResponseError, InvalidKeyError, RateLimitedError):
                raise

            except errors.APIError as err:
                code = getattr(err, "code", None)
                msg = str(getattr(err, "message", str(err))).lower()

                if code in (401, 403) or (
                    code == 400 and any(k in msg for k in ["api_key", "invalid", "key not valid", "api key"])
                ):
                    raise InvalidKeyError(original_error=err) from err
                if code == 429 or "resource_exhausted" in msg or "quota" in msg:
                    raise RateLimitedError(original_error=err) from err

                # If server overload (404 model not found, 500, 502, 503, 504) and fallbacks remain, try next model
                if (code in (404, 500, 502, 503, 504) or "unavailable" in msg or "not found" in msg or "deadline" in msg) and idx < len(models_to_try) - 1:
                    logger.warning("Model %s returned code %s (%s); trying fallback %s", current_model, code, msg, models_to_try[idx + 1])
                    continue

                if code in (408, 504) or "deadline" in msg or "timed out" in msg:
                    raise TimeoutError(original_error=err) from err
                if code in (500, 502, 503) or "unavailable" in msg:
                    if "demand" in msg or code == 503:
                        raise NetworkError("Gemini servers are currently experiencing high demand. Please try again in a moment.", original_error=err) from err
                    raise NetworkError("Gemini service is temporarily unavailable. Please try again later.", original_error=err) from err

                raise UnknownError(message=f"Gemini API error ({code}): {err.message}", original_error=err) from err

            except httpx.TimeoutException as err:
                if idx < len(models_to_try) - 1:
                    logger.warning("Model %s timed out; trying fallback %s", current_model, models_to_try[idx + 1])
                    continue
                raise TimeoutError(original_error=err) from err

            except (httpx.NetworkError, ConnectionError, OSError) as err:
                raise NetworkError(original_error=err) from err

            except ProviderError:
                raise

            except Exception as err:
                raise UnknownError(message=f"Unexpected error: {str(err)}", original_error=err) from err
