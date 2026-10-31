"""Tests for GeminiProvider streaming, model fallbacks, usage metadata, and list_models."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
from google.genai import errors

from ai.gemini_provider import (
    FALLBACK_MODELS,
    SYSTEM_INSTRUCTION,
    SYSTEM_INSTRUCTION_CHAT,
    GeminiProvider,
)
from ai.provider import (
    BlockedError,
    EmptyResponseError,
    InvalidKeyError,
    NetworkError,
    RateLimitedError,
    TimeoutError,
)
from config.settings import Settings


def _create_mock_chunk(text: str, usage_metadata: dict = None, finish_reason: str = None):
    chunk = MagicMock()
    chunk.text = text
    if usage_metadata:
        um = MagicMock()
        um.prompt_token_count = usage_metadata.get("prompt_tokens", 0)
        um.candidates_token_count = usage_metadata.get("output_tokens", 0)
        um.total_token_count = usage_metadata.get("total_tokens", 0)
        chunk.usage_metadata = um
    else:
        chunk.usage_metadata = None

    if finish_reason:
        cand = MagicMock()
        cand.finish_reason = finish_reason
        chunk.candidates = [cand]
    else:
        chunk.candidates = []
    return chunk


def test_ask_stream_success_and_usage_metadata():
    """ask_stream yields incremental text chunks and returns final usage metadata."""
    mock_client = MagicMock()
    provider = GeminiProvider(model="gemini-2.5-flash", client=mock_client)

    chunks = [
        _create_mock_chunk("Hello "),
        _create_mock_chunk("world!"),
        _create_mock_chunk("", usage_metadata={"prompt_tokens": 10, "output_tokens": 5, "total_tokens": 15}),
    ]
    mock_client.models.generate_content_stream.return_value = chunks

    stream = provider.ask_stream(question="Say hello")
    received = []
    usage = None
    try:
        while True:
            received.append(next(stream))
    except StopIteration as stop:
        usage = stop.value

    assert received == ["Hello ", "world!"]
    assert usage == {"prompt_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    assert provider.last_usage_metadata == usage


def test_ask_stream_fallback_only_before_first_chunk():
    """Fallback to secondary model occurs if primary model fails before any chunk is yielded."""
    mock_client = MagicMock()
    provider = GeminiProvider(model="primary-failing-model", client=mock_client)

    # Primary model fails immediately with 503 APIError
    err_503 = errors.APIError(code=503, response_json={"error": {"message": "503 Service Unavailable"}})
    fallback_chunks = [
        _create_mock_chunk("Fallback answer chunk 1"),
        _create_mock_chunk(" chunk 2", usage_metadata={"prompt_tokens": 5, "output_tokens": 8, "total_tokens": 13}),
    ]

    def mock_stream(model, contents, config):
        if model == "primary-failing-model":
            raise err_503
        return fallback_chunks

    mock_client.models.generate_content_stream.side_effect = mock_stream

    with patch("ai.gemini_provider.load_settings", return_value=Settings(fallback_models_enabled=True)):
        stream = provider.ask_stream(question="Test question")
        received = []
        try:
            while True:
                received.append(next(stream))
        except StopIteration as stop:
            pass

        assert received == ["Fallback answer chunk 1", " chunk 2"]


def test_ask_stream_no_fallback_midstream():
    """Once the first chunk is yielded, any subsequent error ends the stream without fallback."""
    mock_client = MagicMock()
    provider = GeminiProvider(model="gemini-2.5-flash", client=mock_client)

    class FailingStream:
        def __iter__(self):
            yield _create_mock_chunk("First chunk OK")
            # Mid-stream failure!
            raise ConnectionError("Network dropped mid-stream")

    mock_client.models.generate_content_stream.return_value = FailingStream()

    with patch("ai.gemini_provider.load_settings", return_value=Settings(fallback_models_enabled=True)):
        stream = provider.ask_stream(question="Test question")
        # First chunk succeeds
        first = next(stream)
        assert first == "First chunk OK"

        # Next chunk raises NetworkError directly (no fallback attempted!)
        with pytest.raises(NetworkError):
            next(stream)


def test_ask_stream_safety_block():
    """Safety filter blocks raise BlockedError."""
    mock_client = MagicMock()
    provider = GeminiProvider(model="gemini-2.5-flash", client=mock_client)

    chunks = [
        _create_mock_chunk("", finish_reason="SAFETY"),
    ]
    mock_client.models.generate_content_stream.return_value = chunks

    stream = provider.ask_stream(question="Blocked question")
    with pytest.raises(BlockedError):
        next(stream)


def test_list_models_live_and_fallback():
    """list_models returns generateContent models from API, or static list on error."""
    mock_client = MagicMock()
    provider = GeminiProvider(client=mock_client)

    # 1. API success with models list
    m1 = MagicMock()
    m1.name = "models/gemini-2.5-flash"
    m1.supported_actions = ["generateContent"]
    m2 = MagicMock()
    m2.name = "models/text-embedding-004"
    m2.supported_actions = ["embedContent"]
    m3 = MagicMock()
    m3.name = "models/gemini-3.5-flash"
    m3.supported_actions = ["generateContent"]

    mock_client.models.list.return_value = [m1, m2, m3]

    models = provider.list_models()
    assert "gemini-2.5-flash" in models
    assert "gemini-3.5-flash" in models
    assert "text-embedding-004" not in models

    # 2. API failure returns static fallback list
    mock_client.models.list.side_effect = RuntimeError("Network error")
    fallback_res = provider.list_models()
    assert len(fallback_res) > 0
    assert "gemini-2.5-flash" in fallback_res or "gemini-3.5-flash" in fallback_res


def test_system_instructions_exist():
    """Verify distinct system instructions for overlay and main window chat."""
    assert len(SYSTEM_INSTRUCTION) > 20
    assert len(SYSTEM_INSTRUCTION_CHAT) > 20
    assert "screen utility" in SYSTEM_INSTRUCTION
    assert "desktop AI assistant" in SYSTEM_INSTRUCTION_CHAT
