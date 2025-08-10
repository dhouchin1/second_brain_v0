#!/usr/bin/env bash
set -Eeuo pipefail

DATE="$(date +%Y%m%d-%H%M%S)"
REPO_TOP="$(git rev-parse --show-toplevel)"
cd "$REPO_TOP"

echo "==> Fetching all refs"
git fetch --all --prune

REPO_NAME="$(basename "$REPO_TOP")"
OUT_DIR="backups"
mkdir -p "$OUT_DIR"

BUNDLE="$OUT_DIR/${REPO_NAME}-${DATE}.bundle"
echo "==> Creating bundle: $BUNDLE"
git bundle create "$BUNDLE" --all

echo "==> Tagging main"
git checkout main
git pull --ff-only
TAG="pre-scaffolds-${DATE}"
git tag -a "$TAG" -m "Snapshot before scaffold integration $DATE"
git push origin "$TAG"

echo "==> Done. Restore example:"
echo "    git clone --mirror $BUNDLE restored-${REPO_NAME}.git"
