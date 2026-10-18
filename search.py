"""Simple keyword search over notes, used by the Ask page."""

import re

# Common words that appear in almost every question, so they don't help find notes.
STOP_WORDS = {
    "a", "about", "all", "an", "and", "any", "are", "as", "at", "be", "by", "can",
    "did", "do", "does", "for", "from", "has", "have", "how", "i", "in", "is", "it",
    "me", "my", "of", "on", "or", "our", "so", "that", "the", "their", "there",
    "this", "to", "was", "we", "were", "what", "when", "where", "which", "who",
    "why", "will", "with", "you",
}

TITLE_OR_TAG_WEIGHT = 3  # a word in the title or tags counts more than one in the body
DEFAULT_LIMIT = 5


def tokenize(text):
    """Split text into lowercase words, dropping punctuation and stop words."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [word for word in words if word not in STOP_WORDS]


def _score(note, query_words):
    """How well one note matches the question's words (0 = no match)."""
    title_words = set(tokenize(note["title"]))
    tag_words = set(tokenize(" ".join(note["tags"])))
    body_words = tokenize(f"{note['body']} {note['summary'] or ''}")

    score = 0
    for word in query_words:
        if word in title_words or word in tag_words:
            score += TITLE_OR_TAG_WEIGHT
        score += body_words.count(word)
    return score


def search_notes(question, notes, limit=DEFAULT_LIMIT):
    """Return up to `limit` notes that match the question, best match first.

    Notes with the same score keep their original order (newest first).
    """
    query_words = set(tokenize(question))
    scored = [(_score(note, query_words), note) for note in notes]
    matches = [pair for pair in scored if pair[0] > 0]
    matches.sort(key=lambda pair: pair[0], reverse=True)
    return [note for _, note in matches[:limit]]
