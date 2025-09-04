#!/usr/bin/env python3
"""
Add email column to users table for magic link authentication
"""

import sqlite3
from pathlib import Path

def add_email_column():
    # Use the same DB path as the app
    db_path = Path(__file__).parent / "notes.db"
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Check if email column already exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'email' not in columns:
            print("Adding email column to users table...")
            # Add column without unique constraint first
            cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
            conn.commit()
            print("✅ Email column added successfully!")
            
            # Create unique index separately (after data is populated)
            print("Creating unique index on email...")
            try:
                cursor.execute("CREATE UNIQUE INDEX idx_users_email ON users(email)")
                conn.commit()
                print("✅ Unique index created!")
            except sqlite3.OperationalError as e:
                if "already exists" not in str(e):
                    print(f"⚠️  Index creation failed: {e}")
        else:
            print("ℹ️  Email column already exists")
            
        # Show current users
        cursor.execute("SELECT id, username, email FROM users")
        users = cursor.fetchall()
        
        print(f"\nCurrent users ({len(users)}):")
        for user in users:
            print(f"  ID: {user[0]}, Username: {user[1]}, Email: {user[2] or '(no email)'}")
            
        # Offer to add email to existing users
        if users and not any(user[2] for user in users):
            print("\n💡 You can add email addresses to existing users for magic link login:")
            for user in users:
                email = input(f"Email for user '{user[1]}' (press Enter to skip): ").strip()
                if email and '@' in email:
                    try:
                        cursor.execute("UPDATE users SET email = ? WHERE id = ?", (email, user[0]))
                        print(f"   ✅ Updated {user[1]} with email {email}")
                    except sqlite3.IntegrityError:
                        print(f"   ❌ Email {email} already exists")
                        
            conn.commit()
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    add_email_column()