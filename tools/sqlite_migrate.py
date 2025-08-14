#!/usr/bin/env python3
import sqlite3, sys

DB = sys.argv[1] if len(sys.argv) > 1 else "second_brain.db"

DDL = [
    "ALTER TABLE notes ADD COLUMN body TEXT;",
    "ALTER TABLE notes ADD COLUMN tags TEXT;",
    "ALTER TABLE notes ADD COLUMN created_at TEXT;",
]

con = sqlite3.connect(DB)
cur = con.cursor()
for stmt in DDL:
    try:
        cur.execute(stmt)
        print(f"OK: {stmt}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(f"SKIP (exists): {stmt}")
        else:
            print(f"ERR: {stmt} -> {e}")
con.commit()
con.close()
print("Done.")