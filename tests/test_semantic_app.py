"""Semantic search in the app: saving notes, the Ask page and the embed-notes command.

A fake embedder replaces the Voyage API. It gives texts about wood or timber one
vector and everything else another, so "wood" and "timber" "mean" the same thing.
"""

import pytest

import ai
import db
import embeddings

WOOD = [1.0, 0.0]
OTHER = [0.0, 1.0]


def fake_embed_texts(texts, input_type, client=None):
    return [WOOD if ("wood" in t.lower() or "timber" in t.lower()) else OTHER for t in texts]


@pytest.fixture
def fake_embeddings(monkeypatch):
    """Turn embeddings on, with the fake embedder. Returns the list of calls made."""
    calls = []

    def recording_embed(texts, input_type, client=None):
        calls.append((list(texts), input_type))
        return fake_embed_texts(texts, input_type)

    monkeypatch.setattr(embeddings, "embed_texts", recording_embed)
    return calls


@pytest.fixture
def project_id(db_path):
    return db.create_project(db_path, "Harbour Road")


def add_embedded_note(db_path, title, body):
    note_id = db.create_note(db_path, title, body)
    vector = fake_embed_texts([f"{title} {body}"], "document")[0]
    db.save_embedding(db_path, note_id, vector, embeddings.MODEL)
    return note_id


# ---------- Saving notes ----------

def test_saved_note_gets_a_vector_that_includes_the_ai_summary(
    client, db_path, project_id, monkeypatch, fake_embeddings
):
    analysis = {"summary": "Timber arrives Thursday.", "action_items": [], "tags": ["delivery"]}
    monkeypatch.setattr(ai, "analyze_note", lambda *args: analysis)

    client.post(f"/project/{project_id}/notes", data={"body": "Rang the yard."})

    note = db.get_note(db_path, 1)
    assert note["embedding"] == WOOD  # found "timber" in the summary
    assert note["embedding_model"] == embeddings.MODEL
    assert fake_embeddings == [
        (["Rang the yard.\nTimber arrives Thursday.\nTags: delivery"], "document")
    ]


def test_note_is_still_saved_when_embedding_fails(client, db_path, project_id, monkeypatch):
    monkeypatch.setattr(embeddings, "embed_texts", lambda *args: None)

    response = client.post(f"/project/{project_id}/notes", data={"body": "Rang the yard."})

    assert response.status_code == 302
    assert db.get_note(db_path, 1)["embedding"] is None


# ---------- Ask page ----------

def test_ask_finds_notes_by_meaning(client, db_path, monkeypatch, fake_embeddings):
    timber = add_embedded_note(db_path, "Timber call", "Arrives Thursday.")
    add_embedded_note(db_path, "Painting", "Hallway done.")
    sent = []

    def fake_answer(question, notes):
        sent.extend(note["id"] for note in notes)
        return {"answer": "Thursday.", "note_ids": [timber]}

    monkeypatch.setattr(ai, "answer_question", fake_answer)

    page = client.post("/ask", data={"question": "When does the wood come?"}).data.decode()

    assert sent == [timber]  # no shared words, found by meaning; painting left out
    assert "Thursday." in page
    assert (["When does the wood come?"], "query") in fake_embeddings


def test_ask_falls_back_to_keywords_when_embeddings_fail(client, db_path, monkeypatch):
    note_id = add_embedded_note(db_path, "Timber call", "Delivery on Thursday.")
    monkeypatch.setattr(embeddings, "embed_texts", lambda *args: None)
    monkeypatch.setattr(
        ai, "answer_question", lambda *args: {"answer": "Thursday.", "note_ids": [note_id]}
    )

    page = client.post("/ask", data={"question": "delivery?"}).data.decode()

    assert "Thursday." in page


def test_ask_with_nothing_close_skips_claude(client, db_path, monkeypatch, fake_embeddings):
    add_embedded_note(db_path, "Painting", "Hallway done.")

    def must_not_be_called(*args):
        raise AssertionError("the API should not be called")

    monkeypatch.setattr(ai, "answer_question", must_not_be_called)

    page = client.post("/ask", data={"question": "Where is the wood?"}).data.decode()

    assert "I couldn&#39;t find that in your notes." in page


# ---------- flask embed-notes ----------

def run_embed_notes(client):
    return client.application.test_cli_runner().invoke(args=["embed-notes"])


def test_embed_notes_command_fills_in_missing_vectors(client, db_path, fake_embeddings):
    missing = db.create_note(db_path, "Timber call", "Arrives Thursday.")
    add_embedded_note(db_path, "Painting", "Hallway done.")  # already has one
    fake_embeddings.clear()

    result = run_embed_notes(client)

    assert result.exit_code == 0
    assert "Embedded 1 notes." in result.output
    assert db.get_note(db_path, missing)["embedding"] == WOOD
    assert len(fake_embeddings) == 1  # only the missing note was sent


def test_embed_notes_command_is_safe_to_run_again(client, db_path, fake_embeddings):
    add_embedded_note(db_path, "Painting", "Hallway done.")

    result = run_embed_notes(client)

    assert result.exit_code == 0
    assert "Every note already has a vector." in result.output


def test_embed_notes_command_fails_clearly_without_a_key(client, db_path):
    db.create_note(db_path, "Timber call", "Arrives Thursday.")  # embeddings blocked in tests

    result = run_embed_notes(client)

    assert result.exit_code == 1
    assert "VOYAGE_API_KEY" in result.output
