# Build Log Viewer

View, search, and analyze development session build logs stored in Second Brain.

## Instructions

Help the user view and analyze their development session history:

1. **Understand intent** - What does the user want to see?
   - Recent sessions?
   - Specific session by ID?
   - Sessions for a particular feature/task?
   - Analytics across all sessions?

2. **Query the database** - Use search or direct queries to find build logs

3. **Present results** - Format in a readable way with key insights

4. **Offer actions** - Suggest related sessions, export options, or analytics

## Usage Examples

### View Recent Sessions

```python
from services.search_adapter import get_search_service

# Search for build log type notes
search_service = get_search_service()
results = search_service.search(
    query="type:build_log",
    user_id=1,
    limit=10,
    filters={"content_type": "build_log"}
)

# Display results
print("📋 Recent Development Sessions\n")
print("=" * 60)

for i, session in enumerate(results, 1):
    metadata = json.loads(session.get('metadata', '{}'))
    session_id = metadata.get('session_id', 'N/A')
    task = metadata.get('task_description', session['title'])
    duration = metadata.get('duration_minutes', 'N/A')
    created = session.get('created_at', 'N/A')

    print(f"\n{i}. {task}")
    print(f"   Session ID: {session_id}")
    print(f"   Date: {created}")
    print(f"   Duration: {duration} minutes")
    print(f"   Note ID: {session['id']}")

    # Show files changed if available
    tech_context = metadata.get('technical_context', {})
    files = tech_context.get('files_changed', [])
    if files:
        print(f"   Files Changed: {len(files)}")

    # Show outcomes
    outcomes = metadata.get('outcomes', {})
    if outcomes.get('success'):
        print(f"   Status: ✅ Success")
    if outcomes.get('deliverables'):
        print(f"   Deliverables: {len(outcomes['deliverables'])}")

print("\n" + "=" * 60)
```

### View Specific Session by ID

```python
import sqlite3
import json
from pathlib import Path

def get_session_by_id(session_id: str):
    """Get detailed session information by session ID"""

    conn = sqlite3.connect('notes.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Query for the session
    cursor.execute("""
        SELECT * FROM notes
        WHERE metadata LIKE ?
        LIMIT 1
    """, (f'%{session_id}%',))

    row = cursor.fetchone()
    conn.close()

    if not row:
        print(f"❌ Session not found: {session_id}")
        return None

    # Parse the session
    session = dict(row)
    metadata = json.loads(session.get('metadata', '{}'))

    # Display detailed view
    print("\n" + "=" * 70)
    print(f"📝 BUILD LOG: {session['title']}")
    print("=" * 70)

    # Session Info
    print(f"\n🆔 Session ID: {metadata.get('session_id', 'N/A')}")
    print(f"📅 Date: {session['created_at']}")
    print(f"⏱️  Duration: {metadata.get('duration_minutes', 'N/A')} minutes")
    print(f"💬 Messages: {metadata.get('message_count', 'N/A')}")

    # Task Description
    print(f"\n📋 Task:")
    print(f"   {metadata.get('task_description', 'N/A')}")

    # AI Summary
    if session.get('summary'):
        print(f"\n🤖 AI Summary:")
        print(f"   {session['summary']}")

    # Tags
    if session.get('tags'):
        tags = session['tags'].split(',')
        print(f"\n🏷️  Tags: {', '.join(tags)}")

    # Technical Context
    tech_context = metadata.get('technical_context', {})
    if tech_context:
        print(f"\n🔧 Technical Context:")

        files = tech_context.get('files_changed', [])
        if files:
            print(f"   Files Changed ({len(files)}):")
            for file in files[:10]:  # Show first 10
                print(f"      • {file}")
            if len(files) > 10:
                print(f"      ... and {len(files) - 10} more")

        commands = tech_context.get('commands_executed', [])
        if commands:
            print(f"\n   Commands Executed ({len(commands)}):")
            for cmd in commands[:5]:  # Show first 5
                print(f"      $ {cmd}")
            if len(commands) > 5:
                print(f"      ... and {len(commands) - 5} more")

    # Outcomes
    outcomes = metadata.get('outcomes', {})
    if outcomes:
        print(f"\n✨ Outcomes:")

        if outcomes.get('success') is not None:
            status = "✅ Success" if outcomes['success'] else "⚠️  Incomplete"
            print(f"   Status: {status}")

        deliverables = outcomes.get('deliverables', [])
        if deliverables:
            print(f"\n   Deliverables:")
            for item in deliverables:
                print(f"      ✓ {item}")

        next_steps = outcomes.get('next_steps', [])
        if next_steps:
            print(f"\n   Next Steps:")
            for item in next_steps:
                print(f"      □ {item}")

        learnings = outcomes.get('learnings', [])
        if learnings:
            print(f"\n   Key Learnings:")
            for item in learnings:
                print(f"      💡 {item}")

    # Full Content (abbreviated)
    print(f"\n📄 Full Conversation:")
    print(f"   {len(session['body'])} characters")
    print(f"   Preview: {session['body'][:200]}...")

    print("\n" + "=" * 70)

    return session

# Example usage
session = get_session_by_id("session_20250113_103045")
```

