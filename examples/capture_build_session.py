#!/usr/bin/env python3
"""
Build Log Capture Script

This script demonstrates how to capture a Claude Code development session
as a structured build log in Second Brain.

Usage:
    python examples/capture_build_session.py

Features:
    - Interactive session capture
    - Automatic file change detection
    - Git command extraction
    - AI-powered summarization
    - Rich metadata generation

Example:
    $ python examples/capture_build_session.py
    Task: Implement user authentication
    Duration: 90 minutes
    Files changed: auth.py, user.py
    ...
    ✅ Session saved as note #1247
"""

import sys
import os
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.unified_capture_service import (
    get_capture_service,
    UnifiedCaptureRequest,
    CaptureSourceType
)
from database import get_db_connection


def get_git_changed_files() -> List[str]:
    """
    Get list of files changed in the current git repository.

    Returns:
        List of file change descriptions
    """
    try:
        import subprocess

        # Get staged files
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-status'],
            capture_output=True,
            text=True,
            check=True
        )

        files = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue

            status, filename = line.split('\t', 1)
            if status == 'A':
                files.append(f"Created: {filename}")
            elif status == 'M':
                files.append(f"Modified: {filename}")
            elif status == 'D':
                files.append(f"Deleted: {filename}")
            else:
                files.append(f"{status}: {filename}")

        # Also get unstaged changes
        result = subprocess.run(
            ['git', 'diff', '--name-status'],
            capture_output=True,
            text=True,
            check=True
        )

        for line in result.stdout.strip().split('\n'):
            if not line:
                continue

            status, filename = line.split('\t', 1)
            file_desc = f"Modified (unstaged): {filename}"
            if file_desc not in files and f"Modified: {filename}" not in files:
                files.append(file_desc)

        return files

    except Exception as e:
        print(f"Warning: Could not get git changes: {e}")
        return []


def get_recent_git_commands() -> List[str]:
    """
    Extract recent git commands from shell history.

    Returns:
        List of git commands executed
    """
    try:
        import subprocess

        # Try to get from bash history
        history_file = Path.home() / '.bash_history'
        if not history_file.exists():
            history_file = Path.home() / '.zsh_history'

        if history_file.exists():
            commands = []
            with open(history_file, 'r', errors='ignore') as f:
                # Get last 100 lines
                lines = f.readlines()[-100:]

                for line in lines:
                    line = line.strip()
                    # Extract git, pytest, npm, etc commands
                    if any(cmd in line for cmd in ['git', 'pytest', 'npm', 'pip', 'docker']):
                        if line not in commands:
                            commands.append(line)

            return commands[-20:]  # Last 20 relevant commands

        return []

    except Exception as e:
        print(f"Warning: Could not get command history: {e}")
        return []


def interactive_capture():
    """
    Interactive session capture with prompts for user input.
    """
    print("=" * 70)
    print("📝 BUILD LOG SESSION CAPTURE")
    print("=" * 70)
    print()

    # Get task description
    print("What were you working on?")
    task_description = input("Task: ").strip()

    if not task_description:
        print("❌ Task description is required")
        return

    print()

    # Get duration
    print("How long did you work on this? (in minutes)")
    duration_input = input("Duration (minutes): ").strip()
    try:
        duration_minutes = int(duration_input) if duration_input else None
    except ValueError:
        print("⚠️  Invalid duration, skipping...")
        duration_minutes = None

    print()

    # Get files changed
    print("Detecting files changed from git...")
    auto_files = get_git_changed_files()

    if auto_files:
        print(f"Found {len(auto_files)} changed files:")
        for f in auto_files[:5]:
            print(f"  - {f}")
        if len(auto_files) > 5:
            print(f"  ... and {len(auto_files) - 5} more")

        use_auto = input("\nUse detected files? (Y/n): ").strip().lower()
        if use_auto != 'n':
            files_changed = auto_files
        else:
            files_changed = []
    else:
        files_changed = []

    if not files_changed:
        print("\nEnter files changed (one per line, empty line to finish):")
        files_changed = []
        while True:
            file = input("  File: ").strip()
            if not file:
                break
            files_changed.append(file)

    print()

    # Get commands executed
    print("Detecting commands from history...")
    auto_commands = get_recent_git_commands()

    if auto_commands:
        print(f"Found {len(auto_commands)} recent commands:")
        for cmd in auto_commands[:5]:
            print(f"  - {cmd}")
        if len(auto_commands) > 5:
            print(f"  ... and {len(auto_commands) - 5} more")

        use_auto = input("\nUse detected commands? (Y/n): ").strip().lower()
        if use_auto != 'n':
            commands_executed = auto_commands
        else:
            commands_executed = []
    else:
        commands_executed = []

    if not commands_executed:
        print("\nEnter commands executed (one per line, empty line to finish):")
        commands_executed = []
        while True:
            cmd = input("  Command: ").strip()
            if not cmd:
                break
            commands_executed.append(cmd)

    print()

    # Get conversation log
    print("Conversation transcript:")
    print("(Paste your conversation, then press Ctrl+D when done)")
    print("-" * 70)

    try:
        conversation_lines = []
        while True:
            try:
                line = input()
                conversation_lines.append(line)
            except EOFError:
                break
    except KeyboardInterrupt:
        print("\n❌ Cancelled")
        return

    conversation_log = '\n'.join(conversation_lines)

    if not conversation_log.strip():
        print("❌ Conversation log is required")
        return

    print()

    # Get outcomes
    print("Was the task completed successfully? (Y/n)")
    success = input("Success: ").strip().lower() != 'n'

    print("\nDeliverables (one per line, empty line to finish):")
    deliverables = []
    while True:
        item = input("  - ").strip()
        if not item:
            break
        deliverables.append(item)

    print("\nNext steps (one per line, empty line to finish):")
    next_steps = []
    while True:
        item = input("  - ").strip()
        if not item:
            break
        next_steps.append(item)

    outcomes = {
        "success": success,
        "deliverables": deliverables,
        "next_steps": next_steps
    }

    print()
    print("=" * 70)
    print("📊 SESSION SUMMARY")
    print("=" * 70)
    print(f"Task: {task_description}")
    print(f"Duration: {duration_minutes} minutes" if duration_minutes else "Duration: Not specified")
    print(f"Files Changed: {len(files_changed)}")
    print(f"Commands: {len(commands_executed)}")
    print(f"Success: {'✅' if success else '⚠️'}")
    print(f"Deliverables: {len(deliverables)}")
    print(f"Next Steps: {len(next_steps)}")
    print()

    confirm = input("Save this session? (Y/n): ").strip().lower()
    if confirm == 'n':
        print("❌ Cancelled")
        return

    # Save the session
    save_build_session(
        task_description=task_description,
        conversation_log=conversation_log,
        files_changed=files_changed,
        commands_executed=commands_executed,
        duration_minutes=duration_minutes,
        outcomes=outcomes
    )


