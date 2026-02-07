"""Test the organizing targets API endpoints."""
import sys
sys.path.insert(0, '.')

from api.labor_api_v5 import app
from fastapi.testclient import TestClient

client = TestClient(app)

# Test targets stats
print('Testing /api/targets/stats...')
response = client.get('/api/targets/stats')
if response.status_code == 200:
    data = response.json()
    print(f'  Total targets: {data["overall"]["total_targets"]}')
    print(f'  TOP tier: {data["overall"]["top_tier"]}')
    total_funding = float(data["overall"]["total_funding"] or 0)
    print(f'  Total funding: ${total_funding/1e9:.2f}B')
else:
    print(f'  Error: {response.status_code}')
    print(response.text)

# Test targets search
print('\nTesting /api/targets/search?state=NY&tier=TOP&limit=5...')
response = client.get('/api/targets/search?state=NY&tier=TOP&limit=5')
if response.status_code == 200:
    data = response.json()
    print(f'  Total results: {data["total"]}')
    for t in data['targets'][:5]:
        funding = float(t["total_govt_funding"] or 0)
        print(f'    - {t["employer_name"][:45]} | {t["priority_tier"]} | ${funding/1e6:.1f}M')
else:
    print(f'  Error: {response.status_code}')
    print(response.text)

# Test targets for union
print('\nTesting /api/targets/for-union/531654 (AFSCME DC 37)...')
response = client.get('/api/targets/for-union/531654')
if response.status_code == 200:
    data = response.json()
    if data.get('union'):
        print(f'  Union: {data["union"]["union_name"]}')
        print(f'  Recommended targets: {data["total_found"]}')
else:
    print(f'  Error: {response.status_code}')

print('\nAPI tests completed!')
