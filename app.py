"""Smart Notes web app (Flask routes).

Run locally with:  flask --app app run --debug
Settings come from environment variables; locally they are read from .env.
"""

import os
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import (
    Flask, abort, flash, redirect, render_template, request, session, url_for
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash

import ai
import db
import search
from timeago import time_ago
from weeks import due_status, week_label

HEADING_LENGTH = 60  # notes without a title use their first line, cut to this length
MAX_PROJECT_NAME = 60
LOCAL_HOSTS = ["localhost", "127.0.0.1"]
# Settings the app can't run safely without, and the environment variable for each.
REQUIRED_SETTINGS = {"SECRET_KEY": "SECRET_KEY", "PASSWORD_HASH": "APP_PASSWORD_HASH"}
# Pages anyone may see without logging in ("static" serves the CSS).
PUBLIC_ENDPOINTS = {"login", "static"}

HOW_TO_MAKE = {
    "SECRET_KEY": 'python3 -c "import secrets; print(secrets.token_hex(32))"',
    "APP_PASSWORD_HASH": "the password command in PLAN.md, section 3",
}


def load_settings(db_path=None):
    """Read the app's settings from environment variables.

    load_dotenv() first copies .env into the environment, but only for names that
    aren't set already. On Render there is no .env, so the real variables are used.
    """
    load_dotenv()
    on_render = bool(os.getenv("RENDER"))  # Render sets RENDER=true on its servers

    # Only answer requests addressed to this app. Blocks "DNS rebinding", where another
    # website points its own name at our server to get past the Origin check below.
    hosts = list(LOCAL_HOSTS)
    if os.getenv("RENDER_EXTERNAL_HOSTNAME"):  # e.g. smart-notes.onrender.com
        hosts.append(os.getenv("RENDER_EXTERNAL_HOSTNAME"))

    return {
        "ON_RENDER": on_render,
        # Signs the session cookie (flash messages, and later the login). It must stay
        # the same across restarts and stay secret, so it can't be made up here.
        "SECRET_KEY": os.getenv("SECRET_KEY"),
        # The login password, stored only as a hash (a one-way scramble of it).
        "PASSWORD_HASH": os.getenv("APP_PASSWORD_HASH"),
        # Stay logged in for 30 days instead of until the browser closes.
        "PERMANENT_SESSION_LIFETIME": timedelta(days=30),
        # Seconds to wait after a wrong password, so guessing is slow.
        "LOGIN_FAIL_DELAY": 1,
        "DATABASE": db_path or os.getenv("DATABASE_PATH", db.DEFAULT_DB_PATH),
        "TRUSTED_HOSTS": hosts,
        # Online the site is HTTPS only, so the cookie must never travel over plain HTTP.
        # Locally it's http://, where a Secure cookie would be dropped by the browser.
        "SESSION_COOKIE_SECURE": on_render,
        # Browsers won't attach the cookie to form posts started by other websites.
        "SESSION_COOKIE_SAMESITE": "Lax",
    }


def create_app(db_path=None, test_config=None):
    """Build the Flask app.

    Tests pass in a temporary database path, and test_config to override settings.
    """
    app = Flask(__name__)
    app.config.update(load_settings(db_path))
    if test_config:
        app.config.update(test_config)

    # Fail fast: refusing to start is better than running with a missing secret.
    for setting, env_name in REQUIRED_SETTINGS.items():
        if not app.config[setting]:
            raise RuntimeError(
                f"{env_name} is not set. Add it to .env (locally) or to the Render "
                f"environment. Make it with: {HOW_TO_MAKE[env_name]}"
            )

    if app.config["ON_RENDER"]:
        # Render's proxy receives the HTTPS request and passes it on as plain HTTP,
        # adding X-Forwarded-Proto: https. ProxyFix makes Flask trust that header, so
        # request.host_url starts with https:// and matches the browser's Origin.
        # Only on Render: without a proxy in front, anyone could send that header.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    db.init_db(app.config["DATABASE"])

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

    # Registered after the Origin check, so the login form is protected by it too.
    @app.before_request
    def require_login():
        """Send every request to the login page unless I'm logged in.

        One central check, so a new page can't forget to be protected.
        """
        if request.routing_exception is not None:
            # Flask already knows this request fails (e.g. 400 for an untrusted host),
            # and url_for() can't work for it. Let Flask show that error.
            return None
        if session.get("logged_in") or request.endpoint in PUBLIC_ENDPOINTS:
            return None
        return redirect(url_for("login", next=request.full_path.rstrip("?")))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        next_url = safe_next_url(request.args.get("next"))
        if session.get("logged_in"):
            return redirect(next_url)
        if request.method == "GET":
            return render_template("login.html")

        password = request.form.get("password", "")
        if not check_password_hash(app.config["PASSWORD_HASH"], password):
            time.sleep(app.config["LOGIN_FAIL_DELAY"])
            # 401 = unauthorized: the page is shown again with the error.
            return render_template("login.html", error="Wrong password."), 401

        session.clear()  # start a fresh session for the logged-in user
        session["logged_in"] = True
        session.permanent = True  # keep it for PERMANENT_SESSION_LIFETIME
        return redirect(next_url)

    # POST only, like Delete: a link (GET) must never change anything.
    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        flash("Logged out")
        return redirect(url_for("login"))

    @app.route("/")
    def index():
        """All open notes from every project, or a welcome screen when there are none."""
        if not db.list_projects(app.config["DATABASE"]):
            return render_template("index.html", projects=[])
        return render_notes_page()

    @app.route("/projects", methods=["POST"])
    def create_project():
        name = request.form.get("name", "").strip()
        if not name:
            flash("Please type a project name.", "error")
            return redirect(request.referrer or url_for("index"))
        project_id = db.create_project(app.config["DATABASE"], name[:MAX_PROJECT_NAME])
        return redirect(url_for("view_project", project_id=project_id))

    def render_notes_page(project=None, error=None, body=""):
        """Sidebar, note cards and the add-note box.

        With a project: that project's open notes. Without: "All notes" from every project.
        """
        db_path = app.config["DATABASE"]
        if project:
            notes = db.list_project_notes(db_path, project["id"])
        else:
            notes = db.list_open_notes(db_path)
        page = render_template(
            "notes.html",
            projects=db.list_projects(db_path),
            project=project,
            notes=notes,
            error=error,
            body=body,  # keeps what was typed when there is an error
        )
        # Status 400 = bad request: the page is shown again with the error message.
        return (page, 400) if error else page

    def save_note(project, body):
        """Save a note in a project, then let Claude analyse it. Return the note id."""
        db_path = app.config["DATABASE"]
        # Save first, so the note is kept even if the AI step fails.
        note_id = db.create_note(db_path, "", body, project_id=project["id"])
        note = db.get_note(db_path, note_id)

        # Notes have no title, so the project name gives Claude the context instead.
        analysis = ai.analyze_note(project["name"], body, note["created_at"])
        if analysis is not None:
            db.save_analysis(
                db_path, note_id, analysis["summary"], analysis["action_items"], analysis["tags"]
            )
        flash("Note saved ✓")
        return note_id

    @app.route("/project/<int:project_id>")
    def view_project(project_id):
        project = db.get_project(app.config["DATABASE"], project_id)
        if project is None:
            abort(404)
        return render_notes_page(project)

    @app.route("/project/<int:project_id>/notes", methods=["POST"])
    def add_note(project_id):
        """Add-note box on a project page."""
        project = db.get_project(app.config["DATABASE"], project_id)
        if project is None:
            abort(404)
        body = request.form.get("body", "").strip()
        if not body:
            return render_notes_page(project, error="Please type a note first.")
        save_note(project, body)
        return redirect(url_for("view_project", project_id=project_id))

    @app.route("/notes", methods=["POST"])
    def add_note_from_all_notes():
        """Add-note box on the All notes page, where a menu picks the project."""
        project = db.get_project(
            app.config["DATABASE"], request.form.get("project_id", type=int)
        )
        body = request.form.get("body", "").strip()
        if project is None:
            return render_notes_page(error="Please choose a project for the note.", body=body)
        if not body:
            return render_notes_page(error="Please type a note first.")
        save_note(project, body)
        return redirect(url_for("index"))

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


def safe_next_url(next_url):
    """Where to go after logging in: a page on this site, or home.

    Only accepts paths like "/ask". "//evil.com" or "https://evil.com" would send me
    to another site after logging in (an "open redirect"), so those go home instead.
    """
    if next_url and next_url.startswith("/") and not next_url.startswith(("//", "/\\")):
        return next_url
    return url_for("index")
