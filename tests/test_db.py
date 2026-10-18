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
