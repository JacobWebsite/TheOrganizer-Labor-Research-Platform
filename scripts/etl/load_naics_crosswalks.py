"""
Load NAICS Crosswalks into PostgreSQL - Fixed
=============================================
"""
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os
import re

crosswalk_dir = r'C:\Users\jakew\Downloads\labor-data-project\naics_crosswalks'

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
conn.autocommit = True
cur = conn.cursor()

print("="*70)
print("CREATING NAICS CROSSWALK TABLES")
print("="*70)

# Drop existing indexes and tables
cur.execute("DROP INDEX IF EXISTS idx_naics_xwalk_source")
cur.execute("DROP INDEX IF EXISTS idx_naics_xwalk_target")
cur.execute("DROP INDEX IF EXISTS idx_sic_naics_sic")
cur.execute("DROP INDEX IF EXISTS idx_sic_naics_naics")
cur.execute("DROP INDEX IF EXISTS idx_naics_ref_version")

# Create tables
cur.execute("""
DROP TABLE IF EXISTS naics_version_crosswalk CASCADE;
DROP TABLE IF EXISTS naics_sic_crosswalk CASCADE;
DROP TABLE IF EXISTS naics_codes_reference CASCADE;

CREATE TABLE naics_version_crosswalk (
    id SERIAL PRIMARY KEY,
    source_version INTEGER NOT NULL,
    target_version INTEGER NOT NULL,
    source_code VARCHAR(10) NOT NULL,
    source_title TEXT,
    target_code VARCHAR(10) NOT NULL,
    target_title TEXT,
    UNIQUE(source_version, target_version, source_code, target_code)
);

CREATE TABLE naics_sic_crosswalk (
    id SERIAL PRIMARY KEY,
    sic_code VARCHAR(10) NOT NULL,
    sic_title TEXT,
    naics_2002_code VARCHAR(10) NOT NULL,
    naics_2002_title TEXT,
    UNIQUE(sic_code, naics_2002_code)
);

CREATE TABLE naics_codes_reference (
    id SERIAL PRIMARY KEY,
    naics_version INTEGER NOT NULL,
    naics_code VARCHAR(20) NOT NULL,
    naics_title TEXT,
    code_level INTEGER,
    change_indicator VARCHAR(20),
    UNIQUE(naics_version, naics_code)
);

CREATE INDEX idx_naics_xwalk_source ON naics_version_crosswalk(source_version, source_code);
CREATE INDEX idx_naics_xwalk_target ON naics_version_crosswalk(target_version, target_code);
CREATE INDEX idx_sic_naics_sic ON naics_sic_crosswalk(sic_code);
CREATE INDEX idx_sic_naics_naics ON naics_sic_crosswalk(naics_2002_code);
CREATE INDEX idx_naics_ref_version ON naics_codes_reference(naics_version, naics_code);
""")
print("Tables created")

def clean_code(val):
    if pd.isna(val):
        return None
    val = str(val).strip()
    val = re.sub(r'[^\d-]', '', val)
    return val if val else None

def clean_text(val):
    if pd.isna(val):
        return None
    return str(val).strip()[:500]

def clean_naics_code(val):
    """For structure files - keep code as-is but limit length"""
    if pd.isna(val):
        return None
    val = str(val).strip()[:15]
    return val if val else None

# Load 2022 to 2017 crosswalk
print("\n1. Loading 2022->2017 crosswalk...")
df = pd.read_excel(os.path.join(crosswalk_dir, '2022_to_2017.xlsx'), header=1)
df.columns = ['code_2022', 'title_2022', 'code_2017_a', 'title_2017_a', 
              'code_2017_b', 'title_2017_b', 'code_2017_c', 'title_2017_c',
              'code_2017_d', 'title_2017_d', 'code_2017_e']

rows = []
for _, r in df.iterrows():
    code_2022 = clean_code(r['code_2022'])
    title_2022 = clean_text(r['title_2022'])
    if not code_2022:
        continue
    for suffix in ['a', 'b', 'c', 'd']:
        code_2017 = clean_code(r.get(f'code_2017_{suffix}'))
        title_2017 = clean_text(r.get(f'title_2017_{suffix}'))
        if code_2017:
            rows.append((2022, 2017, code_2022, title_2022, code_2017, title_2017))

if rows:
    execute_values(cur, """
        INSERT INTO naics_version_crosswalk (source_version, target_version, source_code, source_title, target_code, target_title)
        VALUES %s ON CONFLICT DO NOTHING
    """, rows)
print(f"   Loaded {len(rows):,} mappings")

# Load 2017 to 2012 crosswalk
print("\n2. Loading 2017->2012 crosswalk...")
df = pd.read_excel(os.path.join(crosswalk_dir, '2017_to_2012.xlsx'), header=1)
df.columns = ['code_2017', 'title_2017', 'code_2012_a', 'title_2012_a', 
              'code_2012_b', 'title_2012_b', 'code_2012_c', 'title_2012_c',
              'code_2012_d', 'title_2012_d', 'code_2012_e']

rows = []
for _, r in df.iterrows():
    code_2017 = clean_code(r['code_2017'])
    title_2017 = clean_text(r['title_2017'])
    if not code_2017:
        continue
    for suffix in ['a', 'b', 'c', 'd']:
        code_2012 = clean_code(r.get(f'code_2012_{suffix}'))
        title_2012 = clean_text(r.get(f'title_2012_{suffix}'))
        if code_2012:
            rows.append((2017, 2012, code_2017, title_2017, code_2012, title_2012))

