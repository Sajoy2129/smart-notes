"""Tests for settings read from environment variables (on my Mac and on the server).

monkeypatch.setenv() sets an environment variable for one test only.
"""

import pytest

import db
from app import create_app
from tests.conftest import TEST_PASSWORD, TEST_PASSWORD_HASH

SERVER_HOST = "3-120-45-67.sslip.io"


@pytest.fixture
def local_env(monkeypatch):
    """The environment variables the app needs, as on my Mac."""
    monkeypatch.setenv("SECRET_KEY", "from-env")
    monkeypatch.setenv("APP_PASSWORD_HASH", TEST_PASSWORD_HASH)


@pytest.fixture
def on_server(local_env, monkeypatch):
    """Pretend we're running on the server, behind Caddy."""
    monkeypatch.setenv("BEHIND_PROXY", "true")
    monkeypatch.setenv("PUBLIC_HOSTNAME", SERVER_HOST)


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
    path = str(tmp_path / "server.db")
    monkeypatch.setenv("DATABASE_PATH", path)

    app = create_app()

    assert app.config["DATABASE"] == path
    assert (tmp_path / "server.db").exists()  # init_db created it


POSTGRES_URL = "postgresql://notes:secret@db.example.com:5432/smart_notes"


@pytest.fixture
def init_db_calls(monkeypatch):
    """Replace db.init_db with a stand-in that records what it was given.

    So these tests check which database the app picks without needing a real
    PostgreSQL server to connect to.
    """
    calls = []
    monkeypatch.setattr(db, "init_db", calls.append)
    return calls


def test_database_url_selects_postgres(local_env, monkeypatch, init_db_calls):
    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)

    app = create_app()

    assert app.config["DATABASE"] == POSTGRES_URL
    assert init_db_calls == [POSTGRES_URL]  # the tables are made in PostgreSQL


def test_database_url_wins_over_database_path(local_env, monkeypatch, init_db_calls):
    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("DATABASE_PATH", "/home/ubuntu/data/smart_notes.db")

    app = create_app()

    assert app.config["DATABASE"] == POSTGRES_URL


def test_empty_database_url_means_sqlite(local_env, monkeypatch, init_db_calls):
    # "DATABASE_URL=" with nothing after it in .env must not count as set.
    monkeypatch.setenv("DATABASE_URL", "")

    app = create_app()

    assert app.config["DATABASE"] == db.DEFAULT_DB_PATH


# ---------- Production safety ----------

def test_debug_is_off(db_path, local_env):
    # gunicorn never turns debug on; only `flask run --debug` does, on my Mac.
    assert create_app(db_path).debug is False


def test_locally_the_cookie_works_over_plain_http(db_path, local_env):
    app = create_app(db_path)

    assert app.config["SESSION_COOKIE_SECURE"] is False
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_on_the_server_the_cookie_is_https_only(db_path, on_server):
    assert create_app(db_path).config["SESSION_COOKIE_SECURE"] is True


def test_behind_proxy_must_say_true(db_path, local_env, monkeypatch):
    # Anything other than "true" (like "false" or "0") leaves the proxy settings off.
    monkeypatch.setenv("BEHIND_PROXY", "false")

    assert create_app(db_path).config["SESSION_COOKIE_SECURE"] is False


# ---------- The server's address and HTTPS proxy ----------

def test_server_address_is_allowed(db_path, on_server):
    client = create_app(db_path).test_client()

    response = client.get("/login", base_url=f"https://{SERVER_HOST}")

    assert response.status_code == 200


def test_server_address_is_not_allowed_elsewhere(db_path, local_env):
    client = create_app(db_path).test_client()

    response = client.get("/login", base_url=f"https://{SERVER_HOST}")

    assert response.status_code == 400


def proxied_post(client, path, data):
    """A form post as Caddy delivers it: plain HTTP to the app, with
    X-Forwarded-Proto: https, while the browser's Origin says https://."""
    return client.post(
        path,
        data=data,
        base_url=f"http://{SERVER_HOST}",
        headers={"Origin": f"https://{SERVER_HOST}", "X-Forwarded-Proto": "https"},
    )


def test_login_and_add_note_through_the_proxy(db_path, on_server):
    # ProxyFix makes the https Origin match, so neither post is blocked with 403.
    app = create_app(db_path)
    project_id = make_project(app)
    client = app.test_client()

    login = proxied_post(client, "/login", {"password": TEST_PASSWORD})
    add = proxied_post(client, f"/project/{project_id}/notes", {"body": "Rang the client."})

    assert login.status_code == 302
    assert add.status_code == 302
    assert len(db.list_notes(db_path)) == 1  # really saved, not sent to /login


def test_forwarded_header_is_ignored_without_a_proxy(db_path, local_env):
    # Locally there's no proxy, so a client claiming "https" must not be believed.
    client = create_app(db_path).test_client()

    response = client.post(
        "/login",
        data={"password": TEST_PASSWORD},
        base_url="http://localhost",
        headers={"Origin": "https://localhost", "X-Forwarded-Proto": "https"},
    )

    assert response.status_code == 403
