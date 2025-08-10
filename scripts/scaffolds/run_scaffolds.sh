#!/usr/bin/env bash
set -Eeuo pipefail
command -v git >/dev/null || { echo "git required"; exit 1; }
command -v gh  >/dev/null || { echo "gh required";  exit 1; }

TOP="$(git rev-parse --show-toplevel)"
cd "$TOP"

BASE="$(git rev-parse --abbrev-ref HEAD)"
[[ "$BASE" =~ ^integration/ ]] || { echo "Run from an integration/* branch."; exit 1; }

mkdir -p integration-logs
LABEL="scaffold"
gh label create "$LABEL" --color "633974" --description "Scaffold application" 2>/dev/null || true

mapfile -t SCRIPTS < <(ls -1 scripts/scaffolds/scaffold-*.sh 2>/dev/null | sort -V)
[ "${#SCRIPTS[@]}" -gt 0 ] || { echo "No scaffold scripts found."; exit 1; }

git fetch --all --prune

i=0
for f in "${SCRIPTS[@]}"; do
  ((i++)) || true
  base="$(basename "$f")"
  num="${base#scaffold-}"; num="${num%.sh}"
  slug="$(grep -E '^##[[:space:]]*Title:' "$f" | head -1 | sed -E 's/^##[[:space:]]*Title:[[:space:]]*//' | tr '[:upper:][:space:]' '[:lower:]-' | tr -cd 'a-z0-9-')"
  [ -z "$slug" ] && slug="step-${num}"
  BR="scaffold/${num}-${slug}"

  git checkout "$BASE"
  git pull --ff-only
  git branch -D "$BR" 2>/dev/null || true
  git checkout -b "$BR" "$BASE"

  LOG="integration-logs/${base%.sh}.log"
  chmod +x "$f"
  if "$f" >"$LOG" 2>&1; then
    echo "✅ $base"
  else
    echo "❌ $base failed. See $LOG"
    git reset --hard
    continue
  fi

  if git status --porcelain | grep -q .; then
    git add -A
    git commit -m "feat(scaffold): apply ${num} (${slug})" -m "Log: ${LOG}"
    git push -u origin "$BR"
    gh pr create --head "$BR" --base "$BASE" \
      --title "Scaffold ${num}: ${slug} → ${BASE}" \
      --body "Applies scaffold ${num}. See ${LOG}." \
      --label "$LABEL" --label scaffolds || true
  else
    echo "(no changes from $base)"
  fi
done
