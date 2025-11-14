# Test Service

Run comprehensive tests for a specific Second Brain service.

## Instructions

You are helping test a specific service in the Second Brain codebase. Follow these steps:

1. **Identify the service** - If not provided, ask which service to test
2. **Locate test file** - Find `tests/test_[service_name].py`
3. **Run pytest** - Execute with verbose output and coverage
4. **Analyze results** - Show passed/failed tests and coverage percentage
5. **Suggest fixes** - If tests fail, analyze errors and suggest solutions

## Available Services to Test

- `unified_capture_service` - Core note capture orchestration
- `unified_capture_router` - API endpoints for capture
- `memory_service` - Episodic and semantic memory
- `search_adapter` - Unified search service
- `advanced_capture_service` - OCR, PDF, YouTube processing
- `enhanced_discord_service` - Discord bot integration
- `enhanced_apple_shortcuts_service` - iOS/macOS integration

## Example Commands

```bash
# Test specific service with coverage
pytest tests/test_unified_capture_service.py -v --cov=services.unified_capture_service --cov-report=term-missing

# Run all tests in a file
pytest tests/test_memory_service.py -v

# Run specific test function
pytest tests/test_unified_capture_service.py::test_basic_capture -v

# Show print statements
pytest tests/test_unified_capture_service.py -v -s
```

## Coverage Report Format

Show results like this:

```
Test Results for [Service Name]
================================

✅ test_basic_functionality - PASSED
✅ test_error_handling - PASSED
❌ test_edge_case - FAILED
⚠️  test_integration - SKIPPED

Passed: 2/3 (67%)
Coverage: 85%

Missing Coverage:
- services/example.py lines 45-52
- services/example.py lines 78-80
```

## Troubleshooting

If tests fail:
1. Check if dependencies are running (Ollama, database)
2. Verify test fixtures are properly set up
3. Look for import errors
4. Check database migrations are applied
5. Ensure test data is properly cleaned up

## Tips

- Run tests in isolation to avoid side effects
- Use `-k pattern` to run tests matching a pattern
- Add `--tb=short` for shorter error traces
- Use `--lf` to re-run only failed tests
- Check `conftest.py` for shared fixtures
