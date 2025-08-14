#!/usr/bin/env python3
import os, sys, hashlib, json

IGNORE = {".git", ".venv", "__pycache__", "backups", ".DS_Store"}
ROOT_A = os.path.abspath(".")  # your current repo root
ROOT_B = os.path.abspath(os.environ.get("PREMIUM_DIR", ""))  # snapshot dir

if not ROOT_B or not os.path.isdir(ROOT_B):
    print("Set PREMIUM_DIR to the premium snapshot path", file=sys.stderr)
    sys.exit(2)

def walk(root):
    for p, ds, fs in os.walk(root):
        ds[:] = [d for d in ds if d not in IGNORE]
        for f in fs:
            if f in IGNORE: 
                continue
            yield os.path.relpath(os.path.join(p, f), root)

def sha(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

a = set(walk(ROOT_A))
b = set(walk(ROOT_B))
added = sorted(b - a)
removed = sorted(a - b)
common = sorted(a & b)

changed = []
for rel in common:
    pa, pb = os.path.join(ROOT_A, rel), os.path.join(ROOT_B, rel)
    if os.path.isdir(pa) or os.path.isdir(pb): 
        continue
    try:
        if sha(pa) != sha(pb): 
            changed.append(rel)
    except FileNotFoundError:
        pass

def bucket(rel): return rel.split("/", 1)[0]

summary = {
    "premium_dir": ROOT_B,
    "added": added,
    "removed": removed,
    "changed": changed,
    "stats": {
        "added_by_topdir": {},
        "changed_by_topdir": {},
        "removed_by_topdir": {},
    }
}
for rel in added:
    summary["stats"]["added_by_topdir"][bucket(rel)] = summary["stats"]["added_by_topdir"].get(bucket(rel), 0) + 1
for rel in changed:
    summary["stats"]["changed_by_topdir"][bucket(rel)] = summary["stats"]["changed_by_topdir"].get(bucket(rel), 0) + 1
for rel in removed:
    summary["stats"]["removed_by_topdir"][bucket(rel)] = summary["stats"]["removed_by_topdir"].get(bucket(rel), 0) + 1

print(json.dumps(summary, indent=2))