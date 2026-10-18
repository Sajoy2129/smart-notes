import db


def test_home_with_no_notes(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"No notes yet" in response.data


def test_new_note_form_loads(client):
    response = client.get("/new")

    assert response.status_code == 200
    assert b"<form" in response.data


def test_saving_a_note_redirects_to_it(client):
    response = client.post("/new", data={"title": "Phone call", "body": "Client rang."})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/note/1")


def test_saved_note_shows_on_home_and_view_pages(client):
    client.post("/new", data={"title": "Phone call", "body": "Client rang."})

    home = client.get("/")
    view = client.get("/note/1")

    assert b"Phone call" in home.data
    assert b"Client rang." in view.data
    assert b"AI summary not available" in view.data


def test_empty_title_shows_error_and_does_not_save(client, db_path):
    response = client.post("/new", data={"title": "  ", "body": "Some text"})

    assert response.status_code == 400
    assert b"Please fill in both" in response.data
    assert b"Some text" in response.data  # what the user typed is kept
    assert db.list_notes(db_path) == []


def test_empty_body_shows_error(client):
    response = client.post("/new", data={"title": "Title", "body": ""})

    assert response.status_code == 400


def test_missing_note_returns_404(client):
    assert client.get("/note/999").status_code == 404


def test_html_in_notes_is_escaped(client):
    client.post("/new", data={"title": "<script>x</script>", "body": "hi"})

    response = client.get("/note/1")

    assert b"<script>x</script>" not in response.data
    assert b"&lt;script&gt;" in response.data


def test_note_page_has_delete_button_with_confirm(client):
    client.post("/new", data={"title": "Call", "body": "Rang."})

    response = client.get("/note/1")

    assert b'action="/note/1/delete"' in response.data
    assert b"confirm(" in response.data


def test_delete_removes_note_and_goes_home(client, db_path):
    client.post("/new", data={"title": "Call", "body": "Rang."})

    response = client.post("/note/1/delete")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    assert db.get_note(db_path, 1) is None


def test_delete_needs_post(client):
    client.post("/new", data={"title": "Call", "body": "Rang."})

    assert client.get("/note/1/delete").status_code == 405  # 405 = method not allowed


def test_delete_missing_note_returns_404(client):
    assert client.post("/note/999/delete").status_code == 404
