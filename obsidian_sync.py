<<<<<<< HEAD
"""Obsidian sync utilities.

Provides the `ObsidianSync` class used by the app without registering FastAPI
routes at import-time. Optional dependencies (watchdog) are imported lazily.
Frontmatter read/write is handled via `obsidian_common` with a graceful
fallback, so a hard dependency on `python-frontmatter` is not required.
"""

import os
# Note: yaml handled via obsidian_common helpers when needed
=======
# obsidian_sync.py - Enhanced bidirectional sync with transcription

import os
import yaml
>>>>>>> origin/main
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import hashlib
import time
<<<<<<< HEAD
from config import settings
from obsidian_common import sanitize_filename, dump_frontmatter_file, load_frontmatter_file
import json
=======
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import frontmatter
from config import settings
>>>>>>> origin/main

@dataclass
class SyncState:
    file_path: str
    last_modified: float
    content_hash: str
    note_id: Optional[int] = None

class ObsidianSync:
<<<<<<< HEAD
    def __init__(self, vault_path: Optional[Path] = None, db_path: Optional[Path] = None):
        """Initialize sync manager with defaults from settings if not provided."""
        # Resolve vault path; allow relative paths (e.g., "vault") by anchoring to base_dir
        vpath = Path(vault_path) if vault_path else Path(settings.vault_path)
        if not vpath.is_absolute():
            vpath = Path(settings.base_dir) / vpath
        self.vault_path = vpath
        self.db_path = db_path or settings.db_path
        self.sync_state_file = self.vault_path / ".secondbrain" / "sync_state.json"
        self.audio_dir = self.vault_path / "audio"
        self.attachments_dir = self.vault_path / "attachments"
=======
    def __init__(self, vault_path: Path, db_path: Path):
        self.vault_path = vault_path
        self.db_path = db_path
        self.sync_state_file = vault_path / ".secondbrain" / "sync_state.json"
        self.audio_dir = vault_path / "audio"
        self.attachments_dir = vault_path / "attachments"
>>>>>>> origin/main
        self._ensure_directories()
        
    def _ensure_directories(self):
        """Create necessary directories"""
<<<<<<< HEAD
        # Ensure vault root exists first, then subdirectories
        self.vault_path.mkdir(parents=True, exist_ok=True)
        (self.vault_path / ".secondbrain").mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.attachments_dir.mkdir(parents=True, exist_ok=True)
=======
        (self.vault_path / ".secondbrain").mkdir(exist_ok=True)
        self.audio_dir.mkdir(exist_ok=True)
        self.attachments_dir.mkdir(exist_ok=True)
>>>>>>> origin/main
    
    def export_note_to_obsidian(self, note_id: int) -> Path:
        """Export a single note to Obsidian vault"""
        import sqlite3
<<<<<<< HEAD
        # frontmatter is optional; use common helpers for writing
=======
>>>>>>> origin/main
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        note = conn.execute(
            "SELECT * FROM notes WHERE id = ?", (note_id,)
        ).fetchone()
        
        if not note:
            raise ValueError(f"Note {note_id} not found")
        
<<<<<<< HEAD
        # Determine target file: prefer existing file for this note id to avoid duplicates
        existing_rel = self._find_note_file(note_id)
        if existing_rel:
            filepath = self.vault_path / existing_rel
        else:
            timestamp = (note['timestamp'] or datetime.now().strftime("%Y-%m-%d %H:%M:%S")).replace(":", "-").replace(" ", "_")
            safe_title = sanitize_filename(note['title'] or 'untitled')
            filename = f"{timestamp}_{safe_title}_id{note_id}.md"
            filepath = self.vault_path / filename
=======
        # Generate filename
        timestamp = note['timestamp'][:19] if note['timestamp'] else datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_title = self._sanitize_filename(note['title'] or 'untitled')
        filename = f"{timestamp}_{safe_title}.md"
        filepath = self.vault_path / filename
