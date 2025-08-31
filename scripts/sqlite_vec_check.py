"""
Sanity check for sqlite-vec extension loading.

Reads env:
- SQLITE_DB (default: notes.db)
- SQLITE_VEC_PATH (required for this check)
"""
import os
import sqlite3
import sys

DB = os.getenv("SQLITE_DB", "notes.db")
VEC = os.getenv("SQLITE_VEC_PATH")

if not VEC:
    print("ERROR: SQLITE_VEC_PATH not set. Export path to sqlite-vec0.dylib/.so and retry.")
    sys.exit(1)

con = sqlite3.connect(DB)
try:
    con.enable_load_extension(True)
    con.load_extension(VEC)
    cur = con.cursor()
    # Create a tiny temp vec0 table to prove extension works
    cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp.__vec_check USING vec0(embedding float[3])")
    cur.execute("DROP TABLE temp.__vec_check")
    print("OK: sqlite-vec loaded and vec0 table can be created.")
except Exception as e:
    print(f"FAIL: could not load sqlite-vec: {e}")
    sys.exit(2)
finally:
    con.close()

