"""Check for EIN/TIN in SAM data and verify key columns."""
import zipfile

SAM_ZIP = r"C:\Users\jakew\Downloads\SAM_PUBLIC_UTF-8_MONTHLY_V2_20260201.zip"

with zipfile.ZipFile(SAM_ZIP, 'r') as zf:
    fname = zf.infolist()[0].filename
    with zf.open(fname) as f:
        f.readline()  # skip BOF

        # Read 100 records and analyze specific columns
        records = []
        for i in range(100):
            line = f.readline().decode('utf-8', errors='replace').strip()
            fields = line.split('|')
            records.append(fields)

        # Column 22 - is it employees or something else?
        print("=== Column 22 values (first 20) ===")
        vals = set()
        for r in records:
            if len(r) > 22:
                vals.add(r[22])
        print(f"Unique values: {sorted(vals)[:30]}")
        print()

        # Check if EIN might be hidden - look for 9-digit patterns
        print("=== Searching for EIN-like patterns (9-digit numbers) ===")
        import re
        for col_idx in range(min(142, len(records[0]))):
            nine_digit_count = 0
            for r in records:
                if col_idx < len(r) and re.match(r'^\d{9}$', r[col_idx].strip()):
                    nine_digit_count += 1
            if nine_digit_count > 5:
                examples = [r[col_idx].strip() for r in records[:5] if col_idx < len(r)]
                print(f"  Column [{col_idx}]: {nine_digit_count}/100 look like EINs. Examples: {examples}")
        print()

        # Check column 1, 2, 4 - might be DUNS/EIN
        print("=== Columns 1, 2, 4 (potential IDs) ===")
        for col in [1, 2, 4]:
            vals = [r[col].strip() for r in records[:10] if col < len(r)]
            non_empty = [v for v in vals if v]
            print(f"  Col [{col}]: {len(non_empty)}/10 non-empty. Values: {vals[:5]}")
        print()

        # Column 30 - entity count? Number of employees?
        print("=== Column 30 values ===")
        vals = [r[30].strip() for r in records[:20] if len(r) > 30]
        print(f"  Values: {vals}")
        print()

        # Check col 20 more carefully
        print("=== Column 20 values (first 30 unique) ===")
        vals = set()
        for r in records:
            if len(r) > 20:
                vals.add(r[20])
        print(f"  Unique: {sorted(vals)[:30]}")
        print()

        # Look for entity type codes
        print("=== Column 27 (entity structure codes) ===")
        vals = {}
        for r in records:
            if len(r) > 27:
                v = r[27].strip()
                vals[v] = vals.get(v, 0) + 1
        for k, v in sorted(vals.items(), key=lambda x: -x[1])[:15]:
            print(f"  {k}: {v}")
        print()

        # Status codes column 5
        print("=== Column 5 (status) ===")
        vals = {}
        for r in records:
            if len(r) > 5:
                v = r[5].strip()
                vals[v] = vals.get(v, 0) + 1
        for k, v in sorted(vals.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v}")
        print()

        # Column 6
        print("=== Column 6 (purpose?) ===")
        vals = {}
        for r in records:
            if len(r) > 6:
                v = r[6].strip()
                vals[v] = vals.get(v, 0) + 1
        for k, v in sorted(vals.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v}")

        # Check state distribution
        print()
        print("=== Column 18 (state) distribution ===")
        vals = {}
        for r in records:
            if len(r) > 18:
                v = r[18].strip()
                vals[v] = vals.get(v, 0) + 1
        for k, v in sorted(vals.items(), key=lambda x: -x[1])[:10]:
            print(f"  {k}: {v}")
