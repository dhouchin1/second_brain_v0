#!/usr/bin/env python3
"""
Second Brain MCP Server

An MCP (Model Context Protocol) server that exposes Second Brain functionality
to Claude Code and other MCP clients.

Provides tools for:
- Searching notes
- Creating notes
- Retrieving note details
- Analyzing vault statistics
- Managing tags

Installation:
    pip install mcp

Usage:
    python mcp_server.py

Configuration (in Claude Code settings):
    {
        "mcpServers": {
            "second-brain": {
                "command": "python",
                "args": ["/Users/dhouchin/mvp-setup/second_brain/mcp_server.py"],
                "env": {}
            }
        }
    }
"""

import asyncio
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List
from collections import Counter

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
    from mcp.server.stdio import stdio_server
except ImportError:
    print("Error: mcp package not installed")
    print("Install with: pip install mcp")
    exit(1)

# Database path
DB_PATH = Path(__file__).parent / "notes.db"

# Initialize MCP server
app = Server("second-brain")


def get_db():
    """Get database connection"""
    return sqlite3.connect(str(DB_PATH))


# ============================================================================
# MCP Tool: Search Notes
# ============================================================================

@app.list_tools()
async def list_tools() -> List[Tool]:
    """List all available tools"""
    return [
        Tool(
            name="search_notes",
            description="Search through Second Brain notes using full-text search",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results (default: 10)",
                        "default": 10
                    },
                    "user_id": {
                        "type": "number",
                        "description": "User ID to search for (default: 1)",
                        "default": 1
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="create_note",
            description="Create a new note in Second Brain",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Note content"
                    },
                    "title": {
                        "type": "string",
                        "description": "Note title (optional, will be auto-generated if not provided)"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for the note (optional)"
                    },
                    "user_id": {
                        "type": "number",
                        "description": "User ID (default: 1)",
                        "default": 1
                    }
                },
                "required": ["content"]
            }
        ),
        Tool(
            name="get_note",
            description="Get details of a specific note by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {
                        "type": "number",
                        "description": "Note ID"
                    },
                    "user_id": {
                        "type": "number",
                        "description": "User ID (default: 1)",
                        "default": 1
                    }
                },
                "required": ["note_id"]
            }
        ),
        Tool(
            name="get_vault_stats",
            description="Get statistics and analytics about the Second Brain vault",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "number",
                        "description": "User ID (default: 1)",
                        "default": 1
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_tags",
            description="Get all tags and their frequencies",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "number",
                        "description": "User ID (default: 1)",
                        "default": 1
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of tags to return (default: 20)",
                        "default": 20
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_recent_notes",
            description="Get recently created notes",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "number",
                        "description": "User ID (default: 1)",
                        "default": 1
                    },
                    "limit": {
                        "type": "number",
                        "description": "Number of notes to return (default: 10)",
                        "default": 10
                    },
                    "days": {
                        "type": "number",
                        "description": "Number of days to look back (default: 7)",
                        "default": 7
                    }
                },
                "required": []
            }
        ),
        # ============================================================================
        # Build Log Tools
        # ============================================================================
        Tool(
            name="save_build_session",
            description="Save a Claude Code development session as a structured build log",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Brief description of the task"
                    },
                    "conversation_log": {
                        "type": "string",
                        "description": "Full conversation transcript (markdown formatted)"
                    },
                    "files_changed": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of files created/modified/deleted",
                        "default": []
                    },
                    "commands_executed": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of commands run during session",
                        "default": []
                    },
                    "duration_minutes": {
                        "type": "number",
                        "description": "Session duration in minutes"
                    },
                    "outcomes": {
                        "type": "object",
                        "description": "Session outcomes (success, deliverables, next_steps)",
                        "properties": {
                            "success": {"type": "boolean"},
                            "deliverables": {"type": "array", "items": {"type": "string"}},
                            "next_steps": {"type": "array", "items": {"type": "string"}}
                        }
                    },
                    "user_id": {
                        "type": "number",
                        "description": "User ID (default: 1)",
                        "default": 1
                    }
                },
                "required": ["task_description", "conversation_log"]
            }
        ),
        Tool(
            name="get_build_sessions",
            description="Get list of recent development session build logs",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "number",
                        "description": "User ID (default: 1)",
                        "default": 1
                    },
                    "limit": {
                        "type": "number",
                        "description": "Number of sessions to return (default: 10)",
                        "default": 10
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_build_session_by_id",
            description="Get detailed information about a specific build session",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID (e.g., session_20250113_103045)"
                    },
                    "user_id": {
                        "type": "number",
                        "description": "User ID (default: 1)",
                        "default": 1
                    }
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="get_build_session_analytics",
            description="Get analytics and statistics across all build sessions",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "number",
                        "description": "User ID (default: 1)",
                        "default": 1
                    }
                },
                "required": []
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> List[TextContent]:
    """Handle tool calls"""

    if name == "search_notes":
        return await search_notes_tool(arguments)
    elif name == "create_note":
        return await create_note_tool(arguments)
    elif name == "get_note":
        return await get_note_tool(arguments)
    elif name == "get_vault_stats":
        return await get_vault_stats_tool(arguments)
    elif name == "get_tags":
        return await get_tags_tool(arguments)
    elif name == "get_recent_notes":
        return await get_recent_notes_tool(arguments)
    elif name == "save_build_session":
        return await save_build_session_tool(arguments)
    elif name == "get_build_sessions":
        return await get_build_sessions_tool(arguments)
    elif name == "get_build_session_by_id":
        return await get_build_session_by_id_tool(arguments)
    elif name == "get_build_session_analytics":
        return await get_build_session_analytics_tool(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ============================================================================
# Tool Implementations
# ============================================================================

async def search_notes_tool(args: Dict[str, Any]) -> List[TextContent]:
    """Search notes using FTS5"""
    query = args["query"]
    limit = args.get("limit", 10)
    user_id = args.get("user_id", 1)

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Search using FTS5
        cursor.execute("""
            SELECT n.id, n.title, n.content, n.tags, n.created_at, n.type
            FROM notes n
            JOIN notes_fts fts ON n.id = fts.rowid
            WHERE fts MATCH ? AND n.user_id = ?
            ORDER BY fts.rank
            LIMIT ?
        """, (query, user_id, limit))

        results = cursor.fetchall()

        if not results:
            return [TextContent(
                type="text",
                text=f"No results found for '{query}'"
            )]

        # Format results
        output = f"Found {len(results)} results for '{query}':\n\n"
        for i, (note_id, title, content, tags, created_at, note_type) in enumerate(results, 1):
            output += f"{i}. **{title or 'Untitled'}** (ID: {note_id})\n"
            output += f"   Type: {note_type or 'text'}\n"
            if tags:
                output += f"   Tags: {tags}\n"
            output += f"   Created: {created_at}\n"
            # Truncate content
            preview = content[:200] if content else ""
            if len(content or "") > 200:
                preview += "..."
            output += f"   Preview: {preview}\n\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error searching notes: {str(e)}")]
    finally:
        conn.close()