>>>>>>> origin/main
        
        # Prepare frontmatter
        frontmatter_data = {
            'id': note['id'],
            'title': note['title'],
            'created': note['timestamp'],
            'type': note['type'],
            'tags': note['tags'].split(',') if note['tags'] else [],
            'summary': note['summary'],
            'status': note['status']
        }
<<<<<<< HEAD
        # Optional metadata fields if present in schema
        for opt_key in [
            'file_filename','file_type','file_mime_type','file_size','extracted_text',
            'file_metadata','source_url','web_metadata','screenshot_path'
        ]:
            try:
                if opt_key in note.keys() and note[opt_key] is not None and note[opt_key] != '':
                    # Parse JSON for metadata fields if possible
                    if opt_key in {'file_metadata','web_metadata'} and isinstance(note[opt_key], (str, bytes)):
                        try:
                            frontmatter_data[opt_key] = json.loads(note[opt_key])
                        except Exception:
                            frontmatter_data[opt_key] = note[opt_key]
                    else:
                        frontmatter_data[opt_key] = note[opt_key]
            except Exception:
                pass
=======
>>>>>>> origin/main
        
        if note['actions']:
            frontmatter_data['actions'] = note['actions'].split('\n')
        
<<<<<<< HEAD
        # Handle media/attachments copies and embed links
        media_links: List[str] = []
        # Audio (original and converted wav if present)
        try:
            if 'audio_filename' in note.keys() and note['audio_filename']:
                orig = settings.audio_dir / note['audio_filename']
                if orig.exists():
                    shutil.copy2(orig, self.audio_dir / orig.name)
                    media_links.append(f"![[audio/{orig.name}]]")
                conv = orig.with_suffix('.converted.wav')
                if conv.exists():
                    shutil.copy2(conv, self.audio_dir / conv.name)
                    media_links.append(f"![[audio/{conv.name}]]")
        except Exception:
            pass
        # Other attachments (images, PDFs)
        try:
            if 'file_filename' in note.keys() and note['file_filename']:
                fsrc = (settings.uploads_dir / note['file_filename']) if hasattr(settings, 'uploads_dir') else None
                if fsrc and fsrc.exists():
                    shutil.copy2(fsrc, self.attachments_dir / fsrc.name)
                    media_links.append(f"![[attachments/{fsrc.name}]]")
        except Exception:
            pass
        
        # Create content
        content = note['content'] or ""
        # Add source URL if available
        try:
            if 'source_url' in note.keys() and note['source_url']:
                content = f"Source: {note['source_url']}\n\n" + content
        except Exception:
            pass
        # Include summary and extracted text sections when present
        if note['summary'] and (not content or note['summary'] != content):
            content = f"## Summary\n{note['summary']}\n\n## Full Content\n{content}".strip()
        try:
            if 'extracted_text' in note.keys() and note['extracted_text']:
                content = content + ("\n\n## Extracted Text\n" + str(note['extracted_text']))
        except Exception:
            pass
        
        # Add action items
        if note['actions']:
            actions = [a.strip() for a in str(note['actions']).split('\n') if a.strip()]
            if actions:
                content += f"\n\n## Action Items\n"
                for action in actions:
                    content += f"- [ ] {action}\n"
        
        # Create markdown with frontmatter and write
        # Append media links at end
        media_block = ("\n\n" + "\n".join(media_links) + "\n") if media_links else ""
        dump_frontmatter_file(filepath, content + media_block, frontmatter_data)
=======
        # Handle audio files
        audio_link = ""
        if note['audio_filename']:
            audio_src = settings.audio_dir / note['audio_filename']
            audio_dest = self.audio_dir / note['audio_filename']
            
            if audio_src.exists():
                shutil.copy2(audio_src, audio_dest)
                audio_link = f"\n\n![[audio/{note['audio_filename']}]]\n"
        
        # Create content
        content = note['content'] or ""
        if note['summary'] and note['summary'] != content:
            content = f"## Summary\n{note['summary']}\n\n## Full Content\n{content}"
        
        # Add action items
        if note['actions']:
            actions = note['actions'].split('\n')
            content += f"\n\n## Action Items\n"
            for action in actions:
                content += f"- [ ] {action}\n"
        
        # Create markdown with frontmatter
        post = frontmatter.Post(content + audio_link, **frontmatter_data)
        
        # Write file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(frontmatter.dumps(post))
