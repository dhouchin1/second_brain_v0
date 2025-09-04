#!/usr/bin/env python3
"""
Database Migration for File Support
Adds file handling columns to the notes table
"""

import sqlite3
from pathlib import Path
from config import settings

def migrate_notes_table_for_files():
    """Add file-related columns to notes table"""
    conn = sqlite3.connect(settings.db_path)
    c = conn.cursor()
    
    # Check current table structure
    columns = [row[1] for row in c.execute("PRAGMA table_info(notes)")]
    
    migrations_needed = []
    
    # Add file-related columns if they don't exist
    new_columns = {
        'file_filename': 'TEXT',  # Stored filename for any file type
        'file_type': 'TEXT',      # image, document, audio
        'file_mime_type': 'TEXT', # Original MIME type
        'file_size': 'INTEGER',   # File size in bytes
        'extracted_text': 'TEXT', # OCR/PDF extracted text
        'file_metadata': 'TEXT'   # JSON metadata about the file
    }
    
    for col_name, col_type in new_columns.items():
        if col_name not in columns:
            migrations_needed.append(f"ALTER TABLE notes ADD COLUMN {col_name} {col_type}")
    
    # Execute migrations
    for migration in migrations_needed:
        print(f"Executing: {migration}")
        c.execute(migration)
    
    # Update FTS table to include extracted_text
    fts_columns = [row[1] for row in c.execute("PRAGMA table_info(notes_fts)")]
    if 'extracted_text' not in fts_columns:
        print("Updating FTS table for extracted_text...")
        c.execute("DROP TABLE IF EXISTS notes_fts")
        c.execute('''
            CREATE VIRTUAL TABLE notes_fts USING fts5(
                title, summary, tags, actions, content, extracted_text,
                content='notes', content_rowid='id'
            )
        ''')
        
        # Repopulate FTS from existing notes
        c.execute("""
            INSERT INTO notes_fts(rowid, title, summary, tags, actions, content, extracted_text)
            SELECT id, title, summary, tags, actions, content, COALESCE(extracted_text, '')
            FROM notes
        """)
    
    conn.commit()
    conn.close()
    print("Database migration completed successfully!")

if __name__ == "__main__":
    migrate_notes_table_for_files()