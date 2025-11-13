#!/usr/bin/env python3
"""
Test script for the /api/auth/token endpoint
"""
import requests
import sys

# Test configuration
BASE_URL = "http://localhost:8082"
AUTH_TOKEN_URL = f"{BASE_URL}/api/auth/token"

def test_auth_token_endpoint():
    """Test the /api/auth/token endpoint"""

    print("Testing /api/auth/token endpoint...")
    print("-" * 60)

    # Test 1: Without authentication (should fail with 401)
    print("\n1. Testing without authentication (should fail):")
    response = requests.get(AUTH_TOKEN_URL)
    print(f"   Status Code: {response.status_code}")
    if response.status_code == 401:
        print("   ✓ Correctly returns 401 Unauthorized")
    else:
        print(f"   ✗ Expected 401, got {response.status_code}")
        print(f"   Response: {response.text}")

    # Test 2: With authentication cookie
    print("\n2. Testing with authentication cookie:")
    print("   Note: This requires a valid access_token cookie")
    print("   You need to manually test this in the browser or with a valid token")
    print("   Example curl command:")
    print(f'   curl {AUTH_TOKEN_URL} -b "access_token=YOUR_TOKEN"')

    print("\n" + "=" * 60)
    print("To test with authentication:")
    print("1. Log in to the application in your browser")
    print("2. Open browser dev tools (F12)")
    print("3. Go to Console tab")
    print("4. Run: fetch('/api/auth/token').then(r => r.json()).then(console.log)")
    print("5. You should see: {token: '...', user_id: X, username: '...'}")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_auth_token_endpoint()
    except requests.exceptions.ConnectionError:
        print(f"\n✗ Error: Could not connect to {BASE_URL}")
        print("  Make sure the server is running:")
        print("  .venv/bin/python -m uvicorn app:app --reload --port 8082")
        sys.exit(1)
