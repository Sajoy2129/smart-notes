"""Claude API calls for Smart Notes.

analyze_note() turns a rough note into a summary, action items and tags.
answer_question() answers a question using only the notes it is given.
Neither raises: if anything goes wrong they return None, so the app keeps working.
"""

import json
import logging
import os
from datetime import date, datetime

import anthropic

MODEL = "claude-sonnet-5-5"
MAX_ATTEMPTS = 2  # the first try plus one retry, as the spec asks
MAX_TAGS = 5
NOT_FOUND = "I couldn't find that in your notes."

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """You read rough notes (meeting, site visit or phone call notes) \
and return a short summary, the action items and tags.

Rules:
- Use only information that is in the note. Never invent tasks, owners or dates.
- summary: 2-3 sentences in plain, simple English.
- action_items: every task that needs doing.
  - task: what needs doing.
  - owner: the person responsible, only if the note says who. Otherwise null.
  - due_date: the deadline exactly as the note words it (e.g. "next Friday"). \
Otherwise null.
  - due_date_iso: that deadline as YYYY-MM-DD, worked out from the date the note \
was written. Null if there is no deadline or it isn't a single day.
- If there are no tasks, return an empty action_items list.
- tags: 2-5 short lowercase tags about the topic, e.g. "delivery", "painting", "client"."""

ANSWER_PROMPT = """You answer questions about the user's own notes. \
You are given some of their notes, each with an id.

Rules:
- Answer only from these notes. Don't use outside knowledge and don't guess.
- If the notes don't contain the answer, set found to false.
- Otherwise set found to true, answer in plain, simple English (a few sentences \
at most), and put the ids of the notes you used in note_ids."""

NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}

# The exact JSON shapes Claude must reply with (structured outputs).
NOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "owner": NULLABLE_STRING,
                    "due_date": NULLABLE_STRING,
                    "due_date_iso": NULLABLE_STRING,
                },
                "required": ["task", "owner", "due_date", "due_date_iso"],
                "additionalProperties": False,
            },
        },
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "action_items", "tags"],
    "additionalProperties": False,
}

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "answer": {"type": "string"},
        "note_ids": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["found", "answer", "note_ids"],
    "additionalProperties": False,
}


class InvalidReplyError(Exception):
    """Claude replied, but not with the JSON shape we need."""


# ---------- Shared helpers ----------

def _make_client():
    """Create the API client, reading the ANTHROPIC_API_KEY environment variable.

    Locally, create_app() has already copied it from .env into the environment.
    """
    # Without a key the SDK only fails later, with a TypeError, so check for it here.
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise anthropic.AnthropicError("ANTHROPIC_API_KEY is not set")
    # max_retries=0: we do our own single retry below, so the SDK shouldn't add more.
    return anthropic.Anthropic(max_retries=0, timeout=60.0)


