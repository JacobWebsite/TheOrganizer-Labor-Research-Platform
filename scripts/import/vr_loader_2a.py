import os
from db_config import get_connection
"""
VR Data Loader - Checkpoint 2A (Fixed)
Parses voluntary_recognitions.csv and loads into PostgreSQL
Handles duplicates with ON CONFLICT
"""
import csv
import re
import psycopg2
from datetime import datetime
from collections import Counter

# Database connection
conn = get_connection()
conn.autocommit = True  # Use autocommit to avoid transaction issues
cur = conn.cursor()

def parse_date(date_str):
    """Parse M/D/YYYY date format, return None for invalid"""
    if not date_str or not date_str.strip():
        return None
    date_str = date_str.strip()
    
    # Handle typos like "20021-12-13" -> "2021-12-13"
    if re.match(r'^\d{5}-\d{2}-\d{2}$', date_str):
        date_str = date_str[1:]
    if re.match(r'^\d{5}-', date_str):
        date_str = date_str[:4] + date_str[5:]
    
    try:
        return datetime.strptime(date_str, '%m/%d/%Y').date()
    except:
        pass
    try:
        return datetime.strptime(date_str[:10], '%Y-%m-%d').date()
    except:
        pass
    return None

def parse_employee_count(emp_str):
    """Parse employee count, handling 'approx. 29' etc."""
    if not emp_str or not emp_str.strip():
        return None
    match = re.search(r'(\d+)', emp_str.replace(',', ''))
    if match:
        return int(match.group(1))
    return None

def extract_region(case_number, regional_office):
    """Extract NLRB region number"""
    if not case_number:
        return None
    match = re.match(r'^(\d{1,2})-VR-', case_number)
    if match:
        return int(match.group(1))
    if regional_office:
        match = re.search(r'Region (\d+)', regional_office)
        if match:
            return int(match.group(1))
    return None

def determine_case_format(case_number):
    if not case_number:
        return None
    if re.match(r'^\d{1,2}-VR-', case_number):
        return 'old'
    if re.match(r'^1-\d{9,}', case_number):
        return 'new'
    return 'other'

def normalize_name(name):
    if not name:
        return None
    name = ' '.join(name.split())
    name = re.sub(r'\s+(Inc\.?|LLC|Corp\.?|Co\.?|Ltd\.?)$', '', name, flags=re.IGNORECASE)
    return name[:500] if name else None

print("=" * 60)
print("VR Data Loader - Checkpoint 2A (Fixed)")
print("=" * 60)

csv_path = r'C:\Users\jakew\Downloads\labor-data-project\voluntary_recognitions.csv'
print(f"\nReading CSV from: {csv_path}")

records = []
with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        records.append(row)

print(f"Parsed {len(records)} records from CSV")

# Check for duplicates
case_numbers = [r.get('VR Case Number', '').strip() for r in records]
dupes = [cn for cn, count in Counter(case_numbers).items() if count > 1]
print(f"Duplicate case numbers found: {len(dupes)}")
if dupes[:5]:
    print(f"  Examples: {dupes[:5]}")

# Clear existing data
print("\nClearing existing VR data...")
cur.execute("DELETE FROM nlrb_voluntary_recognition")
print("Cleared existing records")

# Use ON CONFLICT to handle duplicates (keep first occurrence)
insert_sql = """
    INSERT INTO nlrb_voluntary_recognition (
        vr_case_number, region, regional_office, case_format,
        unit_city, unit_state,
        date_vr_request_received, date_voluntary_recognition,
        date_vr_notice_sent, date_notice_posted, date_posting_closes,
        date_r_case_petition_filed, case_filed_date,
        employer_name, employer_name_normalized, employer_name_upper,
        union_name, union_name_normalized,
        unit_description, num_employees,
        r_case_number, notes
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s, %s, %s
    )
    ON CONFLICT (vr_case_number) DO NOTHING
"""

print("\nLoading records...")
loaded = 0
skipped_dupes = 0
errors = []

