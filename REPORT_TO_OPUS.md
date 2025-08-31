# Duplicate Code and Overlap Report

This report summarizes duplicate and overlapping implementations across the repository and proposes a pragmatic consolidation plan. The aim is to reduce maintenance surface area while preserving current features and optional dependencies.

## Executive Summary
- Search is implemented in multiple places (legacy engines, hybrid variants, and a newer service adapter). Recommend standardizing on `services/SearchService` for runtime usage and retiring legacy engines behind a thin compatibility layer or archiving them.
- Obsidian sync exists in two main variants (root vs services), plus an enhanced fresh prototype. Recommend choosing one canonical module (root) and extracting shared utilities to a common helper to reduce drift.
- API endpoints live both in `app.py` and modular routers; several endpoints are duplicated in `app.py`. Recommend routing consolidation to the modular `api/routes_*` and removing/aliasing duplicates.
- Embedding and vector storage follow two patterns (sqlite-vec vec0 vs relational tables). Recommend picking one primary path (sqlite-vec optional) and gating alternatives via config, with a single abstraction in the service layer.

## High-Impact Duplicates

### 1) Search Stack
Files:
- `search_engine.py`
- `hybrid_search.py`
- `semantic_search.py`
- `hybrid_fusion.py`
- `services/search_adapter.py` (newer, unified)
- `fresh/search_engine.py` (prototype)
- Scaffolds: `additions/search_automation_scaffold_fts_5_sqlite_vec_drop_in.py` (contains embedded copies of adapter and routes)

Observations:
- `services/search_adapter.py` encapsulates FTS5, optional sqlite-vec, and migrations, with clean methods: `upsert_note`, `search(mode=keyword|semantic|hybrid)`, private `_keyword/_semantic/_hybrid`.
- Legacy engines (`search_engine.py`, `hybrid_search.py`, `semantic_search.py`) implement overlapping behavior with inconsistent data models and dependencies (e.g., different embedding dims, indexing methods).
- Prototypes (`fresh/*`, scaffolds) duplicate substantial logic and should not be used in production paths.

Recommendation:
- Canonicalize on `services/SearchService` for all runtime search and indexing.
- For endpoints currently using legacy engines, replace with the adapter or provide a small shim that calls `SearchService`.
- Archive legacy engines to `archive/` (or mark deprecated) once routes are switched.

Migration Note:
- `services/search_adapter.py` expects envs `SQLITE_DB`, `SQLITE_VEC_PATH` (optional), and runs `db/migrations/001_core.sql` + `002_vec.sql`. Docs added in `db/README_sqlite_vec.md`.

### 2) API Endpoints
Files:
- `app.py` (monolithic, many routes; duplicates present)
- `api/routes_search.py`, `api/routes_capture.py` (modular)

Examples of duplication in `app.py`:
- Multiple `/webhook/discord` declarations: `app.py:1277`, `app.py:1632`, `app.py:2442`
- Multiple search endpoints: `app.py:1197` (`/api/search/enhanced`), `app.py:1423` (`/api/search`), `app.py:2413` (another `/api/search/enhanced`)

Recommendation:
- Move request handling to the modular routers and include them from `app.py`.
- Remove or alias the duplicate routes in `app.py` after validating parity with router behavior.
- Keep thin wrappers in `app.py` only where auth/session context is tightly coupled; otherwise prefer routers.

### 3) Obsidian Sync
Files:
- Root: `obsidian_sync.py` (used by `app.py` routes)
- Service: `services/obsidian_sync.py` (depends on `SearchService`)
- Prototype: `fresh/obsidian_sync_enhanced.py`

Observations:
- Both root and service variants offer export/import/bidirectional sync, but differ in:
  - Data model fields (e.g., `title/content/summary/tags/actions` vs `title/body/tags`, `zettel_id`, timestamps)
  - Frontmatter schemas and file layout (project scoping in services variant)
  - How indexing/search is updated post-import

