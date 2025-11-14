"""
Build Log Service

Database service layer for managing development session build logs.

Provides:
- CRUD operations for build logs
- Search and filtering
- Analytics and statistics
- Export functionality
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from collections import Counter
from pathlib import Path


class BuildLogService:
    """Service for managing build log sessions"""

    def __init__(self, db_connection):
        """
        Initialize build log service.

        Args:
            db_connection: Function that returns SQLite connection
        """
        self.get_db = db_connection

    def create_session(
        self,
        task_description: str,
        conversation_log: str,
        files_changed: List[str] = None,
        commands_executed: List[str] = None,
        duration_minutes: Optional[int] = None,
        outcomes: Optional[Dict] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new build log session.

        Args:
            task_description: Brief description of the task
            conversation_log: Full conversation transcript
            files_changed: List of files that were modified
            commands_executed: List of commands that were run
            duration_minutes: Session duration in minutes
            outcomes: Dict with success, deliverables, next_steps
            session_id: Optional session identifier

        Returns:
            Dict with note_id, session_id, and metadata
        """
        conn = self.get_db()
        cursor = conn.cursor()

        # Generate session ID if not provided
        if not session_id:
            session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        now = datetime.now().isoformat()

        # Build metadata
        metadata = {
            "session_id": session_id,
            "task_description": task_description,
            "duration_minutes": duration_minutes,
            "session_started_at": now,
            "session_type": "development",
            "content_type": "build_log",
            "technical_context": {
                "files_changed": files_changed or [],
                "commands_executed": commands_executed or [],
                "file_change_count": len(files_changed or []),
                "command_count": len(commands_executed or [])
            },
            "outcomes": outcomes or {},
            "capture_timestamp": now,
            "capture_source": "web_ui"
        }

        # Create title
        title = f"Build Log: {task_description}"
        tags = "#build-log,#development-session"

        try:
            cursor.execute("""
                INSERT INTO notes (
                    title, body, tags, created_at, updated_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                title, conversation_log, tags, now, now, json.dumps(metadata)
            ))

            note_id = cursor.lastrowid
            conn.commit()

            return {
                "note_id": note_id,
                "session_id": session_id,
                "title": title,
                "created_at": now,
                "metadata": metadata
            }

        finally:
            conn.close()

    def get_session_by_id(self, note_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a build log session by note ID.

        Args:
            note_id: The note ID

        Returns:
            Dict with session data or None if not found
        """
        conn = self.get_db()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM notes
                WHERE id = ?
                AND (tags LIKE '%build-log%' OR metadata LIKE '%build_log%')
            """, (note_id,))

            row = cursor.fetchone()
            if not row:
                return None

            session = dict(row)
            try:
                session['metadata'] = json.loads(session.get('metadata') or '{}')
            except:
                session['metadata'] = {}

            return session

        finally:
            conn.close()

    def get_session_by_session_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a build log session by session ID.

        Args:
            session_id: The session identifier

        Returns:
            Dict with session data or None if not found
        """
        conn = self.get_db()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM notes
                WHERE metadata LIKE ?
                LIMIT 1
            """, (f'%{session_id}%',))

            row = cursor.fetchone()
            if not row:
                return None

            session = dict(row)
            try:
                session['metadata'] = json.loads(session.get('metadata') or '{}')
            except:
                session['metadata'] = {}

            return session

        finally:
            conn.close()

    def list_sessions(
        self,
        limit: int = 20,
        offset: int = 0,
        order_by: str = 'created_at DESC'
    ) -> List[Dict[str, Any]]:
        """
        List build log sessions.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip
            order_by: SQL ORDER BY clause

        Returns:
            List of session dictionaries
        """
        conn = self.get_db()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute(f"""
                SELECT * FROM notes
                WHERE tags LIKE '%build-log%'
                OR metadata LIKE '%build_log%'
                ORDER BY {order_by}
                LIMIT ? OFFSET ?
            """, (limit, offset))

            sessions = []
            for row in cursor.fetchall():
                session = dict(row)
                try:
                    session['metadata'] = json.loads(session.get('metadata') or '{}')
                except:
                    session['metadata'] = {}
                sessions.append(session)

            return sessions

        finally:
            conn.close()

    def count_sessions(self) -> int:
        """
        Count total number of build log sessions.

        Returns:
            Total count
        """
        conn = self.get_db()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT COUNT(*) FROM notes
                WHERE tags LIKE '%build-log%'
                OR metadata LIKE '%build_log%'
            """)
            return cursor.fetchone()[0]

        finally:
            conn.close()

    def search_sessions(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search build log sessions.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching sessions
        """
        conn = self.get_db()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Use LIKE-based search (FTS5 table not available)
            search_pattern = f"%{query}%"
            cursor.execute("""
                SELECT * FROM notes
                WHERE (tags LIKE '%build-log%' OR metadata LIKE '%build_log%')
                AND (title LIKE ? OR body LIKE ? OR tags LIKE ?)
                ORDER BY created_at DESC
                LIMIT ?
            """, (search_pattern, search_pattern, search_pattern, limit))

            sessions = []
            for row in cursor.fetchall():
                session = dict(row)
                try:
                    session['metadata'] = json.loads(session.get('metadata') or '{}')
                except:
                    session['metadata'] = {}
                sessions.append(session)

            return sessions

        finally:
            conn.close()

    def get_analytics(self) -> Dict[str, Any]:
        """
        Get analytics across all build log sessions.

        Returns:
            Dict with analytics data
        """
        conn = self.get_db()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM notes
                WHERE tags LIKE '%build-log%'
                OR metadata LIKE '%build_log%'
                ORDER BY created_at DESC
            """)

            sessions = [dict(row) for row in cursor.fetchall()]

            if not sessions:
                return {
                    "total_sessions": 0,
                    "message": "No build log sessions found"
                }

            # Parse metadata
            for session in sessions:
                try:
                    session['metadata'] = json.loads(session.get('metadata') or '{}')
                except:
                    session['metadata'] = {}

            # Calculate analytics
            total_sessions = len(sessions)
            total_duration = 0
            total_files = 0
            total_commands = 0
            all_tags = []
            success_count = 0

            for session in sessions:
                metadata = session['metadata']

                # Duration
                duration = metadata.get('duration_minutes', 0)
                if duration:
                    total_duration += duration

                # Technical context
                tech_context = metadata.get('technical_context', {})
                files = tech_context.get('files_changed', [])
                commands = tech_context.get('commands_executed', [])
                total_files += len(files)
                total_commands += len(commands)

                # Tags
                tags = session.get('tags', '').split(',')
                all_tags.extend([t.strip() for t in tags if t.strip()])

                # Outcomes
                outcomes = metadata.get('outcomes', {})
                if outcomes.get('success'):
                    success_count += 1

            # Recent activity
            now = datetime.now()
            last_7_days = sum(
                1 for s in sessions
                if (now - datetime.fromisoformat(s['created_at'])).days <= 7
            )
            last_30_days = sum(
                1 for s in sessions
                if (now - datetime.fromisoformat(s['created_at'])).days <= 30
            )

            # Top tags
            tag_counts = Counter(all_tags)
            top_tags = tag_counts.most_common(10)

            # Most productive days
            session_dates = [
                datetime.fromisoformat(s['created_at']).date()
                for s in sessions
            ]
            date_counts = Counter(session_dates)
            top_dates = date_counts.most_common(5)

            return {
                "total_sessions": total_sessions,
                "success_count": success_count,
                "success_rate": (success_count / total_sessions * 100) if total_sessions > 0 else 0,
                "total_duration": total_duration,
                "total_duration_hours": total_duration / 60 if total_duration > 0 else 0,
                "avg_duration": total_duration / total_sessions if total_sessions > 0 else 0,
                "total_files": total_files,
                "total_commands": total_commands,
                "avg_files_per_session": total_files / total_sessions if total_sessions > 0 else 0,
                "last_7_days": last_7_days,
                "last_30_days": last_30_days,
                "top_tags": [{"tag": tag, "count": count} for tag, count in top_tags],
                "top_dates": [{"date": str(date), "count": count} for date, count in top_dates]
            }

        finally:
            conn.close()

    def delete_session(self, note_id: int) -> bool:
        """
        Delete a build log session.

        Args:
            note_id: The note ID to delete

        Returns:
            True if deleted, False if not found
        """
        conn = self.get_db()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                DELETE FROM notes
                WHERE id = ?
                AND (tags LIKE '%build-log%' OR metadata LIKE '%build_log%')
            """, (note_id,))

            conn.commit()
            return cursor.rowcount > 0

        finally:
            conn.close()

    def update_session(
        self,
        note_id: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Update a build log session.

        Args:
            note_id: The note ID to update
            title: New title (optional)
            body: New body content (optional)
            metadata: New metadata (optional)

        Returns:
            True if updated, False if not found
        """
        conn = self.get_db()
        cursor = conn.cursor()

        try:
            # Build UPDATE query dynamically
            updates = []
            params = []

            if title is not None:
                updates.append("title = ?")
                params.append(title)

            if body is not None:
                updates.append("body = ?")
                params.append(body)

            if metadata is not None:
                updates.append("metadata = ?")
                params.append(json.dumps(metadata))

            if not updates:
                return False

            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())

            params.append(note_id)

            cursor.execute(f"""
                UPDATE notes
                SET {', '.join(updates)}
                WHERE id = ?
                AND (tags LIKE '%build-log%' OR metadata LIKE '%build_log%')
            """, params)

            conn.commit()
            return cursor.rowcount > 0

        finally:
            conn.close()


def get_build_log_service(db_connection):
    """
    Factory function to get build log service instance.

    Args:
        db_connection: Database connection function

    Returns:
        BuildLogService instance
    """
    return BuildLogService(db_connection)
