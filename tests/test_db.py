import sqlite3
import traceback

import pytest

import db


def test_create_and_get_note(db_path):
    note_id = db.create_note(
        db_path,
        "Site visit",
        "Checked the walls.",
        summary="Walls checked.",
        action_items=[{"task": "Buy paint", "owner": None, "due_date": None}],
        tags=["painting"],
    )

    note = db.get_note(db_path, note_id)

    assert note["title"] == "Site visit"
    assert note["body"] == "Checked the walls."
    assert note["summary"] == "Walls checked."
    assert note["action_items"][0]["task"] == "Buy paint"
    assert note["tags"] == ["painting"]
    assert note["created_at"]


def test_note_without_ai_parts_gets_empty_lists(db_path):
    note_id = db.create_note(db_path, "Call", "Rang the client.")

    note = db.get_note(db_path, note_id)

    assert note["summary"] is None
    assert note["action_items"] == []
    assert note["tags"] == []


def test_get_missing_note_returns_none(db_path):
    assert db.get_note(db_path, 999) is None


def test_list_notes_newest_first(db_path):
    db.create_note(db_path, "First", "a")
    db.create_note(db_path, "Second", "b")

    titles = [note["title"] for note in db.list_notes(db_path)]

    assert titles == ["Second", "First"]


def test_list_notes_empty(db_path):
    assert db.list_notes(db_path) == []


def test_delete_note(db_path):
    note_id = db.create_note(db_path, "Old", "Remove me")

    assert db.delete_note(db_path, note_id) is True
    assert db.get_note(db_path, note_id) is None


def test_delete_missing_note_returns_false(db_path):
    assert db.delete_note(db_path, 999) is False


def test_save_analysis_updates_note(db_path):
    note_id = db.create_note(db_path, "Call", "Rang the client.")
    items = [{"task": "Send quote", "owner": None, "due_date": None, "due_date_iso": None}]

    db.save_analysis(db_path, note_id, "Client called.", items, ["client"])

    note = db.get_note(db_path, note_id)
    assert note["summary"] == "Client called."
    assert note["action_items"] == items
    assert note["tags"] == ["client"]


# ---------- Projects ----------

def test_create_and_list_projects_alphabetically(db_path):
    db.create_project(db_path, "Office fit-out")
    db.create_project(db_path, "garden job")

    names = [project["name"] for project in db.list_projects(db_path)]

    assert names == ["garden job", "Office fit-out"]  # A-Z, ignoring upper/lower case


def test_get_project(db_path):
    project_id = db.create_project(db_path, "Harbour Road")

    assert db.get_project(db_path, project_id)["name"] == "Harbour Road"
    assert db.get_project(db_path, 999) is None


def test_project_notes_are_open_notes_of_that_project_newest_first(db_path):
    harbour = db.create_project(db_path, "Harbour Road")
    office = db.create_project(db_path, "Office")
    first = db.create_note(db_path, "", "First", project_id=harbour)
    second = db.create_note(db_path, "", "Second", project_id=harbour)
    db.create_note(db_path, "", "Other project", project_id=office)

    ids = [note["id"] for note in db.list_project_notes(db_path, harbour)]

    assert ids == [second, first]


def test_completed_notes_are_hidden_from_project_but_kept(db_path):
    project_id = db.create_project(db_path, "Harbour Road")
    note_id = db.create_note(db_path, "", "Done soon", project_id=project_id)

    assert db.complete_note(db_path, note_id) is True

    assert db.list_project_notes(db_path, project_id) == []
    assert db.get_note(db_path, note_id)["completed_at"]  # still in the database


def test_complete_missing_note_returns_false(db_path):
    assert db.complete_note(db_path, 999) is False


def test_project_list_counts_open_notes(db_path):
    project_id = db.create_project(db_path, "Harbour Road")
    db.create_note(db_path, "", "Open", project_id=project_id)
    done = db.create_note(db_path, "", "Done", project_id=project_id)
    db.complete_note(db_path, done)

    assert db.list_projects(db_path)[0]["open_count"] == 1


# ---------- Upgrading an old database ----------

def test_old_database_is_upgraded_and_notes_go_to_general(tmp_path):
    # Build a database the way the app did before projects existed.
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE notes (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, "
            "body TEXT NOT NULL, created_at TEXT NOT NULL, summary TEXT, "
            "action_items TEXT, tags TEXT)"
        )
        conn.execute(
            "INSERT INTO notes (title, body, created_at) VALUES ('Old call', 'Rang.', '2026-10-18T10:00:00')"
        )
    conn.close()

    db.init_db(path)
    db.init_db(path)  # running it twice must be safe

    projects = db.list_projects(path)
    assert [project["name"] for project in projects] == ["General"]
    note = db.get_note(path, 1)
    assert note["title"] == "Old call"
    assert note["project_id"] == projects[0]["id"]
    assert note["completed_at"] is None


def test_new_database_has_no_general_project(db_path):
    assert db.list_projects(db_path) == []


