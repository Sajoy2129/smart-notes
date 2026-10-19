import sqlite3

import db


def test_create_and_get_note(db_path):
    note_id = db.create_note(
        db_path,
        "Site visit",
        "Checked the walls.",
        summary="Walls checked.",
        action_items=[{"task": "Buy paint", "owner": None, "due_date": None}],
        tags=["painting"],
    )

    note = db.get_note(db_path, note_id)

    assert note["title"] == "Site visit"
    assert note["body"] == "Checked the walls."
    assert note["summary"] == "Walls checked."
    assert note["action_items"][0]["task"] == "Buy paint"
    assert note["tags"] == ["painting"]
    assert note["created_at"]


def test_note_without_ai_parts_gets_empty_lists(db_path):
    note_id = db.create_note(db_path, "Call", "Rang the client.")

    note = db.get_note(db_path, note_id)

    assert note["summary"] is None
    assert note["action_items"] == []
    assert note["tags"] == []


def test_get_missing_note_returns_none(db_path):
    assert db.get_note(db_path, 999) is None


def test_list_notes_newest_first(db_path):
    db.create_note(db_path, "First", "a")
    db.create_note(db_path, "Second", "b")

    titles = [note["title"] for note in db.list_notes(db_path)]

    assert titles == ["Second", "First"]


def test_list_notes_empty(db_path):
    assert db.list_notes(db_path) == []


def test_delete_note(db_path):
    note_id = db.create_note(db_path, "Old", "Remove me")

    assert db.delete_note(db_path, note_id) is True
    assert db.get_note(db_path, note_id) is None


def test_delete_missing_note_returns_false(db_path):
    assert db.delete_note(db_path, 999) is False


def test_save_analysis_updates_note(db_path):
    note_id = db.create_note(db_path, "Call", "Rang the client.")
    items = [{"task": "Send quote", "owner": None, "due_date": None, "due_date_iso": None}]

    db.save_analysis(db_path, note_id, "Client called.", items, ["client"])

    note = db.get_note(db_path, note_id)
    assert note["summary"] == "Client called."
    assert note["action_items"] == items
    assert note["tags"] == ["client"]


# ---------- Projects ----------

def test_create_and_list_projects_alphabetically(db_path):
    db.create_project(db_path, "Office fit-out")
    db.create_project(db_path, "garden job")

    names = [project["name"] for project in db.list_projects(db_path)]

    assert names == ["garden job", "Office fit-out"]  # A-Z, ignoring upper/lower case


def test_get_project(db_path):
    project_id = db.create_project(db_path, "Harbour Road")

    assert db.get_project(db_path, project_id)["name"] == "Harbour Road"
    assert db.get_project(db_path, 999) is None


def test_project_notes_are_open_notes_of_that_project_newest_first(db_path):
    harbour = db.create_project(db_path, "Harbour Road")
    office = db.create_project(db_path, "Office")
    first = db.create_note(db_path, "", "First", project_id=harbour)
    second = db.create_note(db_path, "", "Second", project_id=harbour)
    db.create_note(db_path, "", "Other project", project_id=office)

    ids = [note["id"] for note in db.list_project_notes(db_path, harbour)]

    assert ids == [second, first]


def test_completed_notes_are_hidden_from_project_but_kept(db_path):
    project_id = db.create_project(db_path, "Harbour Road")
    note_id = db.create_note(db_path, "", "Done soon", project_id=project_id)

    assert db.complete_note(db_path, note_id) is True

    assert db.list_project_notes(db_path, project_id) == []
    assert db.get_note(db_path, note_id)["completed_at"]  # still in the database


def test_complete_missing_note_returns_false(db_path):
    assert db.complete_note(db_path, 999) is False


def test_project_list_counts_open_notes(db_path):
    project_id = db.create_project(db_path, "Harbour Road")
    db.create_note(db_path, "", "Open", project_id=project_id)
    done = db.create_note(db_path, "", "Done", project_id=project_id)
    db.complete_note(db_path, done)

    assert db.list_projects(db_path)[0]["open_count"] == 1


# ---------- Upgrading an old database ----------

def test_old_database_is_upgraded_and_notes_go_to_general(tmp_path):
    # Build a database the way the app did before projects existed.
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE notes (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, "
            "body TEXT NOT NULL, created_at TEXT NOT NULL, summary TEXT, "
            "action_items TEXT, tags TEXT)"
        )
        conn.execute(
            "INSERT INTO notes (title, body, created_at) VALUES ('Old call', 'Rang.', '2026-10-18T10:00:00')"
        )
    conn.close()

    db.init_db(path)
    db.init_db(path)  # running it twice must be safe

    projects = db.list_projects(path)
    assert [project["name"] for project in projects] == ["General"]
    note = db.get_note(path, 1)
    assert note["title"] == "Old call"
    assert note["project_id"] == projects[0]["id"]
    assert note["completed_at"] is None


def test_new_database_has_no_general_project(db_path):
    assert db.list_projects(db_path) == []


def test_open_notes_from_all_projects_newest_first_with_project_name(db_path):
    harbour = db.create_project(db_path, "Harbour Road")
    office = db.create_project(db_path, "Office")
    first = db.create_note(db_path, "", "First", project_id=harbour)
    second = db.create_note(db_path, "", "Second", project_id=office)
    done = db.create_note(db_path, "", "Done", project_id=office)
    db.complete_note(db_path, done)

    notes = db.list_open_notes(db_path)

    assert [note["id"] for note in notes] == [second, first]
    assert [note["project_name"] for note in notes] == ["Office", "Harbour Road"]
