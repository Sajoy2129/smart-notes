"""Shared pytest fixtures.

A fixture is a helper pytest runs before a test and passes in by name.
"""

import pytest

import db


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
