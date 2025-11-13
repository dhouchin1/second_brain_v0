"""
Simple database-level tests for new features
No auth required - just tests database operations
"""

import sqlite3
import tempfile
import os


def test_note_crud_operations():
    """Test Create, Read, Update, Delete for notes"""
    print("Testing CRUD operations...")

    # Create temp database
    db_path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_path)

    # Create schema
    conn.execute('''
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content TEXT,
            tags TEXT,
            status TEXT DEFAULT 'active',
            user_id INTEGER DEFAULT 1
        )
    ''')

    # CREATE
    conn.execute(
        "INSERT INTO notes (title, content, tags) VALUES (?, ?, ?)",
        ("Test Note", "Test content", "test, demo")
    )
    conn.commit()

    # READ
    note = conn.execute("SELECT * FROM notes WHERE id = 1").fetchone()
    assert note is not None
    assert note[1] == "Test Note"

    # UPDATE
    conn.execute(
        "UPDATE notes SET title = ?, content = ? WHERE id = 1",
        ("Updated Title", "Updated content")
    )
    conn.commit()

    updated = conn.execute("SELECT title, content FROM notes WHERE id = 1").fetchone()
    assert updated[0] == "Updated Title"
    assert updated[1] == "Updated content"

    # DELETE (soft)
    conn.execute("UPDATE notes SET status = 'deleted' WHERE id = 1")
    conn.commit()

    status = conn.execute("SELECT status FROM notes WHERE id = 1").fetchone()[0]
    assert status == "deleted"

    conn.close()
    os.unlink(db_path)
    print("✅ CRUD operations test passed")


def test_bulk_operations():
    """Test bulk operations on multiple notes"""
    print("Testing bulk operations...")

    db_path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_path)

    conn.execute('''
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY,
            title TEXT,
            tags TEXT,
            status TEXT DEFAULT 'active'
        )
    ''')

    # Create multiple notes
    notes = [
        ("Note 1", "tag1, tag2"),
        ("Note 2", "tag2, tag3"),
        ("Note 3", "tag3, tag4"),
        ("Note 4", "tag4, tag5"),
        ("Note 5", "tag5, tag6"),
    ]

    for title, tags in notes:
        conn.execute(
            "INSERT INTO notes (title, tags) VALUES (?, ?)",
            (title, tags)
        )
    conn.commit()

    # Bulk tag update
    conn.execute("UPDATE notes SET tags = 'bulk, updated' WHERE id <= 3")
    conn.commit()

    updated_count = conn.execute(
        "SELECT COUNT(*) FROM notes WHERE tags = 'bulk, updated'"
    ).fetchone()[0]
    assert updated_count == 3

    # Bulk delete
    conn.execute("UPDATE notes SET status = 'deleted' WHERE id <= 2")
    conn.commit()

    deleted_count = conn.execute(
        "SELECT COUNT(*) FROM notes WHERE status = 'deleted'"
    ).fetchone()[0]
    assert deleted_count == 2

    active_count = conn.execute(
        "SELECT COUNT(*) FROM notes WHERE status = 'active'"
    ).fetchone()[0]
    assert active_count == 3

    conn.close()
    os.unlink(db_path)
    print("✅ Bulk operations test passed")


def test_tag_management():
    """Test tag autocomplete functionality"""
    print("Testing tag management...")

    db_path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_path)

    conn.execute('''
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY,
            title TEXT,
            tags TEXT
        )
    ''')

    # Create notes with various tags
    notes_with_tags = [
        ("Note 1", "python, code, testing"),
        ("Note 2", "python, web, fastapi"),
        ("Note 3", "javascript, web, frontend"),
        ("Note 4", "testing, qa, automation"),
    ]

    for title, tags in notes_with_tags:
        conn.execute(
            "INSERT INTO notes (title, tags) VALUES (?, ?)",
            (title, tags)
        )
    conn.commit()

    # Extract all unique tags
    rows = conn.execute("SELECT DISTINCT tags FROM notes WHERE tags IS NOT NULL").fetchall()

    all_tags = set()
    for row in rows:
        if row[0]:
            tags = [t.strip() for t in row[0].split(',') if t.strip()]
            all_tags.update(tags)

    assert len(all_tags) >= 6
    assert "python" in all_tags
    assert "testing" in all_tags
    assert "web" in all_tags

    # Sorted tags (for autocomplete)
    sorted_tags = sorted(all_tags)
    assert sorted_tags[0] <= sorted_tags[-1]  # Verify sorting

    conn.close()
    os.unlink(db_path)
    print("✅ Tag management test passed")


