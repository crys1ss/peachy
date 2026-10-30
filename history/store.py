"""SQLite persistence store for Peachy chat history.

Database is stored at %APPDATA%\\Peachy\\history.db.
Features:
- Parameterized SQL queries only.
- WAL mode enabled with short-lived connections.
- Automatic recovery from corrupt database: backs up to history.db.bak, creates fresh DB, logs warning, never crashes.
- Local title generation without AI calls.
- 240px wide JPEG thumbnail (quality 70) when enabled; text-only by default.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import io
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any, Generator, List, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

CREATE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    thumbnail BLOB
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    has_image INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at DESC);
"""


def get_default_history_db_path() -> Path:
    r"""Return default path to history.db.

    Lookup order:
    1. PEACHY_HISTORY_DB_PATH environment variable (for testing & isolated runs)
    2. %APPDATA%\Peachy\history.db (standard Windows user data)
    3. ~/.config/Peachy/history.db (standard fallback)
    """
    env_db = os.environ.get("PEACHY_HISTORY_DB_PATH")
    if env_db and env_db.strip():
        return Path(env_db.strip())

    appdata = os.environ.get("APPDATA")
    if appdata:
        base_dir = Path(appdata)
    else:
        base_dir = Path.home() / ".config"
    return base_dir / "Peachy" / "history.db"


def generate_title(first_question: Optional[str], first_answer: Optional[str]) -> str:
    """Generate title locally without an AI call.

    Rules:
    - The first question cut at 50 characters.
    - If there was no question (empty, None, or default auto-explain text),
      the first six words of the first answer.
    """
    q = (first_question or "").strip()
    if q and q.lower() != "explain this screen":
        return q[:50]

    ans = (first_answer or "").strip()
    words = ans.split()
    if words:
        return " ".join(words[:6])
    return q[:50] if q else "New Conversation"


def create_thumbnail(image_data: Any) -> Optional[bytes]:
    """Generate a 240 px wide JPEG thumbnail (quality 70).

    Never stores full screenshots.
    Returns JPEG bytes or None if image_data is empty/invalid.
    """
    if not image_data:
        return None

    try:
        from PIL import Image

        img = None
        if isinstance(image_data, bytes):
            img = Image.open(io.BytesIO(image_data))
        elif isinstance(image_data, Image.Image):
            img = image_data
        elif hasattr(image_data, "save"):  # QImage or QPixmap
            from PySide6.QtCore import QBuffer, QByteArray, QIODevice

            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            image_data.save(buf, "PNG")
            img = Image.open(io.BytesIO(bytes(ba.data())))

        if img is None:
            return None

        # Convert to RGB (JPEG does not support alpha channel)
        if img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        if w > 0 and h > 0:
            target_w = 240
            target_h = max(1, int(round(h * (target_w / float(w)))))
            img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=70)
        return out.getvalue()
    except Exception as exc:
        logger.warning("Failed to generate thumbnail: %s", exc)
        return None


