"""Tests for FakeProvider and FakeChatSession test doubles."""

from __future__ import annotations

import pytest
from ai.provider import InvalidKeyError, NetworkError
from tests.fakes.fake_chat_session import FakeChatSession
from tests.fakes.fake_provider import FakeProvider


def test_fake_provider_ask():
    """FakeProvider returns scripted answers or default formatted answer."""
    provider = FakeProvider(scripted_answers=["First scripted answer", "Second scripted answer"])

    res1 = provider.ask(image_png=None, question="Hi")
    assert res1.text == "First scripted answer"
    assert len(provider.calls) == 1

    res2 = provider.ask(image_png=None, question="Second question")
    assert res2.text == "Second scripted answer"

    # Default fallback answer when scripted list is exhausted
    res3 = provider.ask(image_png=None, question="Third question")
    assert res3.text == "Fake answer to: Third question"


def test_fake_provider_ask_error():
    """FakeProvider raises configured ProviderError on ask."""
    provider = FakeProvider(error_to_raise=InvalidKeyError("Key invalid"))
    with pytest.raises(InvalidKeyError):
        provider.ask(image_png=None, question="Hi")


def test_fake_provider_stream_and_midstream_error():
    """FakeProvider streams chunks and raises mid-stream error when configured."""
    provider = FakeProvider(
        scripted_chunks=["One ", "Two ", "Three ", "Four"],
        error_to_raise=NetworkError("Network pulled mid-stream"),
        error_after_n_chunks=2,
    )

    gen = provider.ask_stream(question="Count")
    assert next(gen) == "One "
    assert next(gen) == "Two "
    with pytest.raises(NetworkError):
        next(gen)


def test_fake_chat_session_lifecycle_and_signals(qtbot):
    """FakeChatSession conforms to contract signals: new_chat, send, stream chunks, and finish."""
    session = FakeChatSession()

    started_events = []
    session.conversation_started.connect(lambda cid, title: started_events.append((cid, title)))

    messages_added = []
    session.message_added.connect(lambda msg: messages_added.append(msg))

    chunks = []
    session.stream_chunk.connect(lambda req_id, text: chunks.append(text))

    finished_events = []
    session.stream_finished.connect(lambda req_id, msg: finished_events.append(msg))

    # 1. new_chat
    session.new_chat()
    assert len(started_events) == 1
    cid, title = started_events[0]
    assert cid == 1
    assert session.current_conversation_id == 1

    # 2. send
    session.send("Explain this", images=[b"PNG_DATA"])
    assert len(messages_added) == 1
    user_msg = messages_added[0]
    assert user_msg["role"] == "user"
    assert user_msg["text"] == "Explain this"
    assert len(user_msg["attachments"]) == 1
    assert user_msg["attachments"][0]["has_full"] is True

    # 3. Stream chunks and finish
    assert len(chunks) == 3
    assert chunks[-1] == "Hello! I am Peachy, your desktop assistant."
    assert len(finished_events) == 1
    asst_msg = finished_events[0]
    assert asst_msg["role"] == "model"
    assert asst_msg["status"] == "complete"
    assert asst_msg["text"] == "Hello! I am Peachy, your desktop assistant."


def test_fake_chat_session_regenerate(qtbot):
    """Regenerate replaces the last assistant message."""
    session = FakeChatSession()
    session.send("Hello")

    cid = session.current_conversation_id
    assert len(session.messages[cid]) == 2  # user + model

    session.scripted_chunks = ["New regenerated answer."]
    session.regenerate()

    assert len(session.messages[cid]) == 2
    assert session.messages[cid][-1]["text"] == "New regenerated answer."


def test_fake_chat_session_edit_and_resend(qtbot):
    """edit_and_resend drops messages from message_id onward and re-sends."""
    session = FakeChatSession()
    session.send("First question")
    session.send("Second question to edit")

    cid = session.current_conversation_id
    msgs = session.messages[cid]
    assert len(msgs) == 4  # user1, model1, user2, model2

    m2_id = msgs[2]["id"]  # user2 id
    session.scripted_chunks = ["Edited answer."]
    session.edit_and_resend(m2_id, "Second question revised")

    updated_msgs = session.messages[cid]
    assert len(updated_msgs) == 4
    assert updated_msgs[2]["text"] == "Second question revised"
    assert updated_msgs[3]["text"] == "Edited answer."


def test_fake_chat_session_stop(qtbot):
    """stop mid-stream marks assistant message status as 'stopped'."""
    session = FakeChatSession()
    # Pre-set stop so the stream loop stops immediately
    session.is_streaming = True
    session.stop()
    assert session._stop_requested is True


def test_fake_chat_session_error_handling(qtbot):
    """error_on_send triggers stream_failed signal with error_kind and message."""
    session = FakeChatSession()
    session.error_on_send = ("rate_limited", "Peachy needs a breather, try again in a moment")

    failed_events = []
    session.stream_failed.connect(lambda req_id, kind, msg: failed_events.append((kind, msg)))

    session.send("Hi")
    assert len(failed_events) == 1
    assert failed_events[0] == ("rate_limited", "Peachy needs a breather, try again in a moment")
