import os
"""
VR Data Loader - Checkpoint 2B
Extracts union affiliations and local numbers from union names
"""
import re
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
conn.autocommit = True
cur = conn.cursor()

print("=" * 60)
print("VR Data Loader - Checkpoint 2B: Extract Affiliations")
print("=" * 60)

# Affiliation patterns (ordered by priority - most specific first)
AFFILIATION_PATTERNS = [
    # Specific unions
    ('SEIU', r'SEIU|Service Employees International'),
    ('IBT', r'Teamsters|IBT|International Brotherhood of Teamsters'),
    ('UAW', r'\bUAW\b|United Auto|United Automobile'),
    ('CWA', r'\bCWA\b|Communications Workers of America'),
    ('UNITE HERE', r'UNITE\s*HERE|Unite\s*Here'),
    ('AFSCME', r'AFSCME'),
    ('UFCW', r'UFCW|United Food'),
    ('USW', r'\bUSW\b|United Steel|Steelworkers'),
    ('IBEW', r'IBEW|Electrical Workers'),
    ('LIUNA', r'LIUNA|Laborers.*International'),
    ('AFT', r'\bAFT\b|Federation of Teachers'),
    ('OPEIU', r'OPEIU|Office.*Professional.*Employees'),
    ('IAM', r'\bIAM\b|Machinists'),
    ('IUOE', r'IUOE|Operating Engineers'),
    ('TNG-CWA', r'NewsGuild|Newspaper Guild|TNG-CWA'),
    ('RWDSU', r'RWDSU'),
    ('ILWU', r'ILWU|Longshore.*Warehouse'),
    ('ILA', r'\bILA\b|International Longshoremen.*Association'),
    ('SMART', r'\bSMART\b|Sheet Metal'),
    ('BCTGM', r'BCTGM|Bakery.*Confectionery'),
    ('NATCA', r'NATCA|National Air Traffic Controllers'),
    ('ALPA', r'ALPA|Air Line Pilots'),
    ('AFA-CWA', r'\bAFA\b|Association of Flight Attendants'),
    ('IFPTE', r'IFPTE|Professional.*Technical Engineers'),
    ('TWU', r'\bTWU\b|Transport Workers Union'),
    ('ATU', r'\bATU\b|Amalgamated Transit'),
    ('NNU', r'NNU|National Nurses United'),
    ('IUPAT', r'IUPAT|Painters.*Allied Trades'),
    ('UBC', r'\bUBC\b|United Brotherhood.*Carpenters'),
    ('UA', r'United Association.*Plumbers|Plumbers.*Pipefitters'),
    ('AFGE', r'AFGE|American Federation.*Government'),
    ('NEA', r'\bNEA\b|National Education Association'),
    ('NAGE', r'NAGE|National Association.*Government'),
    ('APWU', r'APWU|American Postal Workers'),
    ('NALC', r'NALC|National Association.*Letter Carriers'),
    ('SEATU', r'SEATU|Seafarers.*Entertainment'),
]

def extract_affiliation(union_name):
    """Extract affiliation code from union name"""
    if not union_name:
        return None
    for affil, pattern in AFFILIATION_PATTERNS:
        if re.search(pattern, union_name, re.IGNORECASE):
            return affil
    return 'INDEPENDENT'

def extract_local_number(union_name):
    """Extract local number from union name"""
    if not union_name:
        return None
    
    # Common patterns: "Local 123", "Local No. 123", "Local #123"
    patterns = [
        r'Local\s*(?:No\.?\s*)?#?(\d+)',
        r'Local\s+(\d+)',
        r'\bL\.?\s*(\d+)\b',
        r'#(\d+)\b',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, union_name, re.IGNORECASE)
        if match:
            return match.group(1)
    
    # District/Council patterns
    district_match = re.search(r'District\s*(?:Council\s*)?(\d+)', union_name, re.IGNORECASE)
    if district_match:
        return f"DC{district_match.group(1)}"
    
    return None

# Get all records
cur.execute("""
    SELECT id, union_name 
    FROM nlrb_voluntary_recognition 
    WHERE union_name IS NOT NULL
""")
records = cur.fetchall()
print(f"\nProcessing {len(records)} records...")

# Extract affiliations
affiliation_counts = {}
local_counts = 0
updates = []

for record_id, union_name in records:
    affil = extract_affiliation(union_name)
    local_num = extract_local_number(union_name)
    
    affiliation_counts[affil] = affiliation_counts.get(affil, 0) + 1
    if local_num:
        local_counts += 1
    
    updates.append((affil, local_num, record_id))

# Batch update
print("Updating database...")
cur.executemany("""
    UPDATE nlrb_voluntary_recognition 
    SET extracted_affiliation = %s, extracted_local_number = %s
    WHERE id = %s
""", updates)

print(f"\nUpdated {len(updates)} records")

# Summary
print(f"\n{'=' * 60}")
print("AFFILIATION EXTRACTION RESULTS")
print(f"{'=' * 60}")
print(f"\nRecords with local number: {local_counts} ({100*local_counts/len(records):.1f}%)")
print(f"\nAffiliation distribution:")

for affil, count in sorted(affiliation_counts.items(), key=lambda x: -x[1]):
    pct = 100 * count / len(records)
    bar = '*' * int(pct / 2)
    print(f"  {affil:15} {count:4} ({pct:5.1f}%) {bar}")

# Verify
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(extracted_affiliation) as with_affil,
        COUNT(extracted_local_number) as with_local,
        COUNT(DISTINCT extracted_affiliation) as unique_affils
    FROM nlrb_voluntary_recognition
""")
stats = cur.fetchone()
print(f"\nVerification:")
print(f"  Total records: {stats[0]}")
print(f"  With affiliation: {stats[1]} ({100*stats[1]/stats[0]:.1f}%)")
print(f"  With local number: {stats[2]} ({100*stats[2]/stats[0]:.1f}%)")
print(f"  Unique affiliations: {stats[3]}")

# Show sample extractions
print(f"\nSample extractions:")
cur.execute("""
    SELECT union_name, extracted_affiliation, extracted_local_number
    FROM nlrb_voluntary_recognition
    WHERE extracted_local_number IS NOT NULL
    LIMIT 10
""")
for row in cur.fetchall():
    print(f"  {row[1]:15} Local {row[2]:6} <- {row[0][:50]}...")

cur.close()
conn.close()
print(f"\n{'=' * 60}")
print("CHECKPOINT 2B COMPLETE")
print("Ready for Checkpoint 2C: Final verification")
print(f"{'=' * 60}")
