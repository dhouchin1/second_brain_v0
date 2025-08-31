from fastapi.testclient import TestClient

from app import app


def test_unauthenticated_root_shows_landing_and_others_redirect():
    client = TestClient(app)
    # Root shows landing page now
    r = client.get('/', allow_redirects=False)
    assert r.status_code == 200
    assert b'Second Brain' in r.content

    r = client.get('/search', allow_redirects=False)
    assert r.status_code in (302, 307)
    assert '/login' in r.headers.get('location', '')

    # Detail should still redirect regardless of ID
    r = client.get('/detail/1', allow_redirects=False)
    assert r.status_code in (302, 307)
    assert '/login' in r.headers.get('location', '')


def test_authenticated_pages_render():
    client = TestClient(app)

    # Get CSRF then sign up
    r = client.get('/signup')
    csrf = r.cookies.get('csrf_token')
    assert csrf
    r = client.post('/signup', data={'username': 'redir_user', 'password': 'secret123', 'csrf_token': csrf}, allow_redirects=False)
    assert r.status_code in (302, 303)

    # Now pages should render
    assert client.get('/').status_code == 200
    assert client.get('/search').status_code == 200
