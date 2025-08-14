# ──────────────────────────────────────────────────────────────────────────────
# File: api/routes_search.py
# ──────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
import os, json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.search_adapter import SearchService

router = APIRouter(prefix="/search", tags=["search"])
service = SearchService(db_path=os.getenv('SQLITE_DB','notes.db'), vec_ext_path=os.getenv('SQLITE_VEC_PATH'))

class IndexNoteIn(BaseModel):
    id: int | None = None
    title: str
    body: str
    tags: str = ''

class SearchIn(BaseModel):
    q: str
    mode: str = 'hybrid'
    k: int = 20

@router.post("/index")
def index_note(payload: IndexNoteIn):
    note_id = service.upsert_note(payload.id, payload.title, payload.body, payload.tags)
    return {"ok": True, "id": note_id}

@router.post("")
def search(payload: SearchIn):
    rows = service.search(payload.q, payload.mode, payload.k)
    return {"results": [dict(r) for r in rows]}

