#!/usr/bin/env python3
"""
Simple Build Log Capture Example

Minimal example showing how to save a Claude Code session to Second Brain.

Usage:
    python examples/capture_build_session_simple.py
"""

import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# This will work once BUILD_LOG is added to the enum
# For now, demonstrates the intended usage

def save_session_example():
    """Example: Save a development session"""

    # Session details
    task = "Implement build log capture feature"
    conversation = """
    User: I want to capture our Claude Code sessions as build logs

    Assistant: Great idea! I'll help you implement that. Let me create:
    1. Slash commands for saving/viewing sessions
    2. MCP server tools
    3. Documentation

    [Full conversation would go here...]
    """

    files_changed = [
        "Created: .claude/commands/save-session.md",
        "Created: .claude/commands/build-log.md",
        "Modified: mcp_server.py",
        "Created: BUILD_LOG_IMPLEMENTATION.md"
    ]

    commands = [
        "pytest tests/ -v",
        "git add .",
        "git commit -m 'feat: Add build log capture'",
        "git push origin feature/build-logs"
    ]

    outcomes = {
        "success": True,
        "deliverables": [
            "Build log capture commands created",
            "MCP server updated with 4 new tools",
            "Comprehensive documentation written"
        ],
        "next_steps": [
            "Add BUILD_LOG to CaptureContentType enum",
            "Test with real sessions",
            "Create dashboard widget"
        ]
    }

    # Format as markdown
    log = f"""# Build Log: {task}

**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Duration**: 120 minutes

## Conversation
{conversation}

## Files Changed
{chr(10).join(f'- {f}' for f in files_changed)}

## Commands
```bash
{chr(10).join(commands)}
```

## Outcomes
**Status**: ✅ Success

**Deliverables**:
{chr(10).join(f'- ✓ {d}' for d in outcomes['deliverables'])}

**Next Steps**:
{chr(10).join(f'- □ {s}' for s in outcomes['next_steps'])}
"""

    print("=" * 60)
    print("📝 BUILD LOG EXAMPLE")
    print("=" * 60)
    print(log)
    print("=" * 60)
    print()
    print("To save this for real, use:")
    print("  /save-session command in Claude Code")
    print("  or the MCP server save_build_session tool")
    print()


def mcp_example():
    """Example: Using MCP server to save session"""

    print("=" * 60)
    print("🔌 MCP SERVER EXAMPLE")
    print("=" * 60)
    print()
    print("From Claude Code with MCP server configured:")
    print()
    print('''
    # Ask Claude to save the session via MCP
    User: "Save this session as a build log"

    # Claude uses MCP server tool
    result = await mcp.call_tool("save_build_session", {
        "task_description": "Implement authentication",
        "conversation_log": "Full transcript...",
        "files_changed": ["auth.py", "test_auth.py"],
        "commands_executed": ["pytest tests/"],
        "duration_minutes": 90,
        "outcomes": {
            "success": True,
            "deliverables": ["JWT auth working"],
            "next_steps": ["Add rate limiting"]
        }
    })
    ''')
    print()


def search_example():
    """Example: Searching for build logs"""

    print("=" * 60)
    print("🔍 SEARCH EXAMPLES")
    print("=" * 60)
    print()
    print("Find all build logs:")
    print("  /search-notes #build-log")
    print()
    print("Find sessions about FastAPI:")
    print("  /search-notes fastapi #build-log")
    print()
    print("Find a specific session:")
    print("  /search-notes session:session_20250113_103045")
    print()
    print("View recent sessions:")
    print("  /build-log recent")
    print()
    print("Get analytics:")
    print("  /build-log analytics")
    print()


if __name__ == "__main__":
    print("\n🚀 Second Brain - Build Log Capture Examples\n")

    save_session_example()
    print()

    mcp_example()
    print()

    search_example()

    print()
    print("=" * 60)
    print("📚 For more information:")
    print("  - See BUILD_LOG_IMPLEMENTATION.md")
    print("  - See .claude/ENHANCEMENTS.md")
    print("  - Try /save-session in Claude Code")
    print("=" * 60)
    print()
