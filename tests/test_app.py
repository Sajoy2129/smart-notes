from datetime import date, timedelta

import pytest

import ai
import db


@pytest.fixture
def project_id(db_path):
    """A project to add notes to."""
    return db.create_project(db_path, "Harbour Road")


def save_note(client, project_id, body="Rang the client.", **kwargs):
    """Add a note through the project page's add-note box."""
    return client.post(f"/project/{project_id}/notes", data={"body": body}, **kwargs)


# ---------- Home and projects ----------

def test_home_with_no_projects_shows_welcome(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Welcome to Smart Notes" in response.data
    assert b'action="/projects"' in response.data  # the new-project box


def test_home_shows_all_open_notes_with_project_names(client, db_path, project_id):
    office = db.create_project(db_path, "Office")
    save_note(client, project_id, "Harbour note")
    save_note(client, office, "Office note")
    save_note(client, office, "Finished note")
    client.post("/note/3/complete")

    page = client.get("/").data.decode()

    assert "<h1>All notes</h1>" in page
    assert page.index("Office note") < page.index("Harbour note")  # newest first
    assert "Finished note" not in page
    assert '<span class="note-project">Office</span>' in page
    assert '<span class="note-project">Harbour Road</span>' in page


def test_add_note_box_is_below_the_cards(client, project_id):
    save_note(client, project_id)

    for url in ["/", f"/project/{project_id}"]:
        page = client.get(url).data.decode()
        assert page.index('class="note-grid"') < page.index('id="note-form"'), url


def test_add_note_from_all_notes_page_goes_to_chosen_project(client, db_path, project_id):
    office = db.create_project(db_path, "Office")

    response = client.post("/notes", data={"body": "Call the electrician.", "project_id": office})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    note = db.get_note(db_path, 1)
    assert note["project_id"] == office
    assert note["body"] == "Call the electrician."


def test_all_notes_add_box_lists_projects(client, db_path, project_id):
    page = client.get("/").data.decode()

    assert f'<option value="{project_id}">Harbour Road</option>' in page


def test_all_notes_add_needs_a_real_project(client, db_path, project_id):
    response = client.post("/notes", data={"body": "Lost note", "project_id": "999"})

    assert response.status_code == 400
    assert b"Please choose a project for the note." in response.data
    assert b"Lost note" in response.data  # what was typed is kept
    assert db.list_notes(db_path) == []


def test_all_notes_add_needs_text(client, db_path, project_id):
    response = client.post("/notes", data={"body": "  ", "project_id": project_id})

    assert response.status_code == 400
    assert db.list_notes(db_path) == []


def test_create_project_and_open_it(client, db_path):
    response = client.post("/projects", data={"name": "  Harbour Road  "})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/project/1")
    assert db.get_project(db_path, 1)["name"] == "Harbour Road"


def test_empty_project_name_is_refused(client, db_path):
    response = client.post("/projects", data={"name": "   "}, follow_redirects=True)

    assert b"Please type a project name." in response.data
    assert db.list_projects(db_path) == []


def test_sidebar_lists_projects_and_marks_current(client, db_path, project_id):
    db.create_project(db_path, "Office")

    page = client.get(f"/project/{project_id}").data.decode()

    assert "Office" in page
    assert f'href="/project/{project_id}"\n             aria-current="page"' in page


def test_missing_project_returns_404(client):
    assert client.get("/project/999").status_code == 404
    assert client.post("/project/999/notes", data={"body": "Hi"}).status_code == 404


# ---------- Adding notes ----------

def test_saving_a_note_returns_to_project_and_shows_card(client, project_id):
    response = save_note(client, project_id, "Client rang about the hallway.")

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/project/{project_id}")
    page = client.get(f"/project/{project_id}").data.decode()
    assert 'class="note-card card"' in page
    assert "Client rang about the hallway." in page
    assert "just now" in page


def test_note_needs_no_title(client, db_path, project_id):
    save_note(client, project_id, "Just the text.")

    note = db.get_note(db_path, 1)
    assert note["title"] == ""
    assert note["body"] == "Just the text."
    assert note["project_id"] == project_id


def test_empty_note_shows_error_and_does_not_save(client, db_path, project_id):
    response = save_note(client, project_id, "   ")

    assert response.status_code == 400
    assert b"Please type a note first." in response.data
    assert db.list_notes(db_path) == []


def test_notes_only_show_in_their_own_project(client, db_path, project_id):
    office = db.create_project(db_path, "Office")
    save_note(client, project_id, "Harbour note")
    save_note(client, office, "Office note")

    page = client.get(f"/project/{project_id}").data.decode()

    assert "Harbour note" in page
    assert "Office note" not in page


def test_saving_shows_note_saved_message_once(client, project_id):
    response = save_note(client, project_id, follow_redirects=True)

    assert "Note saved ✓" in response.data.decode()
    # A flash message is shown once, then removed.
    assert "Note saved ✓" not in client.get(f"/project/{project_id}").data.decode()


def test_project_page_has_spinner_text(client, project_id):
    assert "Claude is reading your note…" in client.get(f"/project/{project_id}").data.decode()


# ---------- Completing notes ----------

def test_complete_hides_note_from_project_but_keeps_it(client, db_path, project_id):
    save_note(client, project_id, "Order paint")

    response = client.post("/note/1/complete", follow_redirects=True)

    page = response.data.decode()
    assert "Note completed ✓" in page
    assert "Order paint" not in page.split("</h1>")[1]  # gone from the cards
    assert db.get_note(db_path, 1)["completed_at"]  # still saved


def test_card_has_complete_button(client, project_id):
    save_note(client, project_id)

    assert b'action="/note/1/complete"' in client.get(f"/project/{project_id}").data


def test_complete_needs_post_and_existing_note(client, project_id):
    save_note(client, project_id)

    assert client.get("/note/1/complete").status_code == 405
    assert client.post("/note/999/complete").status_code == 404


def test_completed_note_page_says_completed(client, project_id):
    save_note(client, project_id)
    client.post("/note/1/complete")

    page = client.get("/note/1").data.decode()

    assert "✓ Completed" in page
    assert 'action="/note/1/complete"' not in page  # no second Complete button


def test_sidebar_count_ignores_completed_notes(client, project_id):
    save_note(client, project_id, "One")
    save_note(client, project_id, "Two")
    client.post("/note/1/complete")

    page = client.get(f"/project/{project_id}").data.decode()

    assert '<span class="count">1</span>' in page


# ---------- Note page ----------

def test_note_page_uses_first_line_as_heading(client, project_id):
    save_note(client, project_id, "\nMet client at 10.\nWants hallway off-white.")

    page = client.get("/note/1").data.decode()

    assert "<h1>Met client at 10.</h1>" in page
    assert "<title>Met client at 10. – Smart Notes</title>" in page


def test_long_first_line_is_shortened_in_heading(client, project_id):
    save_note(client, project_id, "x" * 100)

    assert f"<h1>{'x' * 60}…</h1>" in client.get("/note/1").data.decode()


def test_old_notes_keep_their_title(client, db_path):
    db.create_note(db_path, "Old call", "Rang.")

    assert b"<h1>Old call</h1>" in client.get("/note/1").data


def test_note_page_links_back_to_project(client, project_id):
    save_note(client, project_id)

    page = client.get("/note/1").data.decode()

    assert f'href="/project/{project_id}">← Harbour Road' in page


def test_missing_note_returns_404(client):
    assert client.get("/note/999").status_code == 404


def test_html_in_notes_is_escaped(client, project_id):
    save_note(client, project_id, "<script>x</script>")

    for url in ["/note/1", f"/project/{project_id}"]:
        page = client.get(url).data
        assert b"<script>x</script>" not in page, url
        assert b"&lt;script&gt;" in page, url


def test_html_in_project_name_is_escaped(client):
    client.post("/projects", data={"name": "<b>x</b>"})

    assert b"&lt;b&gt;x&lt;/b&gt;" in client.get("/project/1").data


# ---------- Deleting ----------

def test_note_page_has_red_delete_button_with_confirm(client, project_id):
    save_note(client, project_id)

    page = client.get("/note/1").data

    assert b'action="/note/1/delete"' in page
    assert b"confirm(" in page
    assert b'class="button button-danger"' in page


def test_delete_removes_note_and_returns_to_project(client, db_path, project_id):
    save_note(client, project_id)

    response = client.post("/note/1/delete")

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/project/{project_id}")
    assert db.get_note(db_path, 1) is None


def test_delete_needs_post(client, project_id):
    save_note(client, project_id)

    assert client.get("/note/1/delete").status_code == 405  # 405 = method not allowed


def test_delete_missing_note_returns_404(client):
    assert client.post("/note/999/delete").status_code == 404


# ---------- Security ----------

def test_post_from_another_website_is_blocked(client, db_path, project_id):
    # CSRF: a different site's page tries to submit a form to our app.
    save_note(client, project_id)

    response = client.post("/note/1/delete", headers={"Origin": "https://evil.example"})

    assert response.status_code == 403  # 403 = forbidden
    assert db.get_note(db_path, 1) is not None


def test_request_for_another_host_is_rejected(client, db_path, project_id):
    # DNS rebinding: evil.com is made to point at this Mac, so Host and Origin
    # both say evil.com and match each other. Only localhost names are allowed.
    save_note(client, project_id)
    headers = {"Host": "evil.com:5000", "Origin": "http://evil.com:5000"}

    assert client.post("/note/1/delete", headers=headers).status_code == 400
    assert client.get("/", headers={"Host": "evil.com:5000"}).status_code == 400
    assert db.get_note(db_path, 1) is not None


def test_local_addresses_are_allowed(logged_out_client):
    # Accepted means sent on to the login page, not rejected with 400.
    for host in ["127.0.0.1:5000", "localhost:5001"]:
        response = logged_out_client.get("/", headers={"Host": host})
        assert response.status_code == 302
        assert "/login" in response.location


def test_post_from_our_own_pages_is_allowed(client, db_path, project_id):
    save_note(client, project_id)

    response = client.post("/note/1/delete", headers={"Origin": "http://localhost"})

    assert response.status_code == 302
    assert db.get_note(db_path, 1) is None


# ---------- AI results ----------

FAKE_ANALYSIS = {
    "summary": "Priya will send a colour sample.\nTom books scaffolding.",
    "action_items": [
        {"task": "Send colour sample", "owner": "Priya", "due_date": "next Friday",
         "due_date_iso": "2026-10-23"},
    ],
    "tags": ["painting", "client"],
}


def test_saving_sends_project_name_to_claude_and_stores_results(
    client, db_path, project_id, monkeypatch
):
    calls = []

    def fake_analyze(title, body, created_at):
        calls.append((title, body))
        return FAKE_ANALYSIS

    monkeypatch.setattr(ai, "analyze_note", fake_analyze)

    save_note(client, project_id, "Priya to send sample.")

    note = db.get_note(db_path, 1)
    assert calls == [("Harbour Road", "Priya to send sample.")]  # project name as context
    assert note["summary"] == FAKE_ANALYSIS["summary"]
    assert note["action_items"] == FAKE_ANALYSIS["action_items"]
    assert note["tags"] == ["painting", "client"]


def test_card_shows_tags(client, project_id, monkeypatch):
    monkeypatch.setattr(ai, "analyze_note", lambda *args: FAKE_ANALYSIS)
    save_note(client, project_id)

    page = client.get(f"/project/{project_id}").data

    assert b'<span class="tag">painting</span>' in page


def test_note_page_layout_has_summary_checklist_and_tags(client, project_id, monkeypatch):
    monkeypatch.setattr(ai, "analyze_note", lambda *args: FAKE_ANALYSIS)
    save_note(client, project_id, "Priya to send sample.")

    view = client.get("/note/1").data.decode()

    # Summary comes first, then action items, then tags.
    assert view.index("AI summary") < view.index('class="checklist') < view.index('class="tags"')
    assert "Priya will send a colour sample." in view
    assert '<span class="tag">painting</span>' in view
    assert 'type="checkbox"' in view
    assert "AI summary not available" not in view


def test_note_still_saved_when_api_fails(client, db_path, project_id, monkeypatch):
    monkeypatch.setattr(ai, "analyze_note", lambda *args: None)

    response = save_note(client, project_id, "Rang.")

    assert response.status_code == 302
    note = db.get_note(db_path, 1)
    assert note["body"] == "Rang."
    assert note["summary"] is None
    assert b"AI summary not available" in client.get("/note/1").data


def save_with_items(client, monkeypatch, project_id, items):
    """Save a note whose (fake) AI analysis has the given action items."""
    analysis = {"summary": "A note.", "action_items": items, "tags": ["test"]}
    monkeypatch.setattr(ai, "analyze_note", lambda *args: analysis)
    save_note(client, project_id, "Some tasks.")
    return client.get("/note/1").data.decode()


def test_due_date_shows_text_and_week(client, project_id, monkeypatch):
    page = save_with_items(client, monkeypatch, project_id, [
        {"task": "Send sample", "owner": None, "due_date": "next Friday",
         "due_date_iso": "2026-10-23"},
    ])

    assert "due next Friday (23 Oct, week 43)" in page


def test_due_date_without_exact_day_shows_text_only(client, project_id, monkeypatch):
    page = save_with_items(client, monkeypatch, project_id, [
        {"task": "Clear driveway", "owner": "Ben", "due_date": "before Thursday morning",
         "due_date_iso": None},
    ])

    assert "due before Thursday morning" in page
    assert "week" not in page


def test_no_due_date_shows_nothing(client, project_id, monkeypatch):
    page = save_with_items(client, monkeypatch, project_id, [
        {"task": "Book scaffolding", "owner": "Tom", "due_date": None, "due_date_iso": None},
    ])

    assert "Book scaffolding" in page
    assert "due" not in page.split("Book scaffolding")[1].split("</li>")[0]


def test_overdue_and_due_soon_chips_are_coloured(client, project_id, monkeypatch):
    today = date.today()
    page = save_with_items(client, monkeypatch, project_id, [
        {"task": "Old job", "owner": "Sam", "due_date": "last week",
         "due_date_iso": (today - timedelta(days=7)).isoformat()},
        {"task": "Urgent job", "owner": None, "due_date": "tomorrow",
         "due_date_iso": (today + timedelta(days=1)).isoformat()},
    ])

    assert 'class="chip chip-overdue"' in page
    assert 'class="chip chip-due-soon"' in page
    assert '<span class="chip">Sam</span>' in page


# ---------- Design ----------

def test_every_page_uses_new_design(client, project_id):
    save_note(client, project_id)

    for url in [f"/project/{project_id}", "/note/1", "/ask", "/note/999"]:
        page = client.get(url).data
        assert b"/static/app.css" in page, url
        assert b'class="topbar"' in page, url


def test_top_bar_has_all_notes_and_ask_links_and_ask_box(client):
    page = client.get("/").data

    assert b'href="/ask"' in page
    assert b">All notes</a>" in page
    assert b'placeholder="Ask your notes' in page
    assert b"New Note" not in page  # notes are added inside a project now


def test_missing_page_is_friendly(client):
    response = client.get("/note/999")

    assert response.status_code == 404
    assert b"Page not found" in response.data
    assert b"Back to your notes" in response.data


# ---------- Ask page ----------

def add_note(db_path, title, body):
    return db.create_note(db_path, title, body)


def test_ask_page_loads(client):
    response = client.get("/ask")

    assert response.status_code == 200
    assert b'name="question"' in response.data


def test_ask_page_answers_head_requests(client):
    assert client.head("/ask").status_code == 200


def test_ask_empty_question_shows_error(client):
    response = client.post("/ask", data={"question": "  "})

    assert response.status_code == 400
    assert b"Please type a question." in response.data


def test_ask_with_no_matching_notes_skips_api(client, db_path, monkeypatch):
    add_note(db_path, "Site visit", "Painted the hallway.")

    def must_not_be_called(*args):
        raise AssertionError("the API should not be called")

    monkeypatch.setattr(ai, "answer_question", must_not_be_called)

    response = client.post("/ask", data={"question": "scaffolding?"})

    assert b"I couldn&#39;t find that in your notes." in response.data


def test_ask_shows_answer_and_links_only_used_notes(client, db_path, monkeypatch):
    used = add_note(db_path, "Timber call", "Delivery moved to Thursday.")
    add_note(db_path, "Delivery invoice", "Paid the delivery invoice.")
    sent = []

    def fake_answer(question, notes):
        sent.extend(note["id"] for note in notes)
        return {"answer": "The delivery is on Thursday.", "note_ids": [used]}

    monkeypatch.setattr(ai, "answer_question", fake_answer)

    page = client.post("/ask", data={"question": "When is the delivery?"}).data.decode()

    assert sorted(sent) == [1, 2]  # both matching notes were sent to Claude
    assert "The delivery is on Thursday." in page
    assert f'href="/note/{used}"' in page
    assert "Delivery invoice" not in page  # not used, so not linked


def test_ask_links_untitled_notes_by_first_line(client, db_path, project_id, monkeypatch):
    db.create_note(db_path, "", "Timber delivery moved to Thursday.", project_id=project_id)
    monkeypatch.setattr(
        ai, "answer_question", lambda *args: {"answer": "Thursday.", "note_ids": [1]}
    )

    page = client.post("/ask", data={"question": "timber delivery"}).data.decode()

    assert ">Timber delivery moved to Thursday.</a>" in page


def test_ask_when_api_fails_shows_message_and_matches(client, db_path, monkeypatch):
    add_note(db_path, "Timber call", "Delivery moved to Thursday.")
    monkeypatch.setattr(ai, "answer_question", lambda *args: None)

    response = client.post("/ask", data={"question": "delivery"})

    assert response.status_code == 503
    assert b"couldn&#39;t answer right now" in response.data
    assert b'href="/note/1"' in response.data