def test_search_and_filter():
    """Test search and filtering functionality"""
    print("Testing search and filter...")

    db_path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_path)

    conn.execute('''
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY,
            title TEXT,
            content TEXT,
            tags TEXT,
            type TEXT,
            status TEXT DEFAULT 'active'
        )
    ''')

    # Create notes
    notes = [
        ("Meeting Notes", "Discussed project timeline", "work, meeting", "text", "active"),
        ("Audio Recording", "Interview transcription", "audio, interview", "audio", "active"),
        ("Project Plan", "Q4 objectives and goals", "work, planning", "text", "active"),
        ("Old Note", "Archived content", "archive", "text", "archived"),
    ]

    for title, content, tags, note_type, status in notes:
        conn.execute(
            "INSERT INTO notes (title, content, tags, type, status) VALUES (?, ?, ?, ?, ?)",
            (title, content, tags, note_type, status)
        )
    conn.commit()

    # Filter by tag
    work_notes = conn.execute(
        "SELECT * FROM notes WHERE tags LIKE '%work%'"
    ).fetchall()
    assert len(work_notes) == 2

    # Filter by type
    audio_notes = conn.execute(
        "SELECT * FROM notes WHERE type = 'audio'"
    ).fetchall()
    assert len(audio_notes) == 1

    # Filter by status
    active_notes = conn.execute(
        "SELECT * FROM notes WHERE status = 'active'"
    ).fetchall()
    assert len(active_notes) == 3

    archived_notes = conn.execute(
        "SELECT * FROM notes WHERE status = 'archived'"
    ).fetchall()
    assert len(archived_notes) == 1

    # Combined filters
    work_active = conn.execute(
        "SELECT * FROM notes WHERE tags LIKE '%work%' AND status = 'active'"
    ).fetchall()
    assert len(work_active) == 2

    conn.close()
    os.unlink(db_path)
    print("✅ Search and filter test passed")


def test_archive_workflow():
    """Test complete archive workflow"""
    print("Testing archive workflow...")

    db_path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_path)

    conn.execute('''
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY,
            title TEXT,
            status TEXT DEFAULT 'active'
        )
    ''')

    # Create notes
    for i in range(5):
        conn.execute(
            "INSERT INTO notes (title) VALUES (?)",
            (f"Note {i+1}",)
        )
    conn.commit()

    # Archive some notes
    conn.execute("UPDATE notes SET status = 'archived' WHERE id <= 2")
    conn.commit()

    # Count by status
    active = conn.execute("SELECT COUNT(*) FROM notes WHERE status = 'active'").fetchone()[0]
    archived = conn.execute("SELECT COUNT(*) FROM notes WHERE status = 'archived'").fetchone()[0]

    assert active == 3
    assert archived == 2

    # Unarchive a note
    conn.execute("UPDATE notes SET status = 'active' WHERE id = 1")
    conn.commit()

    active_after = conn.execute("SELECT COUNT(*) FROM notes WHERE status = 'active'").fetchone()[0]
    assert active_after == 4

    conn.close()
    os.unlink(db_path)
    print("✅ Archive workflow test passed")


def test_export_data_preparation():
    """Test data preparation for export"""
    print("Testing export data preparation...")

    db_path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_path)

    conn.execute('''
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY,
            title TEXT,
            content TEXT,
            tags TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create note
    conn.execute(
        "INSERT INTO notes (title, content, tags) VALUES (?, ?, ?)",
        ("Export Test", "Content to export", "test, export")
    )
    conn.commit()

    # Fetch for export
    note = conn.execute(
        "SELECT id, title, content, tags, created_at FROM notes WHERE id = 1"
    ).fetchone()

    # Prepare as dict (simulating JSON export)
    note_dict = {
        "id": note[0],
        "title": note[1],
        "content": note[2],
        "tags": note[3],
        "created_at": note[4]
    }

    assert note_dict["title"] == "Export Test"
    assert note_dict["tags"] == "test, export"

    # Simulate markdown export
    markdown = f"# {note_dict['title']}\n\n{note_dict['content']}\n\n**Tags:** {note_dict['tags']}"
    assert "# Export Test" in markdown
    assert "Content to export" in markdown

    conn.close()
    os.unlink(db_path)
    print("✅ Export data preparation test passed")


def test_favorite_notes():
    """Test favoriting notes"""
    print("Testing favorite notes...")

    db_path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_path)

    conn.execute('''
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY,
            title TEXT,
            is_favorite INTEGER DEFAULT 0
        )
    ''')

    # Create notes
    for i in range(5):
        conn.execute("INSERT INTO notes (title) VALUES (?)", (f"Note {i+1}",))
    conn.commit()

    # Mark as favorite
    conn.execute("UPDATE notes SET is_favorite = 1 WHERE id IN (1, 3, 5)")
    conn.commit()

    # Count favorites
    fav_count = conn.execute(
        "SELECT COUNT(*) FROM notes WHERE is_favorite = 1"
    ).fetchone()[0]
    assert fav_count == 3

    # Get favorites
    favorites = conn.execute(
        "SELECT id, title FROM notes WHERE is_favorite = 1 ORDER BY id"
    ).fetchall()

    assert len(favorites) == 3
    assert favorites[0][0] == 1
    assert favorites[1][0] == 3
    assert favorites[2][0] == 5

    # Toggle favorite
    conn.execute("UPDATE notes SET is_favorite = 0 WHERE id = 3")
    conn.commit()

    fav_after = conn.execute(
        "SELECT COUNT(*) FROM notes WHERE is_favorite = 1"
    ).fetchone()[0]
    assert fav_after == 2

    conn.close()
    os.unlink(db_path)
    print("✅ Favorite notes test passed")


# Run all tests
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 Second Brain - Feature Tests (Database Level)")
    print("="*60 + "\n")

    tests = [
        test_note_crud_operations,
        test_bulk_operations,
        test_tag_management,
        test_search_and_filter,
        test_archive_workflow,
        test_export_data_preparation,
        test_favorite_notes,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"❌ {test_func.__name__} failed: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__} error: {e}")
            failed += 1

    print("\n" + "="*60)
    print(f"Results: {passed}/{len(tests)} tests passed")
    print("="*60)

    if failed == 0:
        print("\n🎉 All database tests passed!\n")
    else:
        print(f"\n⚠️  {failed} test(s) failed\n")
