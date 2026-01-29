"""
Download and Load NAICS Crosswalks
==================================
Census Bureau official concordances
"""
import requests
import os

# URLs for Census Bureau crosswalks
CROSSWALK_URLS = {
    '2022_to_2017': 'https://www.census.gov/naics/concordances/2022_to_2017_NAICS.xlsx',
    '2017_to_2012': 'https://www.census.gov/naics/concordances/2017_to_2012_NAICS.xlsx',
    '2012_to_2007': 'https://www.census.gov/naics/concordances/2012_to_2007_NAICS.xlsx',
    '2007_to_2002': 'https://www.census.gov/naics/concordances/2007_to_2002_NAICS.xlsx',
}

# Also get the NAICS structure files (with titles)
STRUCTURE_URLS = {
    '2022': 'https://www.census.gov/naics/2022NAICS/2022_NAICS_Structure.xlsx',
    '2017': 'https://www.census.gov/naics/2017NAICS/2017_NAICS_Structure.xlsx',
    '2012': 'https://www.census.gov/naics/2012NAICS/2012_NAICS_Structure.xlsx',
}

# SIC to NAICS crosswalk
SIC_NAICS_URL = 'https://www.census.gov/naics/concordances/1987_SIC_to_2002_NAICS.xls'

output_dir = r'C:\Users\jakew\Downloads\labor-data-project\naics_crosswalks'
os.makedirs(output_dir, exist_ok=True)

print("="*70)
print("DOWNLOADING NAICS CROSSWALKS FROM CENSUS BUREAU")
print("="*70)

# Download crosswalk files
downloaded_files = {}
for name, url in CROSSWALK_URLS.items():
    print(f"\nDownloading {name}...")
    try:
        response = requests.get(url, timeout=60)
        if response.status_code == 200:
            filepath = os.path.join(output_dir, f'{name}.xlsx')
            with open(filepath, 'wb') as f:
                f.write(response.content)
            print(f"  OK - Saved to {filepath} ({len(response.content):,} bytes)")
            downloaded_files[name] = filepath
        else:
            print(f"  FAILED: HTTP {response.status_code}")
    except Exception as e:
        print(f"  ERROR: {e}")

# Download structure files
for name, url in STRUCTURE_URLS.items():
    print(f"\nDownloading NAICS {name} structure...")
    try:
        response = requests.get(url, timeout=60)
        if response.status_code == 200:
            filepath = os.path.join(output_dir, f'naics_{name}_structure.xlsx')
            with open(filepath, 'wb') as f:
                f.write(response.content)
            print(f"  OK - Saved to {filepath} ({len(response.content):,} bytes)")
            downloaded_files[f'structure_{name}'] = filepath
        else:
            print(f"  FAILED: HTTP {response.status_code}")
    except Exception as e:
        print(f"  ERROR: {e}")

# Download SIC to NAICS crosswalk
print(f"\nDownloading SIC to NAICS crosswalk...")
try:
    response = requests.get(SIC_NAICS_URL, timeout=60)
    if response.status_code == 200:
        filepath = os.path.join(output_dir, 'sic_to_naics_2002.xls')
        with open(filepath, 'wb') as f:
            f.write(response.content)
        print(f"  OK - Saved to {filepath} ({len(response.content):,} bytes)")
        downloaded_files['sic_to_naics'] = filepath
    else:
        print(f"  FAILED: HTTP {response.status_code}")
except Exception as e:
    print(f"  ERROR: {e}")

print(f"\n{'='*70}")
print(f"Downloaded {len(downloaded_files)} files")
print("="*70)

# List downloaded files
for name, path in downloaded_files.items():
    size = os.path.getsize(path)
    print(f"  {name}: {size:,} bytes")
