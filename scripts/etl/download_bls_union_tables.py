#!/usr/bin/env python3
"""
Download BLS Union Membership Tables
Downloads tables from BLS Union Membership News Release
"""
import requests
import os
from pathlib import Path

# BLS Union Membership 2024 tables (released January 2025)
# https://www.bls.gov/news.release/union2.htm

BLS_TABLES = {
    'table3': {
        'name': 'Union affiliation by occupation and industry',
        'url': 'https://www.bls.gov/news.release/union2.t03.htm',
        'output': 'union_2024_table3_industry.html'
    },
    'table5': {
        'name': 'Union affiliation by state',
        'url': 'https://www.bls.gov/news.release/union2.t05.htm',
        'output': 'union_2024_table5_state.html'
    },
    'table1': {
        'name': 'Union affiliation by selected characteristics',
        'url': 'https://www.bls.gov/news.release/union2.t01.htm',
        'output': 'union_2024_table1_characteristics.html'
    }
}

def download_table(url, output_path):
    """Download HTML table from BLS"""
    print(f"Downloading {url}...")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(response.text)

    print(f"  Saved to {output_path}")
    return output_path


def main():
    # Output directory
    output_dir = Path(__file__).resolve().parent.parent.parent / 'data' / 'bls'
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Downloading BLS Union Membership Tables (2024 data)...")
    print("=" * 60)

    for table_id, info in BLS_TABLES.items():
        print(f"\n{table_id.upper()}: {info['name']}")
        output_path = output_dir / info['output']

        try:
            download_table(info['url'], output_path)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    print("\n" + "=" * 60)
    print("✓ Download complete")
    print(f"Files saved to: {output_dir}")
    print("\nNext step: Run parse_bls_union_tables.py to extract data")


if __name__ == '__main__':
    main()
