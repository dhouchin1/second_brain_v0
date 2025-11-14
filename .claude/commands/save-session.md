# Save Development Session

Capture the current Claude Code conversation as a structured build log in Second Brain.

## Instructions

You are capturing a development session to create a permanent record of work completed. Follow these steps:

1. **Gather session context** - Ask user for task description if not obvious from conversation
2. **Extract conversation history** - Collect all user prompts and assistant responses
3. **Analyze the session** - Identify files changed, commands run, outcomes achieved
4. **Create structured log** - Format as comprehensive development log
5. **Store in Second Brain** - Save via unified capture API with rich metadata
6. **Generate AI insights** - Let Ollama create summary, extract tags, identify action items
7. **Confirm success** - Show note ID and provide examples of how to search for it later

## Session Metadata to Capture

### Core Information
- **Session ID**: Unique identifier (e.g., `session_20250113_103045`)
- **Task Description**: What was the user trying to accomplish?
- **Duration**: Session length in minutes (calculate from timestamps)
- **Message Count**: Total user/assistant exchanges
- **Start/End Times**: When did the session begin and end?

### Technical Context
- **Files Changed**: List of created, edited, or deleted files
- **Lines of Code**: Approximate lines added/removed (if applicable)
- **Commands Executed**: Bash commands, git operations, tests run
- **Technologies Used**: Languages, frameworks, tools mentioned
- **Errors Encountered**: Any errors or issues that came up
- **Solutions Found**: How were problems resolved?

### Outcomes & Results
- **Success Status**: Was the task completed successfully?
- **Deliverables**: What was actually built, fixed, or implemented?
- **Tests**: Were tests written? Did they pass?
- **Documentation**: Was documentation created or updated?
- **Next Steps**: What remains to be done?
- **Learnings**: Important insights, decisions, or patterns discovered

## Conversation Format

Structure the conversation transcript like this:

```markdown
# Development Session: [Task Title]

**Date**: 2025-01-13
**Duration**: 120 minutes
**Session ID**: session_20250113_103045

## Task Description
[Brief description of what was being worked on]

## Conversation Log

### Message 1 (User, 10:30 AM)
[User's message...]

### Message 2 (Assistant, 10:31 AM)
[Assistant's response...]

### Message 3 (User, 10:35 AM)
[User's message...]

[Continue for all messages...]

## Technical Summary

**Files Changed**:
- Created: `services/build_log_router.py`
- Modified: `app.py`, `services/unified_capture_service.py`
- Deleted: `old_capture_service.py`

**Commands Executed**:
` ``bash
pytest tests/test_unified_capture.py -v
git add .
git commit -m "feat: Add build log capture"
git push origin feature/build-logs
` ``

**Tests**: ✅ All 16 tests passing

## Outcomes

**Deliverables**:
1. ✅ Implemented unified capture for build logs
2. ✅ Created `/save-session` slash command
3. ✅ Updated MCP server with build log tools
4. ✅ Wrote comprehensive documentation

**Next Steps**:
- [ ] Add export functionality for build logs
- [ ] Create dashboard visualization
- [ ] Integrate with CI/CD pipeline

**Key Learnings**:
- Unified capture service handles all content types elegantly
- AI summarization works exceptionally well for code conversations
- Rich metadata enables powerful search and analytics
```

## Python Implementation

