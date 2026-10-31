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
import threading
import time
from typing import Any, Callable, Generator, List, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

CREATE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    thumbnail BLOB,
    pinned INTEGER NOT NULL DEFAULT 0,
    title_locked INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'overlay'
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    has_image INTEGER NOT NULL DEFAULT 0,
    model TEXT,
    status TEXT NOT NULL DEFAULT 'complete',
    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    mime TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    data BLOB,
    thumb BLOB NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_attachments_message ON attachments(message_id);
CREATE INDEX IF NOT EXISTS idx_conversations_pinned ON conversations(pinned DESC, updated_at DESC);
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


def create_attachment_thumbnail(image_data: Any, max_dim: int = 256) -> bytes:
    """Generate a 256 px PNG thumbnail for attachments.

    Always kept so the transcript can still show a visual preview even when
    full screenshot persistence is turned off.
    Returns PNG bytes.
    """
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
        raise ValueError("Invalid image_data provided for attachment thumbnail.")

    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")

    w, h = img.size
    if w > 0 and h > 0:
        if max(w, h) > max_dim:
            if w >= h:
                target_w = max_dim
                target_h = max(1, int(round(h * (target_w / float(w)))))
            else:
                target_h = max_dim
                target_w = max(1, int(round(w * (target_h / float(h)))))
            img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


_RECOVERY_LOCK = threading.RLock()


