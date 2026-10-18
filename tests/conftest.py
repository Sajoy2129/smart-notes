"""Shared pytest fixtures.

A fixture is a helper pytest runs before a test and passes in by name.
"""

import anthropic
import pytest

import ai
import db


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
def client(db_path):
    """A fake browser that sends requests to the app without a real server."""
    from app import create_app

    app = create_app(db_path)
    app.config["TESTING"] = True
    return app.test_client()
