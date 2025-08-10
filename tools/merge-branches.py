#!/usr/bin/env python3
"""
Auto-merge many remote branches into one integration branch, with discovery.

Examples (run from anywhere inside the repo):
  python tools/merge_branches.py --autostash --rerere
  python tools/merge_branches.py --dry-run
  python tools/merge_branches.py --prefer theirs --push
  python tools/merge_branches.py --include-prefix codex/ --include-prefix xsr6gd-codex/
  python tools/merge_branches.py --continue
"""
from __future__ import annotations
import argparse
import sys
import subprocess
from pathlib import Path
from datetime import datetime

def run(cmd, cwd: Path, check=False, capture=True):
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=capture)
    if check and proc.returncode != 0:
        sys.stderr.write(f"\nCommand failed ({proc.returncode}): {' '.join(cmd)}\n")
        if proc.stdout: sys.stderr.write(proc.stdout + "\n")
        if proc.stderr: sys.stderr.write(proc.stderr + "\n")
        sys.exit(proc.returncode)
    return proc

def repo_root_from_anywhere() -> Path:
    here = Path(__file__).resolve().parent
    out = run(["git", "-C", str(here), "rev-parse", "--show-toplevel"], here, check=True).stdout.strip()
    return Path(out).resolve()

def ensure_clean_or_stash(root: Path, autostash: bool) -> str | None:
    if run(["git", "status", "--porcelain"], root).stdout.strip():
        if not autostash:
            print("Working tree has local changes; commit/stash or rerun with --autostash.")
            sys.exit(1)
        msg = f"auto-stash before merge_branches {datetime.now():%Y-%m-%d %H:%M:%S}"
        run(["git", "stash", "push", "-u", "-m", msg], root, check=True)
        return msg
    return None

def restore_stash_if_any(root: Path, stash_msg: str | None):
    if not stash_msg: return
    lst = run(["git", "stash", "list"], root, check=True).stdout.splitlines()
    match = next((l for l in lst if stash_msg in l), None)
    if match:
        ref = match.split(":")[0]
        print(f"Popping stash {ref} …")
        run(["git", "stash", "pop", ref], root, check=True)

def enable_rerere(root: Path, enable: bool):
    if enable:
        run(["git", "config", "rerere.enabled", "true"], root, check=True)

def checkout_and_update_main(root: Path, main: str, remote: str):
    run(["git", "fetch", "--all"], root, check=True)
    run(["git", "checkout", main], root, check=True)
    run(["git", "pull", remote, main], root, check=True)

def create_or_reset_integration_branch(root: Path, main: str, target: str, remote: str):
    exists = run(["git", "show-ref", "--verify", f"refs/heads/{target}"], root)
    if exists.returncode == 0:
        print(f"Resetting {target} to {remote}/{main}.")
        run(["git", "checkout", target], root, check=True)
        run(["git", "reset", "--hard", f"{remote}/{main}"], root, check=True)
    else:
        run(["git", "checkout", "-b", target, main], root, check=True)

def list_unmerged_files(root: Path) -> list[str]:
    files = []
    for line in run(["git", "status", "--porcelain"], root, check=True).stdout.splitlines():
        if line[:2] in ("UU","AA","DD","AU","UA","UD","DU"):
            files.append(line[3:].strip())
    return files

def auto_resolve(root: Path, policy: str):
    for f in list_unmerged_files(root):
        side = "--theirs" if policy == "theirs" else "--ours"
        run(["git", "checkout", side, "--", f], root, check=True)
        run(["git", "add", f], root, check=True)
    run(["git", "commit", "-m", f"Auto-resolve conflicts preferring {policy}"], root, check=True)

