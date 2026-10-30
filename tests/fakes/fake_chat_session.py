"""Fake ChatSession conforming exactly to the REDESIGN.md section 7 contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from PySide6.QtCore import QObject, Signal


class FakeChatSession(QObject):
    """Fake ChatSession providing scripted signals and behaviors for UI development and testing."""

    conversation_started = Signal(int, str)        # conv_id, title
    conversation_loaded = Signal(int, list)        # conv_id, [MessageDict]
    title_changed = Signal(int, str)               # conv_id, title
    message_added = Signal(dict)                   # MessageDict (user message, persisted)
    stream_started = Signal(int)                   # request_id
    stream_chunk = Signal(int, str)                # request_id, full text so far
    stream_finished = Signal(int, dict)            # request_id, MessageDict (assistant)
    stream_failed = Signal(int, str, str)          # request_id, error_kind, friendly message
    conversations_changed = Signal()
    status_changed = Signal(str)                   # ready | busy | offline | invalid_key | rate_limited | no_key

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.current_conversation_id: Optional[int] = None
        self._status: str = "ready"
        self._answer_length: str = "short"
        self._next_conv_id: int = 1
        self._next_msg_id: int = 1
        self._next_request_id: int = 1

        # In-memory storage for test verification
        self.conversations: dict[int, dict[str, Any]] = {}
        self.messages: dict[int, list[dict[str, Any]]] = {}

        # Scriptable controls
        self.scripted_chunks: list[str] = ["Hello! ", "I am Peachy, ", "your desktop assistant."]
        self.error_on_send: Optional[tuple[str, str]] = None  # (error_kind, friendly_message)
        self.is_streaming: bool = False
        self._stop_requested: bool = False

    @property
    def status(self) -> str:
        return self._status

    def set_status(self, new_status: str) -> None:
        self._status = new_status
        self.status_changed.emit(new_status)

    def set_answer_length(self, length: str) -> None:
        self._answer_length = length

    def new_chat(self) -> None:
        """Create a fresh conversation."""
        cid = self._next_conv_id
        self._next_conv_id += 1
        self.current_conversation_id = cid
        title = "New Chat"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        self.conversations[cid] = {
            "id": cid,
            "title": title,
            "created_at": now_str,
            "updated_at": now_str,
            "pinned": False,
            "source": "chat",
        }
        self.messages[cid] = []
        self.conversation_started.emit(cid, title)
        self.conversations_changed.emit()

    def load(self, conv_id: int) -> None:
        """Load an existing conversation and emit its messages."""
        self.current_conversation_id = conv_id
        msgs = list(self.messages.get(conv_id, []))
        self.conversation_loaded.emit(conv_id, msgs)

    def send(self, text: str, images: list[bytes] = ()) -> None:
        """Send a user message, persist it, and stream response."""
        if self.current_conversation_id is None:
            self.new_chat()
        cid = self.current_conversation_id
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

        attachments = []
        for idx, img_bytes in enumerate(images):
            attachments.append({
                "id": idx + 1,
                "mime": "image/png",
                "thumb": img_bytes[:64] if img_bytes else b"",
                "has_full": True,
            })

        user_msg = {
            "id": self._next_msg_id,
            "conversation_id": cid,
            "role": "user",
            "text": text,
            "created_at": now_str,
            "model": None,
            "status": "complete",
            "attachments": attachments,
        }
        self._next_msg_id += 1
        self.messages.setdefault(cid, []).append(user_msg)
        self.message_added.emit(user_msg)

        req_id = self._next_request_id
        self._next_request_id += 1

        if self.error_on_send:
            err_kind, err_msg = self.error_on_send
            self.stream_failed.emit(req_id, err_kind, err_msg)
            return

        self.is_streaming = True
        self._stop_requested = False
        self.stream_started.emit(req_id)

        accumulated = ""
        for chunk in self.scripted_chunks:
            if self._stop_requested:
                break
            accumulated += chunk
            self.stream_chunk.emit(req_id, accumulated)

        msg_status = "stopped" if self._stop_requested else "complete"
        asst_msg = {
            "id": self._next_msg_id,
            "conversation_id": cid,
            "role": "model",
            "text": accumulated,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
            "model": "gemini-2.5-flash",
            "status": msg_status,
            "attachments": [],
        }
        self._next_msg_id += 1
        self.messages[cid].append(asst_msg)
        self.is_streaming = False
        self.stream_finished.emit(req_id, asst_msg)

    def regenerate(self) -> None:
        """Regenerate the latest assistant message."""
        if self.current_conversation_id is None:
            return
        cid = self.current_conversation_id
        msgs = self.messages.get(cid, [])
        if not msgs:
            return

        # Pop previous assistant response if present
        if msgs[-1]["role"] == "model":
            msgs.pop()

        req_id = self._next_request_id
        self._next_request_id += 1

        self.is_streaming = True
        self._stop_requested = False
        self.stream_started.emit(req_id)

        accumulated = ""
        for chunk in self.scripted_chunks:
            if self._stop_requested:
                break
            accumulated += chunk
            self.stream_chunk.emit(req_id, accumulated)

        msg_status = "stopped" if self._stop_requested else "complete"
        asst_msg = {
            "id": self._next_msg_id,
            "conversation_id": cid,
            "role": "model",
            "text": accumulated,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
            "model": "gemini-2.5-flash",
            "status": msg_status,
            "attachments": [],
        }
        self._next_msg_id += 1
        msgs.append(asst_msg)
        self.is_streaming = False
        self.stream_finished.emit(req_id, asst_msg)

    def edit_and_resend(self, message_id: int, text: str) -> None:
        """Drop messages from message_id onward and re-send text."""
        if self.current_conversation_id is None:
            return
        cid = self.current_conversation_id
        msgs = self.messages.get(cid, [])
        kept = [m for m in msgs if m["id"] < message_id]
        self.messages[cid] = kept
        self.send(text)

    def stop(self) -> None:
        """Stop active streaming generation."""
        if self.is_streaming:
            self._stop_requested = True
