"""SQLite storage for Smart Notes.

Every function takes the database file path, so tests can use a
temporary database instead of the real one.
"""

import json
import sqlite3
from contextlib import closing
from datetime import date, datetime

DEFAULT_DB_PATH = "smart_notes.db"

GENERAL_PROJECT = "General"  # where notes from before projects existed are put

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,  -- '' for notes written inside a project
    body         TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    summary      TEXT,
    action_items TEXT,
    tags         TEXT,
    project_id   INTEGER REFERENCES projects(id),
    completed_at TEXT  -- NULL while the note is open
);

-- How many AI jobs (note analyses or answers) ran each day, for the daily limit.
CREATE TABLE IF NOT EXISTS ai_usage (
    day  TEXT PRIMARY KEY,  -- e.g. '2026-10-20'
    jobs INTEGER NOT NULL
);
"""

# Columns added after version 1. Old databases get them through ALTER TABLE.
NEW_NOTE_COLUMNS = {
    "project_id": "INTEGER REFERENCES projects(id)",
    "completed_at": "TEXT",
}


def _now():
    return datetime.now().isoformat(timespec="seconds")


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
    """Create the tables if needed, and upgrade a database from before projects.

    Safe to run every time the app starts: each step only does something
    when it's still needed.
    """
    with closing(_connect(db_path)) as conn, conn:
        conn.executescript(SCHEMA)
        _add_missing_columns(conn)
        _move_loose_notes_to_general(conn)


def _add_missing_columns(conn):
    """An old notes table was created without the newer columns: add them."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(notes)")}
    for name, column_type in NEW_NOTE_COLUMNS.items():
        if name not in existing:
            # Names come from our own NEW_NOTE_COLUMNS, never from user input.
            conn.execute(f"ALTER TABLE notes ADD COLUMN {name} {column_type}")


def _move_loose_notes_to_general(conn):
    """Notes without a project (from before projects existed) go into "General"."""
    if conn.execute("SELECT 1 FROM notes WHERE project_id IS NULL LIMIT 1").fetchone() is None:
        return
    row = conn.execute("SELECT id FROM projects WHERE name = ?", (GENERAL_PROJECT,)).fetchone()
    if row:
        project_id = row["id"]
    else:
        project_id = conn.execute(
            "INSERT INTO projects (name, created_at) VALUES (?, ?)", (GENERAL_PROJECT, _now())
        ).lastrowid
    conn.execute("UPDATE notes SET project_id = ? WHERE project_id IS NULL", (project_id,))


def create_note(
    db_path, title, body, summary=None, action_items=None, tags=None, project_id=None
):
    """Save a new note and return its id.

    summary is None when the AI step failed or hasn't run.
    """
    with closing(_connect(db_path)) as conn, conn:
        cursor = conn.execute(
            "INSERT INTO notes "
            "(title, body, created_at, summary, action_items, tags, project_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                title,
                body,
                _now(),
                summary,
                json.dumps(action_items or []),
                json.dumps(tags or []),
                project_id,
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


def complete_note(db_path, note_id):
    """Mark a note as done. It stays in the database but leaves its project's list.

    Return True if the note exists, False otherwise.
    """
    with closing(_connect(db_path)) as conn, conn:
        cursor = conn.execute(
            "UPDATE notes SET completed_at = ? WHERE id = ?", (_now(), note_id)
        )
        return cursor.rowcount > 0


def list_project_notes(db_path, project_id):
    """Return a project's open (not completed) notes, newest first."""
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT * FROM notes WHERE project_id = ? AND completed_at IS NULL "
            "ORDER BY created_at DESC, id DESC",
            (project_id,),
        ).fetchall()
    return [_row_to_note(row) for row in rows]


# ---------- Projects ----------

def create_project(db_path, name):
    """Save a new project and return its id."""
    with closing(_connect(db_path)) as conn, conn:
        cursor = conn.execute(
            "INSERT INTO projects (name, created_at) VALUES (?, ?)", (name, _now())
        )
        return cursor.lastrowid


def get_project(db_path, project_id):
    """Return one project as a dict, or None if it doesn't exist."""
    with closing(_connect(db_path)) as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return dict(row) if row else None


def list_projects(db_path):
    """Return all projects A-Z, each with open_count: how many open notes it has."""
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT projects.*, COUNT(notes.id) AS open_count "
            "FROM projects "
            "LEFT JOIN notes ON notes.project_id = projects.id AND notes.completed_at IS NULL "
            "GROUP BY projects.id "
            "ORDER BY projects.name COLLATE NOCASE"
        ).fetchall()
    return [dict(row) for row in rows]


def list_open_notes(db_path):
    """Return open notes from every project, newest first, each with project_name."""
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT notes.*, projects.name AS project_name "
            "FROM notes LEFT JOIN projects ON projects.id = notes.project_id "
            "WHERE notes.completed_at IS NULL "
            "ORDER BY notes.created_at DESC, notes.id DESC"
        ).fetchall()
    return [_row_to_note(row) for row in rows]


# ---------- Daily AI limit ----------

def use_ai_job(db_path, limit, day=None):
    """Count one AI job for today. Return False, counting nothing, if the limit is reached.

    It's one SQL statement, so two requests at the same moment can't both slip under
    the limit. "Upsert": insert today's row with 1 job, or, if the row already exists,
    add 1, but only while jobs < limit. Tests pass in day to check a new day resets.
    """
    day = day or date.today().isoformat()
    with closing(_connect(db_path)) as conn, conn:
        cursor = conn.execute(
            "INSERT INTO ai_usage (day, jobs) SELECT ?, 1 WHERE ? > 0 "
            "ON CONFLICT(day) DO UPDATE SET jobs = jobs + 1 WHERE jobs < ?",
            (day, limit, limit),
        )
        return cursor.rowcount == 1  # 0 rows changed means the limit was reached


def ai_jobs_used(db_path, day=None):
    """How many AI jobs have run on a day (today by default)."""
    day = day or date.today().isoformat()
    with closing(_connect(db_path)) as conn:
        row = conn.execute("SELECT jobs FROM ai_usage WHERE day = ?", (day,)).fetchone()
    return row["jobs"] if row else 0