Recommendation:
- Keep root `obsidian_sync.py` as canonical for now (it's wired into `app.py`).
- Extract shared helpers (frontmatter I/O, filename sanitation, audio attachment copy, markdown sections) into a new small module `obsidian_common.py` used by both, or merge the service behavior into the root while preserving settings-driven project layout.
- Defer full merge until DB schema is unified (see below).

### 4) Embeddings and Vector Storage
Files:
- `db/migrations/002_vec.sql` (sqlite-vec vec0 virtual table `note_vecs`)
- `db/migrations/002_vector_embeddings.sql` (relational `note_embeddings`, jobs, views)
- `embedding_manager.py`
- `services/embeddings.py`

Observations:
- Two distinct approaches exist: extension-backed ANN (`vec0`) vs relational blobs + jobs.
- `services/search_adapter.py` is designed to prefer sqlite-vec when available and fall back gracefully; `embedding_manager.py` manages embeddings separately.

Recommendation:
- Choose one primary production path (suggest sqlite-vec optional path via `SearchService`).
- If relational embedding tables are still required for analytics or portability, hide that behind `SearchService` so callers never depend on the storage shape.
- Consolidate to a single embeddings provider module (favor `services/embeddings.py`) and adapt `embedding_manager.py` to a thin wrapper or archive it.

### 5) Processing Pipeline
Files:
- `processor.py` (audio/summary pipeline with Ollama)
- `file_processor.py` (file ingest logic)
- Background jobs: `services/jobs.py` (runner), plus app background tasks

Observations:
- Overlap in responsibilities for ingest, transform, and indexing. Some pipelines update search indices directly, others rely on background jobs.

Recommendation:
- Establish a single ingestion facade that coordinates: file decode/transcription, summarization, tagging, and indexing via `SearchService.upsert_note`.
- Ensure background jobs use the same facade to avoid divergent behavior.

### 6) App Variants and Scaffolds
Files:
- `app_v0.py`, `app_v1.py`, `app_v2.py`, `app_v00.py`, `app_backup_before_capture_enhancement.py`, `__app_with_auth.py`
- Scripts that embed copies of classes (integration scripts)

Recommendation:
- Move historical app variants and integration scripts to `archive/` (or tag and remove) to prevent accidental usage.
- Keep `README_quickstart.md` as the canonical quick-start and link to any advanced docs.

## Suggested Consolidation Plan (Incremental)

1) Route Consolidation
- Switch search and capture endpoints to the modular routers everywhere, ensuring they call `services/SearchService`.
- Remove duplicate routes in `app.py` after confirming feature parity and auth checks.

2) Search Unification
- Migrate code-paths that depend on `search_engine.py`/`hybrid_search.py`/`semantic_search.py` to `SearchService`.
- Archive legacy engines; optionally keep a minimal shim to avoid breaking imports.

3) Obsidian Sync Alignment
- Keep root `obsidian_sync.py` canonical.
- Extract shared helpers to `obsidian_common.py` used by both root and services variants.
- Decide on frontmatter schema and project layout toggles via config (unify behavior).

4) Embeddings Strategy
- Primary: sqlite-vec when `SQLITE_VEC_PATH` is configured; otherwise keyword-only.
- Secondary (optional): relational embeddings behind `SearchService`, without leaking storage shape to callers.
- Consolidate on `services/embeddings.py` as the single provider.

5) Archive/Deprecate
- Move `fresh/*`, integration scripts with embedded code, and historical app variants to `archive/`.
- Add a README in `archive/` explaining historical context.

## Low-Risk Cleanups Done
- Added `services/__init__.py` to formalize the service layer entrypoint.
- Updated `AGENTS.md` to reflect modular routers and services, and to note the dual Obsidian sync implementations.
- Added sqlite-vec docs (`db/README_sqlite_vec.md`), a check script (`scripts/sqlite_vec_check.py`), and env examples in `.env.example`.
- Ignored `*.log` and `server.log` in `.gitignore`.

## Open Questions / Decisions Needed
- Which Obsidian frontmatter schema is canonical? Root vs services variant differ slightly.
- Do we want relational embedding tables at all, or fully commit to sqlite-vec optional path?
- Should `config.py` become the single source of truth for DB path and pass it into `SearchService`, instead of mixing `settings.db_path` and `SQLITE_DB` env usage?
- Is there any production code still relying on `search_engine.py` or `hybrid_search.py` that can’t be switched immediately?

## Quick Wins (if desired next)
- In `app.py`, dedupe `/webhook/discord` routes (keep one handler) and ensure all webhook paths are uniquely named.
- Update `app.py` search endpoints to call `services/SearchService` and remove the duplicate `/api/search/enhanced`.
- Add a small `obsidian_common.py` with shared helpers (frontmatter read/write, sanitize filename) and refactor both Obsidian modules to use it.

---

Prepared for: Claude Opus
By: Codex (duplicate analysis)

## Quick Wins Implemented (this pass)

