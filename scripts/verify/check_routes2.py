import sys
sys.path.insert(0, r'C:\Users\jakew\Downloads\labor-data-project')

from api.labor_api_v6 import app

all_routes = []
for route in app.routes:
    if hasattr(route, 'path'):
        all_routes.append(route.path)

whd = [r for r in all_routes if 'whd' in r]
print(f"WHD routes: {len(whd)}")
for r in whd:
    print(f"  {r}")

# Total
print(f"\nTotal routes: {len(all_routes)}")

# Last few routes to see if WHD is at the end
print(f"\nLast 15 routes:")
for r in sorted(all_routes)[-15:]:
    print(f"  {r}")
