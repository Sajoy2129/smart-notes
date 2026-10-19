"""Smart Notes web app (Flask routes).

Run with:  flask --app app run --debug
"""

import os
from datetime import datetime

from flask import Flask, abort, flash, redirect, render_template, request, url_for

import ai
import db
import search
from timeago import time_ago
from weeks import due_status, week_label

HEADING_LENGTH = 60  # notes without a title use their first line, cut to this length
MAX_PROJECT_NAME = 60


def create_app(db_path=db.DEFAULT_DB_PATH):
    """Build the Flask app. Tests pass in a temporary database path."""
    app = Flask(__name__)
    app.config["DATABASE"] = db_path
    # Only answer requests addressed to this Mac. Blocks "DNS rebinding", where another
    # website points its own name at 127.0.0.1 to get past the Origin check below.
    app.config["TRUSTED_HOSTS"] = ["localhost", "127.0.0.1"]
    # flash() messages are kept in a signed cookie, which needs a secret key. A random one
    # is fine here: it only means a message is lost if the server restarts mid-redirect.
    app.secret_key = os.urandom(32)
    db.init_db(db_path)

    @app.template_filter("nice_date")
    def nice_date(iso_text):
        """Show '2026-10-18T22:40:00' as '18 Oct 2026, 22:40'."""
        return datetime.fromisoformat(iso_text).strftime("%d %b %Y, %H:%M")

    @app.template_filter("note_heading")
    def note_heading(note):
        """A note's title, or its first line for notes written without one."""
        if note["title"]:
            return note["title"]
        first_line = next((line.strip() for line in note["body"].splitlines() if line.strip()), "")
        return first_line if len(first_line) <= HEADING_LENGTH else first_line[:HEADING_LENGTH] + "…"

    app.add_template_filter(week_label)
    app.add_template_filter(time_ago)
    app.add_template_filter(due_status)

    @app.errorhandler(404)
    def not_found(error):
        return render_template("404.html"), 404

    # CSRF protection: browsers send an Origin header with form posts. If it names
    # another website, that site is trying to act as you (e.g. delete notes), so refuse.
    @app.before_request
    def block_cross_site_posts():
        origin = request.headers.get("Origin")
        if request.method == "POST" and origin and origin != request.host_url.rstrip("/"):
            abort(403)

    @app.route("/")
    def index():
        """Open the first project, or show a welcome screen when there are none."""
        projects = db.list_projects(app.config["DATABASE"])
        if projects:
            return redirect(url_for("view_project", project_id=projects[0]["id"]))
        return render_template("index.html", projects=[])

    @app.route("/projects", methods=["POST"])
    def create_project():
        name = request.form.get("name", "").strip()
        if not name:
            flash("Please type a project name.", "error")
            return redirect(request.referrer or url_for("index"))
        project_id = db.create_project(app.config["DATABASE"], name[:MAX_PROJECT_NAME])
        return redirect(url_for("view_project", project_id=project_id))

    def render_project(project, body="", error=None):
        """The project page: sidebar, add-note box and the open notes as cards."""
        db_path = app.config["DATABASE"]
        return render_template(
            "project.html",
            projects=db.list_projects(db_path),
            project=project,
            notes=db.list_project_notes(db_path, project["id"]),
            body=body,
            error=error,
        )

    @app.route("/project/<int:project_id>")
    def view_project(project_id):
        project = db.get_project(app.config["DATABASE"], project_id)
        if project is None:
            abort(404)
        return render_project(project)

    @app.route("/project/<int:project_id>/notes", methods=["POST"])
    def add_note(project_id):
        db_path = app.config["DATABASE"]
        project = db.get_project(db_path, project_id)
        if project is None:
            abort(404)

        body = request.form.get("body", "").strip()
        if not body:
            # Status 400 = bad request. The page is shown again with a message.
            return render_project(project, error="Please type a note first."), 400

        # Save first, so the note is kept even if the AI step fails.
        note_id = db.create_note(db_path, "", body, project_id=project_id)
        note = db.get_note(db_path, note_id)

        # Notes have no title, so the project name gives Claude the context instead.
        analysis = ai.analyze_note(project["name"], body, note["created_at"])
        if analysis is not None:
            db.save_analysis(
                db_path, note_id, analysis["summary"], analysis["action_items"], analysis["tags"]
            )
        flash("Note saved ✓")
        return redirect(url_for("view_project", project_id=project_id))

    @app.route("/note/<int:note_id>")
    def view_note(note_id):
        db_path = app.config["DATABASE"]
        note = db.get_note(db_path, note_id)
        if note is None:
            abort(404)
        project = db.get_project(db_path, note["project_id"]) if note["project_id"] else None
        return render_template("note.html", note=note, project=project)

    # Asking uses POST because each question costs an API call; a GET could be
    # repeated by refreshes or link previews.
    @app.route("/ask", methods=["GET", "POST"])
    def ask():
        if request.method == "GET":
            return render_template("ask.html", question="")

        question = request.form.get("question", "").strip()
        if not question:
            return render_template(
                "ask.html", question="", error="Please type a question."
            ), 400

        notes = db.list_notes(app.config["DATABASE"])
        matches = search.search_notes(question, notes)
        if not matches:
            # Nothing matched: don't spend an API call, Claude has nothing to read.
            return render_template(
                "ask.html", question=question, answer=ai.NOT_FOUND, sources=[]
            )

        result = ai.answer_question(question, matches)
        if result is None:
            return render_template(
                "ask.html",
                question=question,
                error="The AI couldn't answer right now. These notes might help:",
                sources=matches,
            ), 503  # 503 = service unavailable

        sources = [note for note in matches if note["id"] in result["note_ids"]]
        return render_template(
            "ask.html", question=question, answer=result["answer"], sources=sources
        )

    def back_to_project(note):
        """Where to go after changing a note: its project, or home for older notes."""
        if note["project_id"]:
            return redirect(url_for("view_project", project_id=note["project_id"]))
        return redirect(url_for("index"))

    # POST only: a plain link (GET) must never change anything.
    @app.route("/note/<int:note_id>/complete", methods=["POST"])
    def complete_note(note_id):
        db_path = app.config["DATABASE"]
        note = db.get_note(db_path, note_id)
        if note is None:
            abort(404)
        db.complete_note(db_path, note_id)
        flash("Note completed ✓")
        return back_to_project(note)

    @app.route("/note/<int:note_id>/delete", methods=["POST"])
    def delete_note(note_id):
        db_path = app.config["DATABASE"]
        note = db.get_note(db_path, note_id)
        if note is None:
            abort(404)
        db.delete_note(db_path, note_id)
        return back_to_project(note)

    return app
