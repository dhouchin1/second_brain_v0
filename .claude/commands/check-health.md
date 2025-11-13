# System Health Check

Run a comprehensive health check on all Second Brain services and generate a detailed status report.

## Instructions

Perform a complete health assessment:

1. **Database Health** - Check connectivity, migrations, and integrity
2. **Service Status** - Verify all services are properly initialized
3. **External Dependencies** - Test Ollama, Whisper, and other integrations
4. **Resource Usage** - Check disk space, memory, and performance
5. **API Endpoints** - Test critical endpoints
6. **Generate Report** - Create detailed health report with recommendations

## Health Check Components

### 1. Database Health

```python
import sqlite3
from pathlib import Path

def check_database_health():
    db_path = Path("notes.db")

    # Check file exists
    if not db_path.exists():
        return {"status": "error", "message": "Database file not found"}

    # Check size
    size_mb = db_path.stat().st_size / (1024 * 1024)

    # Check connectivity
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        # Check note count
        cursor.execute("SELECT COUNT(*) FROM notes")
        note_count = cursor.fetchone()[0]

        # Check migrations
        cursor.execute("SELECT COUNT(*) FROM migrations")
        migration_count = cursor.fetchone()[0]

        # Check integrity
        cursor.execute("PRAGMA integrity_check")
        integrity = cursor.fetchone()[0]

        conn.close()

        return {
            "status": "healthy",
            "size_mb": round(size_mb, 2),
            "tables": len(tables),
            "note_count": note_count,
            "migrations": migration_count,
            "integrity": integrity
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

### 2. Service Health

```python
def check_services():
    services = {}

    # Test unified capture service
    try:
        from services.unified_capture_service import get_capture_service
        from database import get_db_connection
        service = get_capture_service(get_db_connection)
        services["unified_capture"] = "✅ Available"
    except Exception as e:
        services["unified_capture"] = f"❌ Error: {str(e)}"

    # Test search service
    try:
        from services.search_adapter import get_search_service
        search = get_search_service()
        services["search"] = "✅ Available"
    except Exception as e:
        services["search"] = f"❌ Error: {str(e)}"

    # Test memory service
    try:
        from services.memory_service import get_memory_service
        from database import get_db_connection
        memory = get_memory_service(get_db_connection)
        services["memory"] = "✅ Available"
    except Exception as e:
        services["memory"] = f"❌ Error: {str(e)}"

    # Test Obsidian sync
    try:
        from obsidian_sync import ObsidianSync
        from config import VAULT_PATH
        sync = ObsidianSync(VAULT_PATH)
        services["obsidian_sync"] = "✅ Available"
    except Exception as e:
        services["obsidian_sync"] = f"❌ Error: {str(e)}"

    return services
```

### 3. External Service Health

```python
import requests
from pathlib import Path

def check_external_services():
    external = {}

    # Check Ollama
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            models = r.json().get("models", [])
            external["ollama"] = {
                "status": "✅ Running",
                "models": [m["name"] for m in models]
            }
        else:
            external["ollama"] = {"status": "⚠️ Responding but error"}
    except:
        external["ollama"] = {"status": "❌ Not running"}

    # Check Whisper
    whisper_path = Path("build/bin/whisper-cli")
    if whisper_path.exists():
        external["whisper"] = {"status": "✅ Binary found"}
    else:
        external["whisper"] = {"status": "❌ Binary not found"}

    # Check Whisper models
    model_dir = Path("models")
    if model_dir.exists():
        models = list(model_dir.glob("ggml-*.bin"))
        external["whisper_models"] = {
            "status": "✅ Models found" if models else "⚠️ No models",
            "count": len(models)
        }
    else:
        external["whisper_models"] = {"status": "❌ Models directory not found"}

    return external
```

### 4. Resource Usage

```python
import shutil
import psutil
import os

def check_resources():
    # Disk space
    total, used, free = shutil.disk_usage(".")
    disk_free_gb = free / (1024**3)
    disk_usage_pct = (used / total) * 100

    # Memory usage (if available)
    try:
        memory = psutil.virtual_memory()
        memory_info = {
            "total_gb": round(memory.total / (1024**3), 2),
            "available_gb": round(memory.available / (1024**3), 2),
            "percent_used": memory.percent
        }
    except:
        memory_info = {"status": "unavailable"}

    # Process info
    try:
        process = psutil.Process(os.getpid())
        process_info = {
            "cpu_percent": process.cpu_percent(),
            "memory_mb": round(process.memory_info().rss / (1024**2), 2)
        }
    except:
        process_info = {"status": "unavailable"}

    return {
        "disk": {
            "free_gb": round(disk_free_gb, 2),
            "usage_percent": round(disk_usage_pct, 2),
            "status": "✅ OK" if disk_free_gb > 5 else "⚠️ Low space"
        },
        "memory": memory_info,
        "process": process_info
    }
```

### 5. API Endpoint Tests

```python
from fastapi.testclient import TestClient

