"""Tests for deploy/backup.sh, the nightly database backup on the server.

They run the real script on a temporary database, so they need the sqlite3
command (built into macOS; installed on the server in deploy/README.md).
"""

import os
import shutil
import sqlite3
import subprocess
import time
from datetime import date
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "deploy" / "backup.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("sqlite3") is None, reason="needs the sqlite3 command"
)


def run_backup(db_file, backup_dir):
    subprocess.run([str(SCRIPT), str(db_file), str(backup_dir)], check=True)


def make_database(path):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE notes (body TEXT)")
        conn.execute("INSERT INTO notes VALUES ('Rang the client.')")
    conn.close()


def set_age_in_days(path, days):
    """Change a file's last-modified time to `days` days ago."""
    then = time.time() - days * 24 * 60 * 60
    os.utime(path, (then, then))


def test_backup_copies_the_notes(tmp_path):
    db_file = tmp_path / "smart_notes.db"
    make_database(db_file)
    backup_dir = tmp_path / "backups"

    run_backup(db_file, backup_dir)

    backup = backup_dir / f"smart_notes-{date.today().isoformat()}.db"
    conn = sqlite3.connect(backup)
    assert conn.execute("SELECT body FROM notes").fetchall() == [("Rang the client.",)]
    conn.close()


def test_backups_older_than_14_days_are_deleted(tmp_path):
    db_file = tmp_path / "smart_notes.db"
    make_database(db_file)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    old = backup_dir / "smart_notes-2026-01-01.db"
    recent = backup_dir / "smart_notes-2026-01-20.db"
    old.write_text("old")
    recent.write_text("recent")
    set_age_in_days(old, 20)
    set_age_in_days(recent, 3)

    run_backup(db_file, backup_dir)

    assert not old.exists()
    assert recent.exists()
