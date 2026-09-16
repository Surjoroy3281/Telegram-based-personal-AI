"""
Tiny SQLite wrapper for storing reminders.
No server needed - it's just a single .db file on disk.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

DB_PATH = "assistant.db"


def init_db(db_path: str = DB_PATH) -> None:
    global DB_PATH
    DB_PATH = db_path
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                remind_at TEXT NOT NULL,   -- ISO format datetime, stored in UTC
                fired INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,        -- "user" or "assistant"
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_activity (
                chat_id INTEGER PRIMARY KEY,
                last_message_at TEXT NOT NULL,
                last_checkin_at TEXT
            )
            """
        )
        conn.commit()


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def add_reminder(chat_id: int, text: str, remind_at: datetime) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO reminders (chat_id, text, remind_at, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, text, remind_at.isoformat(), datetime.utcnow().isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def mark_fired(reminder_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE reminders SET fired = 1 WHERE id = ?", (reminder_id,))
        conn.commit()


def delete_reminder(reminder_id: int, chat_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM reminders WHERE id = ? AND chat_id = ?", (reminder_id, chat_id)
        )
        conn.commit()
        return cur.rowcount > 0


def delete_all_pending_reminders(chat_id: int) -> list[int]:
    """Deletes every not-yet-fired reminder for a chat. Returns the ids that
    were deleted, so the caller can also cancel their scheduled jobs."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id FROM reminders WHERE chat_id = ? AND fired = 0", (chat_id,)
        ).fetchall()
        ids = [r["id"] for r in rows]
        conn.execute("DELETE FROM reminders WHERE chat_id = ? AND fired = 0", (chat_id,))
        conn.commit()
        return ids


def add_message(chat_id: int, role: str, content: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO conversations (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, role, content, datetime.utcnow().isoformat()),
        )
        conn.commit()


def get_recent_messages(chat_id: int, limit: int = 24) -> list[dict]:
    """Returns the last `limit` messages for a chat, oldest first, in the
    {"role": ..., "content": ...} shape the AI backend expects."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content FROM conversations WHERE chat_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def clear_conversation(chat_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM conversations WHERE chat_id = ?", (chat_id,))
        conn.commit()


def get_legacy_memories() -> dict[int, list[str]]:
    """One-time migration helper: the `memories` table was the storage
    before memory moved to plain-text notepad files (see memory_notepad.py).
    Groups any old rows by chat_id so bot.py can migrate them once on
    startup. Safe to call repeatedly - the table stays but is otherwise
    unused now."""
    with _connect() as conn:
        rows = conn.execute("SELECT chat_id, text FROM memories ORDER BY chat_id, id").fetchall()
    grouped: dict[int, list[str]] = {}
    for r in rows:
        grouped.setdefault(r["chat_id"], []).append(r["text"])
    return grouped


def touch_activity(chat_id: int) -> None:
    """Records 'the user just interacted' - call this on any incoming
    message/command. Kept separate from the conversations table so /reset
    (which clears conversation history) doesn't accidentally erase the
    activity timestamp and falsely trigger a check-in."""
    # Timezone-aware, unlike the other created_at fields in this file - this
    # one gets subtracted against an aware "now" in should_send_checkin, so
    # a naive timestamp here would crash that comparison.
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO chat_activity (chat_id, last_message_at, last_checkin_at)
            VALUES (?, ?, NULL)
            ON CONFLICT(chat_id) DO UPDATE SET last_message_at = excluded.last_message_at
            """,
            (chat_id, now),
        )
        conn.commit()


def get_all_chat_activity() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM chat_activity").fetchall()
        return [dict(r) for r in rows]


def set_last_checkin(chat_id: int, when: datetime) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE chat_activity SET last_checkin_at = ? WHERE chat_id = ?",
            (when.isoformat(), chat_id),
        )
        conn.commit()


def get_pending_reminders(chat_id: Optional[int] = None):
    """Reminders that haven't fired yet. Used both for /list and for
    rescheduling on bot restart."""
    with _connect() as conn:
        if chat_id is not None:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE fired = 0 AND chat_id = ? ORDER BY remind_at",
                (chat_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE fired = 0 ORDER BY remind_at"
            ).fetchall()
        return [dict(r) for r in rows]
