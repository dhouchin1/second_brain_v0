#!/usr/bin/env bash
set -Eeuo pipefail
# Usage: PREMIUM_WT=~/ws/second_brain-premium scripts/premium/20_port_paths.sh integration/20250810 app.py templates/ static/ tools/

BASE="${1:?Usage: 20_port_paths.sh <integration-branch> <paths...>}"
shift
[ $# -ge 1 ] || { echo "Provide 1+ paths to port"; exit 1; }

PREMIUM_WT="${PREMIUM_WT:-$HOME/ws/second_brain-premium}"
[ -d "$PREMIUM_WT" ] || { echo "PREMIUM_WT not found: $PREMIUM_WT"; exit 1; }

git fetch --all --prune
git checkout "$BASE"
git pull --ff-only

BR="port/$(date +%Y%m%d-%H%M%S)"
git switch -c "$BR"

# Bring paths from premium worktree
for p in "$@"; do
  if [ -e "$PREMIUM_WT/$p" ]; then
    mkdir -p "$(dirname "$p")" 2>/dev/null || true
    rsync -a --delete "$PREMIUM_WT/$p" "$(dirname "$p")/" 2>/dev/null || cp -R "$PREMIUM_WT/$p" "$(dirname "$p")/" || true
  else
    echo "WARN: $p doesn't exist in premium; skipping"
  fi
done

# Keep noise out
echo -e "\n# local\n.DS_Store\n__pycache__/\nbackups/\n*.bundle" >> .gitignore || true

# Show changes & commit
git status --porcelain
git add -A
git commit -m "feat(port): bring selected paths from premium worktree"

git push -u origin "$BR"
gh pr create --head "$BR" --base "$BASE" --title "Port from premium: $*" --label scaffolds --body "Paths: $*"