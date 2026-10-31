"""Core ChatSession controller managing main window conversation lifecycle and streaming."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, List, Optional

from PySide6.QtCore import QObject, Signal

from ai.gemini_provider import GeminiProvider
from ai.provider import BaseAIProvider
from config.settings import Settings, load_settings
from core.stream_worker import StreamWorker
from history.store import HistoryStore, create_attachment_thumbnail, generate_title
from history.worker import HistoryDbWorker

logger = logging.getLogger(__name__)


def build_context_history(
    messages: List[dict[str, Any]],
    store: Optional[HistoryStore] = None,
    max_turns: int = 40,
    max_chars: int = 60000,
) -> List[Any]:
    """Rebuild provider history from messages for context restore.

    Rules from REDESIGN.md section 6.3:
    - Capped at the last 40 turns or ~60k characters.
    - Images are re-sent ONLY for the latest user turn that still has data.
    - Older images go as the text '[image omitted]'.
    """
    if not messages:
        return []

    # 1. Cap to last max_turns
    subset = messages[-max_turns:]

    # 2. Cap to max_chars going backwards from the newest message
    capped: List[dict[str, Any]] = []
    total_chars = 0
    for m in reversed(subset):
        msg_text = m.get("text") or ""
        total_chars += len(msg_text)
        if total_chars > max_chars and capped:
            break
        capped.append(m)

    capped.reverse()

    # 3. Identify the latest user message with image data
    latest_user_img_idx: Optional[int] = None
    for idx, m in enumerate(reversed(capped)):
        if m.get("role") == "user":
            attachments = m.get("attachments") or []
            has_data = any(att.get("has_full") for att in attachments)
            if has_data:
                latest_user_img_idx = len(capped) - 1 - idx
                break

    # 4. Build Content representations
    from google.genai import types

    contents: List[types.Content] = []
    for idx, m in enumerate(capped):
        role = "user" if m.get("role") == "user" else "model"
        text = m.get("text") or ""
        parts: List[types.Part] = []

        if role == "user":
            attachments = m.get("attachments") or []
            if idx == latest_user_img_idx and store is not None:
                # Re-send full image bytes for the latest turn
                for att in attachments:
                    if att.get("has_full"):
                        data = store.get_attachment_data(att["id"])
                        if data:
                            parts.append(types.Part.from_bytes(data=data, mime_type=att.get("mime", "image/png")))
            elif attachments:
                # Older images replaced with placeholder text
                text += "\n[image omitted]"

        parts.append(types.Part.from_text(text=text))
        contents.append(types.Content(role=role, parts=parts))

    return contents


class ChatSession(QObject):
    """Central session controller for the main window chat interface."""

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

    def __init__(
        self,
        provider: Optional[BaseAIProvider] = None,
        store: Optional[HistoryStore] = None,
        settings: Optional[Settings] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.provider = provider or GeminiProvider()
        self.store = store or HistoryStore()
        self.settings = settings or load_settings()

        self.current_conversation_id: Optional[int] = None
        self._status: str = "ready"
        self._answer_length: str = getattr(self.settings, "answer_length", "short")

        self._current_request_id: int = 0
        self._active_worker: Optional[StreamWorker] = None
        self._messages: List[dict[str, Any]] = []
        self._in_memory_id_counter: int = 1
        self._title_worker: Optional[HistoryDbWorker] = None

    @property
    def status(self) -> str:
        return self._status

    @status.setter
    def status(self, val: str) -> None:
        self._status = val

    def _get_next_in_memory_id(self) -> int:
        nid = self._in_memory_id_counter
        self._in_memory_id_counter += 1
        return nid

    def set_answer_length(self, length: str) -> None:
        """Set default answer length ("short" | "detailed")."""
        self._answer_length = length

    def new_chat(self) -> None:
        """Start a fresh chat conversation."""
        self.stop()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        title = "New Chat"

        if getattr(self.settings, "save_history", False) and self.store:
            cid = self.store.create_conversation(title=title, source="chat")
        else:
            cid = self._get_next_in_memory_id()

        self.current_conversation_id = cid
        self._messages = []
        self.conversation_started.emit(cid, title)
        self.conversations_changed.emit()

    def load(self, conv_id: int) -> None:
        """Load conversation by ID and emit loaded messages."""
        self.stop()
        self.current_conversation_id = conv_id

        if self.store and getattr(self.settings, "save_history", False):
            self._messages = self.store.get_messages(conv_id)

        self.conversation_loaded.emit(conv_id, list(self._messages))

    def send(self, text: str, images: list[bytes] = ()) -> None:
        """Send a prompt and optional images, persisting them and streaming response."""
        if self.current_conversation_id is None:
            self.new_chat()

        cid = self.current_conversation_id
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        save_screenshots = getattr(self.settings, "save_thumbnails", False)
        save_hist = getattr(self.settings, "save_history", False)

        attachments_meta: List[dict[str, Any]] = []
        if save_hist and self.store:
            mid = self.store.add_message(cid, "user", text, has_image=bool(images))
            for img in images:
                thumb = create_attachment_thumbnail(img, 256)
                data = img if save_screenshots else None
                att_id = self.store.add_attachment(mid, "image/png", data, thumb)
                attachments_meta.append({
                    "id": att_id,
                    "mime": "image/png",
                    "thumb": thumb,
                    "has_full": data is not None,
                })
        else:
            mid = self._get_next_in_memory_id()
            for idx, img in enumerate(images):
                thumb = create_attachment_thumbnail(img, 256)
                attachments_meta.append({
                    "id": idx + 1,
                    "mime": "image/png",
                    "thumb": thumb,
                    "has_full": save_screenshots,
                })

        user_msg = {
            "id": mid,
            "conversation_id": cid,
            "role": "user",
            "text": text,
            "created_at": now_str,
            "model": None,
            "status": "complete",
            "attachments": attachments_meta,
        }
        self._messages.append(user_msg)
        self.message_added.emit(user_msg)

        # Start streaming query
        self._current_request_id += 1
        req_id = self._current_request_id
        self.status = "busy"
        self.status_changed.emit("busy")

        context_history = build_context_history(self._messages[:-1], store=self.store)

        self._active_worker = StreamWorker(
            provider=self.provider,
            request_id=req_id,
            question=text,
            images=list(images),
            history=context_history,
            answer_length=self._answer_length,
            parent=self,
        )
        self._active_worker.chunk.connect(self._on_worker_chunk)
        self._active_worker.finished.connect(self._on_worker_finished)
        self._active_worker.failed.connect(self._on_worker_failed)
        self._active_worker.start()
        self.stream_started.emit(req_id)

    def _on_worker_chunk(self, req_id: int, full_text: str) -> None:
        if req_id != self._current_request_id:
            return
        self.stream_chunk.emit(req_id, full_text)

    def _on_worker_finished(self, req_id: int, full_text: str, usage_info: dict) -> None:
        if req_id != self._current_request_id:
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        model_name = self.provider.get_model_name() if hasattr(self.provider, "get_model_name") else "gemini-2.5-flash"
        cid = self.current_conversation_id

        if getattr(self.settings, "save_history", False) and self.store and cid is not None:
            mid = self.store.add_message(
                cid,
                role="model",
                text=full_text,
                model=model_name,
                status="complete",
            )
        else:
            mid = self._get_next_in_memory_id()

        asst_msg = {
            "id": mid,
            "conversation_id": cid,
            "role": "model",
            "text": full_text,
            "created_at": now_str,
            "model": model_name,
            "status": "complete",
            "attachments": [],
        }
        self._messages.append(asst_msg)
        self.status = "ready"
        self.status_changed.emit("ready")
        self.stream_finished.emit(req_id, asst_msg)

        # Trigger AI title generation after first exchange
        self._check_and_trigger_ai_title()

    def _on_worker_failed(self, req_id: int, error_kind: str, friendly_msg: str, partial_text: str) -> None:
        if req_id != self._current_request_id:
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        model_name = self.provider.get_model_name() if hasattr(self.provider, "get_model_name") else "gemini-2.5-flash"
        cid = self.current_conversation_id

        if partial_text:
            if getattr(self.settings, "save_history", False) and self.store and cid is not None:
                mid = self.store.add_message(
                    cid,
                    role="model",
                    text=partial_text,
                    model=model_name,
                    status="error",
                )
            else:
                mid = self._get_next_in_memory_id()

            err_msg = {
                "id": mid,
                "conversation_id": cid,
                "role": "model",
                "text": partial_text,
                "created_at": now_str,
                "model": model_name,
                "status": "error",
                "attachments": [],
            }
            self._messages.append(err_msg)

        self.status = error_kind
        self.status_changed.emit(error_kind)
        self.stream_failed.emit(req_id, error_kind, friendly_msg)

    def _check_and_trigger_ai_title(self) -> None:
        """Trigger off-thread short title generation after first exchange."""
        cid = self.current_conversation_id
        if cid is None or not getattr(self.settings, "save_history", False) or not self.store:
            return

        conv = self.store.get_conversation(cid)
        if not conv or bool(conv.get("title_locked", False)):
            return

        user_msgs = [m for m in self._messages if m.get("role") == "user"]
        asst_msgs = [m for m in self._messages if m.get("role") == "model"]
        if len(user_msgs) != 1 or len(asst_msgs) != 1:
            return

        first_q = user_msgs[0].get("text", "")
        first_a = asst_msgs[0].get("text", "")

        def generate_ai_title() -> Optional[str]:
            prompt = (
                f"Summarize this conversation into a concise 3-6 word title. "
                f"Return ONLY the title without quotes or punctuation.\n\n"
                f"User: {first_q[:150]}\nAssistant: {first_a[:200]}"
            )
            try:
                res = self.provider.ask(image_png=None, question=prompt, answer_length="short")
                raw = res.text.strip().strip('"').strip("'").strip()
                words = raw.split()
                if words:
                    title = " ".join(words[:6])
                    return title[:50]
            except Exception as e:
                logger.debug("AI title generation failed (heuristic title stays): %s", e)
            return None

        self._title_worker = HistoryDbWorker(generate_ai_title, parent=self)
        self._title_worker.finished.connect(lambda title: self._on_ai_title_generated(cid, title))
        self._title_worker.start()

    def _on_ai_title_generated(self, conv_id: int, title: Optional[str]) -> None:
        if not title or not self.store:
            return
        conv = self.store.get_conversation(conv_id)
        if not conv or bool(conv.get("title_locked", False)):
            return

        with self.store.connect() as conn:
            conn.execute(
                "UPDATE conversations SET title = ? WHERE id = ? AND title_locked = 0;",
                (title, conv_id),
            )
        self.title_changed.emit(conv_id, title)
        self.conversations_changed.emit()

    def regenerate(self) -> None:
        """Replace the last assistant message and re-stream answer."""
        if self.current_conversation_id is None or not self._messages:
            return

        self.stop()

        if self._messages and self._messages[-1].get("role") == "model":
            last_asst = self._messages.pop()
            if getattr(self.settings, "save_history", False) and self.store:
                self.store.delete_messages_from(self.current_conversation_id, last_asst["id"])

        last_user = None
        for m in reversed(self._messages):
            if m.get("role") == "user":
                last_user = m
                break

        if not last_user:
            return

        self._current_request_id += 1
        req_id = self._current_request_id
        self.status = "busy"
        self.status_changed.emit("busy")

        idx = self._messages.index(last_user)
        context_history = build_context_history(self._messages[:idx], store=self.store)

        images = []
        if self.store:
            for att in last_user.get("attachments", []):
                if att.get("has_full"):
                    data = self.store.get_attachment_data(att["id"])
                    if data:
                        images.append(data)

        self._active_worker = StreamWorker(
            provider=self.provider,
            request_id=req_id,
            question=last_user.get("text", ""),
            images=images,
            history=context_history,
            answer_length=self._answer_length,
            parent=self,
        )
        self._active_worker.chunk.connect(self._on_worker_chunk)
        self._active_worker.finished.connect(self._on_worker_finished)
        self._active_worker.failed.connect(self._on_worker_failed)
        self._active_worker.start()
        self.stream_started.emit(req_id)

    def edit_and_resend(self, message_id: int, text: str) -> None:
        """Drop messages from message_id onward, update store, and send edited text."""
        if self.current_conversation_id is None:
            return

        self.stop()

        if getattr(self.settings, "save_history", False) and self.store:
            self.store.delete_messages_from(self.current_conversation_id, message_id)

        self._messages = [m for m in self._messages if m.get("id") < message_id]
        self.send(text)

    def stop(self) -> None:
        """Stop active streaming generation immediately and persist partial text with status 'stopped'."""
        if self._active_worker and self._active_worker.isRunning():
            req_id = self._current_request_id
            self._active_worker.cancel()
            self._active_worker.wait(500)
            partial_text = self._active_worker.get_full_text()

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            model_name = self.provider.get_model_name() if hasattr(self.provider, "get_model_name") else "gemini-2.5-flash"
            cid = self.current_conversation_id

            if getattr(self.settings, "save_history", False) and self.store and cid is not None:
                mid = self.store.add_message(
                    cid,
                    role="model",
                    text=partial_text,
                    model=model_name,
                    status="stopped",
                )
            else:
                mid = self._get_next_in_memory_id()

            asst_msg = {
                "id": mid,
                "conversation_id": cid,
                "role": "model",
                "text": partial_text,
                "created_at": now_str,
                "model": model_name,
                "status": "stopped",
                "attachments": [],
            }
            self._messages.append(asst_msg)
            self.status = "ready"
            self.status_changed.emit("ready")
            self.stream_finished.emit(req_id, asst_msg)
