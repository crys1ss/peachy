"""Unit tests for ai/gemini_provider.py using mocked client and fake keys."""

import io
from unittest.mock import MagicMock, patch

from PIL import Image
import pytest

from google.genai import errors, types

from ai.gemini_provider import (
    SYSTEM_INSTRUCTION,
    GeminiProvider,
    get_gemini_api_key,
    prepare_image,
)
from ai.provider import (
    AnswerResult,
    BlockedError,
    EmptyResponseError,
    InvalidKeyError,
    MissingKeyError,
    NetworkError,
    RateLimitedError,
    TimeoutError,
)


def create_dummy_png(width: int = 100, height: int = 100) -> bytes:
    """Helper to create dummy PNG bytes."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def test_missing_key_raises_missing_key_error():
    """Verify missing API key raises MissingKeyError without network call."""
    with patch("ai.gemini_provider.get_gemini_api_key", return_value=None):
        provider = GeminiProvider(api_key=None)
        with pytest.raises(MissingKeyError) as exc_info:
            provider.ask(image_png=None, question="test")
        assert "Gemini API key is missing" in exc_info.value.message


def test_request_contains_image_part_text_and_model_from_settings():
    """Verify request packages image part, text part, system instruction, and model."""
    mock_client = MagicMock()
    mock_chat = MagicMock()
    mock_client.chats.create.return_value = mock_chat

    mock_response = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.finish_reason = None
    mock_response.candidates = [mock_candidate]
    mock_response.text = "Answer from mock model"
    mock_chat.send_message.return_value = mock_response
    mock_chat.get_history.return_value = [{"role": "user"}, {"role": "model"}]

    provider = GeminiProvider(model="gemini-3.8-flash", api_key="fake-key-for-test", client=mock_client)
    img_bytes = create_dummy_png(120, 80)

    result = provider.ask(image_png=img_bytes, question="Explain this diagram")

    # Verify model and system instruction passed to client.chats.create
    mock_client.chats.create.assert_called_once()
    create_kwargs = mock_client.chats.create.call_args.kwargs
    assert create_kwargs["model"] == "gemini-3.8-flash"
    assert create_kwargs["config"].system_instruction == SYSTEM_INSTRUCTION

    # Verify send_message received both image part and text part
    mock_chat.send_message.assert_called_once()
    sent_parts = mock_chat.send_message.call_args.kwargs["message"]
    assert len(sent_parts) == 2
    assert isinstance(sent_parts[0], types.Part)
    assert sent_parts[1] == "Explain this diagram"

    assert result.text == "Answer from mock model"
    assert len(result.history) == 2


def test_model_name_env_override(monkeypatch):
    """Verify PEACHY_MODEL env var overrides settings."""
    monkeypatch.setenv("PEACHY_MODEL", "gemini-override-custom")
    provider = GeminiProvider(model="gemini-3.8-flash")
    assert provider.get_model_name() == "gemini-override-custom"


def test_prepare_image_downscale_only():
    """Verify long side over 2048 is downscaled and small images are never upscaled."""
    # 1. Image under 2048 is NOT resized
    small_bytes = create_dummy_png(800, 600)
    prep_small = prepare_image(small_bytes)
    assert Image.open(io.BytesIO(prep_small)).size == (800, 600)

    # 2. Image over 2048 is downscaled so long side is 2048
    large_bytes = create_dummy_png(4096, 2048)
    prep_large = prepare_image(large_bytes)
    assert Image.open(io.BytesIO(prep_large)).size == (2048, 1024)


def test_sdk_exception_mapping_invalid_key():
    """Verify 400 with invalid key or 401/403 maps to InvalidKeyError."""
    mock_client = MagicMock()
    mock_client.chats.create.side_effect = errors.APIError(
        code=400, response_json={"error": {"message": "API key not valid"}}
    )
    provider = GeminiProvider(api_key="fake-key", client=mock_client)

    with pytest.raises(InvalidKeyError):
        provider.ask(image_png=None, question="test")


def test_sdk_exception_mapping_rate_limited():
    """Verify 429 maps to RateLimitedError."""
    mock_client = MagicMock()
    mock_client.chats.create.side_effect = errors.APIError(
        code=429, response_json={"error": {"message": "Resource exhausted"}}
    )
    provider = GeminiProvider(api_key="fake-key", client=mock_client)

    with pytest.raises(RateLimitedError):
        provider.ask(image_png=None, question="test")


def test_sdk_exception_mapping_timeout():
    """Verify 504 / timeout maps to TimeoutError."""
    mock_client = MagicMock()
    mock_client.chats.create.side_effect = errors.APIError(
        code=504, response_json={"error": {"message": "Deadline exceeded"}}
    )
    provider = GeminiProvider(api_key="fake-key", client=mock_client)

    with pytest.raises(TimeoutError):
        provider.ask(image_png=None, question="test")


def test_sdk_exception_mapping_network_error():
    """Verify 503 / network errors map to NetworkError."""
    mock_client = MagicMock()
    mock_client.chats.create.side_effect = errors.APIError(
        code=503, response_json={"error": {"message": "Service unavailable"}}
    )
    provider = GeminiProvider(api_key="fake-key", client=mock_client)

    with pytest.raises(NetworkError):
        provider.ask(image_png=None, question="test")


def test_sdk_blocked_safety_error():
    """Verify finish_reason = SAFETY maps to BlockedError."""
    mock_client = MagicMock()
    mock_chat = MagicMock()
    mock_client.chats.create.return_value = mock_chat

    mock_response = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.finish_reason = types.FinishReason.SAFETY
    mock_response.candidates = [mock_candidate]
    mock_chat.send_message.return_value = mock_response

    provider = GeminiProvider(api_key="fake-key", client=mock_client)
    with pytest.raises(BlockedError):
        provider.ask(image_png=None, question="test")


def test_empty_response_error():
    """Verify empty text response maps to EmptyResponseError."""
    mock_client = MagicMock()
    mock_chat = MagicMock()
    mock_client.chats.create.return_value = mock_chat

    mock_response = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.finish_reason = None
    mock_response.candidates = [mock_candidate]
    mock_response.text = "   "
    mock_chat.send_message.return_value = mock_response

    provider = GeminiProvider(api_key="fake-key", client=mock_client)
    with pytest.raises(EmptyResponseError):
        provider.ask(image_png=None, question="test")
