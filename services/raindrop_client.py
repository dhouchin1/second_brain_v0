from __future__ import annotations
import os, json, urllib.request
from typing import List, Dict
from services.search_adapter import SearchService

API = 'https://api.raindrop.io/rest/v1/raindrops/0?perpage={limit}&sort=-created'

class RaindropClient:
    def __init__(self):
        self.token = os.getenv('RAINDROP_TOKEN')
        if not self.token:
            raise RuntimeError('RAINDROP_TOKEN not set')
        self.svc = SearchService(db_path=os.getenv('SQLITE_DB','notes.db'),
                                 vec_ext_path=os.getenv('SQLITE_VEC_PATH'))

    def _fetch(self, limit: int = 30) -> List[Dict]:
        url = API.format(limit=limit)
        req = urllib.request.Request(url, headers={'Authorization': f'Bearer {self.token}'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return data.get('items', [])

    def import_latest(self, limit: int = 30) -> int:
        items = self._fetch(limit)
        n = 0
        for it in items:
            title = it.get('title') or it.get('domain') or 'Untitled'
            url = it.get('link') or ''
            excerpt = (it.get('excerpt') or '').strip()
            body = f"{url}\n\n{excerpt}"
            tags = ' '.join(f"#{t}" for t in (it.get('tags') or []))
            self.svc.upsert_note(None, title, body, tags)
            n += 1
        return n
