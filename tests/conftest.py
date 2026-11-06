"""Shared pytest fixtures.

A fixture is a helper pytest runs before a test and passes in by name.

Tests use a temporary SQLite file. To run them on PostgreSQL instead:
    TEST_DATABASE_URL=postgresql://localhost/smart_notes_test pytest
"""

import os

import anthropic
import pytest
from werkzeug.security import generate_password_hash

import ai
import app as app_module
import db
import embeddings

TEST_PASSWORD = "correct horse battery staple"
# Real password hashes are slow on purpose, to make guessing expensive. Tests log in
# hundreds of times, so they use a fast method. Never use this for a real password.
TEST_PASSWORD_HASH = generate_password_hash(TEST_PASSWORD, method="pbkdf2:sha256:1")
TEST_SETTINGS = {
    "SECRET_KEY": "test-secret-key",
    "PASSWORD_HASH": TEST_PASSWORD_HASH,
    "LOGIN_FAIL_DELAY": 0,  # don't make the tests wait
}

# Environment variables the app reads. Cleared for every test, so a test never
# depends on what's set on the machine running it.
APP_ENV_VARS = [
    "SECRET_KEY", "APP_PASSWORD_HASH", "DATABASE_PATH", "BEHIND_PROXY", "PUBLIC_HOSTNAME",
    "AI_DAILY_LIMIT", "DATABASE_URL", "VOYAGE_API_KEY",
]

# Set it to run every test that uses db_path on PostgreSQL instead of SQLite.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def _test_database_name(url):
    """The database the URL really connects to, refusing any not ending in "_test".

    Every test deletes all the tables, so a real database must never be used here.
    The name is read the way PostgreSQL reads it: a "?dbname=..." at the end of the
    URL overrides the name before it. The error names only the database, never the
    URL, which holds the password.
    """
    from psycopg.conninfo import conninfo_to_dict

    name = conninfo_to_dict(url).get("dbname", "")
    if not name.endswith("_test"):
        raise pytest.UsageError(
            f"TEST_DATABASE_URL points at the database {name!r}. Tests delete every "
            "table, so its name must end with '_test', e.g. smart_notes_test."
        )
    return name


def pytest_report_header():
    """Shown at the top of the pytest output, so I can see which database was used."""
    if TEST_DATABASE_URL:
        return f"database: PostgreSQL ({_test_database_name(TEST_DATABASE_URL)})"
    return "database: SQLite (a temporary file per test)"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Runs before every test: ignore the real .env and the app's environment variables."""
    monkeypatch.setattr(app_module, "load_dotenv", lambda: None)
    for name in APP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def no_real_api_calls(monkeypatch):
    """Runs before every test: make creating a real API client fail.

    So no test can ever reach the real Claude or Voyage API (costs money, needs internet).
    Code that isn't given a fake client behaves as if the API is unavailable.
    """

    def blocked():
        raise anthropic.AnthropicError("real API calls are blocked in tests")

    monkeypatch.setattr(ai, "_make_client", blocked)

    def embeddings_blocked():
        raise embeddings.EmbeddingsUnavailable("real API calls are blocked in tests")

    # The same for the Voyage embeddings API: tests fall back to keyword search.
    monkeypatch.setattr(embeddings, "_make_client", embeddings_blocked)


@pytest.fixture
def db_path(tmp_path):
    """A fresh, empty database for each test.

    SQLite: a new file in a temporary folder. PostgreSQL: the test database,
    with its tables deleted and made again, so no test sees another's notes.
    """
    if TEST_DATABASE_URL:
        _test_database_name(TEST_DATABASE_URL)  # stop if it isn't a test database
        with db._connect(TEST_DATABASE_URL) as conn:
            db._execute(conn, "DROP TABLE IF EXISTS notes, projects, ai_usage")
        db.init_db(TEST_DATABASE_URL)
        return TEST_DATABASE_URL
    path = tmp_path / "test.db"
    db.init_db(path)
    return path


@pytest.fixture
def logged_out_client(db_path):
    """A fake browser that sends requests to the app without a real server."""
    from app import create_app

    app = create_app(db_path, TEST_SETTINGS)
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def client(logged_out_client):
    """The same fake browser, already logged in. Most tests use this one."""
    logged_out_client.post("/login", data={"password": TEST_PASSWORD})
    return logged_out_client