class HistoryStore:
    """Manages SQLite storage for conversations and messages with safe corruption recovery."""

    def __init__(
        self,
        db_path: Optional[Path | str] = None,
        on_fallback: Optional[Callable[[str], None]] = None,
    ):
        self.db_path = Path(db_path) if db_path is not None else get_default_history_db_path()
        self.original_db_path = self.db_path
        self._is_fallback: bool = False
        self._fallback_reason: Optional[str] = None
        self.on_fallback = on_fallback

        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as dir_err:
            logger.warning("Could not create history directory for %s: %s", self.db_path, dir_err)
        self._init_db()

    @property
    def is_fallback(self) -> bool:
        """True if store could not access permanent storage and is operating in a temporary session."""
        return self._is_fallback

    @property
    def fallback_reason(self) -> Optional[str]:
        """Diagnostic explanation if operating in non-persistent temporary fallback mode."""
        return self._fallback_reason

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

    def _is_valid_sqlite_header(self) -> bool:
        """Check if existing non-empty db_path has standard SQLite format 3 header.

        If a file exists but is not an SQLite database (e.g. invalid header),
        calling sqlite3.connect() causes SQLite to automatically unlink any
        companion -wal and -shm files during close, destroying uncheckpointed data.
        """
        if not self.db_path.exists():
            return True
        try:
            if self.db_path.stat().st_size == 0:
                return True
            with open(self.db_path, "rb") as f:
                header = f.read(16)
            return header == b"SQLite format 3\x00"
        except Exception:
            return False

    def _init_db(self) -> None:
        """Initialize database schema, backing up and recovering if corrupt or inaccessible."""
        if not self._is_valid_sqlite_header():
            with _RECOVERY_LOCK:
                # Double-checked locking: check if another thread recovered the database while waiting
                if self._is_valid_sqlite_header():
                    try:
                        self._ensure_schema()
                        return
                    except sqlite3.DatabaseError:
                        pass

                logger.warning(
                    "History database at %s has invalid header (not an SQLite database). Initiating synchronized recovery.",
                    self.db_path,
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
                self._activate_temporary_fallback(
                    reason=f"Recovery failed or invalid database at {self.original_db_path} could not be recreated"
                )
                return

        try:
            self._ensure_schema()
            return
        except sqlite3.DatabaseError as exc:
            with _RECOVERY_LOCK:
                # Double-checked locking: check if another thread recovered the database while waiting
                try:
                    self._ensure_schema()
                    return
                except sqlite3.DatabaseError:
                    pass

                logger.warning(
                    "History database at %s corrupt or inaccessible (%s). Initiating synchronized recovery.",
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

                # ONLY reach fallback if original path is genuinely unusable or recovery failed
                self._activate_temporary_fallback(
                    reason=f"Recovery failed or original path {self.original_db_path} is inaccessible ({exc})"
                )

    def _activate_temporary_fallback(self, reason: str) -> None:
        """Switch storage session to temporary fallback database without deleting user files."""
        self._is_fallback = True
        self._fallback_reason = reason

        fallback_dir = Path(tempfile.gettempdir()) / "peachy_history"
        try:
            fallback_dir.mkdir(parents=True, exist_ok=True)
            fallback_db = fallback_dir / f"fallback_{os.getpid()}_{self.original_db_path.name}"
            logger.error(
                "STORAGE DEGRADED: HistoryStore cannot access permanent database at %s. "
                "Reason: %s. "
                "Operating in temporary session mode at %s. "
                "WARNING: Chat history in this session will NOT persist across app restarts.",
                self.original_db_path,
                reason,
                fallback_db,
            )
            self.db_path = fallback_db
            self._ensure_schema()

            if self.on_fallback:
                try:
                    self.on_fallback(self._fallback_reason)
                except Exception as cb_err:
                    logger.warning("Error in on_fallback notification callback: %s", cb_err)
        except Exception as fb_err:
            logger.critical("Fatal: failed to initialize fallback history database at %s: %s", fallback_dir, fb_err)
            raise

    def _ensure_schema(self) -> None:
        """Execute table creation and schema version verification / migration."""
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version';"
            )
            has_schema_ver = cur.fetchone() is not None

            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='conversations';"
            )
            has_conversations = cur.fetchone() is not None

            current_ver: Optional[int] = None
            if has_schema_ver:
                cur = conn.execute("SELECT version FROM schema_version LIMIT 1;")
                row = cur.fetchone()
                if row is not None:
                    current_ver = int(row[0])

            if not has_conversations:
                # Brand new DB: create schema v2 from scratch
                conn.executescript(CREATE_SCHEMA_SQL)
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?);", (SCHEMA_VERSION,)
                )
                return

            if current_ver is None:
                current_ver = 1

        if current_ver < SCHEMA_VERSION:
            self._migrate_v1_to_v2()

    def _migrate_v1_to_v2(self) -> None:
        """Migrate database from schema v1 to schema v2 in a single transaction after backup."""
        # 1. Back up database before running migration
        try:
            with sqlite3.connect(str(self.db_path), timeout=10.0) as cp_conn:
                cp_conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        except Exception as cp_err:
            logger.debug("WAL checkpoint prior to migration backup: %s", cp_err)

        if self.db_path.name == "history.db":
            bak_path = self.db_path.with_name("history.v1.bak")
        else:
            bak_path = self.db_path.with_name(f"{self.db_path.stem}.v1.bak")

        try:
            if bak_path.exists():
                try:
                    bak_path.unlink()
                except OSError:
                    pass
            shutil.copy2(self.db_path, bak_path)
            logger.info("Created pre-migration backup: %s -> %s", self.db_path, bak_path)
        except Exception as bak_err:
            logger.error("Failed to create pre-migration backup %s: %s. Skipping migration to protect user data.", bak_path, bak_err)
            return

        # 2. Run migration in one transaction
        with self.connect() as conn:
            # Idempotently add missing columns to conversations
            cur = conn.execute("PRAGMA table_info(conversations);")
            conv_cols = {r["name"] for r in cur.fetchall()}

            if "pinned" not in conv_cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;")
            if "title_locked" not in conv_cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN title_locked INTEGER NOT NULL DEFAULT 0;")
            if "source" not in conv_cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN source TEXT NOT NULL DEFAULT 'overlay';")

            # Idempotently add missing columns to messages
            cur = conn.execute("PRAGMA table_info(messages);")
            msg_cols = {r["name"] for r in cur.fetchall()}

            if "model" not in msg_cols:
                conn.execute("ALTER TABLE messages ADD COLUMN model TEXT;")
            if "status" not in msg_cols:
                conn.execute("ALTER TABLE messages ADD COLUMN status TEXT NOT NULL DEFAULT 'complete';")

            # Create attachments table and indexes
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS attachments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                    mime TEXT NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    data BLOB,
                    thumb BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_attachments_message ON attachments(message_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_pinned ON conversations(pinned DESC, updated_at DESC);")

            # Update schema_version
            conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);")
            conn.execute("DELETE FROM schema_version;")
            conn.execute("INSERT INTO schema_version (version) VALUES (?);", (SCHEMA_VERSION,))

        logger.info("Successfully migrated database at %s to schema version 2.", self.db_path)

    def _recover_corrupt_db(self) -> bool:
        """Back up corrupt database and all WAL/SHM artifacts, then remove originals.

        Strict recovery requirements:
        - The original database file must be backed up to .bak.
        - Any existing companion files (-wal, -shm) must be backed up to .bak.
        - The original database file must be successfully unlinked.
        - Any existing companion files must be successfully unlinked.
        - All unlinked files must be verified absent from disk.
        - If ANY operation fails, no original files are left partially removed and False is returned.

        Returns:
            True only when all artifacts have been backed up and completely removed so
            the original path can be safely recreated.
            False if backup, unlinking, or verification fails.
        """
        if not self.db_path.exists():
            return False

        files_to_backup = [self.db_path]
        for ext in ("-wal", "-shm"):
            comp = self.db_path.with_name(self.db_path.name + ext)
            if comp.exists():
                files_to_backup.append(comp)

        # 1. Back up all existing database files and companions
        backed_up_pairs = []
        try:
            for src_file in files_to_backup:
                dst_bak = self.db_path.with_name(src_file.name + ".bak")
                if dst_bak.exists():
                    try:
                        dst_bak.unlink()
                    except OSError as unl_bak_err:
                        logger.warning("Could not remove existing backup %s: %s", dst_bak, unl_bak_err)
                        return False

                shutil.copy2(src_file, dst_bak)
                backed_up_pairs.append((src_file, dst_bak))
                logger.info("Database artifact successfully backed up: %s -> %s", src_file, dst_bak)
        except Exception as copy_err:
            logger.error("Failed during backup of database artifact %s: %s. Aborting recovery.", src_file, copy_err)
            return False

        # 2. Strict removal and verification of all original files
        for src_file in files_to_backup:
            unlinked = False
            last_err = None
            for _attempt in range(5):
                try:
                    src_file.unlink()
                    unlinked = True
                    break
                except OSError as unl_err:
                    last_err = unl_err
                    time.sleep(0.05)

            if not unlinked:
                logger.error("Failed to remove database artifact %s: %s. Aborting recovery.", src_file, last_err)
                return False

            if src_file.exists():
                logger.error("Database artifact %s still exists after unlink. Aborting recovery.", src_file)
                return False

        logger.info(
            "All corrupt database artifacts (%d files) successfully backed up and removed from %s.",
            len(files_to_backup),
            self.db_path,
        )
        return True

    def save_exchange(
        self,
        conv_id: Optional[int],
        question: str,
        answer: str,
        has_image: bool = False,
        title: Optional[str] = None,
        thumbnail: Optional[bytes] = None,
        model: Optional[str] = None,
        status: str = "complete",
        source: str = "overlay",
    ) -> int:
        """Atomically persist a user question and model answer exchange in a single transaction.

        If conv_id is None, creates a new conversation with title (generating one if omitted)
        and optional thumbnail, then appends both the user question and model answer.
        If conv_id is provided, appends the user question and model answer, and updates the
        conversation's updated_at timestamp.

        Returns:
            The conversation ID (newly created or existing).
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        with self.connect() as conn:
            if conv_id is None:
                conv_title = title or generate_title(question, answer)
                cur = conn.execute(
                    """
                    INSERT INTO conversations (title, created_at, updated_at, thumbnail, source)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (conv_title, now_str, now_str, thumbnail, source),
                )
                target_conv_id = int(cur.lastrowid)
            else:
                target_conv_id = conv_id
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?;",
                    (now_str, target_conv_id),
                )

            # Insert user question
            conn.execute(
                """
                INSERT INTO messages (conversation_id, role, text, created_at, has_image, status)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (target_conv_id, "user", question, now_str, 1 if has_image else 0, "complete"),
            )

            # Insert model answer
            conn.execute(
                """
                INSERT INTO messages (conversation_id, role, text, created_at, has_image, model, status)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (target_conv_id, "model", answer, now_str, 0, model, status),
            )

            return target_conv_id

    def create_conversation(
        self,
        title: str,
        thumbnail: Optional[bytes] = None,
        source: str = "overlay",
        pinned: bool = False,
    ) -> int:
        """Create a new conversation record. Returns new conversation ID."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO conversations (title, created_at, updated_at, thumbnail, source, pinned)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (title, now_str, now_str, thumbnail, source, 1 if pinned else 0),
            )
            return int(cur.lastrowid)

    def rename_conversation(self, conv_id: int, title: str) -> None:
        """Rename a conversation and lock its title against automatic heuristic updates."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        with self.connect() as conn:
            conn.execute(
                "UPDATE conversations SET title = ?, title_locked = 1, updated_at = ? WHERE id = ?;",
                (title, now_str, conv_id),
            )

    def set_pinned(self, conv_id: int, pinned: bool) -> None:
        """Pin or unpin a conversation."""
        with self.connect() as conn:
            conn.execute(
                "UPDATE conversations SET pinned = ? WHERE id = ?;",
                (1 if pinned else 0, conv_id),
            )

    def add_attachment(
        self,
        message_id: int,
        mime: str,
        data: Optional[bytes],
        thumb: bytes,
        w: Optional[int] = None,
        h: Optional[int] = None,
    ) -> int:
        """Store an attachment (screenshot or image) associated with a message.

        Args:
            message_id: Target message ID.
            mime: MIME type string (e.g. 'image/png').
            data: Full image bytes (or None when screenshot saving is turned off).
            thumb: 256px thumbnail bytes (always persisted).
            w: Width of full image in pixels (optional).
            h: Height of full image in pixels (optional).

        Returns:
            The newly created attachment ID.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO attachments (message_id, mime, width, height, data, thumb, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (message_id, mime, w, h, data, thumb, now_str),
            )
            conn.execute(
                "UPDATE messages SET has_image = 1 WHERE id = ?;",
                (message_id,),
            )
            return int(cur.lastrowid)

    def get_attachment_data(self, attachment_id: int) -> Optional[bytes]:
        """Retrieve full image bytes for an attachment, or None if data was not saved."""
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT data FROM attachments WHERE id = ?;",
                (attachment_id,),
            )
            row = cur.fetchone()
            if row and row["data"] is not None:
                return bytes(row["data"])
            return None

    def delete_messages_from(self, conv_id: int, message_id: int) -> None:
        """Delete messages in conversation with id >= message_id (inclusive).

        Used for edit-and-resend and answer regeneration.
        Cascades to associated attachments.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM messages WHERE conversation_id = ? AND id >= ?;",
                (conv_id, message_id),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?;",
                (now_str, conv_id),
            )

    def add_message(
        self,
        conversation_id: int,
        role: str,
        text: str,
        has_image: bool = False,
        model: Optional[str] = None,
        status: str = "complete",
    ) -> int:
        """Append a message to an existing conversation. Returns message ID."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO messages (conversation_id, role, text, created_at, has_image, model, status)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (conversation_id, role, text, now_str, 1 if has_image else 0, model, status),
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
                """
                SELECT id, title, created_at, updated_at, thumbnail, pinned, title_locked, source
                FROM conversations
                WHERE id = ?;
                """,
                (conversation_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            d = dict(row)
            d["pinned"] = bool(d.get("pinned", 0))
            d["title_locked"] = bool(d.get("title_locked", 0))
            return d

    def get_messages(self, conversation_id: int) -> List[dict[str, Any]]:
        """Retrieve all messages for a conversation in chronological order.

        Returns MessageDicts with attachments metadata (never full image bytes):
        {
            "id": int,
            "conversation_id": int,
            "role": "user" | "model",
            "text": str,
            "created_at": str,
            "has_image": bool,
            "model": Optional[str],
            "status": "complete" | "error" | "stopped",
            "attachments": [
                {"id": int, "mime": str, "thumb": bytes, "has_full": bool}
            ]
        }
        """
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT id, conversation_id, role, text, created_at, has_image, model, status
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id ASC;
                """,
                (conversation_id,),
            )
            rows = cur.fetchall()
            if not rows:
                return []

            msg_ids = [r["id"] for r in rows]
            placeholders = ",".join("?" for _ in msg_ids)
            att_cur = conn.execute(
                f"""
                SELECT id, message_id, mime, thumb, (data IS NOT NULL) AS has_full
                FROM attachments
                WHERE message_id IN ({placeholders})
                ORDER BY id ASC;
                """,
                msg_ids,
            )
            attachments_by_msg: dict[int, list[dict[str, Any]]] = {}
            for ar in att_cur.fetchall():
                m_id = ar["message_id"]
                attachments_by_msg.setdefault(m_id, []).append({
                    "id": ar["id"],
                    "mime": ar["mime"],
                    "thumb": bytes(ar["thumb"]),
                    "has_full": bool(ar["has_full"]),
                })

            result = []
            for r in rows:
                m_id = r["id"]
                result.append({
                    "id": m_id,
                    "conversation_id": r["conversation_id"],
                    "role": r["role"],
                    "text": r["text"],
                    "created_at": r["created_at"],
                    "has_image": bool(r["has_image"]),
                    "model": r["model"],
                    "status": r["status"] if r["status"] is not None else "complete",
                    "attachments": attachments_by_msg.get(m_id, []),
                })
            return result

    def get_last_messages(self, conversation_id: int, limit: int = 20) -> List[dict[str, Any]]:
        """Retrieve up to the last `limit` messages in chronological order with attachments metadata."""
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT id, conversation_id, role, text, created_at, has_image, model, status
                FROM (
                    SELECT id, conversation_id, role, text, created_at, has_image, model, status
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id ASC;
                """,
                (conversation_id, limit),
            )
            rows = cur.fetchall()
            if not rows:
                return []

            msg_ids = [r["id"] for r in rows]
            placeholders = ",".join("?" for _ in msg_ids)
            att_cur = conn.execute(
                f"""
                SELECT id, message_id, mime, thumb, (data IS NOT NULL) AS has_full
                FROM attachments
                WHERE message_id IN ({placeholders})
                ORDER BY id ASC;
                """,
                msg_ids,
            )
            attachments_by_msg: dict[int, list[dict[str, Any]]] = {}
            for ar in att_cur.fetchall():
                m_id = ar["message_id"]
                attachments_by_msg.setdefault(m_id, []).append({
                    "id": ar["id"],
                    "mime": ar["mime"],
                    "thumb": bytes(ar["thumb"]),
                    "has_full": bool(ar["has_full"]),
                })

            result = []
            for r in rows:
                m_id = r["id"]
                result.append({
                    "id": m_id,
                    "conversation_id": r["conversation_id"],
                    "role": r["role"],
                    "text": r["text"],
                    "created_at": r["created_at"],
                    "has_image": bool(r["has_image"]),
                    "model": r["model"],
                    "status": r["status"] if r["status"] is not None else "complete",
                    "attachments": attachments_by_msg.get(m_id, []),
                })
            return result

    def list_conversations(self, query: Optional[str] = None) -> List[dict[str, Any]]:
        """List conversations ordered by pinned DESC, updated_at DESC, id DESC.

        Returns:
            List of dicts with keys: id, title, updated_at, pinned, preview, source
            (and created_at, thumbnail for backwards compatibility).
        """
        with self.connect() as conn:
            if query and query.strip():
                pattern = f"%{query.strip()}%"
                cur = conn.execute(
                    """
                    SELECT 
                        c.id,
                        c.title,
                        c.created_at,
                        c.updated_at,
                        c.thumbnail,
                        c.pinned,
                        c.title_locked,
                        c.source,
                        COALESCE(
                            (SELECT text FROM messages WHERE conversation_id = c.id ORDER BY id DESC LIMIT 1),
                            ''
                        ) AS preview
                    FROM conversations c
                    WHERE c.title LIKE ? OR c.id IN (
                        SELECT conversation_id FROM messages WHERE text LIKE ?
                    )
                    ORDER BY c.pinned DESC, c.updated_at DESC, c.id DESC;
                    """,
                    (pattern, pattern),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT 
                        c.id,
                        c.title,
                        c.created_at,
                        c.updated_at,
                        c.thumbnail,
                        c.pinned,
                        c.title_locked,
                        c.source,
                        COALESCE(
                            (SELECT text FROM messages WHERE conversation_id = c.id ORDER BY id DESC LIMIT 1),
                            ''
                        ) AS preview
                    FROM conversations c
                    ORDER BY c.pinned DESC, c.updated_at DESC, c.id DESC;
                    """
                )

            res = []
            for r in cur.fetchall():
                d = dict(r)
                d["pinned"] = bool(d.get("pinned", 0))
                d["title_locked"] = bool(d.get("title_locked", 0))
                res.append(d)
            return res

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
