"""Fake AI provider implementation for deterministic tests."""

from __future__ import annotations

from typing import Any, Generator, List, Optional

from ai.provider import AnswerResult, BaseAIProvider, ProviderError, UnknownError


class FakeProvider(BaseAIProvider):
    """Deterministic AI provider for testing chat and streaming pipelines."""

    def __init__(
        self,
        scripted_answers: Optional[List[str]] = None,
        scripted_chunks: Optional[List[str]] = None,
        error_to_raise: Optional[Exception] = None,
        error_after_n_chunks: Optional[int] = None,
    ):
        self.scripted_answers = list(scripted_answers) if scripted_answers else []
        self.scripted_chunks = list(scripted_chunks) if scripted_chunks else []
        self.error_to_raise = error_to_raise
        self.error_after_n_chunks = error_after_n_chunks
        self.calls: List[dict[str, Any]] = []
        self.stream_calls: List[dict[str, Any]] = []

    def ask(
        self,
        image_png: Optional[bytes],
        question: str,
        history: Optional[List[Any]] = None,
        answer_length: str = "short",
    ) -> AnswerResult:
        """Submit prompt and optional image, returning scripted answer or raising error."""
        self.calls.append({
            "image_png": image_png,
            "question": question,
            "history": history,
            "answer_length": answer_length,
        })
        if self.error_to_raise is not None:
            raise self.error_to_raise

        if self.scripted_answers:
            text = self.scripted_answers.pop(0)
        else:
            text = f"Fake answer to: {question}"

        updated_history = list(history or [])
        updated_history.append({"role": "user", "parts": [question]})
        updated_history.append({"role": "model", "parts": [text]})
        return AnswerResult(text=text, history=updated_history)

    def ask_stream(
        self,
        image_png: Optional[bytes] = None,
        question: str = "",
        history: Optional[List[Any]] = None,
        answer_length: str = "short",
        images: Optional[List[bytes]] = None,
    ) -> Generator[str, None, None]:
        """Stream chunks of text or raise a chosen ProviderError."""
        self.stream_calls.append({
            "image_png": image_png,
            "question": question,
            "history": history,
            "answer_length": answer_length,
            "images": images,
        })

        if self.error_to_raise is not None and self.error_after_n_chunks is None:
            raise self.error_to_raise

        chunks = self.scripted_chunks if self.scripted_chunks else ["Fake ", "streamed ", "response."]
        for idx, chunk in enumerate(chunks):
            if self.error_after_n_chunks is not None and idx == self.error_after_n_chunks:
                if self.error_to_raise is not None:
                    raise self.error_to_raise
                raise UnknownError("Simulated mid-stream failure")
            yield chunk