async def create_note_tool(args: Dict[str, Any]) -> List[TextContent]:
    """Create a new note"""
    content = args["content"]
    title = args.get("title")
    tags = args.get("tags", [])
    user_id = args.get("user_id", 1)

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Generate title if not provided
        if not title:
            # Simple title generation (first 50 chars)
            title = content[:50].strip()
            if len(content) > 50:
                title += "..."

        # Format tags
        tags_str = ",".join(tags) if tags else None

        # Insert note
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO notes (
                user_id, title, content, body, tags,
                type, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, title, content, content, tags_str,
            'text', 'completed', now, now
        ))

        note_id = cursor.lastrowid
        conn.commit()

        output = f"✅ Note created successfully!\n\n"
        output += f"**ID**: {note_id}\n"
        output += f"**Title**: {title}\n"
        if tags:
            output += f"**Tags**: {', '.join(tags)}\n"
        output += f"**Created**: {now}\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error creating note: {str(e)}")]
    finally:
        conn.close()


async def get_note_tool(args: Dict[str, Any]) -> List[TextContent]:
    """Get note details"""
    note_id = args["note_id"]
    user_id = args.get("user_id", 1)

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, title, content, tags, type, status, created_at, updated_at
            FROM notes
            WHERE id = ? AND user_id = ?
        """, (note_id, user_id))

        result = cursor.fetchone()

        if not result:
            return [TextContent(type="text", text=f"Note #{note_id} not found")]

        note_id, title, content, tags, note_type, status, created_at, updated_at = result

        output = f"# {title or 'Untitled'}\n\n"
        output += f"**ID**: {note_id}\n"
        output += f"**Type**: {note_type or 'text'}\n"
        output += f"**Status**: {status or 'unknown'}\n"
        if tags:
            output += f"**Tags**: {tags}\n"
        output += f"**Created**: {created_at}\n"
        output += f"**Updated**: {updated_at}\n\n"
        output += f"## Content\n\n{content}\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error getting note: {str(e)}")]
    finally:
        conn.close()


async def get_vault_stats_tool(args: Dict[str, Any]) -> List[TextContent]:
    """Get vault statistics"""
    user_id = args.get("user_id", 1)

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Total notes
        total = cursor.execute(
            "SELECT COUNT(*) FROM notes WHERE user_id = ?",
            (user_id,)
        ).fetchone()[0]

        # Notes by type
        cursor.execute("""
            SELECT type, COUNT(*) as count
            FROM notes
            WHERE user_id = ?
            GROUP BY type
            ORDER BY count DESC
        """, (user_id,))
        types = cursor.fetchall()

        # Recent activity (last 30 days)
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        recent = cursor.execute("""
            SELECT COUNT(*) FROM notes
            WHERE user_id = ? AND created_at > ?
        """, (user_id, thirty_days_ago)).fetchone()[0]

        # Tags
        cursor.execute(
            "SELECT tags FROM notes WHERE user_id = ? AND tags IS NOT NULL",
            (user_id,)
        )
        all_tags = []
        for (tags_str,) in cursor.fetchall():
            if tags_str:
                all_tags.extend([t.strip() for t in tags_str.replace('#', '').split(',') if t.strip()])

        tag_counts = Counter(all_tags)
        top_tags = tag_counts.most_common(5)

        # Format output
        output = "# 📊 Second Brain Statistics\n\n"
        output += f"**Total Notes**: {total}\n"
        output += f"**Notes (Last 30 Days)**: {recent}\n\n"

        output += "## Notes by Type\n"
        for note_type, count in types:
            output += f"- {note_type or 'unknown'}: {count}\n"

        output += "\n## Top Tags\n"
        for tag, count in top_tags:
            output += f"- {tag}: {count} notes\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error getting stats: {str(e)}")]
    finally:
        conn.close()


async def get_tags_tool(args: Dict[str, Any]) -> List[TextContent]:
    """Get all tags"""
    user_id = args.get("user_id", 1)
    limit = args.get("limit", 20)

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT tags FROM notes WHERE user_id = ? AND tags IS NOT NULL",
            (user_id,)
        )

        all_tags = []
        for (tags_str,) in cursor.fetchall():
            if tags_str:
                all_tags.extend([t.strip() for t in tags_str.replace('#', '').split(',') if t.strip()])

        tag_counts = Counter(all_tags)
        top_tags = tag_counts.most_common(limit)

        output = f"# 🏷️ Tags (Top {len(top_tags)})\n\n"
        for tag, count in top_tags:
            output += f"- **{tag}**: {count} notes\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error getting tags: {str(e)}")]
    finally:
        conn.close()


async def get_recent_notes_tool(args: Dict[str, Any]) -> List[TextContent]:
    """Get recent notes"""
    user_id = args.get("user_id", 1)
    limit = args.get("limit", 10)
    days = args.get("days", 7)

    conn = get_db()
    cursor = conn.cursor()

    try:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT id, title, content, tags, created_at, type
            FROM notes
            WHERE user_id = ? AND created_at > ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, cutoff, limit))

        results = cursor.fetchall()

        if not results:
            return [TextContent(
                type="text",
                text=f"No notes found in the last {days} days"
            )]

        output = f"# 📝 Recent Notes (Last {days} Days)\n\n"
        for note_id, title, content, tags, created_at, note_type in results:
            output += f"## {title or 'Untitled'} (ID: {note_id})\n"
            output += f"**Type**: {note_type or 'text'}\n"
            if tags:
                output += f"**Tags**: {tags}\n"
            output += f"**Created**: {created_at}\n"
            preview = (content or "")[:150]
            if len(content or "") > 150:
                preview += "..."
            output += f"{preview}\n\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error getting recent notes: {str(e)}")]
    finally:
        conn.close()


# ============================================================================
# Build Log Tool Implementations
# ============================================================================

async def save_build_session_tool(args: Dict[str, Any]) -> List[TextContent]:
    """Save a development session as a build log"""
    task_description = args["task_description"]
    conversation_log = args["conversation_log"]
    files_changed = args.get("files_changed", [])
    commands_executed = args.get("commands_executed", [])
    duration_minutes = args.get("duration_minutes")
    outcomes = args.get("outcomes", {})
    user_id = args.get("user_id", 1)

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Generate session ID
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Build metadata
        metadata = {
            "session_id": session_id,
            "task_description": task_description,
            "duration_minutes": duration_minutes,
            "session_started_at": datetime.now().isoformat(),
            "technical_context": {
                "files_changed": files_changed,
                "commands_executed": commands_executed,
                "file_change_count": len(files_changed),
                "command_count": len(commands_executed)
            },
            "outcomes": outcomes,
            "capture_timestamp": datetime.now().isoformat(),
            "capture_source": "mcp_server",
            "session_type": "development",
            "content_type": "build_log"
        }

        # Create note title
        title = f"Build Log: {task_description}"

        # Insert the build log
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO notes (
                user_id, title, content, body, tags,
                type, status, created_at, updated_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, title, conversation_log, conversation_log,
            "build-log,development-session",
            'build_log', 'completed', now, now,
            json.dumps(metadata)
        ))

        note_id = cursor.lastrowid
        conn.commit()

        # Format output
        output = "✅ Build Session Saved Successfully!\n\n"
        output += f"**Session ID**: {session_id}\n"
        output += f"**Note ID**: {note_id}\n"
        output += f"**Task**: {task_description}\n"

        if duration_minutes:
            output += f"**Duration**: {duration_minutes} minutes\n"

        if files_changed:
            output += f"**Files Changed**: {len(files_changed)}\n"

        if commands_executed:
            output += f"**Commands Run**: {len(commands_executed)}\n"

        if outcomes.get("success") is not None:
            status = "✅ Success" if outcomes["success"] else "⚠️  Incomplete"
            output += f"**Status**: {status}\n"

        output += f"\n🔍 **Search Later**:\n"
        output += f"- By task: `/search-notes {task_description}`\n"
        output += f"- By session: `/search-notes session:{session_id}`\n"
        output += f"- All build logs: `/search-notes #build-log`\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error saving build session: {str(e)}")]
    finally:
        conn.close()


async def get_build_sessions_tool(args: Dict[str, Any]) -> List[TextContent]:
    """Get list of recent build sessions"""
    user_id = args.get("user_id", 1)
    limit = args.get("limit", 10)

    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Query for build log type notes
        cursor.execute("""
            SELECT id, title, body, metadata, created_at
            FROM notes
            WHERE user_id = ?
            AND (type = 'build_log' OR metadata LIKE '%build_log%')
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit))

        sessions = [dict(row) for row in cursor.fetchall()]

        if not sessions:
            return [TextContent(
                type="text",
                text="No build log sessions found. Create one with /save-session!"
            )]

        # Format output
        output = f"# 📋 Recent Development Sessions ({len(sessions)})\n\n"

        for i, session in enumerate(sessions, 1):
            try:
                metadata = json.loads(session.get('metadata') or '{}')
            except:
                metadata = {}

            session_id = metadata.get('session_id', 'N/A')
            task = metadata.get('task_description', session['title'])
            duration = metadata.get('duration_minutes', 'N/A')
            created = session.get('created_at', 'N/A')

            output += f"## {i}. {task}\n"
            output += f"**Session ID**: `{session_id}`\n"
            output += f"**Date**: {created}\n"

            if duration != 'N/A':
                output += f"**Duration**: {duration} minutes\n"

            # Technical context
            tech_context = metadata.get('technical_context', {})
            files = tech_context.get('files_changed', [])
            commands = tech_context.get('commands_executed', [])

            if files:
                output += f"**Files Changed**: {len(files)}\n"
            if commands:
                output += f"**Commands**: {len(commands)}\n"

            # Outcomes
            outcomes = metadata.get('outcomes', {})
            if outcomes.get('success') is not None:
                status = "✅" if outcomes['success'] else "⚠️"
                output += f"**Status**: {status}\n"

            output += f"**Note ID**: {session['id']}\n\n"

        output += f"\n💡 **Tip**: Use `/build-log <session_id>` to view details\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error getting build sessions: {str(e)}")]
    finally:
        conn.close()


