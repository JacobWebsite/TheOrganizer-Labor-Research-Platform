"""Peek at SAM.gov data structure."""
import zipfile
import csv
import io
import os

SAM_ZIP = r"C:\Users\jakew\Downloads\SAM_PUBLIC_UTF-8_MONTHLY_V2_20260201.zip"

print(f"Opening: {SAM_ZIP}")
print(f"Size: {os.path.getsize(SAM_ZIP)/1024/1024:.1f} MB")
print()

with zipfile.ZipFile(SAM_ZIP, 'r') as zf:
    print("=== Files in ZIP ===")
    for info in zf.infolist():
        print(f"  {info.filename} - {info.file_size/1024/1024:.1f} MB (compressed: {info.compress_size/1024/1024:.1f} MB)")
    print()

    # Read first file
    first_file = zf.infolist()[0]
    print(f"=== Reading: {first_file.filename} ===")

    with zf.open(first_file.filename) as f:
        # Read first few lines to detect format
        raw = f.read(50000)
        text = raw.decode('utf-8', errors='replace')
        lines = text.split('\n')

        print(f"First line (header) length: {len(lines[0])} chars")
        print(f"Total lines in sample: {len(lines)}")
        print()

        # Check if pipe-delimited, comma-delimited, or tab-delimited
        first_line = lines[0]
        pipe_count = first_line.count('|')
        comma_count = first_line.count(',')
        tab_count = first_line.count('\t')
        print(f"Delimiter detection: pipes={pipe_count}, commas={comma_count}, tabs={tab_count}")
        print()

        # Determine delimiter
        if pipe_count > comma_count and pipe_count > tab_count:
            delim = '|'
        elif tab_count > comma_count:
            delim = '\t'
        else:
            delim = ','

        print(f"Using delimiter: '{delim}'")
        print()

        # Parse header
        headers = first_line.split(delim)
        print(f"=== {len(headers)} COLUMNS ===")
        for i, h in enumerate(headers):
            print(f"  [{i:3d}] {h.strip()}")
        print()

        # Show first 3 data rows
        print("=== FIRST 3 DATA ROWS (key fields) ===")
        # Find key columns
        key_cols = []
        for name in ['UEI', 'EIN', 'DUNS', 'CAGE', 'LEGAL BUSINESS NAME', 'DBA NAME',
                      'PHYSICAL ADDRESS LINE 1', 'PHYSICAL ADDRESS CITY',
                      'PHYSICAL ADDRESS STATE', 'PHYSICAL ADDRESS ZIP',
                      'NAICS CODE', 'ENTITY STRUCTURE', 'SAM STATUS',
                      'ENTITY_UEI', 'ENTITY_EIN', 'ENTITY_DUNS',
                      'LEGAL_BUSINESS_NAME', 'DBA_NAME',
                      'SAM_EXTRACT_CODE', 'REGISTRATION_STATUS']:
            for i, h in enumerate(headers):
                if name.lower() in h.strip().lower():
                    key_cols.append((i, h.strip()))

        print(f"Found {len(key_cols)} key columns:")
        for i, name in key_cols:
            print(f"  [{i}] {name}")
        print()

        for row_idx in range(1, min(4, len(lines))):
            if not lines[row_idx].strip():
                continue
            fields = lines[row_idx].split(delim)
            print(f"--- Row {row_idx} ({len(fields)} fields) ---")
            for col_idx, col_name in key_cols:
                if col_idx < len(fields):
                    print(f"  {col_name}: {fields[col_idx].strip()[:80]}")
            print()