>>>>>>> origin/main
        
        conn.close()
        return filepath
    
    def import_note_from_obsidian(self, filepath: Path) -> Optional[int]:
        """Import a note from Obsidian vault"""
        import sqlite3
<<<<<<< HEAD
        # frontmatter optional; use common helper for reading
=======
>>>>>>> origin/main
        
        if not filepath.suffix == '.md':
            return None
        
        try:
<<<<<<< HEAD
            metadata, content = load_frontmatter_file(filepath)
=======
            with open(filepath, 'r', encoding='utf-8') as f:
                post = frontmatter.load(f)
            
            metadata = post.metadata
            content = post.content
>>>>>>> origin/main
            
            # Extract components
            title = metadata.get('title', filepath.stem)
            note_type = metadata.get('type', 'note')
            tags = ','.join(metadata.get('tags', []))
            summary = metadata.get('summary', '')
            actions = '\n'.join(metadata.get('actions', []))
            created = metadata.get('created', datetime.now().isoformat())
            
            # Check if note already exists
            conn = sqlite3.connect(self.db_path)
            existing_id = metadata.get('id')
            
            if existing_id:
                # Update existing note
                conn.execute("""
                    UPDATE notes SET title=?, content=?, summary=?, tags=?, actions=?, timestamp=?
                    WHERE id=?
                """, (title, content, summary, tags, actions, created, existing_id))
                note_id = existing_id
            else:
                # Create new note
                conn.execute("""
                    INSERT INTO notes (title, content, summary, tags, actions, type, timestamp, status, user_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'complete', 1)
                """, (title, content, summary, tags, actions, note_type, created))
                note_id = conn.lastrowid
                
                # Update file with new ID
                metadata['id'] = note_id
<<<<<<< HEAD
                dump_frontmatter_file(filepath, content, metadata)
            
            # Update vector index (FTS updates via triggers). Try unified service if available.
            try:
                import os as _os
                from services.search_adapter import SearchService as _SS
                svc = _SS(db_path=str(self.db_path), vec_ext_path=_os.getenv('SQLITE_VEC_PATH'))
                try:
                    svc._upsert_vector(note_id, f"{title}\n\n{content}")
                except Exception:
                    pass
            except Exception:
                # If service layer unavailable, proceed without vector update
                pass
=======
                post.metadata = metadata
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(frontmatter.dumps(post))
            
            # Update search index
            from search_engine import EnhancedSearchEngine
            search_engine = EnhancedSearchEngine(str(self.db_path))
            search_engine.index_note(note_id, title, content, summary, tags, actions)