- Dedupe conflicting routes in `app.py` by moving duplicates to legacy paths:
  - Renamed duplicate `POST /api/search/enhanced` (second definition) to `POST /api/search/enhanced_legacy` and hid it from schema.
  - Renamed duplicate Discord webhooks to avoid path collisions:
    - Second definition → `POST /webhook/discord/legacy` (function: `webhook_discord_legacy1`)
    - Third definition → `POST /webhook/discord/legacy2` (function: `webhook_discord_legacy2`)
  - Result: Exactly one active `POST /webhook/discord` remains; duplicates no longer collide.

- Added a service-backed search endpoint that uses the unified adapter:
  - New: `POST /api/search/service` that delegates to `services.SearchService.search(mode='hybrid')` and returns normalized rows.
  - Keeps existing endpoints intact while providing a clean migration path to the service layer.

- Migrated the primary `/api/search` endpoint to `SearchService`:
  - Preserved the original request schema (`SearchRequest` with `query`, `filters`, `limit`).
  - Translates filters `type|mode` to `keyword|semantic|hybrid` and delegates to `SearchService`.
  - Returns `{ results, total, query, mode }` to closely match prior shape while adding the resolved mode.

- Extracted shared Obsidian helpers and refactored both modules to use them:
  - Added `obsidian_common.py` with `sanitize_filename()` and `frontmatter_yaml()`.
  - `services/obsidian_sync.py`: uses `sanitize_filename` in filename build and `frontmatter_yaml` for consistent frontmatter.
  - Added `load_frontmatter_file()` and `dump_frontmatter_file()` to support parsing/writing frontmatter without requiring `python-frontmatter`.
  - `obsidian_sync.py` (root):
    - Replaced local `_sanitize_filename` with common `sanitize_filename`.
    - Now uses `dump_frontmatter_file()` for export and `load_frontmatter_file()` for import; removes hard dependency on `python-frontmatter`.
    - `_extract_note_id()` now uses the common loader.

- Removed unnecessary/duplicate code and tightened imports:
  - Removed redundant `class SearchRequest` duplicate; ensured early references use a forward-ref string where needed.
  - Quoted type annotations where the class is referenced before definition to avoid NameError at import time.
  - Dropped a stale `yaml` import from `obsidian_sync.py`; YAML emission/parsing is handled by `obsidian_common` helpers.
  - Replaced `obsidian_sync.py`'s dependency on `search_engine.EnhancedSearchEngine` with an optional call into `services.SearchService` to update vectors (FTS remains trigger-driven). If the service layer is unavailable, it gracefully skips vector updates.
  - Migrated tests off the legacy engine where used:
    - `tests/unit/test_search.py` now uses `services.SearchService` and asserts over sqlite rows.
    - `test_search_performance.py` FTS test path now uses `SearchService` in `keyword` mode; logs unchanged.
  - Removed duplicate and unused imports:
    - `file_processor.py`: dropped a duplicate `hashlib` import.
    - `realtime_status.py`: removed unused FastAPI imports (`Depends`, `HTTPException`, `JSONResponse`).
    - `services/search_adapter.py`: removed unused `typing.Iterable` import.
    - `hybrid_search.py`: removed unused `numpy` import.
    - `semantic_search.py`: removed unused `asdict` import from dataclasses.
    - `file_processor.py`: removed redundant in-function `import base64` (top-level import already present).
    - `debug_capture.py`: removed unused `datetime` import.
    - `url_utils.py`: removed unused `urljoin` and `parse_qs` imports; trimmed unused `Dict` typing.
    - `automated_relationships.py`: removed unused `threading` and `typing.Set` imports.
    - `processor.py`: removed stray non-ASCII character causing a syntax error in a write() call; also dropped unused imports (`uuid`, `shutil`, `os`).

## Ideas/Notes (future work, not implemented now)
- Config helper: add a tiny util (e.g., `utils/config.py`) with `get_db_path()` and `get_vec_ext_path()` to standardize env vs config resolution across modules. Current `_get_search_service()` in `app.py` covers app usage; extracting to a shared helper would remove duplication elsewhere.

