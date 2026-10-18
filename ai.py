"""Claude API calls for Smart Notes.

analyze_note() turns a rough note into a summary, action items and tags.
It never raises: if anything goes wrong it returns None, so the caller
can still save the note without the AI parts.
"""

import json
import logging
from datetime import date, datetime

import anthropic
from dotenv import load_dotenv

MODEL = "claude-sonnet-5-5"
MAX_ATTEMPTS = 2  # the first try plus one retry, as the spec asks
MAX_TAGS = 5

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You read rough notes (meeting, site visit or phone call notes) \
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

NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}

# The exact JSON shape Claude must reply with (structured outputs).
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


class InvalidReplyError(Exception):
    """Claude replied, but not with the JSON shape we need."""


def _make_client():
    """Create the API client, reading ANTHROPIC_API_KEY from .env."""
    load_dotenv()
    # max_retries=0: we do our own single retry below, so the SDK shouldn't add more.
    return anthropic.Anthropic(max_retries=0, timeout=60.0)


def _build_user_message(title, body, created_at):
    written_on = datetime.fromisoformat(created_at).strftime("%A %d %B %Y")
    return f"Note written on: {written_on}\nTitle: {title}\n\n<note>\n{body}\n</note>"


def _clean_text_or_none(value):
    """Return a stripped string, or None for null/empty values."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _clean_iso_date(value):
    """Keep due_date_iso only if it's a real YYYY-MM-DD date."""
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        return None


def _parse_reply(text):
    """Turn Claude's reply text into a clean dict, or raise InvalidReplyError."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise InvalidReplyError("reply was not valid JSON") from error

    if not isinstance(data, dict):
        raise InvalidReplyError("reply was not a JSON object")
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


def _request_analysis(client, title, body, created_at):
    """Make one API call and return the parsed result."""
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_message(title, body, created_at)}],
        output_config={
            "effort": "low",  # a short extraction job doesn't need deep thinking
            "format": {"type": "json_schema", "schema": NOTE_SCHEMA},
        },
        # If a safety check wrongly declines the request, retry on another model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        raise InvalidReplyError(f"reply stopped early: {response.stop_reason}")
    text = next((block.text for block in response.content if block.type == "text"), "")
    return _parse_reply(text)


def analyze_note(title, body, created_at, client=None):
    """Ask Claude for a summary, action items and tags.

    Returns {"summary", "action_items", "tags"}, or None if it failed twice
    (or once with an error that retrying won't fix).
    Tests pass in a fake client so no real API call is made.
    """
    try:
        client = client or _make_client()
    except anthropic.AnthropicError as error:  # e.g. no API key found
        logger.warning("AI analysis unavailable: %s", type(error).__name__)
        return None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _request_analysis(client, title, body, created_at)
        except (anthropic.AnthropicError, InvalidReplyError) as error:
            # Log only the error type: never the API key or the note text.
            logger.warning("AI analysis attempt %d failed: %s", attempt, type(error).__name__)
            if not _worth_retrying(error):
                break
    return None
