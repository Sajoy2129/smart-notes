"""Tests for settings read from environment variables (local and on Render).

monkeypatch.setenv() sets an environment variable for one test only.
"""

import pytest

import db
from app import create_app
from tests.conftest import TEST_PASSWORD, TEST_PASSWORD_HASH

RENDER_HOST = "smart-notes.onrender.com"


@pytest.fixture
def local_env(monkeypatch):
    """The environment variables the app needs, as on my Mac."""
    monkeypatch.setenv("SECRET_KEY", "from-env")
    monkeypatch.setenv("APP_PASSWORD_HASH", TEST_PASSWORD_HASH)


@pytest.fixture
def on_render(local_env, monkeypatch):
    """Pretend we're running on Render, with the variables Render sets itself."""
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", RENDER_HOST)


def make_project(app):
    return db.create_project(app.config["DATABASE"], "Harbour Road")


# ---------- Required secrets ----------

def test_missing_secret_key_stops_the_app(db_path, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD_HASH", TEST_PASSWORD_HASH)

    with pytest.raises(RuntimeError, match="SECRET_KEY is not set"):
        create_app(db_path)


def test_missing_password_hash_stops_the_app(db_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "s")

    with pytest.raises(RuntimeError, match="APP_PASSWORD_HASH is not set"):
        create_app(db_path)


def test_secrets_come_from_the_environment(db_path, local_env):
    app = create_app(db_path)

    assert app.secret_key == "from-env"
    assert app.config["PASSWORD_HASH"] == TEST_PASSWORD_HASH


# ---------- Database path ----------

def test_database_path_comes_from_the_environment(tmp_path, local_env, monkeypatch):
    path = str(tmp_path / "render.db")
    monkeypatch.setenv("DATABASE_PATH", path)

    app = create_app()

    assert app.config["DATABASE"] == path
    assert (tmp_path / "render.db").exists()  # init_db created it


# ---------- Production safety ----------

def test_debug_is_off(db_path, local_env):
    # gunicorn never turns debug on; only `flask run --debug` does, on my Mac.
    assert create_app(db_path).debug is False


def test_locally_the_cookie_works_over_plain_http(db_path, local_env):
    app = create_app(db_path)

    assert app.config["SESSION_COOKIE_SECURE"] is False
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_on_render_the_cookie_is_https_only(db_path, on_render):
    assert create_app(db_path).config["SESSION_COOKIE_SECURE"] is True


# ---------- Render's address and HTTPS proxy ----------

def test_render_address_is_allowed(db_path, on_render):
    client = create_app(db_path).test_client()

    response = client.get("/login", base_url=f"https://{RENDER_HOST}")

    assert response.status_code == 200


def test_render_address_is_not_allowed_elsewhere(db_path, local_env):
    client = create_app(db_path).test_client()

    response = client.get("/login", base_url=f"https://{RENDER_HOST}")

    assert response.status_code == 400


def render_post(client, path, data):
    """A form post as Render delivers it: plain HTTP to the app, with
    X-Forwarded-Proto: https, while the browser's Origin says https://."""
    return client.post(
        path,
        data=data,
        base_url=f"http://{RENDER_HOST}",
        headers={"Origin": f"https://{RENDER_HOST}", "X-Forwarded-Proto": "https"},
    )


def test_login_and_add_note_through_render_proxy(db_path, on_render):
    # ProxyFix makes the https Origin match, so neither post is blocked with 403.
    app = create_app(db_path)
    project_id = make_project(app)
    client = app.test_client()

    login = render_post(client, "/login", {"password": TEST_PASSWORD})
    add = render_post(client, f"/project/{project_id}/notes", {"body": "Rang the client."})

    assert login.status_code == 302
    assert add.status_code == 302
    assert len(db.list_notes(db_path)) == 1  # really saved, not sent to /login


def test_forwarded_header_is_ignored_without_render(db_path, local_env):
    # Locally there's no proxy, so a client claiming "https" must not be believed.
    client = create_app(db_path).test_client()

    response = client.post(
        "/login",
        data={"password": TEST_PASSWORD},
        base_url="http://localhost",
        headers={"Origin": "https://localhost", "X-Forwarded-Proto": "https"},
    )

    assert response.status_code == 403