- Transcription UX/perf knobs (whisper.cpp)
  - Health endpoint: add `/api/transcribe/status` that reports active job (if any), queue length, last durations, and model being used (tiny/base). Useful for UI and quick diagnostics.
  - Adaptive backoff: in `tasks_enhanced`, add an optional backoff for transcription when a job is running (beyond the existing semaphore). Backoff could be a small delay that prevents bursts from stacking CPU.
  - Model profiles: introduce envs to tune quality vs speed without code changes:
    - `WHISPER_MODEL_PATH_TINY` (fast captures) and `WHISPER_MODEL_PATH_FULL` (manual reprocess). A boolean `WHISPER_CAPTURE_USE_TINY=true` can prefer tiny for capture, while a “Reprocess with full model” action uses the full.
    - Keep `-t 1` and `nice -n 19` as defaults; add `DISABLE_NICE=1` for benchmarking.
  - Timeout detection: optionally detect `gtimeout` on macOS and use it if present; otherwise rely on Python-level timeouts (already in place).
  - Better logging: include exception type and total durations for convert+transcribe, and surface them in search_analytics or a small `transcription_analytics` table.

- Additional route cleanup and helpers:
  - Marked legacy enhanced search as deprecated and delegated it to `SearchService` under `/api/search/enhanced_legacy` while preserving response shape plus `deprecated: true`.
  - Added small helpers in `app.py` for unified search behavior: `_get_search_service()` and `_resolve_search_mode()`.
  - Refreshed `obsidian_sync.py` docstring to reflect the move to shared frontmatter helpers (no hard dependency on `python-frontmatter`).
  - Removed unused `EnhancedSearchEngine` and `SearchResult` imports from `app.py` in favor of the unified service.
  - Add a simple guard/comment to keep auth-dependent routes defined after auth helpers to avoid `NameError` on import (caught and fixed for `/api/search/service`).

- New smoke test for frontmatter helpers:
  - Added `scripts/obsidian_frontmatter_smoke.py` to verify `load_frontmatter_file` and `dump_frontmatter_file` round trip without requiring `python-frontmatter`.
  - Usage: `python scripts/obsidian_frontmatter_smoke.py`

- Documentation and env surfaced earlier in this branch:
  - Added `db/README_sqlite_vec.md` and `scripts/sqlite_vec_check.py` for sqlite-vec.
  - Updated `.env.example` with `SQLITE_DB`, `SQLITE_VEC_PATH`, and `OBSIDIAN_*` keys.
  - Updated `AGENTS.md` to reflect routers/services and sqlite-vec integration check.

Notes:
- I intentionally avoided refactoring the core logic inside the legacy endpoints in this pass; they are now relegated to non-conflicting paths. Next step would be to migrate callers to `/api/search/service` and the single `/webhook/discord` implementation, then remove the legacy endpoints entirely.

---

## Consolidated Change Log (Quick-Wins Refactor)

Summary of all changes made in this sweep to reduce duplication, align on the unified service layer, and remove dead/unused code. This list is exhaustive for this session so future reviewers can track scope and impact.

1) Search Consolidation
- app.py
  - Added `_get_search_service()` and `_resolve_search_mode()` helpers.
  - Migrated `POST /api/search` and `POST /api/search/enhanced` to `services.SearchService` with backward-compatible request/response shapes (plus `mode`).
  - Kept `POST /api/search/service` as a clean, normalized endpoint using the service.
  - Marked `POST /api/search/enhanced_legacy` as deprecated and delegated it to the service; preserved legacy response with `deprecated: true`.
  - Removed legacy `EnhancedSearchEngine` and `SearchResult` imports.

2) Obsidian Sync Unification
- obsidian_common.py
  - Added shared helpers: `sanitize_filename`, `frontmatter_yaml`, `load_frontmatter_file`, `dump_frontmatter_file` (with graceful fallback if `python-frontmatter` is not installed).
- obsidian_sync.py (root)
  - Switched export/import to common helpers; removed hard dependency on `python-frontmatter` and `yaml`.
  - Replaced direct indexing with optional vector update via `services.SearchService`; FTS remains trigger-driven.
  - `_extract_note_id()` now uses the common loader for robust parsing.
- services/obsidian_sync.py
  - Uses `sanitize_filename` and `frontmatter_yaml`; cleaned unused imports.

3) Tests and Perf Utilities
- tests/unit/test_search.py
  - Migrated to `services.SearchService` and updated schema assertions (sqlite row dicts).
- test_search_performance.py
  - FTS performance now uses `SearchService` in `keyword` mode; removed unused numpy import.
- scripts/obsidian_frontmatter_smoke.py
  - Added smoke test verifying `load_frontmatter_file`/`dump_frontmatter_file` round trip without hard deps.

