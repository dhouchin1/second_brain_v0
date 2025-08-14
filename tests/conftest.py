import pytest
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
import sqlite3
from app import app, get_conn

@pytest.fixture
def client():
    """Test client with temporary database"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        test_db = tmp_path / "test.db"
        
        # Override database connection
        app.dependency_overrides[get_conn] = lambda: sqlite3.connect(str(test_db))
        
        # Initialize test database
        conn = sqlite3.connect(str(test_db))
        conn.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                summary TEXT,
                tags TEXT,
                actions TEXT,
                type TEXT,
                timestamp TEXT,
                audio_filename TEXT,
                content TEXT,
                status TEXT DEFAULT 'complete',
                user_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        conn.commit()
        conn.close()
        
        with TestClient(app) as test_client:
            yield test_client
        
        # Cleanup
        app.dependency_overrides.clear()

@pytest.fixture
def sample_user(client):
    """Create a test user"""
    response = client.post("/register", data={
        "username": "testuser",
        "password": "testpass123"
    })
    assert response.status_code == 200
    return response.json()

@pytest.fixture
def auth_headers(client, sample_user):
    """Get authorization headers"""
    response = client.post("/token", data={
        "username": "testuser",
        "password": "testpass123"
    })
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
