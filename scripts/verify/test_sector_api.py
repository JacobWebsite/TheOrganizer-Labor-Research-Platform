"""Test the sector API endpoints"""
import requests
import json

BASE_URL = "http://localhost:8001"

def test_endpoint(url, desc):
    """Test an endpoint and print results"""
    print(f"\n=== {desc} ===")
    print(f"GET {url}")
    try:
        resp = requests.get(url, timeout=10)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            # Print summary
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, list):
                        print(f"  {k}: {len(v)} items")
                        if v and len(v) > 0:
                            print(f"    First: {json.dumps(v[0], default=str)[:100]}...")
                    else:
                        print(f"  {k}: {v}")
        else:
            print(f"Error: {resp.text[:200]}")
    except Exception as e:
        print(f"Error: {e}")

# Test endpoints
test_endpoint(f"{BASE_URL}/api/health", "Health Check")
test_endpoint(f"{BASE_URL}/api/sectors/list", "List All Sectors")
test_endpoint(f"{BASE_URL}/api/sectors/education/summary", "Education Sector Summary")
test_endpoint(f"{BASE_URL}/api/sectors/education/targets?limit=5", "Education Targets")
test_endpoint(f"{BASE_URL}/api/sectors/education/targets/stats", "Education Target Stats")
test_endpoint(f"{BASE_URL}/api/sectors/social_services/summary", "Social Services Summary")
test_endpoint(f"{BASE_URL}/api/sectors/building_services/targets?tier=HIGH&limit=5", "Building Services HIGH Tier")
