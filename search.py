"""Search over notes, used by the Ask page.

Two ways to find notes, combined by hybrid_search():
- keyword search: notes that contain the question's words;
- semantic search: notes whose meaning is close to the question's, using
  embeddings (see embeddings.py), so "wood" can find a note about "timber".
"""

import re

from embeddings import cosine_similarity

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
# Notes less similar than this to the question are ignored, so an unrelated
# question finds nothing instead of the "least bad" notes. Tuned by trying real
# questions; raise it if Ask sends unrelated notes to Claude.
MIN_SIMILARITY = 0.3
# The standard constant in Reciprocal Rank Fusion. It stops the very top rank
# from counting far more than the next few.
RRF_K = 60


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


def semantic_search(query_vector, notes, model, limit=DEFAULT_LIMIT,
                    min_similarity=MIN_SIMILARITY):
    """Return up to `limit` notes closest in meaning to the question, best first.

    Only notes with a vector from the same model count: vectors from different
    models can't be compared. Notes below min_similarity are left out.
    """
    scored = []
    for note in notes:
        if note.get("embedding") is None or note.get("embedding_model") != model:
            continue
        similarity = cosine_similarity(query_vector, note["embedding"])
        if similarity >= min_similarity:
            scored.append((similarity, note))
    scored.sort(key=lambda pair: pair[0], reverse=True)  # stable: ties stay newest first
    return [note for _, note in scored[:limit]]


def hybrid_search(question, notes, query_vector=None, model=None, limit=DEFAULT_LIMIT):
    """Keyword and semantic search together, best match first.

    Without a query_vector (embeddings off or failed) this is plain keyword search.

    The two ranked lists are merged with Reciprocal Rank Fusion: a note at
    position `rank` (1 = top) in a list gets 1 / (RRF_K + rank) points from it, and
    its points from both lists are added up. A note found by both methods comes
    first. Ranks are used, not the scores, because keyword counts and similarities
    are on different scales.
    """
    keyword_ranked = search_notes(question, notes, limit=len(notes))
    if query_vector is None:
        return keyword_ranked[:limit]
    semantic_ranked = semantic_search(query_vector, notes, model, limit=len(notes))

    points = {}
    for ranked in (keyword_ranked, semantic_ranked):
        for rank, note in enumerate(ranked, start=1):
            points[note["id"]] = points.get(note["id"], 0) + 1 / (RRF_K + rank)

    found = [note for note in notes if note["id"] in points]  # keeps newest-first order
    found.sort(key=lambda note: points[note["id"]], reverse=True)
    return found[:limit]