if rows:
    execute_values(cur, """
        INSERT INTO naics_version_crosswalk (source_version, target_version, source_code, source_title, target_code, target_title)
        VALUES %s ON CONFLICT DO NOTHING
    """, rows)
print(f"   Loaded {len(rows):,} mappings")

# Load 2012 to 2007 crosswalk
print("\n3. Loading 2012->2007 crosswalk...")
df = pd.read_excel(os.path.join(crosswalk_dir, '2012_to_2007.xls'), header=1)
df.columns = ['code_2012', 'title_2012', 'code_2007', 'title_2007']

rows = []
for _, r in df.iterrows():
    code_2012 = clean_code(r['code_2012'])
    title_2012 = clean_text(r['title_2012'])
    code_2007 = clean_code(r['code_2007'])
    title_2007 = clean_text(r['title_2007'])
    if code_2012 and code_2007:
        rows.append((2012, 2007, code_2012, title_2012, code_2007, title_2007))

if rows:
    execute_values(cur, """
        INSERT INTO naics_version_crosswalk (source_version, target_version, source_code, source_title, target_code, target_title)
        VALUES %s ON CONFLICT DO NOTHING
    """, rows)
print(f"   Loaded {len(rows):,} mappings")

# Load 2007 to 2002 crosswalk
print("\n4. Loading 2007->2002 crosswalk...")
df = pd.read_excel(os.path.join(crosswalk_dir, '2007_to_2002.xls'), header=1)
df.columns = ['code_2007', 'title_2007', 'code_2002', 'title_2002']

rows = []
for _, r in df.iterrows():
    code_2007 = clean_code(r['code_2007'])
    title_2007 = clean_text(r['title_2007'])
    code_2002 = clean_code(r['code_2002'])
    title_2002 = clean_text(r['title_2002'])
    if code_2007 and code_2002:
        rows.append((2007, 2002, code_2007, title_2007, code_2002, title_2002))

if rows:
    execute_values(cur, """
        INSERT INTO naics_version_crosswalk (source_version, target_version, source_code, source_title, target_code, target_title)
        VALUES %s ON CONFLICT DO NOTHING
    """, rows)
print(f"   Loaded {len(rows):,} mappings")

# Load SIC to NAICS crosswalk
print("\n5. Loading SIC->NAICS crosswalk...")
df = pd.read_excel(os.path.join(crosswalk_dir, 'sic_to_naics_2002.xls'))
df.columns = ['sic_code', 'sic_title', 'naics_code', 'naics_title']

rows = []
for _, r in df.iterrows():
    sic = clean_code(r['sic_code'])
    sic_title = clean_text(r['sic_title'])
    naics = clean_code(r['naics_code'])
    naics_title = clean_text(r['naics_title'])
    if sic and naics:
        rows.append((sic, sic_title, naics, naics_title))

if rows:
    execute_values(cur, """
        INSERT INTO naics_sic_crosswalk (sic_code, sic_title, naics_2002_code, naics_2002_title)
        VALUES %s ON CONFLICT DO NOTHING
    """, rows)
print(f"   Loaded {len(rows):,} mappings")

# Load NAICS 2022 structure
print("\n6. Loading NAICS 2022 structure...")
df = pd.read_excel(os.path.join(crosswalk_dir, 'naics_2022_structure.xlsx'), header=1)
df.columns = ['change_indicator', 'naics_code', 'naics_title']

rows = []
for _, r in df.iterrows():
    code = clean_naics_code(r['naics_code'])
    title = clean_text(r['naics_title'])
    change = clean_text(r['change_indicator'])
    if code:
        # Extract numeric part for level
        numeric = re.sub(r'[^\d]', '', str(code))
        code_level = len(numeric) if numeric else None
        rows.append((2022, code, title, code_level, change[:15] if change else None))

if rows:
    execute_values(cur, """
        INSERT INTO naics_codes_reference (naics_version, naics_code, naics_title, code_level, change_indicator)
        VALUES %s ON CONFLICT DO NOTHING
    """, rows)
print(f"   Loaded {len(rows):,} codes")

# Load NAICS 2017 structure
print("\n7. Loading NAICS 2017 structure...")
df = pd.read_excel(os.path.join(crosswalk_dir, 'naics_2017_structure.xlsx'), header=1)
df.columns = ['change_indicator', 'naics_code', 'naics_title']

rows = []
for _, r in df.iterrows():
    code = clean_naics_code(r['naics_code'])
    title = clean_text(r['naics_title'])
    change = clean_text(r['change_indicator'])
    if code:
        numeric = re.sub(r'[^\d]', '', str(code))
        code_level = len(numeric) if numeric else None
        rows.append((2017, code, title, code_level, change[:15] if change else None))

if rows:
    execute_values(cur, """
        INSERT INTO naics_codes_reference (naics_version, naics_code, naics_title, code_level, change_indicator)
        VALUES %s ON CONFLICT DO NOTHING
    """, rows)
print(f"   Loaded {len(rows):,} codes")

conn.close()
print("\n" + "="*70)
print("NAICS CROSSWALK LOADING COMPLETE")
print("="*70)
