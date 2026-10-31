"""Tests for the login: every page needs it, except the login page and the CSS."""

import pytest

import db
from app import safe_next_url
from tests.conftest import TEST_PASSWORD


def log_in(client, password=TEST_PASSWORD, next_url=None):
    path = f"/login?next={next_url}" if next_url else "/login"
    return client.post(path, data={"password": password})


# ---------- Logged out ----------

@pytest.mark.parametrize("path", ["/", "/ask", "/note/1", "/project/1"])
def test_pages_send_me_to_login(logged_out_client, path):
    response = logged_out_client.get(path)

    assert response.status_code == 302
    assert response.location.startswith("/login")


def test_posts_are_refused_and_change_nothing(logged_out_client, db_path):
    response = logged_out_client.post("/projects", data={"name": "Sneaky"})

    assert response.status_code == 302
    assert "/login" in response.location
    assert db.list_projects(db_path) == []


def test_login_page_and_css_work_without_login(logged_out_client):
    assert logged_out_client.get("/login").status_code == 200
    assert logged_out_client.get("/static/app.css").status_code == 200


def test_login_page_answers_head_requests(logged_out_client):
    # HEAD = GET without the page body; `curl -I` and uptime checkers send it.
    assert logged_out_client.head("/login").status_code == 200


def test_login_page_hides_the_menu(logged_out_client):
    page = logged_out_client.get("/login").get_data(as_text=True)

    assert 'type="password"' in page
    assert "Log out" not in page
    assert "Ask your notes" not in page  # the search box


# ---------- Logging in ----------

def test_wrong_password_is_refused(logged_out_client):
    response = log_in(logged_out_client, password="guess")

    assert response.status_code == 401
    assert "Wrong password." in response.get_data(as_text=True)
    assert logged_out_client.get("/").status_code == 302  # still logged out


def test_empty_password_is_refused(logged_out_client):
    assert log_in(logged_out_client, password="").status_code == 401


def test_right_password_logs_me_in(logged_out_client):
    response = log_in(logged_out_client)

    assert response.status_code == 302
    assert response.location == "/"
    page = logged_out_client.get("/")
    assert page.status_code == 200
    assert "Log out" in page.get_data(as_text=True)


def test_login_returns_to_the_page_i_asked_for(logged_out_client):
    first = logged_out_client.get("/ask")

    response = logged_out_client.post(first.location, data={"password": TEST_PASSWORD})

    assert response.location == "/ask"


def test_login_cookie_lasts_30_days(logged_out_client):
    response = log_in(logged_out_client)

    cookie = response.headers["Set-Cookie"]
    assert "Expires=" in cookie  # without it, the cookie ends when the browser closes
    assert "HttpOnly" in cookie  # JavaScript can't read it


def test_login_page_when_logged_in_goes_home(client):
    assert client.get("/login").status_code == 302


# ---------- Logging out ----------

def test_logout_logs_me_out(client):
    response = client.post("/logout")

    assert response.location == "/login"
    assert client.get("/").status_code == 302


def test_logout_needs_a_post(client):
    # A link (GET) must never change anything.
    assert client.get("/logout").status_code == 405  # 405 = method not allowed
    assert client.get("/").status_code == 200  # still logged in


# ---------- Where to go after logging in ----------

@pytest.mark.parametrize("next_url, expected", [
    ("/ask", "/ask"),
    ("/project/3?x=1", "/project/3?x=1"),
    (None, "/"),
    ("", "/"),
    ("https://evil.com", "/"),  # another website
    ("//evil.com", "/"),  # browsers read // as "another website"
    ("/\\evil.com", "/"),  # and some read /\ the same way
])
def test_safe_next_url(client, next_url, expected):
    with client.application.test_request_context():
        assert safe_next_url(next_url) == expected


def test_login_never_sends_me_to_another_site(logged_out_client):
    response = log_in(logged_out_client, next_url="//evil.com")

    assert response.location == "/"
