# Smart Notes – Specification

## What it does
Smart Notes is a small web app for saving rough notes, such as meeting notes,
site visit notes or phone call notes. When I save a note, AI writes a short
summary, pulls out action items, and adds tags. I can also ask questions
across all my notes and get answers that show which notes they came from.

## Who uses it
Just me, on my own Mac. No login needed in version 1.

## Pages
- **Home (/)**: list of all notes, newest first. Each shows title, date,
  tags, and its action items as bullet points. A "New note" button at the top.
- **New note (/new)**: a form with a title and a large text box for the note.
  A "Save" button.
- **View note (/note/<id>)**: shows the summary at the top, then action
  items as a checklist, then tags, then the original note text.
  A "Delete" button.
- **Ask (/ask)**: a text box to ask a question about my notes. Shows the
  answer and links to the notes it used.

## What the AI does for each note
When a note is saved, call the Claude API once and get back JSON with:
- **summary**: 2–3 sentences
- **action_items**: a list, each with:
  - task (what needs doing)
  - owner (who, or null if not mentioned)
  - due_date (when, or null if not mentioned)
- **tags**: 2–5 short lowercase tags, for example "delivery", "painting", "client"

Rules for the AI:
- Only use information that is in the note. Never invent owners or dates.
- If there are no action items, return an empty list.
- Keep the summary in plain, simple English.

## Ask page rules
- Find the most relevant notes using simple keyword search.
- Send only those notes to Claude with the question.
- Claude must answer only from those notes.
- If the answer isn't in the notes, say: "I couldn't find that in your notes."
- Show which notes were used, with links.

## Data to store for each note
- id
- title
- original text
- created date and time
- summary
- action items (stored as JSON)
- tags (stored as JSON)

## Error handling
- If the Claude API fails when saving (no internet, wrong key, etc.),
  the note must still be saved. Show "AI summary not available" on the
  note page.
- If Claude returns invalid JSON, try once more. If it fails again,
  save the note without the AI parts.

## Safety
- The API key is stored in .env and never shown, logged, or committed.
- The database file (*.db) is not committed to GitHub.
- Only test with made-up or public notes, not real company or client
  information.

## Decisions
- Model: claude-sonnet-5-5
- Due dates: keep the text as written; when the note mentions a date, also
  work out the real date (from the note's created date) and show its week
  number, e.g. "next Friday (24 Oct, week 43)"
- Styling: custom CSS in static/app.css, following DESIGN.md (replaced Pico.css)
- Title and note text are both required
- Ask "Are you sure?" before deleting a note
- If the Claude API call fails (network error or invalid JSON), try once more
- Tests use pytest and never call the real API

## Not in version 1
- Marking action items as done
- A page listing all open action items
- Filtering by tag
- Editing notes
- "Regenerate summary" button
- Login or multiple users
- Putting the app online

## Version 1 is done when
- [ ] I can create, view, list and delete notes
- [ ] Every new note gets a summary, action items and tags
- [ ] A note with no tasks gets an empty action item list
- [ ] Notes still save when the API is unavailable
- [ ] The Ask page answers from my notes and admits when it can't find something
- [x] The code-reviewer agent finds no serious problems