async def get_build_session_by_id_tool(args: Dict[str, Any]) -> List[TextContent]:
    """Get detailed session information by ID"""
    session_id = args["session_id"]
    user_id = args.get("user_id", 1)

    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Find session by session_id in metadata
        cursor.execute("""
            SELECT * FROM notes
            WHERE user_id = ?
            AND metadata LIKE ?
            LIMIT 1
        """, (user_id, f'%{session_id}%'))

        row = cursor.fetchone()

        if not row:
            return [TextContent(
                type="text",
                text=f"❌ Session not found: {session_id}"
            )]

        session = dict(row)
        try:
            metadata = json.loads(session.get('metadata') or '{}')
        except:
            metadata = {}

        # Format detailed output
        output = "=" * 70 + "\n"
        output += f"# 📝 BUILD LOG: {session['title']}\n"
        output += "=" * 70 + "\n\n"

        output += f"**🆔 Session ID**: {metadata.get('session_id', 'N/A')}\n"
        output += f"**📅 Date**: {session['created_at']}\n"

        if metadata.get('duration_minutes'):
            output += f"**⏱️ Duration**: {metadata['duration_minutes']} minutes\n"

        output += f"**💾 Note ID**: {session['id']}\n\n"

        # Task description
        task = metadata.get('task_description')
        if task:
            output += f"## 📋 Task\n{task}\n\n"

        # Technical Context
        tech_context = metadata.get('technical_context', {})
        files = tech_context.get('files_changed', [])
        commands = tech_context.get('commands_executed', [])

        if files or commands:
            output += "## 🔧 Technical Context\n\n"

            if files:
                output += f"**Files Changed ({len(files)})**:\n"
                for file in files[:10]:
                    output += f"- {file}\n"
                if len(files) > 10:
                    output += f"- ... and {len(files) - 10} more\n"
                output += "\n"

            if commands:
                output += f"**Commands Executed ({len(commands)})**:\n"
                for cmd in commands[:5]:
                    output += f"- `{cmd}`\n"
                if len(commands) > 5:
                    output += f"- ... and {len(commands) - 5} more\n"
                output += "\n"

        # Outcomes
        outcomes = metadata.get('outcomes', {})
        if outcomes:
            output += "## ✨ Outcomes\n\n"

            if outcomes.get('success') is not None:
                status = "✅ Success" if outcomes['success'] else "⚠️ Incomplete"
                output += f"**Status**: {status}\n\n"

            deliverables = outcomes.get('deliverables', [])
            if deliverables:
                output += "**Deliverables**:\n"
                for item in deliverables:
                    output += f"- ✓ {item}\n"
                output += "\n"

            next_steps = outcomes.get('next_steps', [])
            if next_steps:
                output += "**Next Steps**:\n"
                for item in next_steps:
                    output += f"- □ {item}\n"
                output += "\n"

        # Conversation preview
        body = session.get('body', '')
        output += "## 📄 Conversation\n\n"
        output += f"**Length**: {len(body)} characters\n\n"
        preview = body[:500]
        if len(body) > 500:
            preview += "..."
        output += f"**Preview**:\n```\n{preview}\n```\n\n"

        output += "=" * 70 + "\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error getting session: {str(e)}")]
    finally:
        conn.close()


