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
- Top bar: "Smart Notes" on the left; Notes, New Note, Ask links; search box on the right
- Content in a centered column, max width about 900px
- Notes listed as rows: title, date ("2 hours ago"), tags as pills

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