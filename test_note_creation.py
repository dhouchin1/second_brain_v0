#!/usr/bin/env python3

import sqlite3
from datetime import datetime

def test_note_creation_direct():
    """Test note creation directly in the database"""
    print("Testing direct note creation...")
    
    # Connect to database
    conn = sqlite3.connect("notes.db")
    c = conn.cursor()
    
    # Check current count
    before_count = c.execute("SELECT COUNT(*) FROM notes WHERE user_id = 1").fetchone()[0]
    print(f"Notes count before: {before_count}")
    
    # Create a test note directly (simulating what /capture should do)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_id = 1  # dan27 user
    
    c.execute("""
        INSERT INTO notes (title, content, summary, tags, actions, type, timestamp, audio_filename, status, user_id) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "Test Quick Note from Debug",  # title
        "This is a test note to verify the creation process works",  # content
        "",  # summary
        "debug,test",  # tags
        "",  # actions
        "note",  # type
        now,  # timestamp
        None,  # audio_filename
        "complete",  # status (changed from pending for immediate visibility)
        user_id,  # user_id
    ))
    
    conn.commit()
    note_id = c.lastrowid
    print(f"Created note with ID: {note_id}")
    
    # Add to FTS index
    try:
        c.execute("""
            INSERT INTO notes_fts(rowid, title, summary, tags, actions, content) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            note_id,
            "Test Quick Note from Debug",
            "",
            "debug,test",
            "",
            "This is a test note to verify the creation process works"
        ))
        conn.commit()
        print("Added to FTS index")
    except Exception as e:
        print(f"FTS index error: {e}")
    
    # Check count after
    after_count = c.execute("SELECT COUNT(*) FROM notes WHERE user_id = 1").fetchone()[0]
    print(f"Notes count after: {after_count}")
    
    # Verify the note is retrievable with the dashboard query
    dashboard_notes = c.execute("""
        SELECT id, title, type, timestamp, audio_filename, status, tags
        FROM notes
        WHERE user_id = ?
        ORDER BY (tags LIKE '%pinned%') DESC, timestamp DESC
        LIMIT 10
    """, (user_id,)).fetchall()
    
    print(f"Dashboard would show {len(dashboard_notes)} notes:")
    for note in dashboard_notes[:3]:  # Show first 3
        print(f"  - ID: {note[0]}, Title: {note[1][:40]}..., Time: {note[3]}")
    
    conn.close()

def test_authentication_cookies():
    """Test what a logged-in user would have for authentication"""
    print("\nTesting authentication setup...")
    
    # Check users table
    conn = sqlite3.connect("notes.db")
    c = conn.cursor()
    
    users = c.execute("SELECT id, username FROM users").fetchall()
    print("Available users:")
    for user in users:
        print(f"  - ID: {user[0]}, Username: {user[1]}")
    
    conn.close()

def check_recent_notes():
    """Check if recent notes are visible to the dashboard"""
    print("\nChecking recent notes visibility...")
    
    conn = sqlite3.connect("notes.db")
    c = conn.cursor()
    
    # This is the exact query the dashboard uses
    recent_rows = c.execute("""
        SELECT id, title, type, timestamp, audio_filename, status, tags
        FROM notes
        WHERE user_id = ?
        ORDER BY (tags LIKE '%pinned%') DESC, timestamp DESC
        LIMIT 10
    """, (1,)).fetchall()  # user_id = 1 for dan27
    
    print(f"Dashboard recent notes query returns {len(recent_rows)} notes:")
    for r in recent_rows:
        print(f"  - ID: {r[0]}, Title: {(r[1] or 'Untitled')[:40]}..., Type: {r[2]}, Status: {r[5]}")
    
    conn.close()

if __name__ == "__main__":
    check_recent_notes()
    test_authentication_cookies()
    test_note_creation_direct()