def _ask_claude(client, system, user_message, schema):
    """Make one API call and return Claude's reply as Python data (parsed JSON)."""
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=system,
        messages=[{"role": "user", "content": user_message}],
        output_config={
            "effort": "low",  # short extraction/answer jobs don't need deep thinking
            "format": {"type": "json_schema", "schema": schema},
        },
        # If a safety check wrongly declines the request, retry on another model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        raise InvalidReplyError(f"reply stopped early: {response.stop_reason}")
    text = next((block.text for block in response.content if block.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise InvalidReplyError("reply was not valid JSON") from error
    if not isinstance(data, dict):
        raise InvalidReplyError("reply was not a JSON object")
    return data


def _worth_retrying(error):
    """Network problems, rate limits and server errors may work on a second try.

    A wrong API key or a bad request will fail the same way again, so skip those.
    """
    if isinstance(error, InvalidReplyError):
        return True
    if isinstance(error, anthropic.APIConnectionError):  # includes timeouts
        return True
    if isinstance(error, anthropic.APIStatusError):
        return error.status_code == 429 or error.status_code >= 500
    return False


def _call_with_retry(job_name, request, client=None):
    """Run request(client), retrying once if that could help. Return None on failure."""
    try:
        client = client or _make_client()
    except anthropic.AnthropicError as error:  # e.g. no API key found
        logger.warning("%s unavailable: %s", job_name, type(error).__name__)
        return None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return request(client)
        except (anthropic.AnthropicError, InvalidReplyError) as error:
            # Log only the error type: never the API key, notes or questions.
            logger.warning("%s attempt %d failed: %s", job_name, attempt, type(error).__name__)
            if not _worth_retrying(error):
                break
    return None


def _written_on(created_at):
    """'2026-10-18T10:00:00' -> 'Sunday 18 October 2026'."""
    return datetime.fromisoformat(created_at).strftime("%A %d %B %Y")


def _clean_text_or_none(value):
    """Return a stripped string, or None for null/empty values."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


# ---------- Note analysis ----------

def _clean_iso_date(value):
    """Keep due_date_iso only if it's a real YYYY-MM-DD date."""
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        return None


def _parse_analysis(data):
    """Check and clean Claude's analysis, or raise InvalidReplyError."""
    summary = data.get("summary")
    items = data.get("action_items")
    tags = data.get("tags")
    if not isinstance(summary, str) or not summary.strip():
        raise InvalidReplyError("summary missing")
    if not isinstance(items, list) or not isinstance(tags, list):
        raise InvalidReplyError("action_items or tags is not a list")

    action_items = []
    for item in items:
        if not isinstance(item, dict) or not _clean_text_or_none(item.get("task")):
            raise InvalidReplyError("action item without a task")
        action_items.append({
            "task": item["task"].strip(),
            "owner": _clean_text_or_none(item.get("owner")),
            "due_date": _clean_text_or_none(item.get("due_date")),
            "due_date_iso": _clean_iso_date(item.get("due_date_iso")),
        })

    clean_tags = []
    for tag in tags:
        if isinstance(tag, str) and tag.strip() and tag.strip().lower() not in clean_tags:
            clean_tags.append(tag.strip().lower())

    return {
        "summary": summary.strip(),
        "action_items": action_items,
        "tags": clean_tags[:MAX_TAGS],
    }


def analyze_note(title, body, created_at, client=None):
    """Ask Claude for a summary, action items and tags.

    Returns {"summary", "action_items", "tags"}, or None if it failed.
    Tests pass in a fake client so no real API call is made.
    """
    user_message = (
        f"Note written on: {_written_on(created_at)}\n"
        f"Title: {title}\n\n<note>\n{body}\n</note>"
    )

    def request(api_client):
        data = _ask_claude(api_client, ANALYSIS_PROMPT, user_message, NOTE_SCHEMA)
        return _parse_analysis(data)

    return _call_with_retry("AI analysis", request, client)


# ---------- Answering questions ----------

def _format_notes(notes):
    """Put each note in <note> tags with its id, so Claude can say which it used."""
    parts = []
    for note in notes:
        # Notes written inside a project have no title, so skip the empty line.
        title_line = f"Title: {note['title']}\n" if note["title"] else ""
        parts.append(
            f'<note id="{note["id"]}">\n'
            f"{title_line}"
            f"Written on: {_written_on(note['created_at'])}\n\n"
            f"{note['body']}\n"
            f"</note>"
        )
    return "\n\n".join(parts)


def _parse_answer(data, allowed_ids):
    """Check Claude's answer, or raise InvalidReplyError.

    Only ids of notes we actually sent are kept, so we never link to a note
    Claude made up.
    """
    found = data.get("found")
    answer = data.get("answer")
    note_ids = data.get("note_ids")
    if not isinstance(found, bool) or not isinstance(note_ids, list):
        raise InvalidReplyError("found or note_ids has the wrong type")
    if not found:
        return {"answer": NOT_FOUND, "note_ids": []}
    if not _clean_text_or_none(answer):
        raise InvalidReplyError("answer missing")

    used_ids = []
    for note_id in note_ids:
        # bool is a kind of int in Python (True == 1), so rule it out explicitly.
        is_int = isinstance(note_id, int) and not isinstance(note_id, bool)
        if is_int and note_id in allowed_ids and note_id not in used_ids:
            used_ids.append(note_id)
    if not used_ids:
        # The spec says every answer shows its sources; without any we can't do that.
        raise InvalidReplyError("answer has no valid note ids")
    return {"answer": answer.strip(), "note_ids": used_ids}


def answer_question(question, notes, client=None):
    """Answer a question using only the given notes.

    Returns {"answer", "note_ids"}, or None if the API failed.
    If the notes don't hold the answer, answer is NOT_FOUND and note_ids is empty.
    """
    # Notes first, question last: Claude does best with the question at the end.
    user_message = f"<notes>\n{_format_notes(notes)}\n</notes>\n\nQuestion: {question}"
    allowed_ids = {note["id"] for note in notes}

    def request(api_client):
        data = _ask_claude(api_client, ANSWER_PROMPT, user_message, ANSWER_SCHEMA)
        return _parse_answer(data, allowed_ids)

    return _call_with_retry("AI answer", request, client)
