# Enhanced Health Monitoring and System Diagnostics

## Overview

The Second Brain application now includes a comprehensive health monitoring and diagnostic system that provides detailed insights into system health, performance metrics, and automatic healing capabilities.

## Endpoints

### GET /health

Public endpoint providing real-time system health status.

**Response Structure:**
```json
{
    "status": "healthy|degraded|critical|error",
    "timestamp": "2025-09-01T12:00:00.000Z",
    "services": {
        "ollama": {
            "healthy": true,
            "response_time_ms": 45.2,
            "models": ["llama3.2"]
        },
        "whisper": {
            "healthy": true,
            "path_exists": true,
            "executable": true
        },
        "email": {
            "healthy": true,
            "configured": true,
            "service_type": "resend"
        }
    },
    "database": {
        "healthy": true,
        "connection_test": true,
        "tables_present": true,
        "fts_index_status": "functional",
        "integrity_check": "ok",
        "statistics": {
            "users_count": 5,
            "notes_count": 1250,
            "reminders_count": 8
        }
    },
    "resources": {
        "disk_space": {
            "total_gb": 512.0,
            "free_gb": 128.5,
            "used_percent": 74.9
        },
        "memory": {
            "total_gb": 16.0,
            "available_gb": 8.2,
            "used_percent": 48.8
        },
        "directories": {
            "vault": {"exists": true, "writable": true, "files_count": 50},
            "audio": {"exists": true, "writable": true, "files_count": 25},
            "uploads": {"exists": true, "writable": true, "files_count": 10}
        }
    },
    "processing_queue": {
        "healthy": true,
        "queued_tasks": 3,
        "processing_tasks": 1,
        "stalled_tasks": 0,
        "completed_today": 15,
        "average_processing_time_minutes": 2.5,
        "batch_mode": false
    },
    "issues": []
}
```

**HTTP Status Codes:**
- `200`: System healthy or degraded but operational
- `503`: System critical or error state

### GET /api/diagnostics

Protected endpoint providing detailed system analytics (requires authentication).

**Response Structure:**
```json
{
    "timestamp": "2025-09-01T12:00:00.000Z",
    "database_analytics": {
        "table_statistics": {
            "notes": {"row_count": 1250, "column_count": 15},
            "users": {"row_count": 5, "column_count": 4}
        },
        "index_usage": {
            "idx_notes_user_id": {"table": "notes"},
            "idx_notes_fts": {"table": "notes_fts"}
        },
        "fragmentation": {
            "page_size": 4096,
            "total_pages": 2048,
            "free_pages": 25,
            "fragmentation_percent": 1.2,
            "database_size_mb": 8.2
        }
    },
    "search_performance": {
        "fts_index_health": {
            "indexed_documents": 1250,
            "status": "functional"
        },
        "search_patterns": {
            "top_queries": [
                {"query": "project meeting", "frequency": 15},
                {"query": "budget analysis", "frequency": 8}
            ]
        },
        "performance_metrics": {
            "fts_search_time_ms": 12.5,
            "avg_results_per_search": 8.2
        }
    },
    "processing_analytics": {
        "processing_stats": {
            "queued": {"count": 3, "avg_processing_time_minutes": null},
            "processing": {"count": 1, "avg_processing_time_minutes": 2.1},
            "completed": {"count": 245, "avg_processing_time_minutes": 2.8}
        },
        "bottlenecks": []
    },
    "configuration_validation": {
        "ollama_config": {
            "api_url": "http://localhost:11434/api/generate",
            "model": "llama3.2",
            "configured": true
        },
        "whisper_config": {
            "binary_exists": true,
            "model_exists": true,
            "transcriber": "whisper"
        },
        "email_config": {
            "enabled": true,
            "service": "resend",
            "configured": true
        },
        "warnings": []
    },
    "optimization_recommendations": [
        {
            "category": "database",
            "priority": "medium",
            "title": "Database fragmentation detected",
            "description": "Database is 12.5% fragmented",
            "action": "Run VACUUM command to defragment database",
            "auto_fixable": true
        }
    ]
}
```

### POST /api/diagnostics/auto-heal

Protected endpoint that performs automatic system healing and optimization (requires authentication).

**Response Structure:**
```json
{
    "timestamp": "2025-09-01T12:00:00.000Z",
    "actions_performed": [
        "Database defragmented using VACUUM",
        "Database statistics optimized",
        "Reset 2 stalled processing tasks",
        "FTS index verified as functional"
    ],
    "errors": [],
    "recommendations": [
        "Consider increasing processing concurrency for better performance"
    ]
}
```

## Health Status Levels

1. **healthy**: All systems operational, no issues detected
2. **degraded**: Some non-critical issues detected, system still operational
3. **critical**: Critical issues detected (disk space <5%, memory >95%, many stalled tasks)
4. **error**: Health check itself failed

## Monitoring Features

### Database Health
- Connection testing
- Table presence verification
- FTS5 search index status
- Database integrity checks
- Fragmentation analysis
- Performance statistics

### Service Availability
- **Ollama**: API connectivity, response time, available models
- **Whisper.cpp**: Binary availability, model file presence
- **Email Service**: Configuration validation (when enabled)

### Resource Monitoring
- Disk space usage and warnings
- Memory usage monitoring
- Directory structure validation
- File system access verification

### Processing Queue Health
- Queue status and task counts
- Stalled task detection (>2 hours processing)
- Processing performance metrics
- Batch mode status

## Auto-Healing Capabilities

### Database Optimization
- Automatic VACUUM when fragmentation >10%
- Database statistics optimization
- Integrity issue detection

### Queue Management
- Stalled task reset (>4 hours processing)
- Queue cleanup and optimization

### Search Index Maintenance
- FTS index functionality verification
- Automatic index rebuilding when needed

### Directory Structure
- Missing directory creation
- Permission verification

## Configuration

The health monitoring system uses existing configuration from `config.py`. No additional configuration is required.

### Required Dependencies

Add to requirements.txt:
```
psutil>=5.9.0
```

## Usage Examples

### Basic Health Check
```bash
curl http://localhost:8082/health
```

### Detailed Diagnostics (with authentication)
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8082/api/diagnostics
```

### Trigger Auto-Healing (with authentication)
```bash
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8082/api/diagnostics/auto-heal
```

### Monitoring Integration

The health endpoint can be integrated with monitoring systems:

```bash
# Simple status check
if [ $(curl -s -o /dev/null -w "%{http_code}" http://localhost:8082/health) -eq 200 ]; then
    echo "System healthy"
else
    echo "System issues detected"
fi
```

## Testing

Use the provided test script to validate the monitoring system:

```bash
python test_health_monitoring.py
```

## Performance Impact

The health monitoring system is designed to be lightweight:
- Health checks are cached where appropriate
- Database queries are optimized
- Resource checks use efficient system calls
- Minimal impact on application performance

## Troubleshooting

### Common Issues

1. **psutil import error**: Install with `pip install psutil>=5.9.0`
2. **Database connection errors**: Check database file permissions and disk space
3. **Service unavailability**: Verify Ollama is running and Whisper binaries are present
4. **Authentication errors**: Ensure proper JWT token for protected endpoints

### Interpreting Results

- **Red flags**: status="critical", high stalled_tasks, disk_space_critical=true
- **Yellow flags**: status="degraded", fragmentation >10%, high memory usage
- **Green flags**: status="healthy", all services healthy=true, no issues array items

## Integration with Discord Bot

The existing Discord bot `/status` and `/stats` commands can be enhanced to use the new health monitoring data for more comprehensive reporting.