def discover_remote_branches(root: Path, remote: str, include_prefix: list[str], exclude_exact: list[str]) -> list[str]:
    # Get remote branches as names like origin/feature-x; filter to bare names without remote prefix.
    raw = run(["git", "branch", "-r"], root, check=True).stdout.splitlines()
    names = []
    for line in raw:
        name = line.strip()
        if not name or "->" in name:
            continue  # skip origin/HEAD -> origin/main
        if not name.startswith(remote + "/"):
            continue
        short = name[len(remote)+1:]  # strip 'origin/'
        if short in exclude_exact:
            continue
        if include_prefix:
            if any(short.startswith(p) for p in include_prefix):
                names.append(short)
        else:
            names.append(short)
    # de-dupe and keep stable order
    seen, ordered = set(), []
    for n in names:
        if n not in seen:
            seen.add(n); ordered.append(n)
    return ordered

def merge_branch(root: Path, remote: str, branch: str, no_commit: bool, prefer: str | None) -> bool:
    print(f"\n=== Merging {branch} ===")
    args = ["git", "merge", "--no-ff"]
    if no_commit:
        args.append("--no-commit")
    args.append(f"{remote}/{branch}")
    proc = run(args, root)
    if proc.returncode == 0:
        if no_commit:
            print("Dry-run merge ok; aborting to keep tree clean.")
            run(["git", "merge", "--abort"], root, check=True)
        else:
            print(f"Merged {branch} ✓")
        return True

    conflicts = list_unmerged_files(root)
    if not conflicts:
        print(proc.stdout)
        sys.stderr.write(proc.stderr)
        print("Merge failed without detectable conflicts; inspect output above.")
        sys.exit(1)

    print("Conflicts in:")
    for f in conflicts:
        print("  ", f)
    if prefer and not no_commit:
        print(f"Trying auto-resolution preferring {prefer} …")
        auto_resolve(root, prefer)
        return True

    print("\nManual resolution needed. Fix files, then `git add` and `git commit`.")
    print("After committing, re-run with --continue.")
    return False

def parse_args():
    ap = argparse.ArgumentParser(description="Merge multiple remote branches into an integration branch.")
    ap.add_argument("--main", default="main")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--target", default="unified-features")
    ap.add_argument("--include-prefix", action="append", default=["codex/", "xsr6gd-codex/"],
                    help="Remote branch name prefixes to include (repeatable). Default: codex/, xsr6gd-codex/")
    ap.add_argument("--exclude", action="append", default=["main"], help="Exact remote branch names to exclude")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prefer", choices=["theirs","ours"])
    ap.add_argument("--autostash", action="store_true")
    ap.add_argument("--rerere", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--continue", dest="cont", action="store_true")
    return ap.parse_args()

def main():
    args = parse_args()
    root = repo_root_from_anywhere()
    print(f"Repo root: {root}")

    enable_rerere(root, args.rerere)
    stash_msg = ensure_clean_or_stash(root, args.autostash)

    if not args.cont:
        checkout_and_update_main(root, args.main, args.remote)
        create_or_reset_integration_branch(root, args.main, args.target, args.remote)

    merged = set()
    if args.cont:
        log = run(["git", "log", "--pretty=%s", "-n", "400"], root, check=True).stdout.splitlines()
        for s in log:
            if s.startswith("Merge ") and " into unified branch" in s:
                merged.add(s.split("Merge ",1)[1].split(" into ",1)[0].strip())

    branches = discover_remote_branches(root, args.remote, args.include_prefix, args.exclude)
    branches = [b for b in branches if b not in (args.main,)]
    print("Discovered remote branches to merge:")
    for b in branches:
        mark = "(done)" if b in merged else ""
        print(" -", b, mark)

    for br in branches:
        if br in merged:
            continue
        ok = merge_branch(root, args.remote, br, args.dry_run, args.prefer)
        if not ok:
            restore_stash_if_any(root, stash_msg)
            sys.exit(0)

    if args.push and not args.dry_run:
        run(["git", "push", args.remote, args.target], root, check=True)
        print(f"Pushed {args.target} to {args.remote}.")

    restore_stash_if_any(root, stash_msg)
    if args.dry_run:
        print("\nDry run complete. No merge commits created.")
    else:
        print(f"\nAll merges complete on {args.target}. Run tests, then open a PR into {args.main}.")

if __name__ == "__main__":
    main()