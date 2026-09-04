"""Append-only deliberation journal."""

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

JOURNAL_DIR = Path.home() / ".config" / "magi"
JOURNAL_PATH = JOURNAL_DIR / "journal.jsonl"


def _ensure_dir() -> None:
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    actual_mode = JOURNAL_DIR.stat().st_mode & 0o777
    if actual_mode & 0o077:
        os.chmod(JOURNAL_DIR, 0o700)


def cleanup_stale_temps() -> int:
    """Remove .tmp files older than 60s left by interrupted writes. Returns count removed."""
    import time
    removed = 0
    if not JOURNAL_DIR.exists():
        return 0
    cutoff = time.time() - 60
    for f in JOURNAL_DIR.glob("*.tmp"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def _safe_path(path: Path) -> Path:
    """Reject symlinks and paths outside the config dir."""
    if path.is_symlink():
        raise OSError(f"refusing to follow symlink at {path}")
    resolved = path.resolve()
    if not str(resolved).startswith(str(JOURNAL_DIR.resolve())):
        raise OSError(f"journal path escapes config directory: {resolved}")
    return resolved


def _verify_file_permissions(path: Path) -> None:
    if not path.exists():
        return
    actual_mode = path.stat().st_mode & 0o777
    if actual_mode & 0o077:
        os.chmod(path, 0o600)


def save_entry(
    question: str,
    members: list[str],
    rounds: int,
    outcome: str,
    synthesis: str,
    final_verdicts: dict[str, str],
    thread: str | None = None,
    turn: int = 1,
    mode: str | None = None,
    options: list[str] | None = None,
    decision: str = "",
    positions: dict[str, dict] | None = None,
) -> str:
    """Append a deliberation to the journal. Returns the entry's short id.

    `thread` groups the turns of one conversation; `positions` keeps each
    member's full final response so the thread can be shown again and
    resumed. Older entries have neither and count as one-turn threads.
    """
    _ensure_dir()
    entry_id = uuid.uuid4().hex[:8]
    entry = {
        "id": entry_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "members": members,
        "rounds": rounds,
        "outcome": outcome,
        "synthesis": synthesis,
        "final_verdicts": final_verdicts,
        "user_outcome": None,
        "thread": thread or entry_id,
        "turn": turn,
        "mode": mode,
        "options": list(options or []),
        "decision": decision,
        "positions": positions or {},
    }
    safe = _safe_path(JOURNAL_PATH)
    fd = os.open(str(safe), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, (json.dumps(entry) + "\n").encode())
    finally:
        os.close(fd)
    return entry_id


def load_entries(limit: int | None = None) -> list[dict]:
    """Return entries newest first. None limit returns all."""
    if not JOURNAL_PATH.exists():
        return []
    safe = _safe_path(JOURNAL_PATH)
    _verify_file_permissions(safe)
    entries = []
    with safe.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    entries.reverse()
    if limit and limit > 0:
        entries = entries[:limit]
    return entries


def new_thread_id() -> str:
    return uuid.uuid4().hex[:8]


def load_thread(thread_id: str) -> list[dict]:
    """Every turn of one conversation, oldest first."""
    turns = [e for e in load_entries() if e.get("thread", e["id"]) == thread_id]
    turns.reverse()
    return turns


def find_entry(id_prefix: str) -> dict | None:
    """Find the first entry whose id starts with id_prefix."""
    for entry in load_entries():
        if entry["id"].startswith(id_prefix):
            return entry
    return None


def set_user_outcome(id_prefix: str, outcome_text: str) -> bool:
    """Set user outcome on a journal entry. Returns True if matched."""
    if not JOURNAL_PATH.exists():
        return False
    safe = _safe_path(JOURNAL_PATH)
    entries = []
    matched = False
    with safe.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not matched and entry.get("id", "").startswith(id_prefix):
                entry["user_outcome"] = outcome_text
                matched = True
            entries.append(entry)
    if matched:
        fd, tmp_path = tempfile.mkstemp(dir=str(JOURNAL_DIR), suffix=".tmp")
        f = None
        try:
            f = os.fdopen(fd, "w")
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
            f.close()
            os.replace(tmp_path, str(safe))
        except BaseException:
            if f is not None:
                f.close()
            else:
                os.close(fd)
            os.unlink(tmp_path)
            raise
    return matched