def save_build_session(
    task_description: str,
    conversation_log: str,
    files_changed: List[str] = None,
    commands_executed: List[str] = None,
    duration_minutes: Optional[int] = None,
    outcomes: Optional[Dict] = None,
    session_id: Optional[str] = None
):
    """
    Save a development session as a build log.

    Args:
        task_description: Brief description of what was worked on
        conversation_log: Full conversation transcript
        files_changed: List of files that were modified
        commands_executed: List of commands that were run
        duration_minutes: How long the session took
        outcomes: Dict with success, deliverables, next_steps
        session_id: Optional session identifier

    Returns:
        Note ID of the saved session
    """
    # Generate session ID if not provided
    if not session_id:
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Initialize service
    try:
        capture_service = get_capture_service(get_db_connection)
    except Exception as e:
        print(f"❌ Error initializing capture service: {e}")
        return None

    # Build metadata
    metadata = {
        "session_id": session_id,
        "task_description": task_description,
        "duration_minutes": duration_minutes,
        "session_started_at": datetime.now().isoformat(),
        "technical_context": {
            "files_changed": files_changed or [],
            "commands_executed": commands_executed or [],
            "file_change_count": len(files_changed or []),
            "command_count": len(commands_executed or [])
        },
        "outcomes": outcomes or {},
        "capture_timestamp": datetime.now().isoformat(),
        "capture_source": "manual_script",
        "session_type": "development"
    }

    # Format conversation as markdown
    formatted_log = f"""# Development Session: {task_description}

**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Session ID**: {session_id}
**Duration**: {duration_minutes} minutes

## Task Description
{task_description}

## Conversation Log

{conversation_log}

## Technical Summary

**Files Changed ({len(files_changed or [])})**:
{chr(10).join(f'- {f}' for f in (files_changed or []))}

**Commands Executed ({len(commands_executed or [])})**:
```bash
{chr(10).join(commands_executed or [])}
```

## Outcomes

**Success**: {'✅ Yes' if outcomes and outcomes.get('success') else '⚠️ Incomplete'}

**Deliverables**:
{chr(10).join(f'- ✓ {d}' for d in (outcomes or {}).get('deliverables', []))}

**Next Steps**:
{chr(10).join(f'- □ {s}' for s in (outcomes or {}).get('next_steps', []))}
"""

    # Create capture request
    # Note: BUILD_LOG content type needs to be added to CaptureContentType enum
    # For now, we'll use TEXT and set type in metadata
    request = UnifiedCaptureRequest(
        content_type="text",  # TODO: Change to "build_log" after enum update
        source_type=CaptureSourceType.API,
        primary_content=formatted_log,
        metadata=metadata,

        # Enable AI enhancements
        auto_tag=True,
        generate_summary=True,
        extract_actions=True,

        # High priority
        processing_priority=2,

        # User context
        user_context={
            "user_id": 1,
            "platform": "manual_script",
            "client_version": "1.0"
        }
    )

    # Capture the session
    try:
        print()
        print("🔄 Saving session...")

        result = capture_service.unified_capture(request)

        print()
        print("=" * 70)
        print("✅ BUILD SESSION SAVED SUCCESSFULLY!")
        print("=" * 70)
        print()
        print(f"📝 Note ID: {result['note_id']}")
        print(f"🆔 Session ID: {session_id}")

        if result.get('ai_summary'):
            print(f"\n🤖 AI Summary:")
            summary = result['ai_summary'][:200]
            if len(result['ai_summary']) > 200:
                summary += "..."
            print(f"   {summary}")

        if result.get('tags'):
            print(f"\n🏷️  Tags: {', '.join(result['tags'])}")

        print(f"\n🔍 Search Later:")
        print(f"   /search-notes {task_description}")
        print(f"   /search-notes session:{session_id}")
        print(f"   /search-notes #build-log")

        print()
        print("=" * 70)

        return result['note_id']

    except Exception as e:
        print(f"\n❌ Error saving build session: {e}")
        import traceback
        traceback.print_exc()
        return None


def example_usage():
    """
    Example of programmatic session capture.
    """
    conversation = """# Development Session: Implement Unified Capture System

User: I need to refactor the capture system to be more modular