class HistoryStore:
    """Manages SQLite storage for conversations and messages with safe corruption recovery."""

    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = Path(db_path) if db_path is not None else get_default_history_db_path()
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as dir_err:
            logger.warning("Could not create history directory for %s: %s", self.db_path, dir_err)
        self._init_db()

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a short-lived connection with WAL mode and foreign keys enabled."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            yield conn
            conn.commit()
        except sqlite3.DatabaseError as db_err:
            conn.rollback()
            logger.warning("Database error during operation: %s", db_err)
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize database schema, backing up and recovering if corrupt or inaccessible."""
        try:
            self._ensure_schema()
            return
        except sqlite3.DatabaseError as exc:
            logger.warning(
                "History database at %s corrupt or inaccessible (%s). Attempting backup and recreation.",
                self.db_path,
                exc,
            )
            recovered = self._recover_corrupt_db()
            if recovered:
                try:
                    self._ensure_schema()
                    logger.info("Successfully recreated fresh history database at original path %s.", self.db_path)
                    return
                except Exception as rec_err:
                    logger.error(
                        "Re-initializing schema at original path %s failed after corrupt DB removal: %s",
                        self.db_path,
                        rec_err,
                    )

            # ONLY reach fallback if original path is genuinely unusable/inaccessible (e.g. read-only volume, permissions)
            fallback_dir = Path(tempfile.gettempdir()) / "peachy_history"
            try:
                fallback_dir.mkdir(parents=True, exist_ok=True)
                fallback_db = fallback_dir / f"fallback_{os.getpid()}_{self.db_path.name}"
                logger.error(
                    "DATABASE RECOVERY FAILED at original path %s. Redirecting session to temporary database at %s. "
                    "Warning: chat history in this temporary database will not persist across app restarts.",
                    self.db_path,
                    fallback_db,
                )
                self.db_path = fallback_db
                self._ensure_schema()
            except Exception as fb_err:
                logger.critical("Fatal: failed to initialize fallback history database at %s: %s", fallback_dir, fb_err)
                raise

    def _ensure_schema(self) -> None:
        """Execute table creation and schema version verification."""
        with self.connect() as conn:
            conn.executescript(CREATE_SCHEMA_SQL)
            cur = conn.execute("SELECT version FROM schema_version LIMIT 1;")
            row = cur.fetchone()
            if row is None:
                conn.execute("INSERT INTO schema_version (version) VALUES (?);", (SCHEMA_VERSION,))

    def _recover_corrupt_db(self) -> bool:
        """Back up corrupt database to history.db.bak and delete the original.

        Returns:
            True if corrupt database was safely backed up and removed, allowing the original
            path to be cleanly recreated.
            False if backup or removal failed.
        """
        if not self.db_path.exists():
            return False

        bak_path = self.db_path.with_name(self.db_path.name + ".bak")
        try:
            if bak_path.exists():
                try:
                    bak_path.unlink()
                except OSError as unl_bak_err:
                    logger.warning("Could not remove existing backup %s: %s", bak_path, unl_bak_err)

            shutil.copy2(self.db_path, bak_path)
            logger.info("Corrupt database successfully backed up to %s", bak_path)

            self.db_path.unlink()
            if self.db_path.exists():
                logger.error("Failed to remove corrupt database file %s: file still exists.", self.db_path)
                return False

            # Also clear any WAL/SHM companion files
            for ext in ("-wal", "-shm"):
                companion = self.db_path.with_name(self.db_path.name + ext)
                if companion.exists():
                    try:
                        companion.unlink()
                    except OSError as comp_err:
                        logger.warning("Could not remove companion file %s: %s", companion, comp_err)

            return True
        except Exception as exc:
            logger.error("Failed during corrupt DB recovery backup for %s: %s", self.db_path, exc)
            return False

    def create_conversation(self, title: str, thumbnail: Optional[bytes] = None) -> int:
        """Create a new conversation record. Returns new conversation ID."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO conversations (title, created_at, updated_at, thumbnail)
                VALUES (?, ?, ?, ?);
                """,
                (title, now_str, now_str, thumbnail),
            )
            return int(cur.lastrowid)

    def add_message(
        self,
        conversation_id: int,
        role: str,
        text: str,
        has_image: bool = False,
    ) -> int:
        """Append a message to an existing conversation. Returns message ID."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO messages (conversation_id, role, text, created_at, has_image)
                VALUES (?, ?, ?, ?, ?);
                """,
                (conversation_id, role, text, now_str, 1 if has_image else 0),
            )
            conn.execute(
                """
                UPDATE conversations SET updated_at = ? WHERE id = ?;
                """,
                (now_str, conversation_id),
            )
            return int(cur.lastrowid)

    def update_conversation_timestamp(self, conversation_id: int) -> None:
        """Update updated_at to current timestamp."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        with self.connect() as conn:
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?;",
                (now_str, conversation_id),
            )

    def get_conversation(self, conversation_id: int) -> Optional[dict[str, Any]]:
        """Retrieve conversation by ID."""
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT id, title, created_at, updated_at, thumbnail FROM conversations WHERE id = ?;",
                (conversation_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_messages(self, conversation_id: int) -> List[dict[str, Any]]:
        """Retrieve all messages for a conversation in chronological order."""
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT id, conversation_id, role, text, created_at, has_image
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id ASC;
                """,
                (conversation_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def get_last_messages(self, conversation_id: int, limit: int = 20) -> List[dict[str, Any]]:
        """Retrieve up to the last `limit` messages in chronological order."""
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT id, conversation_id, role, text, created_at, has_image
                FROM (
                    SELECT id, conversation_id, role, text, created_at, has_image
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id ASC;
                """,
                (conversation_id, limit),
            )
            return [dict(r) for r in cur.fetchall()]

    def list_conversations(self, query: Optional[str] = None) -> List[dict[str, Any]]:
        """List conversations ordered by updated_at DESC, optionally filtered by message text."""
        with self.connect() as conn:
            if query and query.strip():
                pattern = f"%{query.strip()}%"
                cur = conn.execute(
                    """
                    SELECT DISTINCT c.id, c.title, c.created_at, c.updated_at, c.thumbnail
                    FROM conversations c
                    JOIN messages m ON c.id = m.conversation_id
                    WHERE m.text LIKE ?
                    ORDER BY c.updated_at DESC, c.id DESC;
                    """,
                    (pattern,),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT id, title, created_at, updated_at, thumbnail
                    FROM conversations
                    ORDER BY updated_at DESC, id DESC;
                    """
                )
            return [dict(r) for r in cur.fetchall()]

    def search_conversations(self, query: str) -> List[dict[str, Any]]:
        """Search conversations containing query in message text."""
        return self.list_conversations(query=query)

    def delete_conversation(self, conversation_id: int) -> bool:
        """Delete a conversation and its messages."""
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM conversations WHERE id = ?;",
                (conversation_id,),
            )
            return cur.rowcount > 0

    def clear_all(self) -> bool:
        """Delete all conversations and messages, and vacuum database."""
        with self.connect() as conn:
            conn.execute("DELETE FROM messages;")
            conn.execute("DELETE FROM conversations;")
        conn_vacuum = sqlite3.connect(str(self.db_path), timeout=10.0)
        try:
            conn_vacuum.isolation_level = None
            conn_vacuum.execute("VACUUM;")
        finally:
            conn_vacuum.close()
        logger.info("Cleared all conversations and vacuumed history database.")
        return True

    def export_markdown(self, conversation_id: int) -> str:
        """Export conversation transcript as standard Markdown."""
        conv = self.get_conversation(conversation_id)
        if not conv:
            return ""

        messages = self.get_messages(conversation_id)
        lines = [
            f"# {conv['title']}",
            f"*Date: {conv['created_at']}*",
            "",
            "---",
            "",
        ]

        for msg in messages:
            role = "You" if msg["role"] == "user" else "Peachy"
            lines.append(f"### {role}")
            lines.append("")
            lines.append(msg["text"].strip())
            lines.append("")

        return "\n".join(lines)