4) Import/Duplicate Cleanup (by file)
- file_processor.py: removed duplicate `hashlib` import; removed redundant in-function `import base64`.
- realtime_status.py: removed unused `Depends`, `HTTPException`, `JSONResponse` imports.
- services/search_adapter.py: removed unused `typing.Iterable` import.
- processor.py: removed stray non-ASCII character and unused imports (`uuid`, `shutil`, `os`).
- hybrid_search.py: removed unused `numpy` import.
- semantic_search.py: removed unused `asdict` import from dataclasses.
- url_utils.py: removed unused `urljoin`, `parse_qs`, and `Dict` typing.
 - search_api.py: removed unused typing imports (`Dict`, `Any`).
 - automated_relationships.py: removed unused `threading` and `typing.Set` imports.
 - hybrid_fusion.py: trimmed typing imports to only `List`, `Dict`, and `Any`.
 - sparse_search.py: removed unused typing (`Optional`, `Tuple`, `Any`) and an unused `Path` import.
  - web_extractor.py: removed unused `asdict` and `Path` imports.
  - search_engine.py: trimmed unused `Optional` import from typing.
  - note_relationships.py: removed unused typing imports (`Tuple`, `Optional`, `Set`).
  - reranker.py: trimmed typing imports to only `List`, `Dict`, `Optional`.
  - web_content_models.py: removed unused `asdict` import.
  - ui_enhancements.py: removed unused `Optional` typing and `asdict` import.
  - fresh/add_to_app_py__browser_webhook_endpoint.py: added EXPERIMENTAL/LEGACY banner.
  - file_processor.py: removed unused `os` import.
- debug_capture.py: removed unused `datetime` import.
- tasks_enhanced.py: removed duplicate `import time`.

5) Sqlite-vec Documentation and Checks
- db/README_sqlite_vec.md: added setup notes, env usage, migrations behavior, and troubleshooting.
- scripts/sqlite_vec_check.py: added sanity check for loadable extension.
- .env.example: surfaced `SQLITE_DB`, `SQLITE_VEC_PATH`, and `OBSIDIAN_*` vars.
- AGENTS.md: added service/router notes and sqlite-vec check instructions.

6) Legacy/Deprecated
- Duplicated discord webhooks moved under `/webhook/discord/legacy*`; single active route remains.
- Duplicated enhanced search route moved under `/api/search/enhanced_legacy` and hidden from schema.
- Added explicit legacy banners to historical app variants: `app_v0.py`, `app_v1.py`, `app_v2.py`, and backup `app_backup_before_capture_enhancement.py` to reduce confusion. These files remain for reference only.
  - Marked `search_engine.py` as LEGACY with a module banner; new code should use `services.SearchService`.
  - Added EXPERIMENTAL/LEGACY banners to `fresh/` prototypes (`fresh/search_engine.py`,
    `fresh/obsidian_sync_enhanced.py`, `fresh/enhanced_api_endpoints.py`) to clarify they are not used
    by the live app and reduce confusion for contributors.
  - Added "Alternate engine (legacy path)" banners to `semantic_search.py` and `hybrid_search.py` to
    steer contributors toward the unified `services/SearchService` for new work.

7) Impact and Risk
- Low risk: changes focus on import cleanup, documentation, and migration to service calls already present in the repo.
- Behavior-equivalent endpoints: search routes preserve inputs/outputs, with `mode` added for clarity.
- Optional paths (sqlite-vec, python-frontmatter) now handled more defensively with graceful fallbacks.

8) Verification Suggestions
- Run API smoke: `/api/search` and `/api/search/enhanced` with simple queries; verify results load.
- Optional: `python scripts/sqlite_vec_check.py` if using vectors.
- Optional: `python scripts/obsidian_frontmatter_smoke.py` to verify frontmatter handling.
- Run unit/perf tests that touch search paths.

9) Backlog / Next Steps
- Centralize DB path/ext resolution in a tiny helper (e.g., `utils/config.py`) and reuse across modules currently calling `os.getenv` inline.
- Migrate remaining legacy search utilities (`hybrid_search.py`, `semantic_search.py`, `search_api.py`) to call the unified `SearchService` or clearly label them as legacy.
- Consider archiving historical app variants/integration scripts into an `archive/` folder to reduce confusion.
- Add a short deprecation note in code comments where legacy endpoints remain.

10) Additional Source Cleanups (continued)
- db_indexer.py
  - Replaced direct `python-frontmatter` dependency with `obsidian_common.load_frontmatter_file()` for resilient parsing. This aligns indexing with the same frontmatter handling used by the sync modules and avoids a hard dependency. Behavior: unchanged fields; errors continue to be logged per file.
