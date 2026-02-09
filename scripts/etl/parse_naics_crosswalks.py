"""
Parse and Load NAICS Crosswalks into PostgreSQL
===============================================
"""
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os

crosswalk_dir = r'C:\Users\jakew\Downloads\labor-data-project\naics_crosswalks'

# Connect to database
conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
conn.autocommit = True
cur = conn.cursor()

print("="*70)
print("PARSING NAICS CROSSWALK FILES")
print("="*70)

# Parse 2022 to 2017 crosswalk
print("\n1. Parsing 2022_to_2017.xlsx...")
try:
    df_2022_2017 = pd.read_excel(os.path.join(crosswalk_dir, '2022_to_2017.xlsx'))
    print(f"   Columns: {list(df_2022_2017.columns)}")
    print(f"   Rows: {len(df_2022_2017):,}")
    print(f"   Sample:\n{df_2022_2017.head(3)}")
except Exception as e:
    print(f"   ERROR: {e}")
    df_2022_2017 = None

# Parse 2017 to 2012 crosswalk
print("\n2. Parsing 2017_to_2012.xlsx...")
try:
    df_2017_2012 = pd.read_excel(os.path.join(crosswalk_dir, '2017_to_2012.xlsx'))
    print(f"   Columns: {list(df_2017_2012.columns)}")
    print(f"   Rows: {len(df_2017_2012):,}")
    print(f"   Sample:\n{df_2017_2012.head(3)}")
except Exception as e:
    print(f"   ERROR: {e}")
    df_2017_2012 = None

# Parse 2012 to 2007 crosswalk
print("\n3. Parsing 2012_to_2007.xls...")
try:
    df_2012_2007 = pd.read_excel(os.path.join(crosswalk_dir, '2012_to_2007.xls'))
    print(f"   Columns: {list(df_2012_2007.columns)}")
    print(f"   Rows: {len(df_2012_2007):,}")
    print(f"   Sample:\n{df_2012_2007.head(3)}")
except Exception as e:
    print(f"   ERROR: {e}")
    df_2012_2007 = None

# Parse 2007 to 2002 crosswalk
print("\n4. Parsing 2007_to_2002.xls...")
try:
    df_2007_2002 = pd.read_excel(os.path.join(crosswalk_dir, '2007_to_2002.xls'))
    print(f"   Columns: {list(df_2007_2002.columns)}")
    print(f"   Rows: {len(df_2007_2002):,}")
    print(f"   Sample:\n{df_2007_2002.head(3)}")
except Exception as e:
    print(f"   ERROR: {e}")
    df_2007_2002 = None

# Parse SIC to NAICS crosswalk
print("\n5. Parsing sic_to_naics_2002.xls...")
try:
    df_sic = pd.read_excel(os.path.join(crosswalk_dir, 'sic_to_naics_2002.xls'))
    print(f"   Columns: {list(df_sic.columns)}")
    print(f"   Rows: {len(df_sic):,}")
    print(f"   Sample:\n{df_sic.head(3)}")
except Exception as e:
    print(f"   ERROR: {e}")
    df_sic = None

# Parse NAICS 2022 structure
print("\n6. Parsing naics_2022_structure.xlsx...")
try:
    df_struct_2022 = pd.read_excel(os.path.join(crosswalk_dir, 'naics_2022_structure.xlsx'))
    print(f"   Columns: {list(df_struct_2022.columns)}")
    print(f"   Rows: {len(df_struct_2022):,}")
    print(f"   Sample:\n{df_struct_2022.head(3)}")
except Exception as e:
    print(f"   ERROR: {e}")
    df_struct_2022 = None

# Parse NAICS 2017 structure
print("\n7. Parsing naics_2017_structure.xlsx...")
try:
    df_struct_2017 = pd.read_excel(os.path.join(crosswalk_dir, 'naics_2017_structure.xlsx'))
    print(f"   Columns: {list(df_struct_2017.columns)}")
    print(f"   Rows: {len(df_struct_2017):,}")
    print(f"   Sample:\n{df_struct_2017.head(3)}")
except Exception as e:
    print(f"   ERROR: {e}")
    df_struct_2017 = None

conn.close()
print("\n" + "="*70)
print("PARSING COMPLETE - Review column names above")
print("="*70)
