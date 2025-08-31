#!/usr/bin/env python3

import requests
import sqlite3

# Test the /capture endpoint
def test_capture():
    print("Testing /capture endpoint...")
    
    # First, let's check if the server is running by hitting the health endpoint
    try:
        health_response = requests.get("http://localhost:8000/health")
        print(f"Health check: {health_response.status_code} - {health_response.json()}")
    except Exception as e:
        print(f"Server not running or accessible: {e}")
        return
    
    # Check current user (we'll need to be logged in)
    try:
        dashboard_response = requests.get("http://localhost:8000/")
        print(f"Dashboard response: {dashboard_response.status_code}")
        if dashboard_response.status_code == 302:
            print("Redirected - user not logged in")
            return
    except Exception as e:
        print(f"Dashboard check failed: {e}")
        return
        
    # Test capture endpoint with a simple note
    test_data = {
        "note": "This is a debug test note",
        "tags": "debug,test",
        "csrf_token": "test"  # This will likely fail, but let's see what happens
    }
    
    try:
        capture_response = requests.post("http://localhost:8000/capture", data=test_data)
        print(f"Capture response: {capture_response.status_code}")
        print(f"Response headers: {capture_response.headers}")
        print(f"Response content: {capture_response.text[:500]}")
    except Exception as e:
        print(f"Capture test failed: {e}")

# Check database state
def check_database():
    print("\nChecking database state...")
    
    conn = sqlite3.connect("notes.db")
    c = conn.cursor()
    
    # Check total notes
    total = c.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    print(f"Total notes: {total}")
    
    # Check notes with user_id
    with_user = c.execute("SELECT COUNT(*) FROM notes WHERE user_id IS NOT NULL").fetchone()[0]
    print(f"Notes with user_id: {with_user}")
    
    # Check notes without user_id
    without_user = c.execute("SELECT COUNT(*) FROM notes WHERE user_id IS NULL").fetchone()[0]
    print(f"Notes without user_id: {without_user}")
    
    # Check recent notes
    recent = c.execute("SELECT id, title, user_id, status, timestamp FROM notes ORDER BY timestamp DESC LIMIT 3").fetchall()
    print("Recent notes:")
    for note in recent:
        print(f"  ID: {note[0]}, Title: {note[1][:50]}, User: {note[2]}, Status: {note[3]}, Time: {note[4]}")
    
    conn.close()

if __name__ == "__main__":
    check_database()
    test_capture()
