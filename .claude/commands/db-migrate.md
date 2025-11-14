# Database Migration Manager

Create, apply, or rollback database migrations for Second Brain.

## Instructions

Manage database schema changes safely:

1. **Understand the action** - Create new, apply pending, or rollback
2. **Check current status** - Show applied migrations
3. **Execute safely** - Backup before destructive operations
4. **Verify results** - Confirm migration success

## Commands

### Check Migration Status

```bash
# Show all migrations
sqlite3 notes.db "SELECT * FROM migrations ORDER BY id DESC"

# Show latest migration
sqlite3 notes.db "SELECT * FROM migrations ORDER BY id DESC LIMIT 1"

# Count migrations
sqlite3 notes.db "SELECT COUNT(*) FROM migrations"
```

### Apply Migrations

```bash
# Run migration script (applies all pending)
python migrate_db.py

# Check what would be applied
ls db/migrations/*.sql
```

### Create New Migration

```bash
# Generate migration file with timestamp
MIGRATION_NAME="add_note_categories"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
touch "db/migrations/${TIMESTAMP}_${MIGRATION_NAME}.sql"

# Edit the new file
```

### Migration File Template

```sql
-- Migration: Add note categories
-- Created: 2025-11-13
-- Description: Add category support to notes table

-- Check if column exists before adding
-- SQLite doesn't support IF NOT EXISTS for ALTER TABLE

PRAGMA foreign_keys=OFF;

BEGIN TRANSACTION;

-- Add new column
ALTER TABLE notes ADD COLUMN category TEXT DEFAULT 'general';

-- Create index
CREATE INDEX IF NOT EXISTS idx_notes_category ON notes(category);

-- Update existing data if needed
UPDATE notes SET category = 'default' WHERE category IS NULL;

-- Record migration
INSERT INTO migrations (name, applied_at)
VALUES ('add_note_categories', datetime('now'));

COMMIT;

PRAGMA foreign_keys=ON;
```

## Common Migration Patterns

### Add Column

```sql
-- Simple add column
ALTER TABLE notes ADD COLUMN priority INTEGER DEFAULT 0;

-- With index
ALTER TABLE notes ADD COLUMN status TEXT DEFAULT 'active';
CREATE INDEX IF NOT EXISTS idx_notes_status ON notes(status);
```

### Add Table

```sql
-- Create new table
CREATE TABLE IF NOT EXISTS note_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT,
    icon TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create relationship table
CREATE TABLE IF NOT EXISTS note_category_mapping (
    note_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    PRIMARY KEY (note_id, category_id),
    FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES note_categories(id) ON DELETE CASCADE
);
```

### Add FTS5 Virtual Table

```sql
-- Create FTS5 search table
CREATE VIRTUAL TABLE IF NOT EXISTS categories_fts USING fts5(
    name,
    description,
    content='note_categories',
    content_rowid='id'
);

-- Create triggers to keep FTS5 in sync
CREATE TRIGGER IF NOT EXISTS categories_ai AFTER INSERT ON note_categories BEGIN
    INSERT INTO categories_fts(rowid, name, description)
    VALUES (new.id, new.name, new.description);
END;

CREATE TRIGGER IF NOT EXISTS categories_ad AFTER DELETE ON note_categories BEGIN
    DELETE FROM categories_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS categories_au AFTER UPDATE ON note_categories BEGIN
    DELETE FROM categories_fts WHERE rowid = old.id;
    INSERT INTO categories_fts(rowid, name, description)
    VALUES (new.id, new.name, new.description);
END;
```

### Add Index

```sql
-- Single column index
CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at DESC);

-- Multi-column index
CREATE INDEX IF NOT EXISTS idx_notes_user_created ON notes(user_id, created_at DESC);

-- Partial index (conditional)
CREATE INDEX IF NOT EXISTS idx_notes_pending ON notes(status)
WHERE status = 'pending';

-- Full-text search index
CREATE INDEX IF NOT EXISTS idx_notes_body_fts ON notes_fts(body);
```