```python
from services.unified_capture_service import (
    get_capture_service,
    UnifiedCaptureRequest,
    CaptureContentType,
    CaptureSourceType
)
from database import get_db_connection
import json
from datetime import datetime

def save_build_session(
    task_description: str,
    conversation_log: str,
    files_changed: list,
    commands_executed: list,
    outcomes: dict,
    duration_minutes: int = None,
    session_id: str = None
):
    """
    Save a Claude Code development session as a structured build log.

    Args:
        task_description: Brief description of the task
        conversation_log: Full conversation transcript (formatted markdown)
        files_changed: List of files created/modified/deleted
        commands_executed: List of bash commands run
        outcomes: Dict with 'success', 'deliverables', 'next_steps'
        duration_minutes: Session duration in minutes
        session_id: Optional session identifier

    Returns:
        dict: Response with note_id and metadata
    """

    # Generate session ID if not provided
    if not session_id:
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Initialize capture service
    capture_service = get_capture_service(get_db_connection)

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
        "capture_source": "claude_code_web",
        "session_type": "development"
    }

    # Create capture request
    request = UnifiedCaptureRequest(
        content_type="build_log",  # Will need to add to CaptureContentType enum
        source_type=CaptureSourceType.API,
        primary_content=conversation_log,
        metadata=metadata,

        # Enable all AI enhancements
        auto_tag=True,               # Extract tags (python, fastapi, etc.)
        generate_summary=True,        # AI-generated summary
        extract_actions=True,         # Identify TODO items

        # High priority processing
        processing_priority=2,

        # User context
        user_context={
            "user_id": 1,  # Or get from auth
            "platform": "claude_code_web",
            "client_version": "1.0"
        }
    )

    # Capture the session
    try:
        result = capture_service.unified_capture(request)

        print(f"✅ Build session saved successfully!")
        print(f"   Note ID: {result['note_id']}")
        print(f"   Session ID: {session_id}")
        print(f"   AI Summary: {result.get('ai_summary', 'N/A')[:100]}...")
        print(f"   Tags: {', '.join(result.get('tags', []))}")
        print(f"\n🔍 Search for it later with:")
        print(f"   /search-notes {task_description}")
        print(f"   /search-notes session:{session_id}")

        return result

    except Exception as e:
        print(f"❌ Error saving build session: {str(e)}")
        raise

# Example usage
if __name__ == "__main__":
    # Sample conversation
    conversation = """
# Development Session: Add Build Log Capture

**Date**: 2025-01-13
**Duration**: 120 minutes

## Conversation Log

### User (10:30 AM)
I need to add a feature to capture our Claude Code sessions as build logs

### Assistant (10:31 AM)
Great idea! I'll help you implement a build log capture system...

[Full conversation continues...]
"""

    # Save the session
    result = save_build_session(
        task_description="Implement build log capture system",
        conversation_log=conversation,
        files_changed=[
            "Created: .claude/commands/save-session.md",
            "Created: .claude/commands/build-log.md",
            "Modified: mcp_server.py",
            "Created: services/build_log_router.py"
        ],
        commands_executed=[
            "pytest tests/ -v",
            "git add .",
            "git commit -m 'feat: Add build log capture'",
            "git push origin feature/build-logs"
        ],
        outcomes={
            "success": True,
            "deliverables": [
                "Build log capture slash command",
                "MCP server integration",
                "Comprehensive documentation"
            ],
            "next_steps": [
                "Add dashboard visualization",
                "Create export functionality"
            ]
        },
        duration_minutes=120
    )
```

## Quick Capture (Minimal Version)

For a quick session save without all the metadata:

```python
from services.unified_capture_service import get_capture_service, UnifiedCaptureRequest, CaptureSourceType
from database import get_db_connection

def quick_save_session(task: str, conversation: str):
    """Quick save of development session"""
    service = get_capture_service(get_db_connection)

    request = UnifiedCaptureRequest(
        content_type="build_log",
        source_type=CaptureSourceType.API,
        primary_content=f"# {task}\n\n{conversation}",
        metadata={"task": task},
        auto_tag=True,
        generate_summary=True
    )

    result = service.unified_capture(request)
    print(f"✅ Saved as note {result['note_id']}")
    return result
```

## Response Format

After saving, display:

```
✅ Development Session Saved Successfully!

📝 Build Log Details:
   Note ID: 1247
   Session ID: session_20250113_103045
   Task: Implement build log capture system
   Duration: 120 minutes
   Files Changed: 4
   Commands Run: 4

🤖 AI Analysis:
   Summary: Successfully implemented a comprehensive build log capture
            system that integrates with the unified capture service...

   Tags: #python #fastapi #build-logs #claude-code #integration

   Action Items:
   • Add dashboard visualization for build logs
   • Create export functionality for sessions
   • Write integration tests

🔍 Search Later:
   • Search by task: "build log capture"
   • Search by session: "session:session_20250113_103045"
   • Search by tag: "#build-logs"

💾 Exported to Obsidian:
   vault/20250113_103045_Implement_build_log_capture_id1247.md
```

## Tips

**When to Save Sessions**:
- ✅ At the end of a major feature implementation
- ✅ After solving a complex bug
- ✅ When you want to document a learning experience
- ✅ After pair programming or code review sessions
- ✅ Before switching to a new task

**What to Include**:
- ✅ Full conversation transcript (keep context)
- ✅ All files that were touched
- ✅ Commands executed (especially git, tests, deploy)
- ✅ Screenshots or error messages (if relevant)
- ✅ Links to related PRs, issues, or docs

**Search Later**:
```
Find sessions by keyword:     /search-notes "api integration"
Find by technology:           /search-notes #fastapi
Find recent sessions:         /search-notes type:build_log
Find by date:                 /search-notes "2025-01-13"
Find by outcome:              /search-notes "tests passing"
```
