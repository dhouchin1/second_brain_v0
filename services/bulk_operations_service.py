"""
Bulk Operations Service

Provides comprehensive bulk/batch operations for notes management including:
- Bulk delete, update, tag, and move operations
- Import/export functionality
- Bulk metadata operations
- Performance optimized batch processing
"""

import json
import sqlite3
import zipfile
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Union
from dataclasses import dataclass
from io import StringIO, BytesIO

@dataclass
class BulkOperationResult:
    operation: str
    note_id: int
    status: str
    message: str = ""
    error: Optional[str] = None

class BulkOperationsService:
    def __init__(self, get_conn: Callable[[], sqlite3.Connection], vault_path: str = "vault"):
        self.get_conn = get_conn
        self.vault_path = Path(vault_path)
        
    def execute_bulk_operations(self, user_id: int, operations: List[Dict[str, Any]]) -> List[BulkOperationResult]:
        """Execute multiple bulk operations in sequence"""
        results = []
        conn = self.get_conn()
        
        try:
            # Process operations in batches for better performance
            for operation in operations:
                try:
                    if operation["action"] == "delete":
                        result = self._bulk_delete(conn, user_id, operation)
                    elif operation["action"] == "update":
                        result = self._bulk_update(conn, user_id, operation)
                    elif operation["action"] == "tag":
                        result = self._bulk_tag(conn, user_id, operation)
                    elif operation["action"] == "move":
                        result = self._bulk_move(conn, user_id, operation)
                    elif operation["action"] == "export":
                        result = self._bulk_export(conn, user_id, operation)
                    elif operation["action"] == "duplicate":
                        result = self._bulk_duplicate(conn, user_id, operation)
                    else:
                        result = BulkOperationResult(
                            operation["action"],
                            operation.get("note_id", 0),
                            "error",
                            error=f"Unknown operation: {operation['action']}"
                        )
                    
                    if isinstance(result, list):
                        results.extend(result)
                    else:
                        results.append(result)
                        
                except Exception as e:
                    results.append(BulkOperationResult(
                        operation.get("action", "unknown"),
                        operation.get("note_id", 0),
                        "error",
                        error=str(e)
                    ))
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            results.append(BulkOperationResult("bulk_operation", 0, "error", error=str(e)))
        
        return results
    
    def _bulk_delete(self, conn: sqlite3.Connection, user_id: int, operation: Dict[str, Any]) -> Union[BulkOperationResult, List[BulkOperationResult]]:
        """Delete notes in bulk"""
        cursor = conn.cursor()
        
        if "note_ids" in operation:
            # Delete multiple specific notes
            results = []
            for note_id in operation["note_ids"]:
                try:
                    # Check if note exists and belongs to user
                    cursor.execute("SELECT id, title FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
                    note = cursor.fetchone()
                    
                    if not note:
                        results.append(BulkOperationResult("delete", note_id, "error", error="Note not found"))
                        continue
                    
                    # Delete from notes table
                    cursor.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
                    
                    # Delete from FTS index
                    cursor.execute("DELETE FROM notes_fts WHERE rowid = ?", (note_id,))
                    
                    # Delete associated files if any
                    cursor.execute("DELETE FROM file_metadata WHERE note_id = ?", (note_id,))
                    
                    results.append(BulkOperationResult("delete", note_id, "success", f"Deleted note: {note[1]}"))
                    
                except Exception as e:
                    results.append(BulkOperationResult("delete", note_id, "error", error=str(e)))
            
            return results
            
        elif "filter" in operation:
            # Delete notes matching filter criteria
            filter_conditions = []
            filter_params = [user_id]
            
            if "tags" in operation["filter"]:
                filter_conditions.append("tags LIKE ?")
                filter_params.append(f"%{operation['filter']['tags']}%")
            
            if "date_range" in operation["filter"]:
                date_range = operation["filter"]["date_range"]
                if "start" in date_range:
                    filter_conditions.append("created_at >= ?")
                    filter_params.append(date_range["start"])
                if "end" in date_range:
                    filter_conditions.append("created_at <= ?")
                    filter_params.append(date_range["end"])
            
            if not filter_conditions:
                return BulkOperationResult("delete", 0, "error", error="No valid filter criteria provided")
            
            where_clause = " AND ".join(filter_conditions)
            
            # Get matching notes first
            cursor.execute(f"SELECT id, title FROM notes WHERE user_id = ? AND {where_clause}", filter_params)
            notes_to_delete = cursor.fetchall()
            
            if not notes_to_delete:
                return BulkOperationResult("delete", 0, "success", "No notes matched filter criteria")
            
            # Delete matching notes
            note_ids = [note[0] for note in notes_to_delete]
            placeholders = ",".join("?" * len(note_ids))
            
            cursor.execute(f"DELETE FROM notes WHERE id IN ({placeholders})", note_ids)
            cursor.execute(f"DELETE FROM notes_fts WHERE rowid IN ({placeholders})", note_ids)
            
            deleted_count = len(notes_to_delete)
            return BulkOperationResult("delete", 0, "success", f"Deleted {deleted_count} notes matching filter")
        
        return BulkOperationResult("delete", 0, "error", error="No valid delete criteria provided")
    
    def _bulk_update(self, conn: sqlite3.Connection, user_id: int, operation: Dict[str, Any]) -> Union[BulkOperationResult, List[BulkOperationResult]]:
        """Update notes in bulk"""
        cursor = conn.cursor()
        
        note_ids = operation.get("note_ids", [])
        updates = operation.get("updates", {})
        
        if not note_ids or not updates:
            return BulkOperationResult("update", 0, "error", error="Missing note_ids or updates")
        
        results = []
        
        for note_id in note_ids:
            try:
                # Build update query dynamically
                update_fields = []
                update_values = []
                
                if "title" in updates:
                    update_fields.append("title = ?")
                    update_values.append(updates["title"])
                
                if "content" in updates:
                    update_fields.append("content = ?")
                    update_values.append(updates["content"])
                
                if "summary" in updates:
                    update_fields.append("summary = ?")
                    update_values.append(updates["summary"])
                
                if "tags" in updates:
                    update_fields.append("tags = ?")
                    update_values.append(updates["tags"])
                
                if "status" in updates:
                    update_fields.append("status = ?")
                    update_values.append(updates["status"])
                
                if not update_fields:
                    results.append(BulkOperationResult("update", note_id, "error", error="No valid update fields"))
                    continue
                
                update_values.extend([note_id, user_id])
                update_query = f"UPDATE notes SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?"
                
                cursor.execute(update_query, update_values)
                
                if cursor.rowcount > 0:
                    results.append(BulkOperationResult("update", note_id, "success", "Updated successfully"))
                else:
                    results.append(BulkOperationResult("update", note_id, "error", error="Note not found"))
                    
            except Exception as e:
                results.append(BulkOperationResult("update", note_id, "error", error=str(e)))
        
        return results
    
    def _bulk_tag(self, conn: sqlite3.Connection, user_id: int, operation: Dict[str, Any]) -> Union[BulkOperationResult, List[BulkOperationResult]]:
        """Add, remove, or replace tags in bulk"""
        cursor = conn.cursor()
        
        note_ids = operation.get("note_ids", [])
        tag_operation = operation.get("tag_operation", "add")  # add, remove, replace
        tags = operation.get("tags", "")
        
        if not note_ids:
            return BulkOperationResult("tag", 0, "error", error="No note_ids provided")
        
        results = []
        
        for note_id in note_ids:
            try:
                # Get current tags
                cursor.execute("SELECT tags FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
                row = cursor.fetchone()
                
                if not row:
                    results.append(BulkOperationResult("tag", note_id, "error", error="Note not found"))
                    continue
                
                current_tags = set(tag.strip() for tag in (row[0] or "").split(",") if tag.strip())
                new_tags = set(tag.strip() for tag in tags.split(",") if tag.strip())
                
                if tag_operation == "add":
                    final_tags = current_tags.union(new_tags)
                elif tag_operation == "remove":
                    final_tags = current_tags.difference(new_tags)
                elif tag_operation == "replace":
                    final_tags = new_tags
                else:
                    results.append(BulkOperationResult("tag", note_id, "error", error="Invalid tag operation"))
                    continue
                
                final_tags_str = ", ".join(sorted(final_tags)) if final_tags else ""
                
                cursor.execute(
                    "UPDATE notes SET tags = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
                    (final_tags_str, note_id, user_id)
                )
                
                results.append(BulkOperationResult("tag", note_id, "success", f"Tags updated: {final_tags_str}"))
                
            except Exception as e:
                results.append(BulkOperationResult("tag", note_id, "error", error=str(e)))
        
        return results
    
    def _bulk_move(self, conn: sqlite3.Connection, user_id: int, operation: Dict[str, Any]) -> Union[BulkOperationResult, List[BulkOperationResult]]:
        """Move notes to different status/folder in bulk"""
        cursor = conn.cursor()
        
        note_ids = operation.get("note_ids", [])
        target_status = operation.get("target_status", "active")
        
        if not note_ids:
            return BulkOperationResult("move", 0, "error", error="No note_ids provided")
        
        results = []
        
        for note_id in note_ids:
            try:
                cursor.execute(
                    "UPDATE notes SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
                    (target_status, note_id, user_id)
                )
                
                if cursor.rowcount > 0:
                    results.append(BulkOperationResult("move", note_id, "success", f"Moved to {target_status}"))
                else:
                    results.append(BulkOperationResult("move", note_id, "error", error="Note not found"))
                    
            except Exception as e:
                results.append(BulkOperationResult("move", note_id, "error", error=str(e)))
        
        return results
    
    def _bulk_export(self, conn: sqlite3.Connection, user_id: int, operation: Dict[str, Any]) -> BulkOperationResult:
        """Export notes in bulk to various formats"""
        cursor = conn.cursor()
        
        note_ids = operation.get("note_ids", [])
        export_format = operation.get("format", "json")  # json, csv, markdown, zip
        
        if not note_ids:
            return BulkOperationResult("export", 0, "error", error="No note_ids provided")
        
        try:
            # Get notes data
            placeholders = ",".join("?" * len(note_ids))
            cursor.execute(f"""
                SELECT id, title, content, summary, tags, created_at, updated_at, file_type
                FROM notes 
                WHERE id IN ({placeholders}) AND user_id = ?
                ORDER BY created_at DESC
            """, note_ids + [user_id])
            
            notes = cursor.fetchall()
            
            if not notes:
                return BulkOperationResult("export", 0, "error", error="No notes found")
            
            # Create export data
            export_data = []
            for note in notes:
                export_data.append({
                    "id": note[0],
                    "title": note[1],
                    "content": note[2],
                    "summary": note[3],
                    "tags": note[4],
                    "created_at": note[5],
                    "updated_at": note[6],
                    "file_type": note[7]
                })
            
            # Generate export file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if export_format == "json":
                export_path = f"exports/notes_export_{timestamp}.json"
                Path("exports").mkdir(exist_ok=True)
                with open(export_path, 'w') as f:
                    json.dump(export_data, f, indent=2, default=str)
            
            elif export_format == "csv":
                export_path = f"exports/notes_export_{timestamp}.csv"
                Path("exports").mkdir(exist_ok=True)
                with open(export_path, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=export_data[0].keys())
                    writer.writeheader()
                    writer.writerows(export_data)
            
            elif export_format == "markdown":
                export_path = f"exports/notes_export_{timestamp}.md"
                Path("exports").mkdir(exist_ok=True)
                with open(export_path, 'w') as f:
                    f.write(f"# Notes Export - {timestamp}\n\n")
                    for note in export_data:
                        f.write(f"## {note['title']}\n\n")
                        if note['tags']:
                            f.write(f"**Tags:** {note['tags']}\n\n")
                        if note['summary']:
                            f.write(f"**Summary:** {note['summary']}\n\n")
                        if note['content']:
                            f.write(f"{note['content']}\n\n")
                        f.write("---\n\n")
            
            elif export_format == "zip":
                export_path = f"exports/notes_export_{timestamp}.zip"
                Path("exports").mkdir(exist_ok=True)
                with zipfile.ZipFile(export_path, 'w') as zf:
                    # Add JSON data
                    zf.writestr("notes.json", json.dumps(export_data, indent=2, default=str))
                    
                    # Add individual markdown files
                    for note in export_data:
                        filename = f"note_{note['id']}_{note['title'][:50]}.md".replace("/", "_")
                        content = f"# {note['title']}\n\n"
                        if note['tags']:
                            content += f"**Tags:** {note['tags']}\n\n"
                        if note['summary']:
                            content += f"**Summary:** {note['summary']}\n\n"
                        if note['content']:
                            content += f"{note['content']}\n"
                        zf.writestr(filename, content)
            
            return BulkOperationResult("export", 0, "success", f"Exported {len(notes)} notes to {export_path}")
            
        except Exception as e:
            return BulkOperationResult("export", 0, "error", error=str(e))
    
    def _bulk_duplicate(self, conn: sqlite3.Connection, user_id: int, operation: Dict[str, Any]) -> Union[BulkOperationResult, List[BulkOperationResult]]:
        """Duplicate notes in bulk"""
        cursor = conn.cursor()
        
        note_ids = operation.get("note_ids", [])
        suffix = operation.get("suffix", " (Copy)")
        
        if not note_ids:
            return BulkOperationResult("duplicate", 0, "error", error="No note_ids provided")
        
        results = []
        
        for note_id in note_ids:
            try:
                # Get original note
                cursor.execute("""
                    SELECT title, content, summary, tags, file_type
                    FROM notes 
                    WHERE id = ? AND user_id = ?
                """, (note_id, user_id))
                
                note = cursor.fetchone()
                
                if not note:
                    results.append(BulkOperationResult("duplicate", note_id, "error", error="Note not found"))
                    continue
                
                # Create duplicate
                new_title = note[0] + suffix
                cursor.execute("""
                    INSERT INTO notes (user_id, title, content, summary, tags, file_type, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
                """, (user_id, new_title, note[1], note[2], note[3], note[4]))
                
                new_note_id = cursor.lastrowid
                results.append(BulkOperationResult("duplicate", note_id, "success", f"Duplicated as note {new_note_id}"))
                
            except Exception as e:
                results.append(BulkOperationResult("duplicate", note_id, "error", error=str(e)))
        
        return results
    
    def import_notes(self, user_id: int, import_data: bytes, file_format: str) -> List[BulkOperationResult]:
        """Import notes from various formats"""
        results = []
        conn = self.get_conn()
        cursor = conn.cursor()
        
        try:
            if file_format == "json":
                data = json.loads(import_data.decode('utf-8'))
                
                if not isinstance(data, list):
                    data = [data]  # Handle single object
                
                for item in data:
                    try:
                        cursor.execute("""
                            INSERT INTO notes (user_id, title, content, summary, tags, file_type, status, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
                        """, (
                            user_id,
                            item.get('title', 'Imported Note'),
                            item.get('content', ''),
                            item.get('summary', ''),
                            item.get('tags', ''),
                            item.get('file_type', 'text')
                        ))
                        
                        note_id = cursor.lastrowid
                        results.append(BulkOperationResult("import", note_id, "success", f"Imported: {item.get('title', 'Untitled')}"))
                        
                    except Exception as e:
                        results.append(BulkOperationResult("import", 0, "error", error=str(e)))
            
            elif file_format == "csv":
                import csv
                csv_data = import_data.decode('utf-8')
                reader = csv.DictReader(StringIO(csv_data))
                
                for row in reader:
                    try:
                        cursor.execute("""
                            INSERT INTO notes (user_id, title, content, summary, tags, file_type, status, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
                        """, (
                            user_id,
                            row.get('title', 'Imported Note'),
                            row.get('content', ''),
                            row.get('summary', ''),
                            row.get('tags', ''),
                            row.get('file_type', 'text')
                        ))
                        
                        note_id = cursor.lastrowid
                        results.append(BulkOperationResult("import", note_id, "success", f"Imported: {row.get('title', 'Untitled')}"))
                        
                    except Exception as e:
                        results.append(BulkOperationResult("import", 0, "error", error=str(e)))
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            results.append(BulkOperationResult("import", 0, "error", error=str(e)))
        
        return results
    
    def get_bulk_operation_stats(self, user_id: int) -> Dict[str, Any]:
        """Get statistics for bulk operations"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        try:
            # Total notes
            cursor.execute("SELECT COUNT(*) FROM notes WHERE user_id = ?", (user_id,))
            total_notes = cursor.fetchone()[0]
            
            # Notes by status
            cursor.execute("""
                SELECT status, COUNT(*) 
                FROM notes 
                WHERE user_id = ? 
                GROUP BY status
            """, (user_id,))
            status_counts = dict(cursor.fetchall())
            
            # Notes by type
            cursor.execute("""
                SELECT file_type, COUNT(*) 
                FROM notes 
                WHERE user_id = ? 
                GROUP BY file_type
            """, (user_id,))
            type_counts = dict(cursor.fetchall())
            
            # Recent activity
            cursor.execute("""
                SELECT COUNT(*) 
                FROM notes 
                WHERE user_id = ? AND created_at >= datetime('now', '-7 days')
            """, (user_id,))
            recent_notes = cursor.fetchone()[0]
            
            return {
                "total_notes": total_notes,
                "status_breakdown": status_counts,
                "type_breakdown": type_counts,
                "recent_notes_7_days": recent_notes,
                "operations_available": [
                    "delete", "update", "tag", "move", "export", "duplicate", "import"
                ]
            }
            
        except Exception as e:
            return {"error": str(e)}

print("[Bulk Operations Service] Loaded successfully")