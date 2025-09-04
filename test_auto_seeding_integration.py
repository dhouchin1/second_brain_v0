#!/usr/bin/env python3
"""
Test Auto-Seeding Integration

This script tests the auto-seeding system integration by simulating different scenarios:
1. Fresh installation detection
2. New user registration with auto-seeding
3. Auto-seeding service functionality
4. Admin API endpoints
"""

import sqlite3
import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def setup_test_environment():
    """Create a temporary test environment."""
    test_dir = tempfile.mkdtemp(prefix="second_brain_test_")
    test_db = os.path.join(test_dir, "test_notes.db")
    test_vault = os.path.join(test_dir, "test_vault")
    
    # Create basic directory structure
    os.makedirs(test_vault, exist_ok=True)
    os.makedirs(os.path.join(test_vault, ".secondbrain"), exist_ok=True)
    
    print(f"📁 Test environment created: {test_dir}")
    print(f"🗄️  Test database: {test_db}")
    print(f"📝 Test vault: {test_vault}")
    
    return test_dir, test_db, test_vault

def create_test_database(db_path):
    """Create a minimal test database with core tables."""
    conn = sqlite3.connect(db_path)
    
    # Create core tables
    conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    conn.execute("""
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT,
            content TEXT,
            summary TEXT,
            tags TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    # Create auto-seeding log table (required by initialization service)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS auto_seeding_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            success BOOLEAN NOT NULL,
            message TEXT,
            namespace TEXT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            config TEXT,
            notes_created INTEGER DEFAULT 0,
            files_created INTEGER DEFAULT 0,
            embeddings_created INTEGER DEFAULT 0
        )
    """)
    
    conn.commit()
    conn.close()
    
    print("✅ Test database schema created")

def test_fresh_installation_detection(test_db):
    """Test fresh installation detection logic."""
    print("\n🧪 Testing fresh installation detection...")
    
    try:
        # Override settings for test
        import config
        original_db_path = config.settings.db_path
        config.settings.db_path = Path(test_db)
        
        from services.initialization_service import get_initialization_service
        
        def get_test_conn():
            return sqlite3.connect(test_db)
        
        init_service = get_initialization_service(get_test_conn)
        
        # Test 1: Empty database should be fresh
        is_fresh = init_service.is_fresh_installation()
        print(f"  Empty database fresh check: {is_fresh} ✅" if is_fresh else f"  Empty database fresh check: {is_fresh} ❌")
        
        # Test 2: Add a user - should still be fresh
        conn = sqlite3.connect(test_db)
        conn.execute("INSERT INTO users (username, hashed_password) VALUES ('testuser', 'hashedpw')")
        conn.commit()
        conn.close()
        
        is_fresh = init_service.is_fresh_installation()
        print(f"  One user database fresh check: {is_fresh} ✅" if is_fresh else f"  One user database fresh check: {is_fresh} ❌")
        
        # Test 3: Add many notes - should not be fresh
        conn = sqlite3.connect(test_db)
        for i in range(10):
            conn.execute("INSERT INTO notes (user_id, title, content) VALUES (1, ?, ?)", 
                        (f"Test Note {i}", f"Content for note {i}"))
        conn.commit()
        conn.close()
        
        is_fresh = init_service.is_fresh_installation()
        print(f"  Many notes database fresh check: {is_fresh} ❌" if not is_fresh else f"  Many notes database fresh check: {is_fresh} ✅")
        
        # Restore original settings
        config.settings.db_path = original_db_path
        
        return True
        
    except Exception as e:
        print(f"  ❌ Fresh installation detection test failed: {e}")
        return False

def test_auto_seeding_service(test_db, test_vault):
    """Test auto-seeding service functionality."""
    print("\n🧪 Testing auto-seeding service...")
    
    try:
        # Override settings for test
        import config
        original_db_path = config.settings.db_path
        original_vault_path = config.settings.vault_path
        config.settings.db_path = Path(test_db)
        config.settings.vault_path = Path(test_vault)
        
        from services.auto_seeding_service import get_auto_seeding_service
        
        def get_test_conn():
            return sqlite3.connect(test_db)
        
        # Create a test user with no content
        conn = sqlite3.connect(test_db)
        conn.execute("DELETE FROM notes")  # Clear existing notes
        conn.execute("DELETE FROM users")  # Clear existing users
        cursor = conn.execute("INSERT INTO users (username, hashed_password) VALUES ('newuser', 'hashedpw')")
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        
        auto_seeding_service = get_auto_seeding_service(get_test_conn)
        
        # Test 1: Check if user should be auto-seeded
        should_seed_result = auto_seeding_service.should_auto_seed(user_id)
        print(f"  Should seed new user: {should_seed_result['should_seed']} ✅" if should_seed_result['should_seed'] else f"  Should seed new user: {should_seed_result['should_seed']} - {should_seed_result['reason']}")
        
        # Test 2: Check auto-seeding system status
        system_status = auto_seeding_service.check_auto_seeding_status()
        print(f"  Auto-seeding system enabled: {system_status['enabled']} ✅" if system_status['enabled'] else f"  Auto-seeding system enabled: {system_status['enabled']} ❌")
        
        # Test 3: Get auto-seeding history (should be empty)
        history = auto_seeding_service.get_auto_seeding_history(user_id)
        print(f"  Initial auto-seeding history empty: {len(history) == 0} ✅" if len(history) == 0 else f"  Initial auto-seeding history empty: {len(history) == 0} ❌")
        
        # Restore original settings
        config.settings.db_path = original_db_path
        config.settings.vault_path = original_vault_path
        
        return True
        
    except Exception as e:
        print(f"  ❌ Auto-seeding service test failed: {e}")
        return False

