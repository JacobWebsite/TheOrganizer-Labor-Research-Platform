"""Check full structure of Mergent CSV files"""
import pandas as pd
import os

base_path = r"C:\Users\jakew\Downloads\labor-data-project\AFSCME case example NY"
fname = "1_2000_other_industries_advancesearch18488938096983ac1794e51.csv"
fpath = os.path.join(base_path, fname)

df = pd.read_excel(fpath, engine='openpyxl')

print("=== ALL COLUMNS ===")
for i, col in enumerate(df.columns):
    # Get sample value
    sample = df[col].dropna().iloc[0] if len(df[col].dropna()) > 0 else "N/A"
    if isinstance(sample, str) and len(sample) > 50:
        sample = sample[:50] + "..."
    print(f"{i:2}. {col:40} | Sample: {sample}")

print("\n\n=== NAICS Distribution ===")
naics_cols = [c for c in df.columns if 'naics' in c.lower() or 'sic' in c.lower()]
for col in naics_cols:
    print(f"\n{col}:")
    print(df[col].value_counts().head(10))

# Check unique NAICS prefixes
if 'Primary NAICS Code' in df.columns:
    print("\n=== NAICS 3-digit prefixes (industries) ===")
    df['naics_3'] = df['Primary NAICS Code'].astype(str).str[:3]
    print(df['naics_3'].value_counts().head(30))
