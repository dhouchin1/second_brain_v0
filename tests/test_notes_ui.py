from fastapi.testclient import TestClient
import sqlite3
from datetime import datetime

from app import app
from config import settings


def get_csrf_token(resp):
    return resp.cookies.get("csrf_token")


def create_user_and_login(client: TestClient, username: str, password: str = "secret123"):
    # Get CSRF for signup
    r = client.get("/signup")
    assert r.status_code == 200
    csrf = get_csrf_token(r)
    assert csrf
    r = client.post("/signup", data={"username": username, "password": password, "csrf_token": csrf}, allow_redirects=False)
    assert r.status_code in (302, 303)


def get_user_id(username: str) -> int:
    conn = sqlite3.connect(str(settings.db_path))
    row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    assert row, f"user {username} not found"
    return int(row[0])


def insert_note_for_user(user_id: int, title: str = "Test Note") -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(str(settings.db_path))
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO notes (title, content, summary, tags, actions, type, timestamp, status, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'complete', ?)
        """,
        (title, "body", "", "test,ui", "", "text", now, user_id),
    )
    note_id = cur.lastrowid
    conn.commit()
    conn.close()
    return int(note_id)


def note_exists(note_id: int) -> bool:
    conn = sqlite3.connect(str(settings.db_path))
    row = conn.execute("SELECT 1 FROM notes WHERE id=?", (note_id,)).fetchone()
    conn.close()
    return bool(row)


def test_edit_note_csrf_and_update():
    client = TestClient(app)
    username = "user_edit"
    create_user_and_login(client, username)
    user_id = get_user_id(username)
    note_id = insert_note_for_user(user_id, title="Original Title")

    # GET edit page -> CSRF
    r = client.get(f"/edit/{note_id}")
    assert r.status_code == 200
    csrf = get_csrf_token(r)
    assert csrf

    # POST without CSRF -> redirect back to edit
    r = client.post(f"/edit/{note_id}", data={"content": "new", "tags": "x,y"}, allow_redirects=False)
    assert r.status_code in (302, 303)
    assert f"/edit/{note_id}" in r.headers.get("location", "")

    # POST with CSRF -> redirect to detail
    r = client.post(
        f"/edit/{note_id}",
        data={"content": "updated content", "tags": "a,b", "csrf_token": csrf},
        allow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert f"/detail/{note_id}" in r.headers.get("location", "")


def test_delete_note_csrf():
    client = TestClient(app)
    username = "user_delete"
    create_user_and_login(client, username)
    user_id = get_user_id(username)
    note_id = insert_note_for_user(user_id)

    # Need CSRF from dashboard
    r = client.get("/")
    assert r.status_code == 200
    csrf = get_csrf_token(r)
    assert csrf

    # POST delete without CSRF -> redirect to /
    r = client.post(f"/delete/{note_id}", allow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers.get("location", "").endswith("/")
    assert note_exists(note_id)

    # POST delete with CSRF -> note removed
    r = client.post(f"/delete/{note_id}", data={"csrf_token": csrf}, allow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers.get("location", "").endswith("/")
    assert not note_exists(note_id)


def test_capture_with_csrf_creates_note():
    client = TestClient(app)
    username = "user_capture"
    create_user_and_login(client, username)

    # Fetch CSRF from dashboard
    r = client.get("/")
    assert r.status_code == 200
    csrf = get_csrf_token(r)
    assert csrf

    # Submit capture form
    r = client.post(
        "/capture",
        data={"note": "Hello world", "tags": "t1,t2", "csrf_token": csrf},
        allow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert r.headers.get("location", "").endswith("/")
