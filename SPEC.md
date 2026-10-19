# Smart Notes – Specification

## What it does
Smart Notes is a small web app for saving rough notes, such as meeting notes,
site visit notes or phone call notes. When I save a note, AI writes a short
summary, pulls out action items, and adds tags. I can also ask questions
across all my notes and get answers that show which notes they came from.

## Who uses it
Just me. Version 1 ran only on my own Mac. It is now also online (Render),
so every page needs a login: one password, no usernames and no sign-up.
- **Log in (/login)**: a password box. A wrong password waits 1 second, then
  says "Wrong password." After logging in I go back to the page I asked for,
  and I stay logged in for 30 days.
- **Log out**: a button in the top bar.

## Pages
- **Home (/) – All notes**: open notes from every project as cards, newest
  first, each labelled with its project. Below the cards, a box to add a note
  with a menu to choose its project. With no projects yet, shows a welcome
  message.
- **Projects sidebar**: on the left, a list of my projects (A–Z, with how
  many open notes each has) and a box to add a new project.
- **Project (/project/<id>)**: the project's open notes as cards, newest
  first, then a box at the bottom to add a note (no title needed). Each card
  shows the note text, date, tags and a "Complete" button.
- **View note (/note/<id>)**: shows the summary at the top, then action
  items as a checklist, then tags, then the original note text.
  "Complete" and "Delete" buttons, and a link back to the project.
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

## Data to store for each project
- id
- name
- created date and time

## Data to store for each note
- id
- project it belongs to
- title (empty for notes written inside a project; older notes keep theirs)
- original text
- created date and time
- summary
- action items (stored as JSON)
- tags (stored as JSON)
- completed date and time (empty while the note is open)

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
- Notes belong to a project; only the note text is required (no title).
  Claude gets the project name as context instead of a title
- Completing a note hides it from its project but keeps it in the database
  (the Ask page can still find it)
- Notes from before projects existed were moved into a "General" project
- Ask "Are you sure?" before deleting a note
- If the Claude API call fails (network error or invalid JSON), try once more
- Tests use pytest and never call the real API

## Not in version 1
- Marking single action items as done (a whole note can be completed)
- Seeing or reopening completed notes
- Renaming or deleting projects
- A page listing all open action items
- Filtering by tag
- Editing notes
- "Regenerate summary" button
- Login or multiple users
- Putting the app online

## Version 1 is done when
- [x] I can create projects, and create, view, list, complete and delete notes
- [x] Every new note gets a summary, action items and tags
- [x] A note with no tasks gets an empty action item list
- [x] Notes still save when the API is unavailable
- [x] The Ask page answers from my notes and admits when it can't find something
- [x] The code-reviewer agent finds no serious problems