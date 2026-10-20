"""Tests for the usage limits that protect my Claude API bill.

The daily AI limit and the longest note and question allowed.
"""

import pytest

import ai
import db
from app import MAX_NOTE_LENGTH, MAX_QUESTION_LENGTH, create_app
from tests.conftest import TEST_PASSWORD, TEST_SETTINGS


@pytest.fixture
def project_id(db_path):
    return db.create_project(db_path, "Harbour Road")


@pytest.fixture
def ai_calls(monkeypatch):
    """Replace both AI functions with fakes that record every call made to them."""
    calls = []

    def fake_analyze(*args):
        calls.append("analyze")
        return {"summary": "A note.", "action_items": [], "tags": ["test"]}

    def fake_answer(question, notes):
        calls.append("answer")
        return {"answer": "Friday.", "note_ids": [notes[0]["id"]]}

    monkeypatch.setattr(ai, "analyze_note", fake_analyze)
    monkeypatch.setattr(ai, "answer_question", fake_answer)
    return calls


def client_with_limit(db_path, limit):
    """A logged-in fake browser for an app with the given daily AI limit."""
    app = create_app(db_path, {**TEST_SETTINGS, "AI_DAILY_LIMIT": limit})
    client = app.test_client()
    client.post("/login", data={"password": TEST_PASSWORD})
    return client


# ---------- Daily AI limit ----------

def test_default_limit_is_50(client):
    assert client.application.config["AI_DAILY_LIMIT"] == 50


def test_each_saved_note_counts_one_ai_job(client, db_path, project_id, ai_calls):
    client.post(f"/project/{project_id}/notes", data={"body": "Rang the client."})

    assert ai_calls == ["analyze"]
    assert db.ai_jobs_used(db_path) == 1


def test_note_is_saved_without_ai_when_limit_reached(db_path, project_id, ai_calls):
    client = client_with_limit(db_path, 1)
    client.post(f"/project/{project_id}/notes", data={"body": "First note"})

    response = client.post(
        f"/project/{project_id}/notes", data={"body": "Second note"}, follow_redirects=True
    )

    assert ai_calls == ["analyze"]  # no AI call for the second note
    assert b"Daily AI limit reached" in response.data
    second = db.get_note(db_path, 2)
    assert second["body"] == "Second note"  # the note itself is kept
    assert second["summary"] is None


def test_ask_is_refused_when_limit_reached(db_path, project_id, ai_calls):
    db.create_note(db_path, "", "Timber delivery on Friday.", project_id=project_id)
    client = client_with_limit(db_path, 0)

    response = client.post("/ask", data={"question": "When is the timber delivery?"})

    assert response.status_code == 429
    assert ai_calls == []
    assert b"Daily AI limit reached, try again tomorrow." in response.data
    assert b'href="/note/1"' in response.data  # the matching notes are still shown


def test_ask_with_no_matches_does_not_use_the_limit(client, db_path, ai_calls):
    client.post("/ask", data={"question": "Anything about rockets?"})

    assert db.ai_jobs_used(db_path) == 0


def test_limit_comes_from_the_environment(db_path, monkeypatch):
    monkeypatch.setenv("AI_DAILY_LIMIT", "7")

    assert create_app(db_path, TEST_SETTINGS).config["AI_DAILY_LIMIT"] == 7


def test_limit_that_is_not_a_number_stops_the_app(db_path, monkeypatch):
    monkeypatch.setenv("AI_DAILY_LIMIT", "fifty")

    with pytest.raises(RuntimeError, match="AI_DAILY_LIMIT must be a whole number"):
        create_app(db_path, TEST_SETTINGS)


# ---------- Size limits ----------

def test_too_long_note_is_refused_and_kept_in_the_box(client, db_path, project_id, ai_calls):
    body = "x" * (MAX_NOTE_LENGTH + 1)

    response = client.post(f"/project/{project_id}/notes", data={"body": body})

    assert response.status_code == 400
    assert b"The most is 10,000" in response.data
    assert body.encode() in response.data  # what was typed isn't lost
    assert db.list_notes(db_path) == []
    assert ai_calls == []


def test_too_long_note_is_refused_on_all_notes_page(client, db_path, project_id):
    body = "x" * (MAX_NOTE_LENGTH + 1)

    response = client.post("/notes", data={"body": body, "project_id": project_id})

    assert response.status_code == 400
    assert db.list_notes(db_path) == []


def test_note_of_exactly_the_maximum_is_saved(client, db_path, project_id, ai_calls):
    client.post(f"/project/{project_id}/notes", data={"body": "x" * MAX_NOTE_LENGTH})

    assert len(db.list_notes(db_path)) == 1


def test_too_long_question_is_refused(client, db_path, ai_calls):
    response = client.post("/ask", data={"question": "x" * (MAX_QUESTION_LENGTH + 1)})

    assert response.status_code == 400
    assert b"under 500 characters" in response.data
    assert ai_calls == []
    assert db.ai_jobs_used(db_path) == 0


def test_question_boxes_have_a_maxlength(client):
    page = client.get("/ask").data.decode()

    assert page.count('maxlength="500"') == 2  # the Ask page and the top bar
