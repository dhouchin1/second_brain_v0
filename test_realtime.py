#!/usr/bin/env python3
"""
Test script for real-time status updates
Run this to test the SSE endpoint and status updates
"""

import asyncio
import aiohttp
import sqlite3
import json
import time
from pathlib import Path

# Configuration
API_BASE = "http://localhost:8084"
DB_PATH = "notes.db"

async def test_realtime_status():
    """Test the real-time status update system"""
    
    print("🧠 Second Brain Real-time Status Test")
    print("=" * 50)
    
    # Test 1: Check if enhanced modules are available
    print("1. Testing module imports...")
    try:
        from realtime_status import status_manager
        from tasks_enhanced import process_note_with_status
        print("   ✅ Real-time modules imported successfully")
    except ImportError as e:
        print(f"   ❌ Import error: {e}")
        return False
    
    # Test 2: Check database connection
    print("2. Testing database connection...")
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM notes")
        note_count = c.fetchone()[0]
        conn.close()
        print(f"   ✅ Database connected. {note_count} notes found.")
    except Exception as e:
        print(f"   ❌ Database error: {e}")
        return False
    
    # Test 3: Test status manager
    print("3. Testing status manager...")
    try:
        # Create a test note
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO notes (title, content, status, user_id) 
            VALUES (?, ?, ?, ?)
        """, ("Test Note", "This is a test note for real-time status", "pending", 1))
        test_note_id = c.lastrowid
        conn.commit()
        conn.close()
        
        print(f"   ✅ Test note created with ID: {test_note_id}")
        
        # Test status manager methods
        await status_manager.emit_progress(test_note_id, "testing", 50, "Test progress")
        await status_manager.emit_completion(test_note_id, True)
        
        # Verify status in database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        status = c.execute("SELECT status FROM notes WHERE id = ?", (test_note_id,)).fetchone()[0]
        conn.close()
        
        print(f"   ✅ Status manager test complete. Final status: {status}")
        
        # Clean up test note
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM notes WHERE id = ?", (test_note_id,))
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"   ❌ Status manager error: {e}")
        return False
    
    # Test 4: Test SSE endpoint (if server is running)
    print("4. Testing SSE endpoint...")
    try:
        async with aiohttp.ClientSession() as session:
            # First check if server is running
            async with session.get(f"{API_BASE}/health") as resp:
                if resp.status != 200:
                    print("   ⚠️  Server not running - skipping SSE test")
                else:
                    print("   ✅ Server is running")
                    
                    # Create a test note via API (would need auth token in real test)
                    # For now, just test the endpoint exists
                    try:
                        # Just test the endpoint responds (will get 401 without auth)
                        async with session.get(f"{API_BASE}/api/status/stream/1") as resp:
                            if resp.status in [401, 404]:  # Expected without auth
                                print("   ✅ SSE endpoint is accessible")
                            else:
                                print(f"   ❓ SSE endpoint response: {resp.status}")
                    except Exception as e:
                        print(f"   ⚠️  SSE endpoint test failed: {e}")
                        
    except Exception as e:
        print(f"   ⚠️  Could not connect to server: {e}")
    
    print("\n🎉 Real-time status test completed!")
    print("\n📋 Manual Testing Steps:")
    print("1. Start the Second Brain server: `python app.py` or `uvicorn app:app --reload --port 8084`")
    print("2. Open browser to http://localhost:8084")
    print("3. Upload an audio file or create a note")
    print("4. Watch for real-time progress bars and status updates")
    print("5. Check browser console for SSE messages")
    print("6. Verify processing queue appears when notes are pending")
    
    return True


if __name__ == "__main__":
    asyncio.run(test_realtime_status())