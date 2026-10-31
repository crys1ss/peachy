"""Comprehensive unit tests for ChatSession controller using FakeProvider and mock store."""

from __future__ import annotations

from pathlib import Path
import pytest
from PySide6.QtCore import QCoreApplication

from ai.provider import (
    BlockedError,
    EmptyResponseError,
    InvalidKeyError,
    MissingKeyError,
    NetworkError,
    RateLimitedError,
    TimeoutError,
)
from config.settings import Settings
from core.chat_session import ChatSession, build_context_history
from history.store import HistoryStore
from tests.fakes.fake_provider import FakeProvider


@pytest.fixture
def session_components(tmp_path: Path):
    """Provide a ChatSession wired to a throwaway HistoryStore and FakeProvider."""
    store = HistoryStore(db_path=tmp_path / "chat_session_test.db")
    settings = Settings(save_history=True, save_thumbnails=True)
    provider = FakeProvider(scripted_chunks=["Chunk 1, ", "Chunk 2, ", "done."])
    session = ChatSession(provider=provider, store=store, settings=settings)
    return session, store, provider, settings


def test_send_and_streaming_flow(session_components, qtbot):
    """send() creates messages, emits stream chunks in order, and finishes with complete MessageDict."""
    session, store, provider, settings = session_components

    started = []
    session.conversation_started.connect(lambda cid, t: started.append((cid, t)))

    added_messages = []
    session.message_added.connect(lambda msg: added_messages.append(msg))

    chunks = []
    session.stream_chunk.connect(lambda req_id, txt: chunks.append(txt))

    finished = []
    session.stream_finished.connect(lambda req_id, msg: finished.append(msg))

    session.send("Hello Peachy")

    # Wait for background stream worker to finish
    qtbot.waitUntil(lambda: len(finished) == 1, timeout=3000)

    # 1. New chat started
    assert len(started) == 1
    cid = session.current_conversation_id
    assert cid > 0

    # 2. User message emitted and persisted
    assert len(added_messages) == 1
    user_msg = added_messages[0]
    assert user_msg["role"] == "user"
    assert user_msg["text"] == "Hello Peachy"
    assert user_msg["conversation_id"] == cid

    # 3. Stream chunks delivered
    assert len(chunks) == 3
    assert chunks[-1] == "Chunk 1, Chunk 2, done."

    # 4. Assistant message finished and persisted
    asst_msg = finished[0]
    assert asst_msg["role"] == "model"
    assert asst_msg["status"] == "complete"
    assert asst_msg["text"] == "Chunk 1, Chunk 2, done."

    # Store verification
    persisted = store.get_messages(cid)
    assert len(persisted) == 2
    assert persisted[0]["text"] == "Hello Peachy"
    assert persisted[1]["text"] == "Chunk 1, Chunk 2, done."
    assert persisted[1]["status"] == "complete"


def test_stop_mid_stream(session_components, qtbot):
    """stop() mid-stream cancels worker and persists partial text with status 'stopped'."""
    session, store, provider, settings = session_components

    # Script multiple chunks with slight delay
    provider.scripted_chunks = ["Partial start ", "more text ", "should not be reached"]
    finished = []
    session.stream_finished.connect(lambda req_id, msg: finished.append(msg))

    session.send("Generate long response")

    # Wait until at least first chunk is emitted
    qtbot.waitUntil(lambda: len(session._messages) >= 1, timeout=1000)

    # Call stop immediately
    session.stop()

    assert len(finished) == 1
    asst_msg = finished[0]
    assert asst_msg["status"] == "stopped"

    cid = session.current_conversation_id
    persisted = store.get_messages(cid)
    assert len(persisted) == 2
    assert persisted[-1]["status"] == "stopped"


def test_regenerate_replaces_last_answer(session_components, qtbot):
    """regenerate() removes the previous assistant message and re-runs the last prompt."""
    session, store, provider, settings = session_components

    finished = []
    session.stream_finished.connect(lambda req_id, msg: finished.append(msg))

    session.send("First question")
    qtbot.waitUntil(lambda: len(finished) == 1, timeout=3000)
    assert finished[0]["text"] == "Chunk 1, Chunk 2, done."

    # Update provider chunks for regenerated answer
    provider.scripted_chunks = ["Regenerated ", "fresh ", "answer."]
    session.regenerate()

    qtbot.waitUntil(lambda: len(finished) == 2, timeout=3000)
    assert finished[1]["text"] == "Regenerated fresh answer."

    # Verify store has exactly 1 user msg and 1 model msg
    cid = session.current_conversation_id
    messages = store.get_messages(cid)
    assert len(messages) == 2
    assert messages[0]["text"] == "First question"
    assert messages[1]["text"] == "Regenerated fresh answer."


