"""
Checkpoint 6C: Test all VR API endpoints
"""
import requests
import json

BASE_URL = "http://127.0.0.1:8003"

def test_endpoint(name, url, expected_key=None):
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if expected_key and expected_key in data:
                print(f"[OK] {name}")
                return data
            elif not expected_key:
                print(f"[OK] {name}")
                return data
            else:
                print(f"[FAIL] {name}: Missing key '{expected_key}'")
        else:
            print(f"[FAIL] {name}: Status {resp.status_code}")
    except Exception as e:
        print(f"[ERR] {name}: {str(e)[:50]}")
    return None

print("=" * 60)
print("VR API Endpoint Tests - Checkpoint 6C")
print("=" * 60)

# Health check
print("\n--- Core Endpoints ---")
data = test_endpoint("Health Check", f"{BASE_URL}/api/health", "status")
if data:
    print(f"     VR Records: {data.get('vr_records', 'N/A')}")

# Statistics endpoints
print("\n--- Statistics Endpoints ---")
data = test_endpoint("Summary Stats", f"{BASE_URL}/api/vr/stats/summary", "total_vr_cases")
if data:
    print(f"     Total: {data['total_vr_cases']}, Match: {data['employer_match_pct']}% emp, {data['union_match_pct']}% union")

data = test_endpoint("By Year", f"{BASE_URL}/api/vr/stats/by-year", "years")
if data:
    print(f"     Years: {len(data['years'])}")

data = test_endpoint("By State", f"{BASE_URL}/api/vr/stats/by-state", "states")
if data:
    print(f"     States: {len(data['states'])}")

data = test_endpoint("By Affiliation", f"{BASE_URL}/api/vr/stats/by-affiliation", "affiliations")
if data:
    print(f"     Affiliations: {len(data['affiliations'])}")

# Search endpoints
print("\n--- Search Endpoints ---")
data = test_endpoint("Search (all)", f"{BASE_URL}/api/vr/search?limit=5", "total")
if data:
    print(f"     Total: {data['total']}, Returned: {len(data['results'])}")

data = test_endpoint("Search (CA)", f"{BASE_URL}/api/vr/search?state=CA&limit=3", "total")
if data:
    print(f"     CA cases: {data['total']}")

data = test_endpoint("Search (SEIU)", f"{BASE_URL}/api/vr/search?affiliation=SEIU&limit=3", "total")
if data:
    print(f"     SEIU cases: {data['total']}")

# Map data
print("\n--- Map & Pipeline Endpoints ---")
data = test_endpoint("Map Data", f"{BASE_URL}/api/vr/map?limit=10", "features")
if data:
    print(f"     Features with coords: {len(data['features'])}")

data = test_endpoint("New Employers", f"{BASE_URL}/api/vr/new-employers?limit=5", "total")
if data:
    print(f"     New employers: {data['total']}")

data = test_endpoint("Pipeline", f"{BASE_URL}/api/vr/pipeline?limit=5", "summary")
if data:
    print(f"     Pipeline sequences: {len(data['summary'])}")

# Organizing endpoints
print("\n--- Combined Organizing Endpoints ---")
data = test_endpoint("Organizing Summary", f"{BASE_URL}/api/organizing/summary", "years")
if data:
    print(f"     Years: {len(data['years'])}")

data = test_endpoint("Organizing By State", f"{BASE_URL}/api/organizing/by-state", "states")
if data:
    print(f"     States: {len(data['states'])}")

# Case detail
print("\n--- Case Detail Endpoint ---")
data = test_endpoint("Case Detail", f"{BASE_URL}/api/vr/1-3543081791", "vr_case")
if data:
    case = data['vr_case']
    print(f"     Case: {case['vr_case_number']}, Employer: {case['employer_name'][:30]}")

print("\n" + "=" * 60)
print("All endpoint tests complete!")
print("=" * 60)