>>>>>>> origin/main
            
            conn.commit()
            conn.close()
            
            return note_id
            
        except Exception as e:
            print(f"Failed to import {filepath}: {e}")
            return None
    
    def sync_all_to_obsidian(self, user_id: int = 1):
        """Export all notes to Obsidian"""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        notes = conn.execute(
            "SELECT id FROM notes WHERE user_id = ?", (user_id,)
        ).fetchall()
        
        exported = []
        for note in notes:
            try:
                filepath = self.export_note_to_obsidian(note[0])
                exported.append(str(filepath))
            except Exception as e:
                print(f"Failed to export note {note[0]}: {e}")
        
        conn.close()
        return exported
    
    def sync_from_obsidian(self) -> List[int]:
        """Import all markdown files from Obsidian vault"""
        imported = []
        
        for md_file in self.vault_path.rglob("*.md"):
            # Skip files in .secondbrain directory
            if ".secondbrain" in str(md_file):
                continue
                
            note_id = self.import_note_from_obsidian(md_file)
            if note_id:
                imported.append(note_id)
        
        return imported
    
    def bidirectional_sync(self, user_id: int = 1) -> Dict[str, List]:
        """Perform bidirectional sync between Second Brain and Obsidian"""
        import sqlite3
        import json
        
        # Load previous sync state
        sync_state = self._load_sync_state()
        
        # Get current file states
        current_files = self._scan_vault_files()
        
        # Get current database states
        conn = sqlite3.connect(self.db_path)
        db_notes = conn.execute("""
            SELECT id, title, timestamp, content, summary, tags, actions, audio_filename
            FROM notes WHERE user_id = ?
        """, (user_id,)).fetchall()
        conn.close()
        
        results = {
            "exported_to_obsidian": [],
            "imported_from_obsidian": [],
            "conflicts": [],
            "skipped": []
        }
        
        # Check for changes in database notes
        for note in db_notes:
            note_id = note[0]
            note_hash = self._hash_note_content(note)
            
            # Find corresponding file
            note_file = self._find_note_file(note_id)
            
            if note_file and note_file in sync_state:
                # File exists and was synced before
                if sync_state[note_file]["content_hash"] != note_hash:
                    # Database note changed, export to Obsidian
                    try:
                        filepath = self.export_note_to_obsidian(note_id)
                        results["exported_to_obsidian"].append(str(filepath))
                    except Exception as e:
                        results["skipped"].append(f"Export failed for note {note_id}: {e}")
            elif not note_file:
                # New note, export to Obsidian
                try:
                    filepath = self.export_note_to_obsidian(note_id)
                    results["exported_to_obsidian"].append(str(filepath))
                except Exception as e:
                    results["skipped"].append(f"Export failed for note {note_id}: {e}")
        
        # Check for changes in Obsidian files
        for filepath, file_state in current_files.items():
            if filepath in sync_state:
                # File was synced before
                if sync_state[filepath]["content_hash"] != file_state.content_hash:
                    # File changed in Obsidian
                    if file_state.note_id:
                        # Check for conflicts (both changed)
                        note_changed = self._check_note_changed_in_db(file_state.note_id, sync_state[filepath])
                        if note_changed:
                            results["conflicts"].append({
                                "file": filepath,
                                "note_id": file_state.note_id,
                                "action": "manual_resolution_needed"
                            })
                            continue
                    
                    # Import from Obsidian
                    note_id = self.import_note_from_obsidian(Path(filepath))
                    if note_id:
                        results["imported_from_obsidian"].append(filepath)
            else:
                # New file in Obsidian
                note_id = self.import_note_from_obsidian(Path(filepath))
                if note_id:
                    results["imported_from_obsidian"].append(filepath)
        
        # Update sync state
        self._save_sync_state(current_files, db_notes)
        
        return results
    
    def watch_obsidian_changes(self, user_id: int = 1):
        """Watch Obsidian vault for changes and auto-sync"""
<<<<<<< HEAD
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError as e:
            raise RuntimeError("watchdog package is required for watching vault changes") from e

=======
        
>>>>>>> origin/main
        class ObsidianEventHandler(FileSystemEventHandler):
            def __init__(self, sync_manager):
                self.sync_manager = sync_manager
                self.user_id = user_id
                
            def on_modified(self, event):
                if event.is_directory or not event.src_path.endswith('.md'):
                    return
                
                # Debounce changes (wait 2 seconds)
                time.sleep(2)
                
                filepath = Path(event.src_path)
                if ".secondbrain" not in str(filepath):
                    note_id = self.sync_manager.import_note_from_obsidian(filepath)
                    if note_id:
                        print(f"Auto-imported note {note_id} from {filepath}")
            
            def on_created(self, event):
                self.on_modified(event)
        
        event_handler = ObsidianEventHandler(self)
        observer = Observer()
        observer.schedule(event_handler, str(self.vault_path), recursive=True)
        observer.start()
        
        return observer
    
    def _load_sync_state(self) -> Dict[str, SyncState]:
        """Load previous sync state"""
<<<<<<< HEAD
=======
        import json
