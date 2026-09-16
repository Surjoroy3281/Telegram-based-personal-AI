"""
Plain-text "notepad" memory storage - one remembered fact per line, kept as
a plain .txt file per chat under memories/. Open it in any text editor to
see (or hand-edit) exactly what the bot remembers - no database, no ids to
track. The AI manages entries by matching their actual text via its
remember/forget tools (see ai_brain.py), and /memories, /forget, /forgetall
give you the same thing manually if you'd rather not do it conversationally.
"""
import os

MEMORY_DIR = "memories"


def _path(chat_id: int) -> str:
    os.makedirs(MEMORY_DIR, exist_ok=True)
    return os.path.join(MEMORY_DIR, f"{chat_id}.txt")


def read_all(chat_id: int) -> list[str]:
    path = _path(chat_id)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def append(chat_id: int, fact: str) -> bool:
    """Adds a fact as a new line. Returns False (and skips writing) if it's
    an exact duplicate of an existing line, case-insensitive."""
    fact = fact.strip()
    if not fact:
        return False
    existing = read_all(chat_id)
    if any(e.lower() == fact.lower() for e in existing):
        return False
    with open(_path(chat_id), "a", encoding="utf-8") as f:
        f.write(fact + "\n")
    return True


def remove_matching(chat_id: int, text: str) -> list[str]:
    """Removes every line containing `text` (case-insensitive substring) -
    forgiving on purpose, so "forget about peanuts" matches a line like
    "allergic to peanuts" without needing an exact quote. Returns the lines
    that were removed."""
    text = text.strip().lower()
    if not text:
        return []
    existing = read_all(chat_id)
    removed = [line for line in existing if text in line.lower()]
    if removed:
        remaining = [line for line in existing if text not in line.lower()]
        _write_all(chat_id, remaining)
    return removed


def clear(chat_id: int) -> int:
    existing = read_all(chat_id)
    _write_all(chat_id, [])
    return len(existing)


def _write_all(chat_id: int, lines: list[str]) -> None:
    with open(_path(chat_id), "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
