"""Tests for embeddings.py. A MockTransport fakes the Voyage API: no real calls."""

import json

import httpx2
import pytest

import embeddings

# Saved when this file is imported, before conftest.py blocks _make_client for each test.
REAL_MAKE_CLIENT = embeddings._make_client


def fake_client(replies):
    """An HTTP client whose "server" is this test.

    replies: one per request, each a status code (an error reply) or a list of
    vectors (a good reply). The client keeps the requests it sent in .sent.
    """
    replies = list(replies)
    sent = []

    def handle(request):
        sent.append(json.loads(request.content))
        reply = replies.pop(0)
        if isinstance(reply, int):
            return httpx2.Response(reply, json={"detail": "error"})
        data = [{"object": "embedding", "embedding": v, "index": i} for i, v in enumerate(reply)]
        return httpx2.Response(200, json={"object": "list", "data": data})

    client = httpx2.Client(transport=httpx2.MockTransport(handle))
    client.sent = sent
    return client


# ---------- cosine_similarity ----------

def test_same_direction_is_1():
    assert embeddings.cosine_similarity([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)


def test_opposite_direction_is_minus_1():
    assert embeddings.cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)


def test_unrelated_is_0():
    assert embeddings.cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)


def test_zero_vector_does_not_divide_by_zero():
    assert embeddings.cosine_similarity([0, 0], [1, 1]) == 0.0


# ---------- embed_texts ----------

def test_returns_one_vector_per_text_and_sends_model_and_type():
    client = fake_client([[[0.1, 0.2], [0.3, 0.4]]])

    vectors = embeddings.embed_texts(["a", "b"], "document", client)

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert client.sent == [
        {"input": ["a", "b"], "model": embeddings.MODEL, "input_type": "document"}
    ]


def test_empty_list_makes_no_call():
    client = fake_client([])

    assert embeddings.embed_texts([], "document", client) == []
    assert client.sent == []


def test_server_error_is_retried_once():
    client = fake_client([500, [[1.0, 0.0]]])

    assert embeddings.embed_texts(["a"], "document", client) == [[1.0, 0.0]]
    assert len(client.sent) == 2


def test_two_failures_give_none():
    client = fake_client([503, 503])

    assert embeddings.embed_texts(["a"], "document", client) is None


def test_wrong_key_is_not_retried():
    client = fake_client([401])

    assert embeddings.embed_texts(["a"], "document", client) is None
    assert len(client.sent) == 1


def test_wrong_number_of_vectors_gives_none():
    client = fake_client([[[1.0]], [[1.0]]])  # 1 vector back for 2 texts, twice

    assert embeddings.embed_texts(["a", "b"], "document", client) is None


def test_many_texts_are_sent_in_batches(monkeypatch):
    monkeypatch.setattr(embeddings, "BATCH_SIZE", 2)
    client = fake_client([[[1], [2]], [[3]]])

    assert embeddings.embed_texts(["a", "b", "c"], "document", client) == [[1], [2], [3]]
    assert [request["input"] for request in client.sent] == [["a", "b"], ["c"]]


def test_no_api_key_gives_none_without_a_call(monkeypatch):
    monkeypatch.setattr(embeddings, "_make_client", REAL_MAKE_CLIENT)
    # conftest.py already removed VOYAGE_API_KEY from the environment.

    assert embeddings.embed_texts(["a"], "document") is None


def test_embed_question_uses_query_type():
    client = fake_client([[[0.5, 0.5]]])

    assert embeddings.embed_question("When?", client) == [0.5, 0.5]
    assert client.sent[0]["input_type"] == "query"


# ---------- note_text ----------

def test_note_text_joins_title_body_summary_and_tags():
    note = {"title": "Call", "body": "Rang Sam.", "summary": "Sam called.", "tags": ["paint"]}

    assert embeddings.note_text(note) == "Call\nRang Sam.\nSam called.\nTags: paint"


def test_note_text_skips_empty_parts():
    note = {"title": "", "body": "Rang Sam.", "summary": None, "tags": []}

    assert embeddings.note_text(note) == "Rang Sam."


def test_failure_log_shows_status_code_but_not_the_text(caplog):
    client = fake_client([429, 429])

    embeddings.embed_texts(["secret note text"], "document", client)

    assert "HTTPStatusError 429" in caplog.text
    assert "secret note text" not in caplog.text
