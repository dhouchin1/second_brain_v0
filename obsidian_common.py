"""Shared Obsidian helpers used by both root and service sync modules.

Non-invasive utilities only; avoids changing behavior of existing modules.
"""
from __future__ import annotations
import json
import re
from typing import Dict, Tuple
from pathlib import Path

def load_frontmatter_file(path: Path) -> Tuple[Dict, str]:
    """Load frontmatter and content from a markdown file.

    Tries python-frontmatter if installed; otherwise falls back to a simple
    parser that reads a leading YAML block between '---' lines.
    Returns (metadata, content).
    """
    try:
        import frontmatter  # type: ignore
        post = frontmatter.load(path)
        return dict(post.metadata or {}), post.content or ""
    except Exception:
        text = Path(path).read_text(encoding='utf-8')
        meta: Dict = {}
        content = text
        if text.startswith('---'):
            try:
                # naive split on first two '---' lines
                parts = text.split('\n')
                # find closing '---'
                end = None
                for i in range(1, min(len(parts), 200)):
                    if parts[i].strip() == '---':
                        end = i
                        break
                if end is not None:
                    meta_lines = parts[1:end]
                    body = parts[end+1:]
                    for line in meta_lines:
                        if ':' in line:
                            k, v = line.split(':', 1)
                            k = k.strip()
                            v = v.strip()
                            # try JSON-like parse for lists/strings/bools
                            try:
                                import json
                                meta[k] = json.loads(v)
                            except Exception:
                                meta[k] = v.strip('"')
                    content = "\n".join(body)
            except Exception:
                # fallback: keep full text as content
                pass
        return meta, content

def dump_frontmatter_file(path: Path, content: str, meta: Dict) -> None:
    """Write frontmatter and content to a markdown file.

    Uses python-frontmatter if available; otherwise emits a YAML block via
    frontmatter_yaml() followed by content.
    """
    try:
        import frontmatter  # type: ignore
        post = frontmatter.Post(content, **meta)
        Path(path).write_text(frontmatter.dumps(post), encoding='utf-8')
    except Exception:
        Path(path).write_text(frontmatter_yaml(meta) + content, encoding='utf-8')

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for filesystem.

    - Remove invalid characters
    - Replace spaces with underscores
    - Limit to 50 characters
    """
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = filename.replace(' ', '_')
    return filename[:50]

def frontmatter_yaml(meta: Dict) -> str:
    """Build a simple YAML frontmatter block from a dict.

    Uses JSON serialization for values to avoid YAML injection and to keep types explicit.
    """
    lines = ['---'] + [f"{k}: {json.dumps(v)}" for k, v in meta.items()] + ['---', '']
    return "\n".join(lines)
