"""Smart Notes web app (Flask routes).

Run with:  flask --app app run --debug
"""

from datetime import datetime

from flask import Flask, abort, redirect, render_template, request, url_for

import ai
import db


def create_app(db_path=db.DEFAULT_DB_PATH):
    """Build the Flask app. Tests pass in a temporary database path."""
    app = Flask(__name__)
    app.config["DATABASE"] = db_path
    db.init_db(db_path)

    @app.template_filter("nice_date")
    def nice_date(iso_text):
        """Show '2026-10-18T22:40:00' as '18 Oct 2026, 22:40'."""
        return datetime.fromisoformat(iso_text).strftime("%d %b %Y, %H:%M")

    @app.route("/")
    def index():
        notes = db.list_notes(app.config["DATABASE"])
        return render_template("index.html", notes=notes)

    @app.route("/new", methods=["GET", "POST"])
    def new_note():
        if request.method == "GET":
            return render_template("new.html", title="", body="", error=None)

        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        if not title or not body:
            # Show the form again, keeping what was typed, with status 400 (bad request).
            error = "Please fill in both the title and the note."
            return render_template("new.html", title=title, body=body, error=error), 400

        # Save first, so the note is kept even if the AI step fails.
        db_path = app.config["DATABASE"]
        note_id = db.create_note(db_path, title, body)
        note = db.get_note(db_path, note_id)

        analysis = ai.analyze_note(title, body, note["created_at"])
        if analysis is not None:
            db.save_analysis(
                db_path, note_id, analysis["summary"], analysis["action_items"], analysis["tags"]
            )
        return redirect(url_for("view_note", note_id=note_id))

    @app.route("/note/<int:note_id>")
    def view_note(note_id):
        note = db.get_note(app.config["DATABASE"], note_id)
        if note is None:
            abort(404)
        return render_template("note.html", note=note)

    # POST only: a plain link (GET) must never delete anything.
    @app.route("/note/<int:note_id>/delete", methods=["POST"])
    def delete_note(note_id):
        if not db.delete_note(app.config["DATABASE"], note_id):
            abort(404)
        return redirect(url_for("index"))

    return app