>>>>>>> origin/main
        
        if not self.sync_state_file.exists():
            return {}
        
        try:
            with open(self.sync_state_file, 'r') as f:
                data = json.load(f)
            
            return {
                path: SyncState(**state_data) 
                for path, state_data in data.items()
            }
        except:
            return {}
    
    def _save_sync_state(self, current_files: Dict[str, SyncState], db_notes: List):
        """Save current sync state"""
<<<<<<< HEAD
=======
        import json
>>>>>>> origin/main
        
        # Combine file and database states
        state_data = {}
        
        for filepath, file_state in current_files.items():
            state_data[filepath] = {
                "file_path": file_state.file_path,
                "last_modified": file_state.last_modified,
                "content_hash": file_state.content_hash,
                "note_id": file_state.note_id
            }
        
        with open(self.sync_state_file, 'w') as f:
            json.dump(state_data, f, indent=2)
    
    def _scan_vault_files(self) -> Dict[str, SyncState]:
        """Scan vault for markdown files and their states"""
        files = {}
        
        for md_file in self.vault_path.rglob("*.md"):
            if ".secondbrain" in str(md_file):
                continue
            
            filepath = str(md_file.relative_to(self.vault_path))
            content_hash = self._hash_file(md_file)
            note_id = self._extract_note_id(md_file)
            
            files[filepath] = SyncState(
                file_path=filepath,
                last_modified=md_file.stat().st_mtime,
                content_hash=content_hash,
                note_id=note_id
            )
        
        return files
    
    def _hash_file(self, filepath: Path) -> str:
        """Generate hash of file content"""
        with open(filepath, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    
    def _hash_note_content(self, note: tuple) -> str:
        """Generate hash of note content from database"""
        content = f"{note[1]}{note[3]}{note[4]}{note[5]}{note[6]}"  # title+content+summary+tags+actions
        return hashlib.md5(content.encode()).hexdigest()
    
    def _extract_note_id(self, filepath: Path) -> Optional[int]:
        """Extract note ID from frontmatter"""
        try:
<<<<<<< HEAD
            meta, _ = load_frontmatter_file(filepath)
            return meta.get('id')
        except Exception:
=======
            with open(filepath, 'r', encoding='utf-8') as f:
                post = frontmatter.load(f)
            return post.metadata.get('id')
        except:
>>>>>>> origin/main
            return None
    
    def _find_note_file(self, note_id: int) -> Optional[str]:
        """Find file corresponding to note ID"""
        for md_file in self.vault_path.rglob("*.md"):
            if ".secondbrain" in str(md_file):
                continue
            
            file_note_id = self._extract_note_id(md_file)
            if file_note_id == note_id:
                return str(md_file.relative_to(self.vault_path))
        
        return None
    
    def _check_note_changed_in_db(self, note_id: int, last_sync_state: SyncState) -> bool:
        """Check if note was modified in database since last sync"""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        note = conn.execute(
            "SELECT title, content, summary, tags, actions FROM notes WHERE id = ?",
            (note_id,)
        ).fetchone()
        conn.close()
        
        if not note:
            return False
        
        current_hash = self._hash_note_content(note)
        return current_hash != last_sync_state.content_hash
    
<<<<<<< HEAD
    # _sanitize_filename provided by obsidian_common.sanitize_filename
=======
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem"""
        import re
        # Remove invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Replace spaces with underscores
        filename = filename.replace(' ', '_')
        # Limit length
        return filename[:50]
>>>>>>> origin/main
    
    def create_obsidian_plugin_config(self):
        """Create configuration for Second Brain Obsidian plugin"""
        plugin_dir = self.vault_path / ".obsidian" / "plugins" / "second-brain"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        
        config = {
<<<<<<< HEAD
            "apiUrl": "http://localhost:8082",
=======
            "apiUrl": "http://localhost:8084",
>>>>>>> origin/main
            "autoSync": True,
            "syncInterval": 300,  # 5 minutes
            "audioTranscription": True,
            "aiSummaries": True
        }
        
        with open(plugin_dir / "data.json", 'w') as f:
            json.dump(config, f, indent=2)
        
        # Create basic plugin manifest
        manifest = {
            "id": "second-brain-sync",
            "name": "Second Brain Sync",
            "version": "1.0.0",
            "minAppVersion": "0.15.0",
            "description": "Sync notes with Second Brain AI system",
            "author": "Second Brain Team",
            "authorUrl": "https://github.com/dhouchin1/second_brain"
        }
        
        with open(plugin_dir / "manifest.json", 'w') as f:
            json.dump(manifest, f, indent=2)

<<<<<<< HEAD
    async def save_note_to_obsidian(self, filename: str, markdown_content: str) -> bool:
        """Save provided markdown content as a file in the Obsidian vault.

        Matches the usage in app.py where the markdown for a single note is
        generated and needs to be written to disk. Returns True on success.
        """
        try:
            self.vault_path.mkdir(parents=True, exist_ok=True)
            out = self.vault_path / (f"{filename}.md" if not filename.endswith('.md') else filename)
            out.write_text(markdown_content, encoding='utf-8')
            return True
        except Exception as e:
            print(f"Failed to save note to Obsidian: {e}")
            return False
=======

# API endpoints for Obsidian sync
@app.post("/api/obsidian/sync")
async def obsidian_sync(
    direction: str = "bidirectional",  # "to_obsidian", "from_obsidian", "bidirectional"
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user)
):
    """Sync with Obsidian vault"""
    
    def perform_sync(user_id: int, sync_direction: str):
        obsidian = ObsidianSync(settings.vault_path, settings.db_path)
        
        if sync_direction == "to_obsidian":
            result = obsidian.sync_all_to_obsidian(user_id)
            return {"exported": result}
        elif sync_direction == "from_obsidian":
            result = obsidian.sync_from_obsidian()
            return {"imported": result}
        else:
            result = obsidian.bidirectional_sync(user_id)
            return result
    
    if background_tasks:
        background_tasks.add_task(perform_sync, current_user.id, direction)
        return {"status": "sync_started", "direction": direction}
    else:
        result = perform_sync(current_user.id, direction)
        return {"status": "completed", "result": result}

@app.post("/api/obsidian/watch")
async def start_obsidian_watch(
    current_user: User = Depends(get_current_user)
):
    """Start watching Obsidian vault for changes"""
    
    obsidian = ObsidianSync(settings.vault_path, settings.db_path)
    observer = obsidian.watch_obsidian_changes(current_user.id)
    
    # Store observer reference (in production, use proper process management)
    app.state.obsidian_observer = observer
    
    return {"status": "watching_started"}

@app.post("/api/obsidian/stop-watch")
async def stop_obsidian_watch():
    """Stop watching Obsidian vault"""
    
    if hasattr(app.state, 'obsidian_observer'):
        app.state.obsidian_observer.stop()
        app.state.obsidian_observer.join()
        delattr(app.state, 'obsidian_observer')
    
    return {"status": "watching_stopped"}

@app.get("/api/obsidian/status")
async def obsidian_sync_status(
    current_user: User = Depends(get_current_user)
):
    """Get Obsidian sync status"""
    
    obsidian = ObsidianSync(settings.vault_path, settings.db_path)
    
    # Count files in vault
    vault_files = len(list(obsidian.vault_path.rglob("*.md")))
    
    # Count notes in database
    conn = get_conn()
    c = conn.cursor()
    db_notes = c.execute(
        "SELECT COUNT(*) FROM notes WHERE user_id = ?", 
        (current_user.id,)
    ).fetchone()[0]
    conn.close()
    
    # Check if watching
    watching = hasattr(app.state, 'obsidian_observer')
    
    return {
        "vault_path": str(settings.vault_path),
        "vault_files": vault_files,
        "database_notes": db_notes,
        "auto_watching": watching,
        "last_sync": "2025-01-12T10:30:00Z"  # This would be stored in database
    }
>>>>>>> origin/main
