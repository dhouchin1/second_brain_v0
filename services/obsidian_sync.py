from __future__ import annotations
import os, json
from pathlib import Path
from datetime import datetime
from typing import Optional

from services.search_adapter import SearchService
from services.utils import make_zid, slugify

VAULT = Path(os.getenv('OBSIDIAN_VAULT_PATH', '')).expanduser()
PROJECTS_ROOT = os.getenv('OBSIDIAN_PROJECTS_ROOT', '').strip('/')
PER_PROJECT = os.getenv('OBSIDIAN_PER_PROJECT', '1') not in {'0','false','False'}

class ObsidianSync:
    def __init__(self, svc: Optional[SearchService] = None):
        if not VAULT:
            raise RuntimeError('OBSIDIAN_VAULT_PATH not set')
        self.svc = svc or SearchService(db_path=os.getenv('SQLITE_DB','notes.db'),
                                        vec_ext_path=os.getenv('SQLITE_VEC_PATH'))

    def _project_for(self, row) -> str:
        tags = (row.get('tags') or '').strip()
        first = tags.split()[0].lstrip('#') if tags else 'Inbox'
        return first or 'Inbox'

    def _dest_path(self, row) -> Path:
        title = row['title'] or 'Untitled'
        zid = row['zettel_id'] or make_zid()
        if not row['zettel_id']:
            cur = self.svc.conn.cursor()
            cur.execute("UPDATE notes SET zettel_id=? WHERE id=?", (zid, row['id']))
            self.svc.conn.commit()
        fname = f"{zid} {slugify(title)}.md"
        base = (VAULT / (PROJECTS_ROOT or '') / self._project_for(row)) if PER_PROJECT else VAULT
        base.mkdir(parents=True, exist_ok=True)
        return base / fname

    def _frontmatter(self, row) -> str:
        created = row.get('created_at') or datetime.now().isoformat()
        updated = row.get('updated_at') or datetime.now().isoformat()
        tags = (row.get('tags') or '').split()
        fm = {'id': row.get('zettel_id'), 'title': row.get('title'),
              'created': created, 'updated': updated, 'tags': tags}
        lines = ['---'] + [f"{k}: {json.dumps(v)}" for k,v in fm.items()] + ['---','']
        return "\n".join(lines)

    def _append_build_log(self, project_dir: Path, line: str) -> None:
        log = project_dir / 'BuildLog.md'
        ts = datetime.now().strftime('%Y-%m-%d %H:%M')
        with log.open('a', encoding='utf-8') as f:
            f.write(f"- [{ts}] {line}\n")

    def push_note(self, note_id: int) -> Path:
        row = self.svc.conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
        if not row:
            raise ValueError(f"No note {note_id}")
        dest = self._dest_path(row)
        md = self._frontmatter(row) + (row.get('body') or '')
        dest.write_text(md, encoding='utf-8')
        self._append_build_log(dest.parent, f"Pushed note {row['title']} → {dest.name}")
        return dest

    def push_all(self, limit: int = 1000) -> int:
        rows = self.svc.conn.execute(
            "SELECT * FROM notes ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        for r in rows:
            self.push_note(r['id'])
        return len(rows)
