# SPDX-License-Identifier: GPL-3.0-or-later
"""Local records and path boundaries. The workspace must be private to its owner."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import sqlite3
import tempfile

from .schema import State, now, task_id, transition


def safe_path(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative or "\x00" in relative:
        raise ValueError("Invalid relative path")
    p = PurePosixPath(relative)
    if p.is_absolute() or PureWindowsPath(relative).drive or any(v in ("", ".", "..") for v in relative.split("/")):
        raise ValueError("Path must be a clean relative path")
    root = Path(root).resolve()
    candidate = root.joinpath(*p.parts)
    current = root
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symlinks are not allowed")
    if not candidate.resolve().is_relative_to(root):
        raise ValueError("Path escapes configured root")
    return candidate


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    """Atomic publication within an already authorized directory."""
    path = Path(path)
    content = json.dumps(value, indent=2, allow_nan=False) + "\n"
    fd, temp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class OwnerLock:
    """OS advisory lock, released on process death; no stale PID signalling."""
    def __init__(self, path):
        self.file = open(path, "a+b")
        self.file.write(b"0")
        self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("A mission service already owns this workspace") from None

    def close(self):
        self.file.close()


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = safe_path(self.root, "missions.sqlite3")
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, record TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY, task_id TEXT,
                    timestamp TEXT, event TEXT, attempt INTEGER);
            """)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db, timeout=10)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def folder(self, identity):
        return safe_path(self.root, task_id(identity))

    def get(self, identity):
        with self.connect() as conn:
            row = conn.execute("SELECT record FROM tasks WHERE id=?", (task_id(identity),)).fetchone()
        if row is None:
            raise ValueError("Task not found")
        return json.loads(row[0])

    def all(self):
        with self.connect() as conn:
            return [json.loads(row[0]) for row in conn.execute("SELECT record FROM tasks ORDER BY rowid")]

    def create(self, record):
        with self.connect() as conn:
            conn.execute("INSERT INTO tasks VALUES (?,?)", (record["id"], json.dumps(record, allow_nan=False)))
            conn.execute("INSERT INTO events(task_id,timestamp,event,attempt) VALUES (?,?,?,?)",
                         (record["id"], now(), "queued", 0))

    def update(self, identity, *, state=None, **changes):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT record FROM tasks WHERE id=?", (task_id(identity),)).fetchone()
            if row is None:
                raise ValueError("Task not found")
            record = json.loads(row[0])
            if state is not None:
                transition(record["state"], state)
                record["state"] = State(state).value
            record.update(changes, updated_at=now())
            conn.execute("UPDATE tasks SET record=? WHERE id=?", (json.dumps(record, allow_nan=False), identity))
            conn.execute("INSERT INTO events(task_id,timestamp,event,attempt) VALUES (?,?,?,?)",
                         (identity, now(), State(state).value if state else "attempt", record["attempts"]))
        return record

    def events(self, identity):
        self.get(identity)
        with self.connect() as conn:
            return [dict(zip(("timestamp", "event", "attempt"), row)) for row in conn.execute(
                "SELECT timestamp,event,attempt FROM events WHERE task_id=? ORDER BY sequence", (identity,))]