### Modify Column (SQLite Workaround)

SQLite doesn't support ALTER COLUMN, so you need to recreate the table:

```sql
-- Rename old table
ALTER TABLE notes RENAME TO notes_old;

-- Create new table with modified schema
CREATE TABLE notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,  -- Changed from NULL to NOT NULL
    body TEXT,
    -- ... other columns
);

-- Copy data
INSERT INTO notes SELECT * FROM notes_old;

-- Drop old table
DROP TABLE notes_old;

-- Recreate indices
CREATE INDEX IF NOT EXISTS idx_notes_title ON notes(title);
```

## Migration Best Practices

### 1. Always Backup First

```bash
# Backup database before migration
cp notes.db notes.db.backup.$(date +%Y%m%d_%H%M%S)

# Or use SQLite backup command
sqlite3 notes.db ".backup notes.db.backup"
```

### 2. Test on Copy First

```bash
# Test migration on copy
cp notes.db notes_test.db
sqlite3 notes_test.db < db/migrations/new_migration.sql

# If successful, apply to real database
```

### 3. Use Transactions

```sql
BEGIN TRANSACTION;
-- Your migration code here
COMMIT;
-- If error occurs, SQLite will auto-rollback
```

### 4. Add Migration Metadata

```sql
-- Record migration in migrations table
INSERT INTO migrations (name, applied_at, description)
VALUES (
    'add_categories',
    datetime('now'),
    'Add category support to notes with many-to-many relationship'
);
```

### 5. Handle Data Migration

```sql
-- Update existing data when adding constraints
UPDATE notes SET title = 'Untitled' WHERE title IS NULL OR title = '';

-- Migrate data to new structure
INSERT INTO new_table (id, field)
SELECT id, old_field FROM old_table;
```

## Rollback Procedure

Since SQLite doesn't support easy rollbacks, maintain rollback scripts:

### Create Rollback Migration

```sql
-- File: db/migrations/rollback_20251113_add_categories.sql
-- Rollback: Remove category support

BEGIN TRANSACTION;

-- Drop tables in reverse order
DROP TABLE IF EXISTS note_category_mapping;
DROP TABLE IF EXISTS note_categories;
DROP INDEX IF EXISTS idx_notes_category;

-- Remove column (if possible, or use table recreation)
-- SQLite: Must recreate table to remove column
ALTER TABLE notes RENAME TO notes_old;

CREATE TABLE notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    body TEXT
    -- ... without category column
);

INSERT INTO notes SELECT id, title, body FROM notes_old;
DROP TABLE notes_old;

-- Remove migration record
DELETE FROM migrations WHERE name = 'add_categories';

COMMIT;
```

## Check Migration Applied

```python
import sqlite3

def check_migration_applied(migration_name):
    conn = sqlite3.connect('notes.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM migrations WHERE name = ?", (migration_name,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

# Usage
if check_migration_applied('add_categories'):
    print("✅ Migration already applied")
else:
    print("⚠️ Migration not yet applied")
```

## Verify Migration

```bash
# Check table schema
sqlite3 notes.db ".schema notes"

# Check indices
sqlite3 notes.db ".indices notes"

# Count records
sqlite3 notes.db "SELECT COUNT(*) FROM notes"

# Test query
sqlite3 notes.db "SELECT * FROM notes LIMIT 1"
```

## Troubleshooting

### Migration Failed Mid-Way
```bash
# Restore from backup
cp notes.db.backup notes.db

# Check what went wrong
sqlite3 notes.db "PRAGMA integrity_check"
```

### Column Already Exists
```sql
-- Check before adding
SELECT COUNT(*) FROM pragma_table_info('notes') WHERE name='category';

-- Or handle with Python
```

### Foreign Key Constraints
```sql
-- Disable during migration
PRAGMA foreign_keys=OFF;
-- ... migration code ...
PRAGMA foreign_keys=ON;
```
