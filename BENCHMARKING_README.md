# Search Benchmarking System

The Second Brain search benchmarking system provides comprehensive performance and quality measurement capabilities for search algorithms, enabling continuous monitoring, regression detection, and A/B testing.

## Overview

The benchmarking system consists of:

- **Golden Queries**: Predefined test queries with expected outcomes
- **Benchmarking Service**: Core service for running benchmarks and analyzing results
- **Automated Integration**: CLI tools and scheduling for continuous benchmarking
- **API Endpoints**: REST API for benchmark execution and results analysis
- **Analytics & Reporting**: Performance tracking and regression detection

## Quick Start

### 1. Running Your First Benchmark

```bash
# Run a quick benchmark to validate system
python test_benchmarking.py

# Run automated benchmark
python automated_benchmarking.py quick
```

### 2. API Endpoints

The benchmarking API is available at `/api/benchmarking/` with the following endpoints:

```bash
# Run full benchmark suite
POST /api/benchmarking/run-benchmark

# Quick benchmark for specific queries
POST /api/benchmarking/quick-benchmark

# Get benchmark history
GET /api/benchmarking/suites

# Get detailed results
GET /api/benchmarking/suite/{suite_id}

# Performance trends
GET /api/benchmarking/performance-trends

# Analytics dashboard
GET /api/benchmarking/analytics/dashboard
```

### 3. Example API Usage

```python
import requests

# Run a quick benchmark
response = requests.post("http://localhost:8082/api/benchmarking/quick-benchmark", 
    json={
        "queries": ["meeting notes", "python tutorial"],
        "search_mode": "hybrid",
        "result_limit": 10
    }
)

print(response.json())
```

## Golden Queries Structure

Golden queries are defined in `golden_queries.json` and organized by categories:

### Query Categories

1. **keyword_search**: Basic keyword-based search scenarios
2. **semantic_search**: Concept-based and semantic search scenarios  
3. **hybrid_search**: Combined keyword and semantic search
4. **intent_based**: Search scenarios based on user intent
5. **edge_cases**: Edge cases and challenging scenarios
6. **performance_stress**: Performance and load testing

### Query Structure

```json
{
  "id": "kw_01",
  "query": "meeting notes",
  "description": "Find meeting-related content",
  "expected_result_types": ["note"],
  "min_results": 1,
  "quality_threshold": 0.7,
  "performance_target": {
    "max_time_ms": 500,
    "target_recall": 0.8
  },
  "context": {
    "user_intent": "find_existing",
    "scenario_type": "content_search"
  }
}
```

## Automated Benchmarking

### CLI Commands

```bash
# Daily benchmark (default categories)
python automated_benchmarking.py daily

# Weekly comprehensive benchmark
python automated_benchmarking.py weekly  

# Quick validation benchmark
python automated_benchmarking.py quick

# CI/CD benchmark (fails on regressions)
python automated_benchmarking.py ci

# Generate daily report
python automated_benchmarking.py report
```

### Configuration

Create `benchmarking_config.json` to customize automation:

```json
{
  "schedule": {
    "run_on_startup": true,
    "daily_benchmark": true,
    "weekly_full_benchmark": true
  },
  "alerts": {
    "regression_threshold": 0.15,
    "performance_threshold": 0.20,
    "webhook_url": "https://your-webhook-url"
  },
  "benchmarking": {
    "default_categories": ["keyword_search", "semantic_search"],
    "search_modes": ["hybrid", "keyword", "semantic"]
  },
  "ci_integration": {
    "fail_on_regressions": true,
    "max_execution_time_increase": 0.25,
    "min_quality_score": 0.6
  }
}
```

### CI/CD Integration

Add to your CI pipeline:

```yaml
# .github/workflows/search-benchmarks.yml
name: Search Benchmarks
on: [push, pull_request]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.9
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run benchmarks
        run: python automated_benchmarking.py ci
```

## Quality Metrics

The system tracks multiple quality metrics:

- **Relevance Score**: Average relevance of search results
- **Recall**: Ability to find relevant results
- **Precision**: Accuracy of returned results  
- **Result Count**: Number of results returned
- **Search Time**: Query execution time
- **Result Diversity**: Variety of result types
- **Intent Accuracy**: Match between expected and actual result types

