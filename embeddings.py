"""Embeddings for Smart Notes, from the Voyage AI API.

An embedding is a list of numbers (a "vector") that stands for the meaning of a text.
Texts that mean similar things get similar vectors, even when they share no words:
"wood delivery" lands close to "timber arrives". The Ask page uses this to find notes
by meaning, not only by matching words.

embed_texts() never raises: if anything goes wrong it returns None, so the app falls
back to keyword search and keeps working.
"""

import logging
import math
import os

import httpx2

API_URL = "https://api.voyageai.com/v1/embeddings"
MODEL = "voyage-4-lite"  # small, cheap and plenty for short notes
MAX_ATTEMPTS = 2  # the first try plus one retry, like ai.py
BATCH_SIZE = 100  # notes sent per request when embedding many at once

logger = logging.getLogger(__name__)


class EmbeddingsUnavailable(Exception):
    """Embeddings can't be made: no API key, or a reply we can't use."""


def _make_client():
    """An HTTP client that sends the Voyage API key with every request.

    Raises EmbeddingsUnavailable if VOYAGE_API_KEY isn't set (the feature is off).
    """
    api_key = os.getenv("VOYAGE_API_KEY")
    if not api_key:
        raise EmbeddingsUnavailable("VOYAGE_API_KEY is not set")
    return httpx2.Client(
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30.0,
    )


def _request_vectors(client, texts, input_type):
    """Make one API call and return one vector per text, in the same order."""
    response = client.post(
        API_URL,
        json={"input": texts, "model": MODEL, "input_type": input_type},
    )
    response.raise_for_status()  # turns 4xx/5xx replies into an HTTPStatusError
    try:
        items = response.json()["data"]
        # Each item says which input it belongs to ("index"); sort to be safe.
        vectors = [item["embedding"] for item in sorted(items, key=lambda i: i["index"])]
    except (ValueError, KeyError, TypeError) as error:
        raise EmbeddingsUnavailable("reply was not the expected JSON") from error
    if len(vectors) != len(texts):
        raise EmbeddingsUnavailable("reply had the wrong number of vectors")
    return vectors


def _describe_error(error):
    """'HTTPStatusError 429' or just 'ConnectTimeout': enough to debug, nothing secret.

    429 means "too many requests" (Voyage's rate limit), 401 a wrong API key.
    """
    if isinstance(error, httpx2.HTTPStatusError):
        return f"{type(error).__name__} {error.response.status_code}"
    return type(error).__name__


def _worth_retrying(error):
    """Timeouts, network problems, rate limits and server errors may work next time.

    A wrong API key (401) or a bad request (400) would fail the same way again.
    """
    if isinstance(error, httpx2.TransportError):  # includes timeouts
        return True
    if isinstance(error, httpx2.HTTPStatusError):
        status = error.response.status_code
        return status == 429 or status >= 500
    return False


def embed_texts(texts, input_type, client=None):
    """Turn each text into a vector. Return the list of vectors, or None on failure.

    input_type is "document" for notes and "query" for questions: Voyage prepares
    each kind slightly differently, which makes questions match notes better.
    Tests pass in a fake client so no real API call is made.
    """
    if not texts:
        return []
    if client is not None:
        return _embed_all(client, texts, input_type)
    try:
        own_client = _make_client()
    except EmbeddingsUnavailable as error:
        logger.info("Embeddings off: %s", error)
        return None
    # "with" closes the client's network connections when we're done.
    with own_client:
        return _embed_all(own_client, texts, input_type)


def _embed_all(client, texts, input_type):
    """Send the texts in batches. Return all vectors, or None if any batch failed."""
    vectors = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = _embed_batch(client, texts[start:start + BATCH_SIZE], input_type)
        if batch is None:
            return None
        vectors.extend(batch)
    return vectors


def _embed_batch(client, texts, input_type):
    """One batch, retried once if that could help. Return None on failure."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _request_vectors(client, texts, input_type)
        except (httpx2.HTTPError, EmbeddingsUnavailable) as error:
            # Log only the error type and HTTP status: never the API key or the note text.
            logger.warning(
                "Embedding attempt %d failed: %s", attempt, _describe_error(error)
            )
            if not _worth_retrying(error):
                break
    return None


def embed_question(question, client=None):
    """The vector for one question, or None if it couldn't be made."""
    vectors = embed_texts([question], "query", client)
    return vectors[0] if vectors else None


def note_text(note):
    """The text of a note that gets embedded: title, body, AI summary and tags."""
    parts = [note["title"], note["body"], note.get("summary") or ""]
    if note.get("tags"):
        parts.append("Tags: " + ", ".join(note["tags"]))
    return "\n".join(part for part in parts if part)


def cosine_similarity(a, b):
    """How alike two vectors are: 1 = same direction (same meaning), 0 = unrelated.

    Formula: (a · b) / (|a| × |b|). The "dot product" a · b multiplies the numbers pair
    by pair and adds them up; |a| is the vector's length. Dividing by the lengths means
    only the direction counts, not the size.
    """
    dot = sum(x * y for x, y in zip(a, b))
    length_a = math.sqrt(sum(x * x for x in a))
    length_b = math.sqrt(sum(y * y for y in b))
    if length_a == 0 or length_b == 0:
        return 0.0
    return dot / (length_a * length_b)
