"""
Download remaining NAICS crosswalks and load all into PostgreSQL
"""
import requests
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os

output_dir = r'C:\Users\jakew\Downloads\labor-data-project\naics_crosswalks'

# Download remaining files (older format .xls)
ADDITIONAL_URLS = {
    '2012_to_2007': 'https://www.census.gov/naics/concordances/2012_to_2007_NAICS.xls',
    '2007_to_2002': 'https://www.census.gov/naics/concordances/2007_to_2002_NAICS.xls',
    '2002_to_sic': 'https://www.census.gov/naics/concordances/2002_NAICS_to_1987_SIC.xls',
}

print("="*70)
print("DOWNLOADING REMAINING CROSSWALKS")
print("="*70)

for name, url in ADDITIONAL_URLS.items():
    filepath = os.path.join(output_dir, f'{name}.xls')
    if os.path.exists(filepath):
        print(f"{name}: Already exists")
        continue
    print(f"\nDownloading {name}...")
    try:
        response = requests.get(url, timeout=60)
        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                f.write(response.content)
            print(f"  OK - {len(response.content):,} bytes")
        else:
            print(f"  FAILED: HTTP {response.status_code}")
    except Exception as e:
        print(f"  ERROR: {e}")

# List all files in directory
print("\n" + "="*70)
print("FILES IN CROSSWALK DIRECTORY")
print("="*70)
for f in os.listdir(output_dir):
    fpath = os.path.join(output_dir, f)
    size = os.path.getsize(fpath)
    print(f"  {f}: {size:,} bytes")