### Search Sessions by Topic/Technology

```python
def search_sessions(query: str, limit: int = 10):
    """Search build log sessions by keyword"""

    from services.search_adapter import get_search_service

    search_service = get_search_service()

    # Combine query with type filter
    full_query = f"{query} build_log"

    results = search_service.search(
        query=full_query,
        user_id=1,
        limit=limit
    )

    print(f"\n🔍 Search Results for: '{query}'")
    print("=" * 60)

    if not results:
        print("No sessions found.")
        return []

    for i, session in enumerate(results, 1):
        print(f"\n{i}. {session['title']}")
        print(f"   Date: {session.get('created_at', 'N/A')}")
        print(f"   Note ID: {session['id']}")

        # Show preview of content
        preview = session.get('body', '')[:150]
        print(f"   Preview: {preview}...")

    print("\n" + "=" * 60)
    print(f"\nFound {len(results)} session(s)")

    return results

# Example searches
search_sessions("fastapi")      # Find sessions about FastAPI
search_sessions("bug fix")      # Find bug fix sessions
search_sessions("database")     # Find database-related work
search_sessions("testing")      # Find sessions with testing
```

### Session Analytics

```python
import sqlite3
import json
from collections import Counter
from datetime import datetime, timedelta

def get_session_analytics():
    """Get analytics across all build log sessions"""

    conn = sqlite3.connect('notes.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all build log sessions
    cursor.execute("""
        SELECT * FROM notes
        WHERE metadata LIKE '%build_log%'
        OR metadata LIKE '%session_id%'
        ORDER BY created_at DESC
    """)

    sessions = [dict(row) for row in cursor.fetchall()]
    conn.close()

    if not sessions:
        print("No build log sessions found.")
        return

    # Calculate analytics
    total_sessions = len(sessions)
    total_duration = 0
    total_files = 0
    total_commands = 0
    all_tags = []
    technologies = Counter()
    success_count = 0

    for session in sessions:
        metadata = json.loads(session.get('metadata', '{}'))

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

    # Display analytics
    print("\n" + "=" * 70)
    print("📊 BUILD LOG ANALYTICS")
    print("=" * 70)

    print(f"\n📈 Overview:")
    print(f"   Total Sessions: {total_sessions}")
    print(f"   Success Rate: {(success_count/total_sessions*100):.1f}%")
    print(f"   Total Duration: {total_duration} minutes ({total_duration/60:.1f} hours)")
    print(f"   Avg Duration: {total_duration/total_sessions:.1f} minutes/session")

    print(f"\n💻 Technical Activity:")
    print(f"   Files Changed: {total_files}")
    print(f"   Commands Executed: {total_commands}")
    print(f"   Avg Files/Session: {total_files/total_sessions:.1f}")

    # Top tags
    tag_counts = Counter(all_tags)
    top_tags = tag_counts.most_common(10)

    if top_tags:
        print(f"\n🏷️  Top Tags:")
        for tag, count in top_tags:
            bar = "█" * (count * 2)
            print(f"   {tag:20} {bar} {count}")

    # Recent activity
    now = datetime.now()
    last_7_days = []
    last_30_days = []

    for session in sessions:
        created = datetime.fromisoformat(session['created_at'])
        days_ago = (now - created).days

        if days_ago <= 7:
            last_7_days.append(session)
        if days_ago <= 30:
            last_30_days.append(session)

    print(f"\n📅 Recent Activity:")
    print(f"   Last 7 days: {len(last_7_days)} sessions")
    print(f"   Last 30 days: {len(last_30_days)} sessions")

    # Most productive days
    session_dates = [datetime.fromisoformat(s['created_at']).date()
                     for s in sessions]
    date_counts = Counter(session_dates)
    top_dates = date_counts.most_common(5)

    if top_dates:
        print(f"\n🗓️  Most Productive Days:")
        for date, count in top_dates:
            print(f"   {date}: {count} sessions")

    print("\n" + "=" * 70)

# Run analytics
get_session_analytics()
```

### Export Sessions

