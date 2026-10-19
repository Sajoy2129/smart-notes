# Smart Notes – Design

## Feel
Clean, calm and professional, like a modern work tool. Not playful.

## Colors
- Main color: deep navy #1E3A5F (buttons, links, top bar)
- Background: very light grey #F6F7F9
- Cards and boxes: white with a thin light grey border
- AI summary box: very light blue #EEF4FB
- Overdue: red #C0392B, due soon: orange #D68910, done: green #1E8449

## Text
- Font: system font (-apple-system, Segoe UI, sans-serif)
- Titles bold, dates and labels small and grey

## Layout
- Top bar: "Smart Notes" on the left; Projects and Ask links; "Ask your notes…" box on the right
- Content in a centered column, max width about 900px (1100px on project pages)
- Project pages: projects sidebar on the left (current project highlighted in
  navy, open-note count on the right, "+ New project" box below); on a phone
  the projects become a row of chips above the notes
- At the top of a project: a white "Type a note…" box with a Save button
- Notes shown as cards in a grid (3 across on a laptop, 1 on a phone): no
  heading, just the note text (up to 5 lines), date ("2 hours ago"), tags as
  pills, and a green outlined "✓ Complete" button
- Messages like "Note saved ✓" float in the top-right corner, so the page doesn't move

## Components
- Buttons: rounded corners, navy background, white text; delete button red
- Tags: small rounded pills, light grey background
- Action items: checkbox, task text, owner and due date as small chips
- AI summary: light blue box with a small "AI summary" label

## Behavior
- Spinner with "Claude is reading your note…" while AI works
- "Note saved ✓" message after saving, fades after 3 seconds
- Confirm before delete
- Friendly empty state when there are no notes
- Friendly error message if AI fails; the note still saves
- Works on a phone screen