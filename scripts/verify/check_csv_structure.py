"""Check structure of Mergent CSV (actually Excel) files"""
import pandas as pd
import os

base_path = r"C:\Users\jakew\Downloads\labor-data-project\AFSCME case example NY"
files = [
    "1_2000_other_industries_advancesearch18488938096983ac1794e51.csv",
    "2001_4000_other_industries_advancesearch8908858966983ac4faff74.csv",
]

for fname in files:
    fpath = os.path.join(base_path, fname)
    print(f"\n=== {fname} ===")
    try:
        # Try reading as Excel (xlsx format)
        df = pd.read_excel(fpath, engine='openpyxl')
        print(f"Rows: {len(df)}")
        print(f"Columns ({len(df.columns)}):")
        for col in df.columns[:20]:
            print(f"  - {col}")
        if len(df.columns) > 20:
            print(f"  ... and {len(df.columns) - 20} more")
        print(f"\nSample row:")
        if len(df) > 0:
            for col in df.columns[:10]:
                print(f"  {col}: {df.iloc[0][col]}")
    except Exception as e:
        print(f"Error: {e}")
        # Try CSV
        try:
            df = pd.read_csv(fpath)
            print(f"As CSV - Rows: {len(df)}")
        except Exception as e2:
            print(f"CSV Error: {e2}")
