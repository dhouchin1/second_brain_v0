#!/usr/bin/env python3
"""
Test script for the enhanced health monitoring system
"""

import requests
import json
import sys
from datetime import datetime

def test_health_endpoint(base_url="http://localhost:8082"):
    """Test the enhanced /health endpoint"""
    print("Testing /health endpoint...")
    
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code in [200, 503]:
            data = response.json()
            print(f"Health Status: {data.get('status', 'unknown')}")
            print(f"Timestamp: {data.get('timestamp')}")
            
            # Print key health metrics
            if 'database' in data:
                db_health = data['database']
                print(f"Database Healthy: {db_health.get('healthy', False)}")
                print(f"Tables Present: {db_health.get('tables_present', False)}")
                print(f"FTS Index: {db_health.get('fts_index_status', 'unknown')}")
            
            if 'services' in data:
                services = data['services']
                print(f"Ollama Service: {'✓' if services.get('ollama', {}).get('healthy', False) else '✗'}")
                print(f"Whisper Service: {'✓' if services.get('whisper', {}).get('healthy', False) else '✗'}")
            
            if 'resources' in data:
                resources = data['resources']
                disk = resources.get('disk_space', {})
                memory = resources.get('memory', {})
                print(f"Disk Usage: {disk.get('used_percent', 0):.1f}%")
                print(f"Memory Usage: {memory.get('used_percent', 0):.1f}%")
            
            if 'processing_queue' in data:
                queue = data['processing_queue']
                print(f"Queue - Queued: {queue.get('queued_tasks', 0)}, Processing: {queue.get('processing_tasks', 0)}")
            
            if 'issues' in data and data['issues']:
                print("Issues detected:")
                for issue in data['issues']:
                    print(f"  - {issue}")
            
            print("✓ Health endpoint test passed")
            return True
            
        else:
            print(f"✗ Unexpected status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to server. Make sure the app is running on port 8082")
        return False
    except Exception as e:
        print(f"✗ Health endpoint test failed: {e}")
        return False

def test_diagnostics_endpoint(base_url="http://localhost:8082"):
    """Test the /api/diagnostics endpoint (requires authentication)"""
    print("\nTesting /api/diagnostics endpoint...")
    print("Note: This endpoint requires authentication, so it will likely fail unless you provide credentials")
    
    try:
        response = requests.get(f"{base_url}/api/diagnostics", timeout=10)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 401:
            print("✓ Diagnostics endpoint requires authentication (as expected)")
            return True
        elif response.status_code == 200:
            data = response.json()
            print("✓ Diagnostics endpoint accessible")
            print(f"Database Analytics: {'present' if 'database_analytics' in data else 'missing'}")
            print(f"Search Performance: {'present' if 'search_performance' in data else 'missing'}")
            print(f"Processing Analytics: {'present' if 'processing_analytics' in data else 'missing'}")
            print(f"Recommendations: {len(data.get('optimization_recommendations', []))} found")
            return True
        else:
            print(f"✗ Unexpected status code: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to server")
        return False
    except Exception as e:
        print(f"✗ Diagnostics endpoint test failed: {e}")
        return False

def main():
    """Run all health monitoring tests"""
    print("Enhanced Health Monitoring System Test")
    print("=" * 50)
    print(f"Test started at: {datetime.now().isoformat()}")
    print()
    
    # Test basic health endpoint
    health_test = test_health_endpoint()
    
    # Test diagnostics endpoint
    diagnostics_test = test_diagnostics_endpoint()
    
    print()
    print("=" * 50)
    print("Test Summary:")
    print(f"Health Endpoint: {'✓ PASS' if health_test else '✗ FAIL'}")
    print(f"Diagnostics Endpoint: {'✓ PASS' if diagnostics_test else '✗ FAIL'}")
    
    if health_test and diagnostics_test:
        print("\n🎉 All tests passed! Health monitoring system is working correctly.")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests failed. Check the output above for details.")
        sys.exit(1)

if __name__ == "__main__":
    main()