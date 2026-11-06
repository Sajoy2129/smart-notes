from search import hybrid_search, search_notes, semantic_search, tokenize

MODEL = "test-model"


def make_note(note_id, title, body, tags=(), summary=None, vector=None, model=MODEL):
    return {
        "id": note_id, "title": title, "body": body, "tags": list(tags), "summary": summary,
        "embedding": vector, "embedding_model": model if vector else None,
    }


def ids(notes):
    return [note["id"] for note in notes]


def test_tokenize_lowercases_and_drops_stop_words_and_punctuation():
    assert tokenize("When is the Timber delivery?") == ["timber", "delivery"]


def test_tokenize_handles_none():
    assert tokenize(None) == []


def test_no_matching_words_returns_empty_list():
    notes = [make_note(1, "Site visit", "Painted the hallway.")]

    assert search_notes("scaffolding", notes) == []


def test_question_of_only_stop_words_returns_empty_list():
    notes = [make_note(1, "What is this", "It is what it is.")]

    assert search_notes("what is it?", notes) == []


def test_title_match_ranks_above_single_body_match():
    notes = [
        make_note(1, "Phone call", "Asked about the delivery."),
        make_note(2, "Delivery update", "Moved to Thursday."),
    ]

    assert ids(search_notes("delivery", notes)) == [2, 1]


def test_tags_and_summary_are_searched():
    notes = [
        make_note(1, "Call", "Rang them.", tags=["painting"]),
        make_note(2, "Visit", "Walked around.", summary="Scaffolding is booked."),
    ]

    assert ids(search_notes("painting", notes)) == [1]
    assert ids(search_notes("scaffolding", notes)) == [2]


def test_matching_is_case_insensitive():
    notes = [make_note(1, "Call", "PRIYA sends the sample.")]

    assert ids(search_notes("priya", notes)) == [1]


def test_equal_scores_keep_newest_first_order():
    notes = [make_note(2, "Call", "paint"), make_note(1, "Call", "paint")]

    assert ids(search_notes("paint", notes)) == [2, 1]


def test_returns_at_most_the_limit():
    notes = [make_note(i, "Delivery", "delivery") for i in range(10)]

    assert len(search_notes("delivery", notes)) == 5
    assert len(search_notes("delivery", notes, limit=2)) == 2


# ---------- Semantic search ----------
# Tiny 2-number vectors stand in for real 1024-number ones. Same maths, easier to read:
# [1, 0] is "about timber", [0, 1] is "about painting".

TIMBER = [1.0, 0.0]
PAINT = [0.0, 1.0]


def test_semantic_search_ranks_by_meaning():
    notes = [
        make_note(1, "Painting", "Hallway done.", vector=PAINT),
        make_note(2, "Timber call", "Arrives Thursday.", vector=TIMBER),
        make_note(3, "Mixed", "Both.", vector=[0.7, 0.7]),
    ]

    # "When does the wood arrive?" has no word in common with note 2, but means the same.
    assert ids(semantic_search([0.9, 0.1], notes, MODEL)) == [2, 3]  # note 1 too far off


def test_semantic_search_skips_notes_without_vectors_or_from_other_models():
    notes = [
        make_note(1, "No vector", "a"),
        make_note(2, "Other model", "b", vector=TIMBER, model="old-model"),
        make_note(3, "Same model", "c", vector=TIMBER),
    ]

    assert ids(semantic_search(TIMBER, notes, MODEL)) == [3]


def test_semantic_search_threshold_drops_weak_matches():
    notes = [make_note(1, "Painting", "Hallway.", vector=PAINT)]

    assert semantic_search(TIMBER, notes, MODEL) == []
    assert ids(semantic_search(TIMBER, notes, MODEL, min_similarity=-1)) == [1]


def test_hybrid_without_query_vector_is_keyword_search():
    notes = [
        make_note(1, "Phone call", "Asked about the delivery.", vector=TIMBER),
        make_note(2, "Delivery update", "Moved to Thursday.", vector=PAINT),
    ]

    assert hybrid_search("delivery", notes) == search_notes("delivery", notes)


def test_hybrid_finds_notes_by_meaning_without_shared_words():
    notes = [make_note(1, "Timber call", "Arrives Thursday.", vector=TIMBER)]

    assert search_notes("wood", notes) == []
    assert ids(hybrid_search("wood", notes, TIMBER, MODEL)) == [1]


def test_hybrid_puts_notes_found_both_ways_first():
    notes = [
        make_note(1, "Delivery invoice", "Paid the delivery.", vector=PAINT),  # words only
        make_note(2, "Timber", "Wood arrives.", vector=[0.8, 0.2]),  # meaning only
        make_note(3, "Timber delivery", "Thursday.", vector=TIMBER),  # both
    ]

    result = ids(hybrid_search("delivery", notes, TIMBER, MODEL))

    assert result[0] == 3
    assert sorted(result) == [1, 2, 3]


def test_hybrid_returns_at_most_the_limit():
    notes = [make_note(i, "Delivery", "delivery", vector=TIMBER) for i in range(10)]

    assert len(hybrid_search("delivery", notes, TIMBER, MODEL)) == 5
