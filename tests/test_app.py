import ai
import db


def test_home_with_no_notes(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"No notes yet" in response.data


def test_new_note_form_loads(client):
    response = client.get("/new")

    assert response.status_code == 200
    assert b"<form" in response.data


def test_saving_a_note_redirects_to_it(client):
    response = client.post("/new", data={"title": "Phone call", "body": "Client rang."})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/note/1")


def test_saved_note_shows_on_home_and_view_pages(client):
    client.post("/new", data={"title": "Phone call", "body": "Client rang."})

    home = client.get("/")
    view = client.get("/note/1")

    assert b"Phone call" in home.data
    assert b"Client rang." in view.data
    assert b"AI summary not available" in view.data


def test_empty_title_shows_error_and_does_not_save(client, db_path):
    response = client.post("/new", data={"title": "  ", "body": "Some text"})

    assert response.status_code == 400
    assert b"Please fill in both" in response.data
    assert b"Some text" in response.data  # what the user typed is kept
    assert db.list_notes(db_path) == []


def test_empty_body_shows_error(client):
    response = client.post("/new", data={"title": "Title", "body": ""})

    assert response.status_code == 400


def test_missing_note_returns_404(client):
    assert client.get("/note/999").status_code == 404


def test_html_in_notes_is_escaped(client):
    client.post("/new", data={"title": "<script>x</script>", "body": "hi"})

    response = client.get("/note/1")

    assert b"<script>x</script>" not in response.data
    assert b"&lt;script&gt;" in response.data


def test_note_page_has_delete_button_with_confirm(client):
    client.post("/new", data={"title": "Call", "body": "Rang."})

    response = client.get("/note/1")

    assert b'action="/note/1/delete"' in response.data
    assert b"confirm(" in response.data


def test_delete_removes_note_and_goes_home(client, db_path):
    client.post("/new", data={"title": "Call", "body": "Rang."})

    response = client.post("/note/1/delete")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    assert db.get_note(db_path, 1) is None


def test_delete_needs_post(client):
    client.post("/new", data={"title": "Call", "body": "Rang."})

    assert client.get("/note/1/delete").status_code == 405  # 405 = method not allowed


def test_delete_missing_note_returns_404(client):
    assert client.post("/note/999/delete").status_code == 404


FAKE_ANALYSIS = {
    "summary": "Priya will send a colour sample.\nTom books scaffolding.",
    "action_items": [
        {"task": "Send colour sample", "owner": "Priya", "due_date": "next Friday",
         "due_date_iso": "2026-10-23"},
    ],
    "tags": ["painting", "client"],
}


def test_saving_stores_ai_results(client, db_path, monkeypatch):
    calls = []

    def fake_analyze(title, body, created_at):
        calls.append((title, body))
        return FAKE_ANALYSIS

    monkeypatch.setattr(ai, "analyze_note", fake_analyze)

    client.post("/new", data={"title": "Site visit", "body": "Priya to send sample."})

    note = db.get_note(db_path, 1)
    assert calls == [("Site visit", "Priya to send sample.")]
    assert note["summary"] == FAKE_ANALYSIS["summary"]
    assert note["action_items"] == FAKE_ANALYSIS["action_items"]
    assert note["tags"] == ["painting", "client"]


def test_ai_results_show_on_pages(client, monkeypatch):
    monkeypatch.setattr(ai, "analyze_note", lambda *args: FAKE_ANALYSIS)
    client.post("/new", data={"title": "Site visit", "body": "Priya to send sample."})

    home = client.get("/").data
    view = client.get("/note/1").data

    assert b"Priya will send a colour sample." in home
    assert b"Tom books scaffolding." not in home  # home shows only the first line
    assert b"Send colour sample" in view
    assert b"Priya" in view
    assert b"AI summary not available" not in view


def test_note_still_saved_when_api_fails(client, db_path, monkeypatch):
    monkeypatch.setattr(ai, "analyze_note", lambda *args: None)

    response = client.post("/new", data={"title": "Call", "body": "Rang."})

    assert response.status_code == 302
    note = db.get_note(db_path, 1)
    assert note["body"] == "Rang."
    assert note["summary"] is None
    assert b"AI summary not available" in client.get("/note/1").data


def save_with_items(client, monkeypatch, items):
    """Save a note whose (fake) AI analysis has the given action items."""
    analysis = {"summary": "A note.", "action_items": items, "tags": ["test"]}
    monkeypatch.setattr(ai, "analyze_note", lambda *args: analysis)
    client.post("/new", data={"title": "Dates", "body": "Some tasks."})
    return client.get("/note/1").data.decode()


def test_due_date_shows_text_and_week(client, monkeypatch):
    page = save_with_items(client, monkeypatch, [
        {"task": "Send sample", "owner": None, "due_date": "next Friday",
         "due_date_iso": "2026-10-23"},
    ])

    assert "due next Friday (23 Oct, week 43)" in page


def test_due_date_without_exact_day_shows_text_only(client, monkeypatch):
    page = save_with_items(client, monkeypatch, [
        {"task": "Clear driveway", "owner": "Ben", "due_date": "before Thursday morning",
         "due_date_iso": None},
    ])

    assert "due before Thursday morning" in page
    assert "week" not in page


def test_no_due_date_shows_nothing(client, monkeypatch):
    page = save_with_items(client, monkeypatch, [
        {"task": "Book scaffolding", "owner": "Tom", "due_date": None, "due_date_iso": None},
    ])

    assert "Book scaffolding" in page
    assert "due" not in page.split("Book scaffolding")[1].split("</label>")[0]
