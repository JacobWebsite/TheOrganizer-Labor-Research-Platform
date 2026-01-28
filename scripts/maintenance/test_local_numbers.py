"""Test local number in API"""
import requests

BASE = "http://localhost:8000/api"

print("Testing union search with local numbers...")
r = requests.get(f"{BASE}/unions/search?affiliation=SEIU&limit=10")
data = r.json()
print(f"Status: {r.status_code}")
print(f"First result keys: {list(data['results'][0].keys())}")
for u in data['results'][:10]:
    local = u.get('local_number') or 'N/A'
    desig = (u.get('desig_name') or '').strip()
    print(f"  {u['f_num']}: Local {local} ({desig}) - {u['city']}, {u['state']} - {u.get('members', 0):,} members")

print("\nTesting union detail...")
r = requests.get(f"{BASE}/unions/31847")  # SEIU 1199
data = r.json()
u = data['union']
print(f"  {u['f_num']}: Local {u.get('local_number')} ({u.get('desig_name')}) - {u['union_name']}")
