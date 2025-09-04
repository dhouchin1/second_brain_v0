#!/usr/bin/env python3
"""
Test script to debug search functionality
"""
import os
import sys
import requests
import time

# Test unified search endpoint
def test_unified_search():
    url = "http://localhost:8082/api/search/unified"
    payload = {
        "query": "test",
        "limit": 5,
        "filters": {
            "mode": "keyword"
        }
    }
    
    print("Testing unified search endpoint...")
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("results"):
                print(f"✅ Success: Found {len(data['results'])} results")
                for result in data['results'][:3]:
                    print(f"   - {result.get('title', 'No title')}")
            else:
                print("❌ No results or error in response")
        else:
            print(f"❌ HTTP Error: {response.status_code}")
    except Exception as e:
        print(f"❌ Request failed: {e}")
    
# Test direct search router endpoint
def test_search_router():
    url = "http://localhost:8082/api/search"
    payload = {
        "query": "test",
        "limit": 5
    }
    
    print("\nTesting search router endpoint...")
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        if response.status_code == 200:
            data = response.json()
            if data.get("results"):
                print(f"✅ Success: Found {len(data['results'])} results")
                for result in data['results'][:3]:
                    print(f"   - {result.get('title', 'No title')}")
            else:
                print("❌ No results in response")
        else:
            print(f"❌ HTTP Error: {response.status_code}")
    except Exception as e:
        print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    print("=== Search Debugging Tool ===")
    test_unified_search()
    test_search_router()
    print("\n=== Test Complete ===")