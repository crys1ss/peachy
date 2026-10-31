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
from typing import Any, Generator, List, Optional

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

SYSTEM_INSTRUCTION_CHAT = (
    "You are Peachy, a direct, concise desktop AI assistant. Provide helpful, accurate responses "
    "using clean markdown formatting for code, lists, and tables. Avoid conversational filler, "
    "unnecessary preambles, and sycophantic pleasantries (never say 'Sure!', 'Certainly!', 'I would be happy to help'). "
    "Answer directly, accurately, and thoughtfully. Provide code in fenced code blocks with language identifiers. "
    "Be concise by default; provide depth and step-by-step detail when the user asks for detail."
)

MAX_IMAGE_LONG_SIDE = 2048
REQUEST_TIMEOUT_MS = 12000  # 12s per model attempt to allow fallbacks before 45s UI timeout


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
        self._last_usage_metadata: Optional[dict[str, int]] = None

    @property
    def last_usage_metadata(self) -> Optional[dict[str, int]]:
        """Return the usage metadata from the most recent streaming response."""
        return self._last_usage_metadata

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

            except Exception as err:
                if self._is_fallback_eligible(err) and idx < len(models_to_try) - 1:
                    logger.warning("Model %s failed (%s); trying fallback %s", current_model, err, models_to_try[idx + 1])
                    continue
                self._map_and_raise_error(err)

    def _is_fallback_eligible(self, err: Exception) -> bool:
        """Return True if the error is a temporary server overload or timeout eligible for fallback."""
        if isinstance(err, (BlockedError, EmptyResponseError, InvalidKeyError, RateLimitedError)):
            return False
        if isinstance(err, (httpx.TimeoutException, TimeoutError)):
            return True
        if isinstance(err, errors.APIError):
            code = getattr(err, "code", None)
            msg = str(getattr(err, "message", str(err))).lower()
            if code in (404, 500, 502, 503, 504) or any(k in msg for k in ["unavailable", "not found", "deadline", "overloaded"]):
                return True
        return False

    def _map_and_raise_error(self, err: Exception) -> None:
        """Map caught client or HTTP errors to typed ProviderError exceptions and raise."""
        if isinstance(err, ProviderError):
            raise err

        if isinstance(err, errors.APIError):
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
                if "demand" in msg or code == 503:
                    raise NetworkError(
                        "Gemini servers are currently experiencing high demand. Please try again in a moment.",
                        original_error=err,
                    ) from err
                raise NetworkError(
                    "Gemini service is temporarily unavailable. Please try again later.",
                    original_error=err,
                ) from err

            raise UnknownError(
                message=f"Gemini API error ({code}): {getattr(err, 'message', str(err))}",
                original_error=err,
            ) from err

        if isinstance(err, httpx.TimeoutException):
            raise TimeoutError(original_error=err) from err

        if isinstance(err, (httpx.NetworkError, ConnectionError, OSError)):
            raise NetworkError(original_error=err) from err

        raise UnknownError(message=f"Unexpected error: {str(err)}", original_error=err) from err

    def ask_stream(
        self,
        images: list[bytes] = (),
        question: str = "",
        history: Optional[List[Any]] = None,
        answer_length: str = "short",
        image_png: Optional[bytes] = None,
        system_instruction: Optional[str] = None,
    ) -> Generator[str, None, Optional[dict[str, int]]]:
        """Stream response chunks using client.models.generate_content_stream.

        Documentation reference:
            Official Google GenAI Python SDK:
            https://googleapis.github.io/python-genai/ (client.models.generate_content_stream)
            https://ai.google.dev/gemini-api/docs/text-generation#generate-a-text-stream

        Rules:
            - Explicitly disables AFC (Automatic Function Calling).
            - Fallback to next model occurs ONLY before the first chunk is yielded.
            - Once the first chunk is sent, errors end the stream immediately without fallback.
            - Usage metadata is captured from the final chunk and returned / recorded.
        """
        client = self._get_client()
        model_name = self.get_model_name()

        all_images = list(images)
        if not all_images and image_png is not None:
            all_images.append(image_png)

        user_parts: List[types.Part] = []
        for img_bytes in all_images:
            if img_bytes:
                prep_bytes = prepare_image(img_bytes)
                user_parts.append(types.Part.from_bytes(data=prep_bytes, mime_type="image/png"))

        q_text = question.strip() if question else ""
        if not q_text and not all_images:
            q_text = "Hello"
        elif not q_text and all_images:
            q_text = "Explain this image"
        user_parts.append(types.Part.from_text(text=q_text))

        contents: List[types.Content] = []
        if history:
            contents.extend(history)
        contents.append(types.Content(role="user", parts=user_parts))

        sys_inst = system_instruction or SYSTEM_INSTRUCTION_CHAT
        if answer_length == "detailed":
            sys_inst += " Provide a detailed, thorough explanation with in-depth context and clear steps."

        config = types.GenerateContentConfig(
            system_instruction=sys_inst,
            http_options=types.HttpOptions(timeout=20000),  # 20s read timeout per chunk
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True,
            ),
        )

        models_to_try = [model_name]
        settings = load_settings()
        if getattr(settings, "fallback_models_enabled", True):
            for fallback in FALLBACK_MODELS:
                if fallback not in models_to_try:
                    models_to_try.append(fallback)

        chunk_yielded = False
        last_chunk = None

        for idx, current_model in enumerate(models_to_try):
            try:
                response_stream = client.models.generate_content_stream(
                    model=current_model,
                    contents=contents,
                    config=config,
                )

                stream_iter = iter(response_stream)

                for chunk in stream_iter:
                    # Check safety filter blocks
                    if hasattr(chunk, "candidates") and chunk.candidates:
                        cand = chunk.candidates[0]
                        if hasattr(cand, "finish_reason") and cand.finish_reason:
                            reason = str(cand.finish_reason).upper()
                            if any(b in reason for b in ["SAFETY", "BLOCKLIST", "PROHIBITED"]):
                                raise BlockedError()

                    text = chunk.text
                    if text:
                        chunk_yielded = True
                        yield text
                    last_chunk = chunk

                if not chunk_yielded:
                    raise EmptyResponseError()

                if idx > 0:
                    logger.info("Primary model %s unavailable; responded using fallback model %s", model_name, current_model)

                break

            except Exception as err:
                # If a chunk has already been yielded to caller:
                # Fallback to another model is STRICTLY DISALLOWED!
                if chunk_yielded:
                    logger.error(
                        "Error occurred mid-stream on model %s after chunks were sent. Fallback disallowed: %s",
                        current_model,
                        err,
                    )
                    self._map_and_raise_error(err)

                # If error happened BEFORE first chunk:
                # Fallback to next model if eligible
                if self._is_fallback_eligible(err) and idx < len(models_to_try) - 1:
                    logger.warning(
                        "Model %s failed before first chunk (%s); falling back to %s",
                        current_model,
                        err,
                        models_to_try[idx + 1],
                    )
                    continue

                self._map_and_raise_error(err)

        usage_info = {
            "prompt_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        if last_chunk and hasattr(last_chunk, "usage_metadata") and last_chunk.usage_metadata:
            um = last_chunk.usage_metadata
            usage_info["prompt_tokens"] = getattr(um, "prompt_token_count", 0) or 0
            usage_info["output_tokens"] = getattr(um, "candidates_token_count", 0) or 0
            usage_info["total_tokens"] = getattr(um, "total_token_count", 0) or 0

        self._last_usage_metadata = usage_info
        return usage_info

    def list_models(self) -> List[str]:
        """Return available Gemini model IDs that support generateContent, with static fallback on error."""
        try:
            client = self._get_client()
            models = []
            for m in client.models.list():
                name = getattr(m, "name", "")
                if name.startswith("models/"):
                    name = name[len("models/"):]
                supported = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None)
                if supported is None or "generateContent" in supported:
                    if name and "gemini" in name.lower() and "embedding" not in name.lower():
                        models.append(name)
            if models:
                return sorted(list(set(models)))
        except Exception as exc:
            logger.warning("Failed to query models from Gemini API (%s). Using static fallback.", exc)

        return list(FALLBACK_MODELS)
