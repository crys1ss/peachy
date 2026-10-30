"""Tests for HistoryStore schema v2, migration from v1, and new v2 store methods."""

from __future__ import annotations

from datetime import datetime
import io
from pathlib import Path
import sqlite3
import pytest

from history.store import (
    SCHEMA_VERSION,
    HistoryStore,
    create_attachment_thumbnail,
)


V1_SCHEMA_SQL = """
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    thumbnail BLOB
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    has_image INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_conversations_updated_at ON conversations(updated_at DESC);
"""


def _create_real_v1_database(db_path: Path) -> None:
    """Helper creating a genuine v1 schema database populated with test records."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(V1_SCHEMA_SQL)
        conn.execute("INSERT INTO schema_version (version) VALUES (1);")
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at, thumbnail) VALUES (?, ?, ?, ?, ?);",
            (1, "V1 Initial Conversation", "2026-10-20 10:00:00.000", "2026-10-20 10:05:00.000", None),
        )
        conn.execute(
            "INSERT INTO messages (id, conversation_id, role, text, created_at, has_image) VALUES (?, ?, ?, ?, ?, ?);",
            (1, 1, "user", "What is schema v1?", "2026-10-20 10:00:00.000", 0),
        )
        conn.execute(
            "INSERT INTO messages (id, conversation_id, role, text, created_at, has_image) VALUES (?, ?, ?, ?, ?, ?);",
            (2, 1, "model", "Schema v1 contains basic conversations and messages.", "2026-10-20 10:05:00.000", 0),
        )
        conn.commit()


def test_v1_to_v2_migration_and_backup(tmp_path: Path):
    """Opening an existing v1 database creates .v1.bak, upgrades schema to v2, and preserves data."""
    db_file = tmp_path / "history.db"
    bak_file = tmp_path / "history.v1.bak"

    _create_real_v1_database(db_file)
    assert db_file.exists()
    assert not bak_file.exists()

    # Initialize store to trigger migration
    store = HistoryStore(db_path=db_file)

    # 1. Backup file .v1.bak was created and contains valid v1 data
    assert bak_file.exists()
    with sqlite3.connect(str(bak_file)) as bak_conn:
        cur = bak_conn.execute("SELECT version FROM schema_version LIMIT 1;")
        assert cur.fetchone()[0] == 1
        cur = bak_conn.execute("SELECT title FROM conversations WHERE id = 1;")
        assert cur.fetchone()[0] == "V1 Initial Conversation"

    # 2. Schema version is upgraded to 2
    with store.connect() as conn:
        cur = conn.execute("SELECT version FROM schema_version LIMIT 1;")
        assert cur.fetchone()[0] == 2

        # 3. New columns exist on conversations
        conv_cur = conn.execute("PRAGMA table_info(conversations);")
        conv_cols = {r["name"]: r["dflt_value"] for r in conv_cur.fetchall()}
        assert "pinned" in conv_cols
        assert "title_locked" in conv_cols
        assert "source" in conv_cols

        # 4. New columns exist on messages
        msg_cur = conn.execute("PRAGMA table_info(messages);")
        msg_cols = {r["name"]: r["dflt_value"] for r in msg_cur.fetchall()}
        assert "model" in msg_cols
        assert "status" in msg_cols

        # 5. attachments table exists
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
        assert "attachments" in tables

    # 6. Existing data was preserved
    conv = store.get_conversation(1)
    assert conv is not None
    assert conv["title"] == "V1 Initial Conversation"
    assert conv["pinned"] is False
    assert conv["title_locked"] is False
    assert conv["source"] == "overlay"

    messages = store.get_messages(1)
    assert len(messages) == 2
    assert messages[0]["text"] == "What is schema v1?"
    assert messages[0]["status"] == "complete"
    assert messages[0]["attachments"] == []
    assert messages[1]["text"] == "Schema v1 contains basic conversations and messages."


def test_migration_is_idempotent(tmp_path: Path):
    """Running migration repeatedly causes no errors and preserves schema version."""
    db_file = tmp_path / "custom_test.db"
    _create_real_v1_database(db_file)

    store = HistoryStore(db_path=db_file)
    assert (tmp_path / "custom_test.v1.bak").exists()

    # Re-run migration multiple times directly
    store._migrate_v1_to_v2()
    store._migrate_v1_to_v2()
    store._ensure_schema()

    with store.connect() as conn:
        cur = conn.execute("SELECT version FROM schema_version LIMIT 1;")
        assert cur.fetchone()[0] == 2


def test_rename_conversation_locks_title(tmp_path: Path):
    """rename_conversation updates title and sets title_locked to 1."""
    store = HistoryStore(db_path=tmp_path / "history.db")
    cid = store.create_conversation("Original Heuristic Title")

    c = store.get_conversation(cid)
    assert c["title"] == "Original Heuristic Title"
    assert c["title_locked"] is False

    store.rename_conversation(cid, "Renamed By User")
    c_after = store.get_conversation(cid)
    assert c_after["title"] == "Renamed By User"
    assert c_after["title_locked"] is True


def test_set_pinned(tmp_path: Path):
    """set_pinned toggles the pinned flag without losing conversation identity."""
    store = HistoryStore(db_path=tmp_path / "history.db")
    cid = store.create_conversation("My Task")

    assert store.get_conversation(cid)["pinned"] is False

    store.set_pinned(cid, True)
    assert store.get_conversation(cid)["pinned"] is True

    store.set_pinned(cid, False)
    assert store.get_conversation(cid)["pinned"] is False


def test_list_conversations_with_v2_fields_and_ordering(tmp_path: Path):
    """list_conversations returns {id, title, updated_at, pinned, preview, source} ordered by pinned DESC, updated_at DESC."""
    store = HistoryStore(db_path=tmp_path / "history.db")

    c1 = store.create_conversation("First Chat")
    store.add_message(c1, "user", "Question 1")
    store.add_message(c1, "model", "Answer 1 preview")

    c2 = store.create_conversation("Second Chat")
    store.add_message(c2, "user", "Question 2")
    store.add_message(c2, "model", "Answer 2 preview")

    # Pin c1 (older conversation) -> should jump to the front of the list
    store.set_pinned(c1, True)

    convs = store.list_conversations()
    assert len(convs) == 2
    # c1 is pinned, so it appears first despite c2 being updated later
    assert convs[0]["id"] == c1
    assert convs[0]["pinned"] is True
    assert convs[0]["preview"] == "Answer 2 preview" or "preview" in convs[0]["preview"]
    assert convs[0]["source"] == "overlay"

    assert convs[1]["id"] == c2
    assert convs[1]["pinned"] is False
    assert convs[1]["preview"] == "Answer 2 preview"

    # Search filter on preview/message text
    filtered = store.list_conversations(query="Question 1")
    assert len(filtered) == 1
    assert filtered[0]["id"] == c1

    # Search filter on title
    filtered_title = store.list_conversations(query="Second")
    assert len(filtered_title) == 1
    assert filtered_title[0]["id"] == c2


def test_attachments_lifecycle_and_data_isolation(tmp_path: Path):
    """add_attachment stores 256px thumb and optional data; get_messages omits full data; get_attachment_data retrieves it."""
    store = HistoryStore(db_path=tmp_path / "history.db")
    cid = store.create_conversation("Attachment Test")

    mid = store.add_message(cid, "user", "Look at this screenshot", has_image=True)

    fake_full_png = b"RAW_FULL_SCREENSHOT_PNG_BYTES_1234567890"
    fake_thumb_png = b"THUMB_PNG_BYTES_256"

    att_id = store.add_attachment(
        message_id=mid,
        mime="image/png",
        data=fake_full_png,
        thumb=fake_thumb_png,
        w=1920,
        h=1080,
    )
    assert att_id > 0

    # Message retrieval returns attachment metadata only, never full image bytes
    messages = store.get_messages(cid)
    assert len(messages) == 1
    msg = messages[0]
    assert len(msg["attachments"]) == 1
    att_meta = msg["attachments"][0]
    assert att_meta["id"] == att_id
    assert att_meta["mime"] == "image/png"
    assert att_meta["thumb"] == fake_thumb_png
    assert att_meta["has_full"] is True
    # Ensure full data is NOT exposed in the MessageDict
    assert "data" not in att_meta

    # get_attachment_data retrieves full bytes
    full_data = store.get_attachment_data(att_id)
    assert full_data == fake_full_png

    # Second attachment with data=None (when "save screenshots" is disabled)
    att_id_no_full = store.add_attachment(
        message_id=mid,
        mime="image/png",
        data=None,
        thumb=fake_thumb_png,
        w=800,
        h=600,
    )
    messages_after = store.get_messages(cid)
    att2 = messages_after[0]["attachments"][1]
    assert att2["has_full"] is False
    assert store.get_attachment_data(att_id_no_full) is None


def test_delete_messages_from_cascades_attachments(tmp_path: Path):
    """delete_messages_from removes target messages (inclusive) and cascades to attachments."""
    store = HistoryStore(db_path=tmp_path / "history.db")
    cid = store.create_conversation("Delete Test")

    m1 = store.add_message(cid, "user", "Message 1")
    m2 = store.add_message(cid, "model", "Answer 1")
    m3 = store.add_message(cid, "user", "Message 2 to edit", has_image=True)
    att_id = store.add_attachment(m3, "image/png", b"full", b"thumb", 100, 100)
    m4 = store.add_message(cid, "model", "Answer 2")

    assert len(store.get_messages(cid)) == 4
    assert store.get_attachment_data(att_id) is not None

    # Delete from m3 onward (inclusive)
    store.delete_messages_from(cid, m3)

    remaining = store.get_messages(cid)
    assert len(remaining) == 2
    assert [m["id"] for m in remaining] == [m1, m2]

    # Cascade deleted the attachment associated with m3
    assert store.get_attachment_data(att_id) is None


def test_create_attachment_thumbnail_generates_valid_png():
    """create_attachment_thumbnail downscales large image to max 256px PNG."""
    from PIL import Image

    # Create a 800x600 test image in memory
    src_img = Image.new("RGBA", (800, 600), color=(255, 100, 100, 255))
    buf = io.BytesIO()
    src_img.save(buf, format="PNG")
    raw_bytes = buf.getvalue()

    thumb_bytes = create_attachment_thumbnail(raw_bytes, max_dim=256)
    assert isinstance(thumb_bytes, bytes)
    assert len(thumb_bytes) > 0

    thumb_img = Image.open(io.BytesIO(thumb_bytes))
    assert thumb_img.format == "PNG"
    assert max(thumb_img.size) == 256
    assert thumb_img.size == (256, 192)
