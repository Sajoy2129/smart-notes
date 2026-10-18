"""SQLite storage for Smart Notes.

Every function takes the database file path, so tests can use a
temporary database instead of the real one.
"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime

DEFAULT_DB_PATH = "smart_notes.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    body         TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    summary      TEXT,
    action_items TEXT,
    tags         TEXT
)
"""


def _connect(db_path):
    """Open a connection whose rows can be read like dicts (row["title"])."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_note(row):
    """Turn a database row into a plain dict, decoding the JSON columns."""
    note = dict(row)
    note["action_items"] = json.loads(note["action_items"] or "[]")
    note["tags"] = json.loads(note["tags"] or "[]")
    return note


def init_db(db_path=DEFAULT_DB_PATH):
    """Create the notes table if it doesn't exist yet."""
    with closing(_connect(db_path)) as conn, conn:
        conn.execute(SCHEMA)


def create_note(db_path, title, body, summary=None, action_items=None, tags=None):
    """Save a new note and return its id.

    summary is None when the AI step failed or hasn't run.
    """
    created_at = datetime.now().isoformat(timespec="seconds")
    with closing(_connect(db_path)) as conn, conn:
        cursor = conn.execute(
            "INSERT INTO notes (title, body, created_at, summary, action_items, tags) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                title,
                body,
                created_at,
                summary,
                json.dumps(action_items or []),
                json.dumps(tags or []),
            ),
        )
        return cursor.lastrowid


def save_analysis(db_path, note_id, summary, action_items, tags):
    """Store the AI results on an existing note."""
    with closing(_connect(db_path)) as conn, conn:
        conn.execute(
            "UPDATE notes SET summary = ?, action_items = ?, tags = ? WHERE id = ?",
            (summary, json.dumps(action_items), json.dumps(tags), note_id),
        )


def get_note(db_path, note_id):
    """Return one note as a dict, or None if there is no note with that id."""
    with closing(_connect(db_path)) as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    return _row_to_note(row) if row else None


def delete_note(db_path, note_id):
    """Delete a note. Return True if it existed, False if there was nothing to delete."""
    with closing(_connect(db_path)) as conn, conn:
        cursor = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        return cursor.rowcount > 0


def list_notes(db_path):
    """Return all notes, newest first."""
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT * FROM notes ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [_row_to_note(row) for row in rows]
