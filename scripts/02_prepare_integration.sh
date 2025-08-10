#!/usr/bin/env bash
set -Eeuo pipefail
INTEG="integration/$(date +%Y%m%d)"

git fetch --all --prune
git checkout main
git pull --ff-only
git config rerere.enabled true

if git rev-parse --verify "$INTEG" >/dev/null 2>&1; then
  echo "==> $INTEG already exists."
else
  git checkout -b "$INTEG"
  git push -u origin "$INTEG"
fi

WT="$HOME/ws/second_brain-integration"
mkdir -p "$(dirname "$WT")"
if [ -d "$WT/.git" ] || { [ -d "$WT" ] && [ -n "$(ls -A "$WT" 2>/dev/null)" ]; }; then
  echo "==> Worktree path exists: $WT"
else
  git worktree add "$WT" "$INTEG"
  echo "==> Worktree created at $WT"
fi

echo "==> Integration branch: $INTEG"
