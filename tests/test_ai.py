"""Tests for ai.py. They use a fake client, so no real API call is made."""

import json
from types import SimpleNamespace

import anthropic
import httpx2

import ai

CREATED_AT = "2026-10-18T10:00:00"

GOOD_REPLY = {
    "summary": "The client wants the hallway painted. Paint arrives Monday.",
    "action_items": [
        {
            "task": "Order white paint",
            "owner": "Sam",
            "due_date": "next Friday",
            "due_date_iso": "2026-10-23",
        }
    ],
    "tags": ["Painting", "client", "client"],
}


def fake_response(text, stop_reason="end_turn"):
    """Something shaped like the SDK's response object."""
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)],
    )


class FakeClient:
    """Stands in for anthropic.Anthropic().

    Give it a list of outcomes: each is a reply (returned) or an exception (raised),
    used one per API call. It also counts the calls.
    """

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def connection_error():
    return anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.test"))


def auth_error():
    request = httpx2.Request("POST", "https://api.test")
    response = httpx2.Response(401, request=request)
    return anthropic.AuthenticationError("invalid x-api-key", response=response, body=None)


def analyze(client):
    return ai.analyze_note("Site visit", "Sam to order paint by next Friday.", CREATED_AT, client)


def test_valid_reply_is_parsed_and_cleaned():
    client = FakeClient([fake_response(json.dumps(GOOD_REPLY))])

    result = analyze(client)

    assert result["summary"].startswith("The client wants")
    assert result["action_items"][0] == GOOD_REPLY["action_items"][0]
    assert result["tags"] == ["painting", "client"]  # lowercased, duplicate removed
    assert client.calls == 1


def test_request_uses_model_schema_and_note_date():
    client = FakeClient([fake_response(json.dumps(GOOD_REPLY))])

    analyze(client)

    kwargs = client.last_kwargs
    assert kwargs["model"] == "claude-sonnet-5-5"
    assert kwargs["output_config"]["format"]["schema"] == ai.NOTE_SCHEMA
    assert "Sunday 18 October 2026" in kwargs["messages"][0]["content"]


def test_note_with_no_tasks_gets_empty_list():
    reply = {"summary": "Just a catch-up call.", "action_items": [], "tags": ["client", "call"]}
    client = FakeClient([fake_response(json.dumps(reply))])

    assert analyze(client)["action_items"] == []


def test_invalid_json_then_valid_retries_once():
    client = FakeClient([fake_response("not json {"), fake_response(json.dumps(GOOD_REPLY))])

    result = analyze(client)

    assert result is not None
    assert client.calls == 2


def test_invalid_json_twice_returns_none():
    client = FakeClient([fake_response("oops"), fake_response("still oops")])

    assert analyze(client) is None
    assert client.calls == 2


def test_wrong_shape_counts_as_invalid():
    client = FakeClient([fake_response('{"summary": ""}'), fake_response("[]")])

    assert analyze(client) is None


def test_network_error_twice_returns_none():
    client = FakeClient([connection_error(), connection_error()])

    assert analyze(client) is None
    assert client.calls == 2


def test_network_error_then_success():
    client = FakeClient([connection_error(), fake_response(json.dumps(GOOD_REPLY))])

    assert analyze(client) is not None


def test_wrong_api_key_is_not_retried():
    client = FakeClient([auth_error()])

    assert analyze(client) is None
    assert client.calls == 1


def test_refusal_counts_as_failure():
    refused = fake_response("", stop_reason="refusal")
    client = FakeClient([refused, refused])

    assert analyze(client) is None


def test_bad_iso_date_becomes_none_but_text_is_kept():
    reply = dict(GOOD_REPLY)
    reply["action_items"] = [
        {"task": "Call back", "owner": None, "due_date": "soon", "due_date_iso": "someday"}
    ]
    client = FakeClient([fake_response(json.dumps(reply))])

    item = analyze(client)["action_items"][0]

    assert item["due_date"] == "soon"
    assert item["due_date_iso"] is None


def test_missing_api_key_returns_none(monkeypatch):
    # monkeypatch temporarily replaces things for this one test only.
    def no_key():
        raise anthropic.AnthropicError("no API key")

    monkeypatch.setattr(ai, "_make_client", no_key)

    assert ai.analyze_note("t", "b", CREATED_AT) is None


# ---------- answer_question ----------

NOTES = [
    {"id": 3, "title": "Timber call", "body": "Delivery moved to Thursday.",
     "created_at": CREATED_AT},
    {"id": 7, "title": "Site visit", "body": "Priya sends sample.", "created_at": CREATED_AT},
]


def answer_reply(found, answer, note_ids):
    return fake_response(json.dumps({"found": found, "answer": answer, "note_ids": note_ids}))


def test_answer_is_returned_with_note_ids():
    client = FakeClient([answer_reply(True, "On Thursday.", [3])])

    result = ai.answer_question("When is the delivery?", NOTES, client)

    assert result == {"answer": "On Thursday.", "note_ids": [3]}


def test_answer_request_contains_notes_with_ids_and_question_last():
    client = FakeClient([answer_reply(True, "On Thursday.", [3])])

    ai.answer_question("When is the delivery?", NOTES, client)

    content = client.last_kwargs["messages"][0]["content"]
    assert '<note id="3">' in content and '<note id="7">' in content
    assert content.endswith("Question: When is the delivery?")
    assert client.last_kwargs["output_config"]["format"]["schema"] == ai.ANSWER_SCHEMA


def test_not_found_gives_standard_message():
    client = FakeClient([answer_reply(False, "No idea", [3])])

    result = ai.answer_question("Who is the plumber?", NOTES, client)

    assert result == {"answer": "I couldn't find that in your notes.", "note_ids": []}


def test_unknown_duplicate_and_bool_ids_are_dropped():
    client = FakeClient([answer_reply(True, "Thursday.", [3, 3, 99, True, 7])])

    result = ai.answer_question("When?", NOTES, client)

    assert result["note_ids"] == [3, 7]


def test_answer_invalid_then_valid_retries_once():
    client = FakeClient([fake_response("nope"), answer_reply(True, "Thursday.", [3])])

    assert ai.answer_question("When?", NOTES, client)["answer"] == "Thursday."
    assert client.calls == 2


def test_answer_found_but_empty_counts_as_invalid():
    client = FakeClient([answer_reply(True, "  ", [3]), answer_reply(True, "", [3])])

    assert ai.answer_question("When?", NOTES, client) is None


def test_answer_api_failing_twice_returns_none():
    client = FakeClient([connection_error(), connection_error()])

    assert ai.answer_question("When?", NOTES, client) is None
