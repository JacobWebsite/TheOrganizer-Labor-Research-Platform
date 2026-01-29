"""
Quick diagnostic - check for duplicate IDs in CSV
"""
import pandas as pd

csv_path = r"C:\Users\jakew\Downloads\federal workers and contracts_OPM.csv"
df = pd.read_csv(csv_path, low_memory=False)

print(f"Total rows: {len(df)}")
print(f"Unique IDs: {df['ID'].nunique()}")
print(f"Duplicate IDs: {len(df) - df['ID'].nunique()}")

# Show duplicate IDs
dup_ids = df[df.duplicated(subset=['ID'], keep=False)]['ID'].unique()
print(f"\nNumber of IDs that appear multiple times: {len(dup_ids)}")

if len(dup_ids) > 0:
    print("\nSample duplicate IDs:")
    for id_val in list(dup_ids)[:5]:
        subset = df[df['ID'] == id_val][['ID', 'Agency', 'UnionAcronym', 'TotalInBargainingUnit']]
        print(f"\nID {id_val}:")
        print(subset.to_string())
