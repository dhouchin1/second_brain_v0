from pathlib import Path
from datetime import datetime, date
import re

# Update this to match your vault location!
VAULT_PATH = Path("/Users/dhouchin/Obsidian/SecondBrain")

def safe_filename(filename: str) -> str:
    # Lowercase, replace spaces with underscores, keep only safe chars
    name = filename.lower().replace(" ", "_")
    return re.sub(r"[^a-z0-9_\-\.]", "", name)

def save_markdown(title, content, filename):
    md_content = f"""---
title: {title}
date: {filename[:16]}
---
{content}
"""
    (VAULT_PATH / filename).write_text(md_content)

def log_project_note(entry: str):
    buildlog_folder = VAULT_PATH / "BuildLog"
    buildlog_folder.mkdir(exist_ok=True)
    log_file = buildlog_folder / f"{date.today().strftime('%Y-%m')}.md"
    dt_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    log_entry = f"\n## {dt_str}\n{entry}\n"
    if log_file.exists():
        log_file.write_text(log_file.read_text() + log_entry)
    else:
        log_file.write_text(f"# Second Brain Devlog – {date.today().strftime('%B %Y')}\n" + log_entry)