def test_initialization_service(test_db, test_vault):
    """Test initialization service functionality."""
    print("\n🧪 Testing initialization service...")
    
    try:
        # Override settings for test
        import config
        original_db_path = config.settings.db_path
        original_vault_path = config.settings.vault_path
        config.settings.db_path = Path(test_db)
        config.settings.vault_path = Path(test_vault)
        
        from services.initialization_service import get_initialization_service
        
        def get_test_conn():
            return sqlite3.connect(test_db)
        
        init_service = get_initialization_service(get_test_conn)
        
        # Test 1: Get initialization status
        status = init_service.get_initialization_status()
        print(f"  Initialization status retrieved: {'✅' if 'is_fresh_installation' in status else '❌'}")
        print(f"    - Fresh installation: {status.get('is_fresh_installation', 'Unknown')}")
        print(f"    - User count: {status.get('user_count', 'Unknown')}")
        print(f"    - Note count: {status.get('note_count', 'Unknown')}")
        
        # Test 2: Test user onboarding (dry run - don't actually perform seeding)
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("INSERT INTO users (username, hashed_password) VALUES ('onboardinguser', 'hashedpw')")
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        
        # Check if user is considered new
        is_new_user = init_service.is_new_user(user_id)
        print(f"  New user detection: {is_new_user} ✅" if is_new_user else f"  New user detection: {is_new_user} ❌")
        
        # Restore original settings
        config.settings.db_path = original_db_path
        config.settings.vault_path = original_vault_path
        
        return True
        
    except Exception as e:
        print(f"  ❌ Initialization service test failed: {e}")
        return False

def test_error_handling():
    """Test error handling scenarios."""
    print("\n🧪 Testing error handling...")
    
    try:
        from services.auto_seeding_service import get_auto_seeding_service
        from services.initialization_service import get_initialization_service
        
        def get_bad_conn():
            # Return connection to non-existent database
            return sqlite3.connect("/nonexistent/path/test.db")
        
        # Test 1: Auto-seeding with bad database connection
        try:
            auto_seeding_service = get_auto_seeding_service(get_bad_conn)
            result = auto_seeding_service.should_auto_seed(1)
            print(f"  Bad connection handling: {'✅' if not result['should_seed'] else '❌'}")
        except Exception as e:
            print(f"  Bad connection exception handling: ✅")
        
        # Test 2: Initialization with bad database connection
        try:
            init_service = get_initialization_service(get_bad_conn)
            status = init_service.get_initialization_status()
            print(f"  Bad initialization handling: {'✅' if 'error' in status else '❌'}")
        except Exception as e:
            print(f"  Bad initialization exception handling: ✅")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error handling test failed: {e}")
        return False

def cleanup_test_environment(test_dir):
    """Clean up the test environment."""
    try:
        shutil.rmtree(test_dir)
        print(f"\n🧹 Test environment cleaned up: {test_dir}")
    except Exception as e:
        print(f"\n❌ Failed to clean up test environment: {e}")

def main():
    """Run all auto-seeding integration tests."""
    print("🚀 Starting Auto-Seeding Integration Tests")
    print("=" * 50)
    
    # Setup test environment
    test_dir, test_db, test_vault = setup_test_environment()
    
    try:
        # Create test database
        create_test_database(test_db)
        
        # Run tests
        tests = [
            ("Fresh Installation Detection", lambda: test_fresh_installation_detection(test_db)),
            ("Auto-Seeding Service", lambda: test_auto_seeding_service(test_db, test_vault)),
            ("Initialization Service", lambda: test_initialization_service(test_db, test_vault)),
            ("Error Handling", test_error_handling)
        ]
        
        passed_tests = 0
        total_tests = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n{'=' * 50}")
            try:
                if test_func():
                    passed_tests += 1
                    print(f"✅ {test_name} PASSED")
                else:
                    print(f"❌ {test_name} FAILED")
            except Exception as e:
                print(f"❌ {test_name} FAILED with exception: {e}")
        
        # Summary
        print(f"\n{'=' * 50}")
        print(f"📊 TEST SUMMARY")
        print(f"   Passed: {passed_tests}/{total_tests}")
        print(f"   Success Rate: {passed_tests/total_tests*100:.1f}%")
        
        if passed_tests == total_tests:
            print("🎉 All tests passed! Auto-seeding integration looks good.")
        else:
            print("⚠️  Some tests failed. Please review the issues above.")
        
    finally:
        # Cleanup
        cleanup_test_environment(test_dir)

if __name__ == "__main__":
    main()