def test_edit_and_resend_drops_later_messages(session_components, qtbot):
    """edit_and_resend() removes subsequent turns from store and re-sends."""
    session, store, provider, settings = session_components

    finished = []
    session.stream_finished.connect(lambda req_id, msg: finished.append(msg))

    session.send("Question 1")
    qtbot.waitUntil(lambda: len(finished) == 1, timeout=3000)

    session.send("Question 2 to edit")
    qtbot.waitUntil(lambda: len(finished) == 2, timeout=3000)

    cid = session.current_conversation_id
    messages_before = store.get_messages(cid)
    assert len(messages_before) == 4  # u1, a1, u2, a2

    q2_id = messages_before[2]["id"]

    provider.scripted_chunks = ["Answer to revised question."]
    session.edit_and_resend(q2_id, "Question 2 REVISED")

    qtbot.waitUntil(lambda: len(finished) == 3, timeout=3000)

    messages_after = store.get_messages(cid)
    assert len(messages_after) == 4
    assert messages_after[0]["text"] == "Question 1"
    assert messages_after[2]["text"] == "Question 2 REVISED"
    assert messages_after[3]["text"] == "Answer to revised question."


def test_stale_request_id_ignored(session_components, qtbot):
    """Chunks or completion from older request IDs are discarded."""
    session, store, provider, settings = session_components

    received_chunks = []
    session.stream_chunk.connect(lambda req_id, txt: received_chunks.append(txt))

    session.current_conversation_id = 1
    session._current_request_id = 5

    # Simulate an older worker delivering request_id=4
    session._on_worker_chunk(4, "Stale chunk text")
    assert len(received_chunks) == 0

    session._on_worker_finished(4, "Stale finished text", {})
    # No assistant message added for stale request
    assert len(session._messages) == 0


def test_error_kinds_mapping(session_components, qtbot):
    """Every provider error maps to the exact error_kind and updates status."""
    session, store, provider, settings = session_components

    error_mappings = [
        (MissingKeyError(), "no_key"),
        (InvalidKeyError(), "invalid_key"),
        (RateLimitedError(), "rate_limited"),
        (NetworkError(), "offline"),
        (TimeoutError(), "offline"),
        (BlockedError(), "blocked"),
        (EmptyResponseError(), "empty"),
    ]

    for exc, expected_kind in error_mappings:
        failed_events = []
        session.stream_failed.connect(lambda req_id, kind, msg: failed_events.append((kind, msg)))

        provider.error_to_raise = exc
        session.send("Trigger error")

        qtbot.waitUntil(lambda: len(failed_events) == 1, timeout=3000)
        kind, msg = failed_events[0]
        assert kind == expected_kind
        assert session.status == expected_kind

        session.stream_failed.disconnect()


def test_context_restore_capping_and_image_omission(tmp_path: Path):
    """Context restore caps at 40 turns / 60k characters and omits older images."""
    store = HistoryStore(db_path=tmp_path / "context_test.db")
    cid = store.create_conversation("Context Restore Chat")

    # Create 50 messages
    for i in range(50):
        role = "user" if i % 2 == 0 else "model"
        mid = store.add_message(cid, role=role, text=f"Turn message {i} " + ("x" * 10))
        if role == "user" and i in (10, 20, 30):
            # Add attachment
            store.add_attachment(mid, "image/png", b"IMAGE_BYTES_" + str(i).encode(), b"THUMB", 100, 100)

    all_messages = store.get_messages(cid)
    assert len(all_messages) == 50

    # Build context history
    contents = build_context_history(all_messages, store=store, max_turns=40, max_chars=60000)

    # 1. Capped at 40 turns
    assert len(contents) == 40

    # 2. Latest user turn with image in the last 40 turns is turn 30
    # Turn 20 had an image too, but it's older than turn 30, so its text must have '[image omitted]'
    turn_20_content = next(c for c in contents if "Turn message 20" in c.parts[0].text)
    assert "[image omitted]" in turn_20_content.parts[0].text

    # Turn 30 is the latest user turn with image; it re-sends image bytes
    turn_30_content = next(c for c in contents if any(hasattr(p, "inline_data") and p.inline_data for p in c.parts))
    assert turn_30_content is not None
