from fastapi.testclient import TestClient

from app import app


def get_csrf_token_from(resp):
    # cookies is a RequestsCookieJar
    return resp.cookies.get('csrf_token')


def test_signup_login_and_dashboard_redirects():
    client = TestClient(app)

    # Unauthenticated visit to / should redirect to /login
    r = client.get('/', allow_redirects=False)
    assert r.status_code in (302, 307)
    assert '/login' in r.headers.get('location', '')

    # Get CSRF from login page
    r = client.get('/login')
    assert r.status_code == 200
    csrf = get_csrf_token_from(r)
    assert csrf

    # Go to signup page and get csrf
    r = client.get('/signup')
    assert r.status_code == 200
    csrf = get_csrf_token_from(r)
    assert csrf

    # Create account via UI
    r = client.post('/signup', data={'username': 'tester', 'password': 'secret123', 'csrf_token': csrf}, allow_redirects=False)
    assert r.status_code in (302, 303)

    # Follow redirect to /
    r = client.get('/')
    assert r.status_code == 200

    # Logout flow
    # Need fresh csrf from any GET page
    r = client.get('/')
    csrf = get_csrf_token_from(r)
    r = client.post('/logout', data={'csrf_token': csrf}, allow_redirects=False)
    assert r.status_code in (302, 303)

    # Now / should redirect back to /login again
    r = client.get('/', allow_redirects=False)
    assert r.status_code in (302, 307)
    assert '/login' in r.headers.get('location', '')