def test_open_notes_from_all_projects_newest_first_with_project_name(db_path):
    harbour = db.create_project(db_path, "Harbour Road")
    office = db.create_project(db_path, "Office")
    first = db.create_note(db_path, "", "First", project_id=harbour)
    second = db.create_note(db_path, "", "Second", project_id=office)
    done = db.create_note(db_path, "", "Done", project_id=office)
    db.complete_note(db_path, done)

    notes = db.list_open_notes(db_path)

    assert [note["id"] for note in notes] == [second, first]
    assert [note["project_name"] for note in notes] == ["Office", "Harbour Road"]


# ---------- Daily AI limit ----------

def test_ai_jobs_are_counted_up_to_the_limit(db_path):
    results = [db.use_ai_job(db_path, 2, day="2026-10-20") for _ in range(3)]

    assert results == [True, True, False]
    assert db.ai_jobs_used(db_path, "2026-10-20") == 2  # the refused job wasn't counted


def test_ai_limit_resets_on_a_new_day(db_path):
    db.use_ai_job(db_path, 1, day="2026-10-20")

    assert db.use_ai_job(db_path, 1, day="2026-10-20") is False
    assert db.use_ai_job(db_path, 1, day="2026-10-21") is True


def test_ai_limit_of_zero_allows_nothing(db_path):
    assert db.use_ai_job(db_path, 0, day="2026-10-20") is False
    assert db.ai_jobs_used(db_path, "2026-10-20") == 0


def test_ai_usage_table_is_added_to_an_old_database(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, title TEXT, body TEXT)")

    db.init_db(path)

    assert db.use_ai_job(path, 5) is True


# ---------- Choosing the database ----------

def test_postgres_urls_are_recognised():
    assert db.is_postgres("postgresql://user:pw@localhost:5432/smart_notes")
    assert db.is_postgres("postgres://user:pw@localhost/smart_notes")


def test_file_paths_are_sqlite(tmp_path):
    assert not db.is_postgres("smart_notes.db")
    assert not db.is_postgres(tmp_path / "test.db")  # a Path object, as tests pass it


class FakePostgresConnection:
    """Stands in for a PostgreSQL connection: it only records the SQL it is given."""

    def execute(self, sql, params):
        self.sql, self.params = sql, params


def test_postgres_queries_get_percent_s_placeholders():
    conn = FakePostgresConnection()

    db._execute(conn, "SELECT * FROM notes WHERE id = ? AND title = ?", (1, "Hi"))

    assert conn.sql == "SELECT * FROM notes WHERE id = %s AND title = %s"
    assert conn.params == (1, "Hi")  # values still travel separately from the SQL


# ---------- The DATABASE_URL password stays secret ----------

@pytest.mark.parametrize(
    "bad_url",
    [
        "postgresql://notes:ab%zzSECRET@localhost/smart_notes",  # "%" not encoded
        "postgresql://notes:p@ssSECRET@localhost/smart_notes",  # "@" not encoded
    ],
)
def test_connection_errors_never_show_the_password(bad_url):
    # PostgreSQL's own error repeats parts of a URL it can't read, password included.
    with pytest.raises(db.DatabaseConnectionError) as error:
        db.init_db(bad_url)

    # The full traceback is what the server writes to its log.
    logged = "".join(traceback.format_exception(error.value))
    assert "SECRET" not in logged
    assert "DATABASE_URL" in logged  # still says what to check
    # Not even hidden inside: error-tracking tools also read the error an error
    # replaced (__context__) or was caused by (__cause__).
    assert error.value.__context__ is None
    assert error.value.__cause__ is None


# ---------- SQL with a literal % ----------

def test_sql_can_contain_a_percent_sign(db_path):
    # PostgreSQL's driver reads % as the start of a placeholder, so a literal % in
    # SQL (as in LIKE '%word%', a text search) needs care. Runs on both databases.
    db.create_note(db_path, "", "Tiles arrive Friday.")
    db.create_note(db_path, "", "Paint the hall.")

    with db._connect(db_path) as conn:
        with_values = db._execute(
            conn, "SELECT body FROM notes WHERE body LIKE '%' || ? || '%'", ("Tiles",)
        ).fetchall()
        without_values = db._execute(conn, "SELECT '100%' AS text").fetchone()

    assert [row["body"] for row in with_values] == ["Tiles arrive Friday."]
    assert without_values["text"] == "100%"


# ---------- The safety check before tests drop tables ----------

def test_safety_check_accepts_a_test_database():
    from tests.conftest import _test_database_name

    assert _test_database_name("postgresql://localhost/smart_notes_test") == "smart_notes_test"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://localhost/smart_notes",
        # The name PostgreSQL really uses can hide in the part after "?".
        "postgresql://localhost/smart_notes_test?dbname=smart_notes",
        "postgresql://localhost/latest_notes",  # contains "test", but isn't a test database
    ],
)
def test_safety_check_refuses_real_databases(url):
    from tests.conftest import _test_database_name

    with pytest.raises(pytest.UsageError):
        _test_database_name(url)


# ---------- Sorting projects ----------

def test_projects_with_the_same_name_keep_the_order_they_were_made(db_path):
    first = db.create_project(db_path, "harbour road")
    second = db.create_project(db_path, "Harbour Road")
    third = db.create_project(db_path, "HARBOUR ROAD")

    assert [p["id"] for p in db.list_projects(db_path)] == [first, second, third]
