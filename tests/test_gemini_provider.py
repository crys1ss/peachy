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

    mock_response = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.finish_reason = None
    mock_response.candidates = [mock_candidate]
    mock_response.text = "Answer from mock model"
    mock_client.models.generate_content.return_value = mock_response

    provider = GeminiProvider(model="gemini-3.8-flash", api_key="fake-key-for-test", client=mock_client)
    img_bytes = create_dummy_png(120, 80)

    result = provider.ask(image_png=img_bytes, question="Explain this diagram")

    # Verify generate_content was called with model, contents, config
    mock_client.models.generate_content.assert_called_once()
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-3.8-flash"
    assert call_kwargs["config"].system_instruction == SYSTEM_INSTRUCTION
    # AFC must be disabled
    assert call_kwargs["config"].automatic_function_calling.disable is True

    # Verify contents list: single user turn with image + text
    contents = call_kwargs["contents"]
    assert len(contents) == 1
    user_turn = contents[0]
    assert user_turn.role == "user"
    assert len(user_turn.parts) == 2
    assert user_turn.parts[1].text == "Explain this diagram"

    assert result.text == "Answer from mock model"
    # History should contain user turn + model turn = 2
    assert len(result.history) == 2


def test_empty_question_defaults_to_explain_screen():
    """Verify empty or whitespace question defaults to 'Explain this screen'."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.finish_reason = None
    mock_response.candidates = [mock_candidate]
    mock_response.text = "Screen explanation"
    mock_client.models.generate_content.return_value = mock_response

    provider = GeminiProvider(api_key="fake-key", client=mock_client)
    provider.ask(image_png=create_dummy_png(50, 50), question="   ")

    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    contents = call_kwargs["contents"]
    assert contents[0].parts[1].text == "Explain this screen"


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
    mock_client.models.generate_content.side_effect = errors.APIError(
        code=400, response_json={"error": {"message": "API key not valid"}}
    )
    provider = GeminiProvider(api_key="fake-key", client=mock_client)

    with pytest.raises(InvalidKeyError):
        provider.ask(image_png=None, question="test")


def test_sdk_exception_mapping_rate_limited():
    """Verify 429 maps to RateLimitedError."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = errors.APIError(
        code=429, response_json={"error": {"message": "Resource exhausted"}}
    )
    provider = GeminiProvider(api_key="fake-key", client=mock_client)

    with pytest.raises(RateLimitedError):
        provider.ask(image_png=None, question="test")


def test_sdk_exception_mapping_timeout():
    """Verify 504 / timeout maps to TimeoutError."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = errors.APIError(
        code=504, response_json={"error": {"message": "Deadline exceeded"}}
    )
    provider = GeminiProvider(api_key="fake-key", client=mock_client)

    with pytest.raises(TimeoutError):
        provider.ask(image_png=None, question="test")


def test_sdk_exception_mapping_network_error():
    """Verify 503 / network errors map to NetworkError."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = errors.APIError(
        code=503, response_json={"error": {"message": "Service unavailable"}}
    )
    provider = GeminiProvider(api_key="fake-key", client=mock_client)

    with pytest.raises(NetworkError):
        provider.ask(image_png=None, question="test")


def test_sdk_blocked_safety_error():
    """Verify finish_reason = SAFETY maps to BlockedError."""
    mock_client = MagicMock()

    mock_response = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.finish_reason = types.FinishReason.SAFETY
    mock_response.candidates = [mock_candidate]
    mock_client.models.generate_content.return_value = mock_response

    provider = GeminiProvider(api_key="fake-key", client=mock_client)
    with pytest.raises(BlockedError):
        provider.ask(image_png=None, question="test")


def test_empty_response_error():
    """Verify empty text response maps to EmptyResponseError."""
    mock_client = MagicMock()

    mock_response = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.finish_reason = None
    mock_response.candidates = [mock_candidate]
    mock_response.text = "   "
    mock_client.models.generate_content.return_value = mock_response

    provider = GeminiProvider(api_key="fake-key", client=mock_client)
    with pytest.raises(EmptyResponseError):
        provider.ask(image_png=None, question="test")


def test_detailed_length_instruction():
    """Verify answer_length='detailed' adds in-depth instruction to system instruction."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.finish_reason = None
    mock_response.candidates = [mock_candidate]
    mock_response.text = "Detailed answer"
    mock_client.models.generate_content.return_value = mock_response

    provider = GeminiProvider(api_key="fake-key", client=mock_client)
    result = provider.ask(image_png=None, question="What is this?", answer_length="detailed")

    assert result.text == "Detailed answer"
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    instruction = call_kwargs["config"].system_instruction
    assert "detailed" in instruction.lower()


def test_fallback_model_on_503():
    """Verify that when primary model returns 503, provider falls back to working model."""
    mock_client = MagicMock()

    mock_success = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.finish_reason = None
    mock_success.candidates = [mock_candidate]
    mock_success.text = "Fallback success"

    # First call (primary model) fails with 503; second call (fallback) succeeds
    mock_client.models.generate_content.side_effect = [
        errors.APIError(code=503, response_json={"error": {"message": "High demand"}}),
        mock_success,
    ]

    provider = GeminiProvider(model="gemini-3.8-flash", api_key="fake-key", client=mock_client)
    result = provider.ask(image_png=None, question="Test question")

    assert result.text == "Fallback success"
    assert mock_client.models.generate_content.call_count == 2


def test_fallback_model_on_504_gateway_timeout():
    """Verify that when primary model returns 504 (deadline exceeded), fallback succeeds."""
    mock_client = MagicMock()

    mock_success = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.finish_reason = None
    mock_success.candidates = [mock_candidate]
    mock_success.text = "Fallback from 504"

    mock_client.models.generate_content.side_effect = [
        errors.APIError(code=504, response_json={"error": {"message": "Deadline expired before operation could complete."}}),
        mock_success,
    ]

    provider = GeminiProvider(model="gemini-3.8-flash", api_key="fake-key", client=mock_client)
    result = provider.ask(image_png=None, question="Test question")

    assert result.text == "Fallback from 504"
    assert mock_client.models.generate_content.call_count == 2


def test_request_timeout_fits_within_hard_timeout():
    """Ensure per-request timeout is short enough (<= 15s) so fallbacks complete before UI 45s deadline."""
    from ai.gemini_provider import REQUEST_TIMEOUT_MS
    from core.app_controller import HARD_TIMEOUT_MS

    assert REQUEST_TIMEOUT_MS <= 15000
    assert REQUEST_TIMEOUT_MS * 2 < HARD_TIMEOUT_MS
