# ──────────────────────────────────────────────────────────────────────────────
# File: services/embeddings.py
# ──────────────────────────────────────────────────────────────────────────────
"""
Local embedding helpers.
- Default provider: Ollama embeddings API (http://localhost:11434)
- Fallback: deterministic pseudo-embedding (for dev without Ollama)
Configure via env:
  EMBEDDINGS_PROVIDER=ollama|none
  EMBEDDINGS_MODEL=nomic-embed-text (or your preferred local model)
"""
from __future__ import annotations
import hashlib
import json
import os
import random
import struct
import urllib.request

DEFAULT_DIM = 768

class Embeddings:
    def __init__(self, provider: str | None = None, model: str | None = None, dim: int = DEFAULT_DIM):
        self.provider = provider or os.getenv('EMBEDDINGS_PROVIDER', 'ollama')
        self.model = model or os.getenv('EMBEDDINGS_MODEL', 'nomic-embed-text')
        self.dim = int(os.getenv('EMBEDDINGS_DIM', str(dim)))

    def embed(self, text: str) -> list[float]:
        if self.provider == 'ollama':
            return self._ollama_embed(text)
        return self._pseudo_embed(text)

    def _ollama_embed(self, text: str) -> list[float]:
        data = json.dumps({"model": self.model, "input": text}).encode('utf-8')
        req = urllib.request.Request(
            os.getenv('OLLAMA_URL', 'http://localhost:11434/api/embeddings'),
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
        vec = payload.get('embedding') or payload.get('data', [{}])[0].get('embedding')
        if not vec:
            raise RuntimeError('No embedding returned from Ollama')
        return vec

    def _pseudo_embed(self, text: str) -> list[float]:
        # Stable pseudo-embedding using a hash; useful for offline dev
        h = hashlib.sha256(text.encode('utf-8')).digest()
        rng = random.Random(h)
        return [rng.uniform(-1.0, 1.0) for _ in range(self.dim)]

    @staticmethod
    def pack_f32(array: list[float]) -> bytes:
        return struct.pack('<%sf' % len(array), *array)