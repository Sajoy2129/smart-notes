from search import search_notes, tokenize


def make_note(note_id, title, body, tags=(), summary=None):
    return {"id": note_id, "title": title, "body": body, "tags": list(tags), "summary": summary}


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