def test_critical_endpoints(app):
    client = TestClient(app)
    endpoints = {}

    # Test health endpoint
    try:
        r = client.get("/health")
        endpoints["/health"] = "✅ OK" if r.status_code == 200 else f"❌ {r.status_code}"
    except Exception as e:
        endpoints["/health"] = f"❌ {str(e)}"

    # Test API endpoints (requires auth)
    test_endpoints = [
        "/api/notes",
        "/api/search",
        "/api/stats",
    ]

    for endpoint in test_endpoints:
        try:
            r = client.get(endpoint)
            # 401 is OK - means auth is working
            # 200 is OK - means endpoint is accessible
            if r.status_code in [200, 401]:
                endpoints[endpoint] = "✅ Responding"
            else:
                endpoints[endpoint] = f"⚠️ Status {r.status_code}"
        except Exception as e:
            endpoints[endpoint] = f"❌ {str(e)}"

    return endpoints
```

## Complete Health Check Script

```python
#!/usr/bin/env python3
"""
Complete health check for Second Brain
Run this to get a comprehensive status report
"""

def run_health_check():
    print("=" * 60)
    print("SECOND BRAIN HEALTH CHECK")
    print("=" * 60)
    print()

    # Database
    print("📊 DATABASE")
    print("-" * 60)
    db_health = check_database_health()
    if db_health["status"] == "healthy":
        print(f"✅ Status: Healthy")
        print(f"   Size: {db_health['size_mb']} MB")
        print(f"   Notes: {db_health['note_count']}")
        print(f"   Tables: {db_health['tables']}")
        print(f"   Migrations: {db_health['migrations']}")
        print(f"   Integrity: {db_health['integrity']}")
    else:
        print(f"❌ Status: {db_health['message']}")
    print()

    # Services
    print("🔧 SERVICES")
    print("-" * 60)
    services = check_services()
    for service, status in services.items():
        print(f"   {service}: {status}")
    print()

    # External
    print("🌐 EXTERNAL SERVICES")
    print("-" * 60)
    external = check_external_services()
    for service, info in external.items():
        if isinstance(info, dict):
            print(f"   {service}: {info['status']}")
            if "models" in info:
                for model in info['models']:
                    print(f"      - {model}")
        else:
            print(f"   {service}: {info}")
    print()

    # Resources
    print("💾 RESOURCES")
    print("-" * 60)
    resources = check_resources()
    print(f"   Disk: {resources['disk']['free_gb']} GB free ({resources['disk']['usage_percent']}% used) - {resources['disk']['status']}")
    if "total_gb" in resources['memory']:
        print(f"   Memory: {resources['memory']['available_gb']} GB available / {resources['memory']['total_gb']} GB total")
    if "cpu_percent" in resources['process']:
        print(f"   Process: {resources['process']['cpu_percent']}% CPU, {resources['process']['memory_mb']} MB RAM")
    print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    issues = []
    if db_health["status"] != "healthy":
        issues.append("Database issues detected")
    if any("❌" in s for s in services.values()):
        issues.append("Some services unavailable")
    if external["ollama"]["status"] != "✅ Running":
        issues.append("Ollama not running")
    if resources["disk"]["free_gb"] < 5:
        issues.append("Low disk space")

    if not issues:
        print("✅ All systems operational")
        return True
    else:
        print("⚠️  Issues found:")
        for issue in issues:
            print(f"   - {issue}")
        return False

if __name__ == "__main__":
    import sys
    success = run_health_check()
    sys.exit(0 if success else 1)
```

## Expected Output

```
============================================================
SECOND BRAIN HEALTH CHECK
============================================================

📊 DATABASE
------------------------------------------------------------
✅ Status: Healthy
   Size: 125.34 MB
   Notes: 1,247
   Tables: 12
   Migrations: 15
   Integrity: ok

🔧 SERVICES
------------------------------------------------------------
   unified_capture: ✅ Available
   search: ✅ Available
   memory: ✅ Available
   obsidian_sync: ✅ Available

🌐 EXTERNAL SERVICES
------------------------------------------------------------
   ollama: ✅ Running
      - llama3.2
      - llama3.2:1b
   whisper: ✅ Binary found
   whisper_models: ✅ Models found (3 models)

💾 RESOURCES
------------------------------------------------------------
   Disk: 45.67 GB free (72.3% used) - ✅ OK
   Memory: 8.2 GB available / 16.0 GB total
   Process: 2.5% CPU, 245.67 MB RAM

============================================================
SUMMARY
============================================================
✅ All systems operational
```

## Recommendations

Based on health check results, provide recommendations:

- **Low disk space** → Clean up old audio files, run database VACUUM
- **High memory usage** → Restart services, check for memory leaks
- **Service failures** → Check logs, verify dependencies
- **Ollama not running** → Start Ollama service, pull required models
- **Database issues** → Run integrity check, consider backup