```python
def export_sessions_to_markdown(output_file: str = "build_log_export.md"):
    """Export all build log sessions to a single markdown file"""

    import sqlite3
    import json
    from datetime import datetime

    conn = sqlite3.connect('notes.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM notes
        WHERE metadata LIKE '%build_log%'
        ORDER BY created_at DESC
    """)

    sessions = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # Generate markdown
    md_content = f"""# Second Brain - Development Build Log
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total Sessions: {len(sessions)}

---

"""

    for i, session in enumerate(sessions, 1):
        metadata = json.loads(session.get('metadata', '{}'))
        session_id = metadata.get('session_id', 'N/A')
        task = metadata.get('task_description', session['title'])
        duration = metadata.get('duration_minutes', 'N/A')

        md_content += f"""
## Session {i}: {task}

**Session ID**: `{session_id}`
**Date**: {session['created_at']}
**Duration**: {duration} minutes
**Note ID**: {session['id']}

### Summary
{session.get('summary', 'No summary available')}

### Tags
{session.get('tags', 'No tags')}

"""

        # Technical context
        tech_context = metadata.get('technical_context', {})
        files = tech_context.get('files_changed', [])
        if files:
            md_content += f"### Files Changed ({len(files)})\n"
            for file in files[:20]:
                md_content += f"- {file}\n"

        # Outcomes
        outcomes = metadata.get('outcomes', {})
        deliverables = outcomes.get('deliverables', [])
        if deliverables:
            md_content += f"\n### Deliverables\n"
            for item in deliverables:
                md_content += f"- ✅ {item}\n"

        md_content += "\n---\n"

    # Write to file
    with open(output_file, 'w') as f:
        f.write(md_content)

    print(f"✅ Exported {len(sessions)} sessions to {output_file}")
    return output_file

# Export
export_file = export_sessions_to_markdown()
```

## Display Formats

### Compact List View

```
📋 Recent Development Sessions
============================================================

1. Implement unified capture system
   Session: session_20250113_103045 | Date: 2025-01-13 10:30
   Duration: 120 min | Files: 4 | Status: ✅ Success

2. Fix search indexing bug
   Session: session_20250113_083015 | Date: 2025-01-13 08:30
   Duration: 45 min | Files: 2 | Status: ✅ Success

3. Add mobile PWA support
   Session: session_20250112_153020 | Date: 2025-01-12 15:30
   Duration: 180 min | Files: 12 | Status: ⚠️  Incomplete

Total: 3 sessions | Avg Duration: 115 min
============================================================
```

### Detailed Single View

```
======================================================================
📝 BUILD LOG: Implement Unified Capture System
======================================================================

🆔 Session ID: session_20250113_103045
📅 Date: 2025-01-13 10:30:45
⏱️  Duration: 120 minutes
💬 Messages: 47

📋 Task:
   Refactor the capture system to be more modular and support
   multiple content types through a unified API

🤖 AI Summary:
   Successfully implemented a comprehensive unified capture system
   that consolidates all content ingestion through a single service.
   The new architecture supports 12 content types and 8 source types
   with intelligent routing and AI enhancement.

🏷️  Tags: python, fastapi, refactoring, api-design, architecture

🔧 Technical Context:
   Files Changed (4):
      • Created: services/unified_capture_service.py
      • Created: services/unified_capture_router.py
      • Modified: app.py
      • Created: tests/test_unified_capture_service.py

   Commands Executed (4):
      $ pytest tests/test_unified_capture_service.py -v
      $ git add .
      $ git commit -m 'feat: Add unified capture system'
      $ git push origin feature/unified-capture

✨ Outcomes:
   Status: ✅ Success

   Deliverables:
      ✓ Unified capture service with 12 content types
      ✓ Comprehensive test suite (16 tests passing)
      ✓ API documentation
      ✓ Migration guide for existing code

   Next Steps:
      □ Add batch processing support
      □ Implement webhook transformers
      □ Create dashboard for capture analytics

   Key Learnings:
      💡 Service-oriented architecture makes testing easier
      💡 Type hints significantly improve code maintainability
      💡 Comprehensive metadata enables powerful analytics

📄 Full Conversation:
   4,523 characters
   Preview: # Development Session: Implement Unified Capture System

User: I need to refactor the capture system...

======================================================================
```

## Tips

**Quick Commands**:
```bash
# View last 10 sessions
/build-log recent

# View specific session
/build-log session_20250113_103045

# Search sessions
/build-log search "fastapi"

# Show analytics
/build-log analytics

# Export all sessions
/build-log export
```

**Useful Queries**:
- Recent work: `/build-log recent 20`
- By technology: `/build-log search "python"`
- Successful builds: `/build-log search "success"`
- Bug fixes: `/build-log search "bug fix"`
- Features: `/build-log search "feature"`
