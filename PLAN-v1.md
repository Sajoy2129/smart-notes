# Smart Notes – Version 1 Plan

## Context
`SPEC.md` describes Smart Notes, a small Flask web app for your own Mac. You write rough notes,
Claude summarizes each one and pulls out action items and tags, and you can ask questions across
all your notes. The project has only the spec, `.gitignore` (`.env`, `.venv`, `*.db`),
`requirements.txt` (Flask, anthropic, python-dotenv) and a `.venv`. There's no code yet.

The first step of implementation copies this plan into the repo as `PLAN.md` and commits it.
After that we build in small steps, and each step ends with a working app and a git commit.

## Decisions (from our Q&A, added to SPEC.md in Step 0)
- **Model:** `claude-sonnet-5-5`, set once as a constant in `ai.py`.
- **Due dates:** keep the text exactly as written (`due_date`). Claude also returns
  `due_date_iso` (YYYY-MM-DD), worked out from the note's created date when the note mentions a
  date, for example "next Friday". Otherwise it's null. **Python** then calculates the ISO week
  number with `date.isocalendar()`, which is reliable, and the page shows
  "next Friday (24 Oct, week 43)". If the note has no date, everything stays null, so nothing is
  invented.
- **Styling:** Pico.css from a CDN link in `base.html`.
- **Extras:** pytest tests with a mocked API, a delete confirmation, one retry on network errors
  as well as invalid JSON, and title and text required.
- **My defaults** (not asked):
  - SQLite through Python's built-in `sqlite3` module.
  - An empty `summary` (NULL) means "AI summary not available".
  - Ask sends the top 5 matching notes to Claude.
  - If no note matches, Ask skips the API call and shows "I couldn't find that in your notes."

## File layout
```
app.py            # Flask routes only (thin)
db.py             # SQLite: init_db, create_note, get_note, list_notes, delete_note
ai.py             # Claude calls: analyze_note(), answer_question(), JSON parsing + retry
search.py         # keyword search: tokenize, score notes, return top N
weeks.py          # due_date_iso -> week number helper
templates/        # base.html, index.html, new.html, note.html, ask.html
tests/            # test_db.py, test_ai.py, test_search.py, test_app.py, conftest.py
```

## Steps (one commit each)
0. **Housekeeping.** Copy this plan to `PLAN.md` and add the decisions to `SPEC.md`. Add `pytest`
   to `requirements.txt` and install it into `.venv`. Commit `.gitignore` and `requirements.txt`.
1. **Database (`db.py`).** Create a `notes` table with these columns: id, title, body,
   created_at, summary, action_items (JSON text), tags (JSON text). Write small CRUD functions
   (create, read, list, delete) and tests in `tests/test_db.py` that use a temporary database file.
2. **Basic pages without AI.** Create `app.py`, the templates and Pico.css, with routes for `/`,
   `/new` (GET and POST, showing an error if the title or text is empty), `/note/<id>` and
   `POST /note/<id>/delete` (with a JS `confirm()` popup). A missing id returns a 404 page. Write
   tests with Flask's test client.
3. **AI analysis (`ai.py`).**
   - `analyze_note(title, body, created_at)` loads the API key with `load_dotenv()` and builds a
     prompt that includes the spec's rules ("only use what's in the note", empty list if no
     tasks, plain English) and today's date for working out due dates.
   - It parses the JSON reply and checks the shape: summary is a string, action_items is a list,
     and tags is a list of 2–5 lowercase strings.
   - If the JSON is invalid or the API call fails (`anthropic.APIError`), it retries once. If the
     second try also fails, it returns `None`.
   - It never logs the key or the full request.
   - Tests replace the real API with a fake client (a *mock*), so they cost nothing and don't
     need internet. Cases: valid JSON, invalid JSON then valid, invalid twice, API error twice,
     and a note with no tasks.
4. **Wire AI into saving.** `POST /new` saves the note first and then calls `analyze_note`. If
   that returns `None`, the note stays saved without AI fields. The note page shows "AI summary
   not available" when `summary` is NULL. Write a test that confirms the note is saved when the
   API fails.
5. **Week numbers (`weeks.py`).** `week_label(iso_date)` returns, for example, "24 Oct, week 43".
   It's used in `note.html`. Write tests for normal dates, null and invalid strings, including a
   year-boundary case.
6. **Ask page.**
   - `search.py` lowercases the question, splits it into words, removes common words like
     "the"/"a"/"what", counts matches in the title, body and tags, and returns the top 5.
   - `answer_question(question, notes)` sends those notes with their ids and tells Claude to
     answer only from them, or reply exactly "I couldn't find that in your notes."
   - `/ask` shows the answer and links to the notes it used.
   - Tests cover search ranking, the zero-match case (no API call) and the mocked answer.
7. **Review and finish.** Run the `code-reviewer` agent and fix any serious findings. Tick the
   "done" checklist in `SPEC.md`.

## Verification
- `source .venv/bin/activate && pytest -v` runs all tests with no real API calls.
- Manual run: `flask --app app run --debug`, then open http://127.0.0.1:5000. Try these with
  made-up notes:
  - A meeting note with tasks, owners and "next Friday", to check the summary, the checklist and
    the week number.
  - A note with no tasks, to check that it gets an empty list.
  - Rename `.env` temporarily, to check that the note still saves and shows "AI summary not
    available".
  - Ask a question that's answered in the notes and one that isn't.
- `git status` never shows `.env` or `*.db`.