for i, row in enumerate(records):
    try:
        case_num = row.get('VR Case Number', '').strip()
        if not case_num:
            errors.append(f"Row {i+1}: Missing case number")
            continue
        
        employer = row.get('Employer', '').strip()
        if not employer:
            errors.append(f"Row {i+1}: Missing employer")
            continue
            
        union = row.get('Union', '').strip() or 'Unknown'
        
        region = extract_region(case_num, row.get('Regional Office', ''))
        case_format = determine_case_format(case_num)
        
        date_request = parse_date(row.get('Date VR Request Received', ''))
        date_recognition = parse_date(row.get('Date of Voluntary Recogition', ''))
        date_notice_sent = parse_date(row.get('Date VR Notice Sent', ''))
        date_posted = parse_date(row.get('Date Notice Posted', ''))
        date_closes = parse_date(row.get('Date Posting Closes', ''))
        date_petition = parse_date(row.get('Date R Case Petition Filed (if any)', ''))
        date_filed = parse_date(row.get('Case Filed Date', ''))
        
        num_employees = parse_employee_count(row.get('Number of Employees', ''))
        
        employer_norm = normalize_name(employer)
        employer_upper = employer_norm.upper() if employer_norm else None
        union_norm = normalize_name(union)
        
        unit_city = row.get('Unit City', '').strip() or None
        unit_state = row.get('Unit State', '').strip() or None
        if unit_state and len(unit_state) != 2:
            unit_state = None
            
        regional_office = row.get('Regional Office', '').strip() or None
        unit_desc = row.get('Unit Description', '').strip() or None
        r_case = row.get('R Case Number', '').strip() or None
        notes = row.get('Notes', '').strip() or None
        
        cur.execute(insert_sql, (
            case_num, region, regional_office, case_format,
            unit_city, unit_state,
            date_request, date_recognition,
            date_notice_sent, date_posted, date_closes,
            date_petition, date_filed,
            employer, employer_norm, employer_upper,
            union, union_norm,
            unit_desc, num_employees,
            r_case, notes
        ))
        
        if cur.rowcount > 0:
            loaded += 1
        else:
            skipped_dupes += 1
        
        if (loaded + skipped_dupes) % 500 == 0:
            print(f"  Processed {loaded + skipped_dupes} records...")
            
    except Exception as e:
        errors.append(f"Row {i+1} ({case_num}): {str(e)[:80]}")

print(f"\n{'=' * 60}")
print(f"CHECKPOINT 2A COMPLETE")
print(f"{'=' * 60}")
print(f"Records loaded: {loaded}")
print(f"Duplicates skipped: {skipped_dupes}")
print(f"Errors: {len(errors)}")

if errors[:5]:
    print("\nFirst 5 errors:")
    for e in errors[:5]:
        print(f"  - {e}")

# Verify
cur.execute("SELECT COUNT(*) FROM nlrb_voluntary_recognition")
total = cur.fetchone()[0]
print(f"\n✅ Verification: {total} records in database")

cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(region) as with_region,
        COUNT(unit_state) as with_state,
        COUNT(num_employees) as with_employees,
        COUNT(date_vr_request_received) as with_date,
        COUNT(r_case_number) as with_r_case
    FROM nlrb_voluntary_recognition
""")
stats = cur.fetchone()
print(f"\nField coverage:")
print(f"  With region: {stats[1]} ({100*stats[1]/stats[0]:.1f}%)")
print(f"  With state: {stats[2]} ({100*stats[2]/stats[0]:.1f}%)")
print(f"  With employee count: {stats[3]} ({100*stats[3]/stats[0]:.1f}%)")
print(f"  With request date: {stats[4]} ({100*stats[4]/stats[0]:.1f}%)")
print(f"  With R case link: {stats[5]} ({100*stats[5]/stats[0]:.1f}%)")

cur.close()
conn.close()
print("\n✅ Ready for Checkpoint 2B: Extract affiliations and local numbers")