## Performance Baselines

### Establishing Baselines

```bash
# Via API
POST /api/benchmarking/baseline
{
  "suite_id": "bench_20240109_123456",
  "notes": "Baseline after performance optimization"
}

# Via CLI
python -c "
from services.search_benchmarking_service import SearchBenchmarkingService
from config import get_connection
service = SearchBenchmarkingService(get_connection)
await service.establish_baseline('suite_id', 'notes')
"
```

### Regression Detection

The system automatically detects:
- **Performance Regressions**: Query time increases > 20% (configurable)
- **Quality Regressions**: Relevance score drops > 15% (configurable)
- **Recall Regressions**: Recall rate decreases > 10% (configurable)

## A/B Testing

### Creating Experiments

```bash
POST /api/benchmarking/ab-test
{
  "experiment_name": "New Ranking Algorithm",
  "description": "Testing improved relevance scoring",
  "control_config": {
    "algorithm": "current",
    "parameters": {"boost_factor": 1.0}
  },
  "variant_config": {
    "algorithm": "new", 
    "parameters": {"boost_factor": 1.5}
  },
  "duration_days": 7,
  "sample_size": 100
}
```

### Analyzing Results

```bash
GET /api/benchmarking/ab-tests/{experiment_id}/results
```

## Analytics Dashboard

Access comprehensive analytics at `/api/benchmarking/analytics/dashboard`:

- Recent benchmark summaries
- Performance trends over time
- Regression alerts
- Quality metrics evolution
- Category-specific performance

## Database Schema

The system uses several database tables:

- `benchmark_suites`: Overall benchmark run information
- `benchmark_results`: Individual query results
- `benchmark_baselines`: Performance baselines for comparison
- `search_analytics`: Real-time search performance tracking
- `ab_test_experiments`: A/B testing experiment definitions
- `ab_test_results`: A/B testing results data

## Adding New Golden Queries

1. **Edit `golden_queries.json`**:
   ```json
   {
     "id": "new_query_01",
     "query": "your test query",
     "description": "What this query tests",
     "expected_result_types": ["note", "template"],
     "min_results": 1,
     "quality_threshold": 0.7,
     "performance_target": {
       "max_time_ms": 500,
       "target_recall": 0.8
     }
   }
   ```

2. **Test the query**:
   ```bash
   python automated_benchmarking.py quick
   ```

3. **Add to appropriate category** in the scenarios array

## Troubleshooting

### Common Issues

1. **No golden queries loaded**
   - Ensure `golden_queries.json` exists in project root
   - Check JSON syntax validity

2. **Database connection errors**
   - Verify database migrations have run
   - Check `notes.db` file permissions

3. **Benchmark timeouts**
   - Adjust timeout values in configuration
   - Check search service performance

4. **Missing search results**
   - Verify search indices are built
   - Check that notes exist in database

### Debug Commands

```bash
# Test system components
python test_benchmarking.py

# Check database tables
sqlite3 notes.db ".tables"

# View recent benchmarks
sqlite3 notes.db "SELECT * FROM benchmark_suites ORDER BY created_at DESC LIMIT 5;"

# Check golden queries syntax  
python -c "import json; print('OK' if json.load(open('golden_queries.json')) else 'ERROR')"
```

## Performance Optimization

### Best Practices

1. **Query Optimization**
   - Use specific, realistic test queries
   - Balance query complexity across categories
   - Include edge cases but don't overwhelm

2. **Baseline Management**
   - Update baselines after major improvements
   - Document baseline changes with meaningful notes
   - Don't update baselines too frequently

3. **CI Integration** 
   - Use quick benchmarks for PR checks
   - Run full benchmarks nightly
   - Set appropriate failure thresholds

4. **Monitoring**
   - Review benchmark reports regularly
   - Set up alerts for critical regressions
   - Track trends over time

## Contributing

When adding new search features:

1. Add corresponding golden queries
2. Run benchmarks before and after changes
3. Update baselines if improvements are substantial
4. Document any changes to expected behavior

The benchmarking system helps ensure search quality remains high as the system evolves and scales.