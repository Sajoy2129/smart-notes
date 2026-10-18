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
