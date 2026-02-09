import requests
import json

r = requests.get("http://127.0.0.1:8001/openapi.json")
data = r.json()
whd_routes = [p for p in data['paths'] if 'whd' in p]
print(f"WHD routes found: {len(whd_routes)}")
for route in whd_routes:
    print(f"  {route}")
print(f"\nTotal routes: {len(data['paths'])}")

# Also check a known working route
osha_routes = [p for p in data['paths'] if 'osha' in p]
print(f"\nOSHA routes: {len(osha_routes)}")
for route in osha_routes:
    print(f"  {route}")
