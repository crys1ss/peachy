"""Abstract interface and typed error hierarchy for AI providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional


class ProviderError(Exception):
    """Base exception for all AI provider errors."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.message = message
        self.original_error = original_error


class MissingKeyError(ProviderError):
    """API key is missing or not configured."""

    DEFAULT_MESSAGE = "Gemini API key is missing. Please set the GEMINI_API_KEY environment variable."

    def __init__(self, message: str = DEFAULT_MESSAGE, original_error: Optional[Exception] = None):
        super().__init__(message, original_error)


class InvalidKeyError(ProviderError):
    """API key is invalid, expired, or unauthorized."""

    DEFAULT_MESSAGE = "Gemini API key is invalid or unauthorized. Please verify your key."

    def __init__(self, message: str = DEFAULT_MESSAGE, original_error: Optional[Exception] = None):
        super().__init__(message, original_error)


class RateLimitedError(ProviderError):
    """API quota or rate limit has been exceeded."""

    DEFAULT_MESSAGE = "Gemini rate limit or quota exceeded. Please wait a moment and try again."

    def __init__(self, message: str = DEFAULT_MESSAGE, original_error: Optional[Exception] = None):
        super().__init__(message, original_error)


class TimeoutError(ProviderError):
    """Request to provider exceeded maximum timeout."""

    DEFAULT_MESSAGE = "Request to Gemini timed out. Please check your network connection and retry."

    def __init__(self, message: str = DEFAULT_MESSAGE, original_error: Optional[Exception] = None):
        super().__init__(message, original_error)


class NetworkError(ProviderError):
    """Underlying network connection failure."""

    DEFAULT_MESSAGE = "Network connection failure communicating with Gemini. Please check your internet connection."

    def __init__(self, message: str = DEFAULT_MESSAGE, original_error: Optional[Exception] = None):
        super().__init__(message, original_error)


class BlockedError(ProviderError):
    """Request or response was blocked by safety/policy filters."""

    DEFAULT_MESSAGE = "Content was blocked by safety filters. Please try a different selection."

    def __init__(self, message: str = DEFAULT_MESSAGE, original_error: Optional[Exception] = None):
        super().__init__(message, original_error)


class EmptyResponseError(ProviderError):
    """Provider returned an empty response body or text."""

    DEFAULT_MESSAGE = "Gemini returned an empty response. Try rephrasing your question."

    def __init__(self, message: str = DEFAULT_MESSAGE, original_error: Optional[Exception] = None):
        super().__init__(message, original_error)


class UnknownError(ProviderError):
    """An unexpected or unclassified error occurred."""

    DEFAULT_MESSAGE = "An unexpected error occurred while communicating with Gemini."

    def __init__(self, message: str = DEFAULT_MESSAGE, original_error: Optional[Exception] = None):
        super().__init__(message, original_error)


# Convenience aliases matching SPEC naming
MissingKey = MissingKeyError
InvalidKey = InvalidKeyError
RateLimited = RateLimitedError
Timeout = TimeoutError
Network = NetworkError
Blocked = BlockedError
EmptyResponse = EmptyResponseError
Unknown = UnknownError


@dataclass
class AnswerResult:
    """Encapsulates answer text and conversation history for follow-ups."""

    text: str
    history: List[Any] = field(default_factory=list)


class BaseAIProvider(ABC):
    """Abstract base class defining the AI provider interface."""

    @abstractmethod
    def ask(
        self,
        image_png: Optional[bytes],
        question: str,
        history: Optional[List[Any]] = None,
    ) -> AnswerResult:
        """Submit a prompt and optional image to the AI provider.

        Args:
            image_png: Raw PNG bytes of the screen crop (or None for follow-ups).
            question: User's question or prompt (may be empty for auto-explain).
            history: Previous conversation history if this is a follow-up.

        Returns:
            AnswerResult containing markdown text and updated conversation history.

        Raises:
            ProviderError or one of its typed subclasses on failure.
        """
        raise NotImplementedError