async def get_build_session_analytics_tool(args: Dict[str, Any]) -> List[TextContent]:
    """Get analytics across all build sessions"""
    user_id = args.get("user_id", 1)

    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Get all build log sessions
        cursor.execute("""
            SELECT * FROM notes
            WHERE user_id = ?
            AND (type = 'build_log' OR metadata LIKE '%build_log%')
            ORDER BY created_at DESC
        """, (user_id,))

        sessions = [dict(row) for row in cursor.fetchall()]

        if not sessions:
            return [TextContent(
                type="text",
                text="No build log sessions found to analyze."
            )]

        # Calculate analytics
        total_sessions = len(sessions)
        total_duration = 0
        total_files = 0
        total_commands = 0
        all_tags = []
        success_count = 0

        for session in sessions:
            try:
                metadata = json.loads(session.get('metadata') or '{}')
            except:
                metadata = {}

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
        last_7_days = sum(1 for s in sessions
                          if (now - datetime.fromisoformat(s['created_at'])).days <= 7)
        last_30_days = sum(1 for s in sessions
                           if (now - datetime.fromisoformat(s['created_at'])).days <= 30)

        # Format output
        output = "=" * 70 + "\n"
        output += "# 📊 BUILD LOG ANALYTICS\n"
        output += "=" * 70 + "\n\n"

        output += "## 📈 Overview\n\n"
        output += f"**Total Sessions**: {total_sessions}\n"

        if success_count > 0:
            success_rate = (success_count / total_sessions * 100)
            output += f"**Success Rate**: {success_rate:.1f}%\n"

        if total_duration > 0:
            output += f"**Total Duration**: {total_duration} minutes ({total_duration/60:.1f} hours)\n"
            output += f"**Avg Duration**: {total_duration/total_sessions:.1f} minutes/session\n"

        output += "\n## 💻 Technical Activity\n\n"
        output += f"**Files Changed**: {total_files}\n"
        output += f"**Commands Executed**: {total_commands}\n"

        if total_sessions > 0:
            output += f"**Avg Files/Session**: {total_files/total_sessions:.1f}\n"

        # Top tags
        if all_tags:
            tag_counts = Counter(all_tags)
            top_tags = tag_counts.most_common(10)

            output += "\n## 🏷️ Top Tags\n\n"
            for tag, count in top_tags:
                bar = "█" * min(count, 20)
                output += f"{tag:20} {bar} {count}\n"

        output += "\n## 📅 Recent Activity\n\n"
        output += f"**Last 7 days**: {last_7_days} sessions\n"
        output += f"**Last 30 days**: {last_30_days} sessions\n"

        output += "\n" + "=" * 70 + "\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error getting analytics: {str(e)}")]
    finally:
        conn.close()


# ============================================================================
# Main
# ============================================================================

async def main():
    """Run the MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
