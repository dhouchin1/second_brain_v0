# CONTRIBUTING_AI.md

## Why this exists
This repo is set up for an “AI co-dev” workflow where I propose small, ready-to-apply patches instead of giant code dumps. You apply them locally, run checks, and we iterate fast.

## Day-to-day flow
1) You tell me the goal, constraints, and acceptance criteria.
2) I propose a short plan and send a unified diff.
3) You apply it locally:
   ```bash
   git checkout -b feature/<short-name>
   ./tools/apply-patch.sh < patch.diff
   # or:
   git apply --whitespace=fix --3way patch.diff

   4.	You run local checks (mirrors of CI) and share results/logs.
	5.	We iterate until green, then you merge to main.

What to include when you open a task
	•	Entry points/endpoints to touch, test data (if any), and exact success criteria.
	•	Schema or config constraints (paths, ports, tokens).
	•	Optional: minimal repro snippet or payload.

Context packet (when changes are broad)

Generate a single file I can read quickly:
python3 pack_context.py
# produces context_bundle.md with labeled code blocks
Or zip the current tree without .git:
```bash
git archive -o repo.zip HEAD

Local pre-merge checks (mirror this in CI later)

```bash
ruff check .
mypy .
pytest -q

Patch hygiene I’ll follow
	•	Unified diffs, small and scoped.
	•	No schema migrations inside request handlers.
	•	Keep FTS mirrors in sync with base tables.
	•	Defensive I/O (path traversal, temp files).
	•	Idempotency where it helps (e.g., hashing uploads, retries).

Rollback / recovery

Every patch should be easy to revert:
```bash
git revert <merge-commit-sha>

Handy commands
	•	Create a context bundle for me to read:
   ```bash
   ./tools/make-context.sh

   •	Apply a patch I send:
   ```bash
   ./tools/apply-patch.sh < patch.diff
   