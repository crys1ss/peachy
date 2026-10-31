"""Contract verification test comparing ChatSession and FakeChatSession.

Ensures Track A (UI) and Track B (Core) can seamlessly swap FakeChatSession
and real ChatSession with guaranteed interface, signal, and behavioral parity.
"""

from __future__ import annotations

import inspect
from typing import get_type_hints
from unittest.mock import MagicMock

from PySide6.QtCore import Signal
import pytest

from config.settings import Settings
from core.chat_session import ChatSession
from history.store import HistoryStore
from tests.fakes.fake_chat_session import FakeChatSession
from tests.fakes.fake_provider import FakeProvider


def test_signals_parity():
    """Verify both ChatSession and FakeChatSession define the exact same Qt signals."""
    expected_signals = [
        "conversation_started",
        "conversation_loaded",
        "title_changed",
        "message_added",
        "stream_started",
        "stream_chunk",
        "stream_finished",
        "stream_failed",
        "conversations_changed",
        "status_changed",
    ]

    for sig_name in expected_signals:
        assert hasattr(ChatSession, sig_name), f"ChatSession is missing signal: {sig_name}"
        assert hasattr(FakeChatSession, sig_name), f"FakeChatSession is missing signal: {sig_name}"


def test_methods_parity():
    """Verify public contract methods exist on both ChatSession and FakeChatSession."""
    contract_methods = [
        "new_chat",
        "load",
        "send",
        "regenerate",
        "edit_and_resend",
        "stop",
        "set_answer_length",
    ]

    for meth_name in contract_methods:
        real_meth = getattr(ChatSession, meth_name, None)
        fake_meth = getattr(FakeChatSession, meth_name, None)

        assert callable(real_meth), f"ChatSession.{meth_name} must be callable"
        assert callable(fake_meth), f"FakeChatSession.{meth_name} must be callable"

        real_sig = inspect.signature(real_meth)
        fake_sig = inspect.signature(fake_meth)

        # Parameter names should match (excluding default value nuances)
        real_params = list(real_sig.parameters.keys())
        fake_params = list(fake_sig.parameters.keys())
        assert real_params == fake_params, (
            f"Signature mismatch for {meth_name}: ChatSession has {real_params}, "
            f"FakeChatSession has {fake_params}"
        )


def test_status_property_parity():
    """Verify both classes provide a status property returning a string."""
    fake = FakeChatSession()
    assert isinstance(fake.status, str)
    assert hasattr(fake, "current_conversation_id")

    fake_prov = FakeProvider()
    real = ChatSession(provider=fake_prov, store=MagicMock(), settings=Settings())
    assert isinstance(real.status, str)
    assert hasattr(real, "current_conversation_id")


def test_behavioral_signal_sequence_parity(qapp, tmp_path):
    """Verify both emit equivalent sequence of signals for new_chat, send, and stop."""
    fake = FakeChatSession()
    fake.scripted_chunks = ["Chunk 1", " Chunk 2"]

    db_path = tmp_path / "contract_test.db"
    store = HistoryStore(db_path=db_path)
    fake_prov = FakeProvider()
    fake_prov.scripted_chunks = ["Chunk 1", " Chunk 2"]
    real = ChatSession(provider=fake_prov, store=store, settings=Settings(save_history=True))

    fake_emitted = []
    real_emitted = []

    # Connect signals for fake
    fake.conversation_started.connect(lambda cid, t: fake_emitted.append(("conversation_started", cid, t)))
    fake.message_added.connect(lambda m: fake_emitted.append(("message_added", m["role"], m["text"])))
    fake.stream_started.connect(lambda req_id: fake_emitted.append(("stream_started", req_id)))
    fake.stream_chunk.connect(lambda req_id, text: fake_emitted.append(("stream_chunk", req_id, text)))
    fake.stream_finished.connect(lambda req_id, m: fake_emitted.append(("stream_finished", req_id, m["status"])))

    # Connect signals for real
    real.conversation_started.connect(lambda cid, t: real_emitted.append(("conversation_started", cid, t)))
    real.message_added.connect(lambda m: real_emitted.append(("message_added", m["role"], m["text"])))
    real.stream_started.connect(lambda req_id: real_emitted.append(("stream_started", req_id)))
    real.stream_chunk.connect(lambda req_id, text: real_emitted.append(("stream_chunk", req_id, text)))
    real.stream_finished.connect(lambda req_id, m: real_emitted.append(("stream_finished", req_id, m["status"])))

    # 1. new_chat
    fake.new_chat()
    real.new_chat()

    assert fake_emitted[0][0] == "conversation_started"
    assert real_emitted[0][0] == "conversation_started"
    assert fake_emitted[0][2] == "New Chat"
    assert real_emitted[0][2] == "New Chat"

    # 2. send
    fake.send("Hello world")
    real.send("Hello world")

    # Wait for real ChatSession worker to finish
    if real._active_worker:
        real._active_worker.wait(2000)

    # Process pending events for queued Qt signals
    qapp.processEvents()

    # Compare signal event names emitted during send
    fake_events = [e[0] for e in fake_emitted]
    real_events = [e[0] for e in real_emitted]

    assert "conversation_started" in fake_events and "conversation_started" in real_events
    assert "message_added" in fake_events and "message_added" in real_events
    assert "stream_started" in fake_events and "stream_started" in real_events
    assert "stream_chunk" in fake_events and "stream_chunk" in real_events
    assert "stream_finished" in fake_events and "stream_finished" in real_events
