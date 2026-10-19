"""Shared pytest fixtures.

A fixture is a helper pytest runs before a test and passes in by name.
"""

import anthropic
import pytest
from werkzeug.security import generate_password_hash

import ai
import app as app_module
import db

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
    "SECRET_KEY", "APP_PASSWORD_HASH", "DATABASE_PATH", "RENDER", "RENDER_EXTERNAL_HOSTNAME"
]


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Runs before every test: ignore the real .env and the app's environment variables."""
    monkeypatch.setattr(app_module, "load_dotenv", lambda: None)
    for name in APP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def no_real_api_calls(monkeypatch):
    """Runs before every test: make creating a real API client fail.

    So no test can ever reach the real Claude API (costs money, needs internet).
    Code that isn't given a fake client behaves as if the API is unavailable.
    """

    def blocked():
        raise anthropic.AnthropicError("real API calls are blocked in tests")

    monkeypatch.setattr(ai, "_make_client", blocked)


@pytest.fixture
def db_path(tmp_path):
    """A fresh, empty database in a temporary folder for each test."""
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
