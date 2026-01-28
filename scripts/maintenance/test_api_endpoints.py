"""Test API endpoints"""
import requests

BASE = "http://localhost:8000/api"

print("=" * 60)
print("Testing API Endpoints")
print("=" * 60)

# Test affiliations
print("\n1. Affiliations:")
try:
    r = requests.get(f"{BASE}/affiliations")
    data = r.json()
    print(f"   Status: {r.status_code}")
    print(f"   Count: {len(data.get('affiliations', []))}")
except Exception as e:
    print(f"   ERROR: {e}")

# Test union search
print("\n2. Union Search (SEIU):")
try:
    r = requests.get(f"{BASE}/unions/search?affiliation=SEIU&limit=5")
    data = r.json()
    print(f"   Status: {r.status_code}")
    print(f"   Total: {data.get('total_count', 0)}")
    if data.get('results'):
        for u in data['results'][:3]:
            print(f"   - {u['f_num']}: {u['union_name'][:40]}")
except Exception as e:
    print(f"   ERROR: {e}")

# Test union detail
print("\n3. Union Detail (f_num=137):")
try:
    r = requests.get(f"{BASE}/unions/137")
    print(f"   Status: {r.status_code}")
    data = r.json()
    if 'union' in data:
        print(f"   Union: {data['union']['union_name']}")
        print(f"   LM records: {len(data.get('lm_financial', []))}")
        print(f"   NLRB summary: {data.get('nlrb_summary', {})}")
    else:
        print(f"   Response: {data}")
except Exception as e:
    print(f"   ERROR: {e}")

# Test employers
print("\n4. Employers for union 137:")
try:
    r = requests.get(f"{BASE}/unions/137/employers?limit=5")
    print(f"   Status: {r.status_code}")
    data = r.json()
    print(f"   Total: {data.get('total_count', 0)}")
except Exception as e:
    print(f"   ERROR: {e}")

# Test elections
print("\n5. Elections for union 137:")
try:
    r = requests.get(f"{BASE}/unions/137/elections?limit=5")
    print(f"   Status: {r.status_code}")
    data = r.json()
    print(f"   Elections: {len(data.get('elections', []))}")
    print(f"   Summary: {data.get('summary', {})}")
except Exception as e:
    print(f"   ERROR: {e}")

# Test cases
print("\n6. Cases for union 137:")
try:
    r = requests.get(f"{BASE}/unions/137/cases?limit=5")
    print(f"   Status: {r.status_code}")
    data = r.json()
    print(f"   Cases: {len(data.get('cases', []))}")
except Exception as e:
    print(f"   ERROR: {e}")
