"""
CHECKPOINT A3: Integration Testing for API v5.0
"""
import requests

API = "http://localhost:8003/api"

def test_endpoint(name, url, expected_keys=None):
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    try:
        resp = requests.get(url, timeout=30)
        data = resp.json()
        
        if resp.status_code == 200:
            print(f"[OK] Status: {resp.status_code}")
            
            if expected_keys:
                missing = [k for k in expected_keys if k not in data]
                if missing:
                    print(f"[WARN] Missing keys: {missing}")
                else:
                    print(f"[OK] All expected keys present")
            
            if 'total' in data:
                print(f"   Total: {data['total']:,}")
            if 'total_workers' in data:
                print(f"   Workers: {data['total_workers']:,}")
            if 'employers' in data and len(data['employers']) > 0:
                print(f"   Sample: {data['employers'][0].get('employer_name', 'N/A')[:50]}")
            if 'sectors' in data:
                for s in data['sectors']:
                    print(f"   {s['sector_code']}: {s.get('total_workers', 0):,.0f} workers")
            if 'unions' in data:
                print(f"   Unions: {len(data['unions'])}")
                
            return True
        else:
            print(f"[FAIL] Status: {resp.status_code}")
            return False
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False

print("=" * 60)
print("CHECKPOINT A3: API Integration Tests (Port 8003)")
print("=" * 60)

tests = [
    ("Health Check", f"{API}/health", ["status", "version"]),
    ("Sector Summary", f"{API}/sectors/summary", ["sectors", "totals"]),
    ("Unified Search - All", f"{API}/employers/unified?limit=5", ["total", "employers"]),
    ("Unified Search - Private", f"{API}/employers/unified?sector=PRIVATE&limit=5", ["total", "employers"]),
    ("Unified Search - Federal", f"{API}/employers/unified?sector=FEDERAL&limit=5", ["total", "employers"]),
    ("Search by Union (AFGE)", f"{API}/employers/unified?union=AFGE&limit=5", ["total", "employers"]),
    ("Search by Union (SEIU)", f"{API}/employers/unified?union=SEIU&limit=5", ["total", "employers"]),
    ("Search by State (CA)", f"{API}/employers/unified?state=CA&limit=5", ["total", "employers"]),
    ("Search by Name (Kaiser)", f"{API}/employers/unified?name=kaiser&limit=5", ["total", "employers"]),
    ("Unions by Sector", f"{API}/unions/by-sector?min_workers=10000", ["unions"]),
    ("Lookups - Unions", f"{API}/lookups/unions", ["unions"]),
    ("Lookups - States", f"{API}/lookups/states", ["states"]),
    ("Stats Overview", f"{API}/stats/overview", ["sectors", "top_unions", "top_employers"]),
]

passed = 0
failed = 0

for name, url, keys in tests:
    if test_endpoint(name, url, keys):
        passed += 1
    else:
        failed += 1

print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed out of {len(tests)} tests")
print("=" * 60)

if failed == 0:
    print("\n[SUCCESS] CHECKPOINT A3 COMPLETE - All tests passed!")
else:
    print(f"\n[WARNING] {failed} test(s) failed - review above")
