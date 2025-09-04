from fastapi.testclient import TestClient
import sqlite3
import base64
from typing import Tuple
import sys, pathlib

# Ensure project root is on path
ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as appmod
from config import settings


def tiny_png_bytes() -> bytes:
    # 1x1 red dot PNG
    b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMA"
        "ASsJTYQAAAAASUVORK5CYII="
    )
    return base64.b64decode(b64)


def ensure_user(client: TestClient, username: str, password: str) -> Tuple[int, str]:
    # Load login page to get CSRF cookie
    r = client.get('/login')
    assert r.status_code == 200
    csrf = client.cookies.get('csrf_token')
    assert csrf, 'Expected csrf_token cookie'

    # Try register (idempotent)
    r = client.post('/register', data={'username': username, 'password': password})
    assert r.status_code in (200, 400), r.text

    # Login with CSRF
    r = client.post('/login', data={'username': username, 'password': password, 'csrf_token': csrf}, allow_redirects=False)
    assert r.status_code in (200, 302), r.text
    assert client.cookies.get('access_token'), 'Expected access_token cookie after login'

    # Lookup user id
    conn = sqlite3.connect(str(settings.db_path))
    c = conn.cursor()
    row = c.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
    conn.close()
    assert row and row[0], 'User not found after login'
    return row[0], client.cookies.get('csrf_token') or csrf


def main():
    client = TestClient(appmod.app)

    print('Ensuring user and session...')
    uid, csrf = ensure_user(client, 'test_user_img', 'pass1234')

    print('Capture text note...')
    r = client.post('/capture', data={'note': 'hello world', 'tags': 'test', 'csrf_token': csrf}, allow_redirects=False)
    assert r.status_code == 302, r.text

    print('Upload image via /capture (JSON accept)...')
    files = {'file': ('red.png', tiny_png_bytes(), 'image/png')}
    headers = {'accept': 'application/json'}
    r = client.post('/capture', data={'note': '', 'tags': 'img', 'csrf_token': csrf}, files=files, headers=headers)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get('success') is True
    note_id = j['id']
    print('Created note id:', note_id)

    print('Lookup stored filename in DB...')
    conn = sqlite3.connect(str(settings.db_path))
    c = conn.cursor()
    row = c.execute('SELECT file_filename FROM notes WHERE id=?', (note_id,)).fetchone()
    conn.close()
    assert row and row[0], 'No stored filename for image note'
    filename = row[0]
    print('Stored file:', filename)

    print('GET /files/{filename} using cookie auth...')
    r = client.get(f'/files/{filename}', allow_redirects=False)
    assert r.status_code == 200, (r.status_code, r.text)
    print('OK (cookie); Content-Type:', r.headers.get('content-type'))

    print('GET /files/{filename} using signed token, no cookies...')
    client2 = TestClient(appmod.app)
    token = appmod.create_file_token(uid, filename)
    r = client2.get(f'/files/{filename}?token={token}', allow_redirects=False)
    assert r.status_code == 200, (r.status_code, r.text)
    print('OK (signed); Content-Type:', r.headers.get('content-type'))

    print('Smoke test passed.')


if __name__ == '__main__':
    main()
