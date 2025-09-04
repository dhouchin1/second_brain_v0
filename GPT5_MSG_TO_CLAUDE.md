# Handoff Notes: Advanced Search and UI polish

Author: GPT‑5 (agent)
Date: 2025‑08‑29

This handoff summarizes what changed in this iteration, what still needs attention, and concrete next steps aligned with second_brain.PRD and AGENTS.md. It’s intended to help you continue quickly without re‑discovering context.

## Summary of Changes

- Obsidian “more” menu now anchors to the trigger on the dashboard.
  - File: `templates/dashboard.html` — dropdown is positioned `right-0 top-full` inside a `relative` wrapper.
- Advanced Search page is wired up end‑to‑end and made consistent with dashboard cards.
  - Files: `templates/search.html`, `static/js/advanced-search.js`.
  - Clean card results with title, timestamp, tags, snippet, and (when present) FTS/Semantic/Combined scores.
  - Suggestions fetch uses cookie auth (`credentials: 'same-origin'`) and de‑dupes items; suggestions close on search.
  - Added filters: type, status, date range, tags, min score (client-side min‑score; others sent to backend).
- Backend hybrid search stabilized when semantic search is unavailable.
  - File: `hybrid_search.py` — removed source of 500s by ensuring semantic results are consistently dict‑backed; uses `notes_fts` for FTS.
- Server‑side filtering added for types/status/tags/date in the search API.
  - File: `search_api.py` — `/api/search/hybrid` enriches results from `notes` and applies filters before returning; fixes `total`.
- FTS coverage ensured and consistency nudged toward `notes_fts` (the index already kept in sync across the app).
  - File: `app.py` — one‑time population path for `notes_fts5`; advanced search now queries `notes_fts`.

## Current State & Validation

- Hybrid search works even without semantic models installed; it degrades to FTS without throwing.
- Suggestions endpoint returns `{ suggestions: [...] }` and UI consumes it correctly.
- Result cards render cleanly; no stray suggestion text after a search.
- Filters:
  - `types`, `status`, `tags`, `date_start/end` — filtered server‑side in the API layer.
  - `minScore` — filtered client‑side only (applied to FTS/Semantic scores present in payload).

## Known Gaps / Follow‑ups

1) Semantic search enablement
- Today, hybrid search logs “Semantic search not available” unless `sentence-transformers` and embeddings are present.
- Next steps:
  - Ensure `requirements.txt` includes `sentence-transformers`, `scikit-learn`, `numpy` (already implied).
  - Use `EmbeddingManager` to rebuild missing embeddings: `/api/search/embeddings/generate` exists in `search_api.py`.
  - Add a small UI affordance on `/search` to prompt generating embeddings if semantic is off (optional).

2) Duplicate endpoints / cleanup
- `app.py` contains legacy `/api/search` and `/api/search/enhanced` routes that overlap conceptually with the router in `search_api.py`.
- There are two `/health` routes in `app.py` (one returns timestamps, one returns tables). Consider consolidating to a single `/health` with useful detail.
- Recommendation: keep `search_api.py` authoritative for search; remove or deprecate legacy search endpoints in `app.py` once you’ve migrated any callers.

3) FTS index strategy
- We aligned hybrid FTS to `notes_fts` (which the app updates everywhere). `notes_fts5` also exists but was occasionally empty.
- Options:
  - A) Remove `notes_fts5` entirely and standardize on `notes_fts`.
  - B) Keep both but add triggers to keep `notes_fts5` in sync. If choosing B, add inserts/updates/deletes mirroring those for `notes_fts`.

4) Server‑side filtering depth
- We filter type/status/tags/dates in `search_api.py` post‑query by enriching from `notes`.
- More scalable approach: push filters into the FTS query itself (e.g., add `n.type = ?`, `n.status = ?`, date range) to reduce result set size before enrichment.
- Also consider “tags any vs all” matching toggle; current implementation requires all requested tags.

5) UI polish / parity with dashboard
- Cards currently emulate dashboard styles via inline CSS in `templates/search.html`.
- Move those to `static/css/advanced-search.css` and adopt the same tokenized CSS variables used on dashboard.
- Add loading indicator (spinner on the search button exists; consider showing a subtle skeleton list in results grid).
- Add a hint/banner when semantic is disabled to explain why “Semantic” mode returns fewer/no results.

6) Tests
- Add fast unit tests for `search_api.py` `/api/search/hybrid` covering server-side filters and degenerate cases (no semantic, no FTS hits, empty DB).
- If you add semantic, include an integration test that stubs embeddings or runs with a tiny model and a temp DB.

## Suggested Next Tasks (ordered)

1. Consolidate FTS usage
- Decide on `notes_fts` vs `notes_fts5` and refactor accordingly; remove the other or add triggers.

2. Remove legacy search endpoints from `app.py`
- Keep a single search surface in `search_api.py`; update frontend to use only `/api/search/*` endpoints.

3. Add semantic enablement path in UI
- Button on `/search` to (a) check semantic availability via `/api/search/embeddings/stats`, (b) trigger generation via `/api/search/embeddings/generate`.

4. Push filters into SQL
- Update `HybridSearchEngine._fts_search()` to accept an optional filter struct and translate to SQL WHERE predicates.

5. Exact style match with dashboard
- Extract card styles to CSS with variables; use `.card-interactive` class and unify typography, spacing, and hover effects.

6. De‑dupe `/health` and return structured readiness
- E.g., `{ ok, db_ok, fts_ok, embeddings_ok, pending_jobs }` with quick checks.

## Quick Dev Notes

- Endpoints used by Advanced Search UI
  - POST `/api/search/hybrid` (payload matches `HybridSearchRequest`)
  - GET `/api/search/suggestions?q=...`
- JS fetches use cookie auth: `credentials: 'same-origin'`. No explicit Authorization header needed for browser UI.
- If you re‑enable semantic, run the embedding generation and then retry Semantic/Hybrid modes.

## File Map (modified this session)

- templates/dashboard.html — ellipsis menu position fix
- templates/search.html — includes script, new filters, card styles
- static/js/advanced-search.js — main UI logic, suggestions, filters, rendering
- search_api.py — hybrid endpoint enrichment and filtering, correct totals
- hybrid_search.py — robust hybrid combination; FTS over `notes_fts`
- app.py — ensured FTS population path for `notes_fts5` (informational), existing FTS remains canonical

## Compatibility Considerations

- Older pages or scripts calling `/api/search` or `/api/search/enhanced` in `app.py` still work; the Advanced Search UI only calls `/api/search/hybrid`.
- With semantic disabled, “Semantic” mode will return none/very few results; this is expected until embeddings exist.

## Closing

System is stable for FTS and ready for you to expand semantic functionality and refine styling. The most impactful next step is consolidating FTS usage and enabling semantic embeddings with a small operational UI.

— GPT‑5
