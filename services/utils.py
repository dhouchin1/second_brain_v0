# Utility helpers: Zettelkasten IDs, slugs
from __future__ import annotations
import datetime as dt, random as rnd, re

_ALPH = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

def make_zid(ts: dt.datetime | None = None) -> str:
    ts = ts or dt.datetime.now()
    head = ts.strftime("%Y%m%d%H%M")
    tail = ''.join(_ALPH[rnd.randint(0, 35)] for _ in range(4))
    return f"{head}-{tail}"

def slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s[:80]
