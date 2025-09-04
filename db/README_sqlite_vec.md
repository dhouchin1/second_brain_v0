sqlite-vec Integration Notes

Overview
- Vector search is optional. When enabled, it augments FTS5 keyword search with ANN over dense vectors via the sqlite-vec extension.
- The app works without sqlite-vec (keyword-only mode). When the extension is available, hybrid search becomes active automatically.

Setup
- Build or download sqlite-vec and locate the loadable extension file (e.g., sqlite-vec0.dylib on macOS, .so on Linux).
- Export the path in your environment:
  - SQLITE_VEC_PATH=/absolute/path/to/sqlite-vec0.dylib
  - SQLITE_DB=notes.db (optional; defaults to notes.db)

Migrations Behavior
- Migration files relevant to vectors:
  - db/migrations/001_core.sql: base schema and FTS5 setup.
  - db/migrations/002_vec.sql: creates vec0 virtual table note_vecs when sqlite-vec is loaded.
  - db/migrations/002_vector_embeddings.sql: alternative embedding/job schema used by some modules.
- If sqlite-vec is not available, applying 002_vec.sql will fail safely and be skipped by the service layer; the app continues in keyword mode.
- Having both 002_vec.sql and 002_vector_embeddings.sql present is intentional for now. The primary runtime path uses 002_vec.sql; the alternative schema supports advanced embedding/job tracking.

Quick Check
- Use the helper to verify extension loading:
  - python scripts/sqlite_vec_check.py
- Expected output: success message and ability to create a temporary vec0 table.

Troubleshooting
- If loading fails, ensure `enable_load_extension` is permitted and SQLITE_VEC_PATH points to the correct library.
- On macOS, you may need to allowloading extensions for the Python SQLite build; most default builds support this.

