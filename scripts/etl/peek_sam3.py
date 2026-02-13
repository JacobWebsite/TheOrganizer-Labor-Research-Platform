"""Map SAM.gov V2 column structure and count records."""
import zipfile

SAM_ZIP = r"C:\Users\jakew\Downloads\SAM_PUBLIC_UTF-8_MONTHLY_V2_20260201.zip"

with zipfile.ZipFile(SAM_ZIP, 'r') as zf:
    fname = zf.infolist()[0].filename
    with zf.open(fname) as f:
        header = f.readline().decode('utf-8').strip()
        print(f"BOF: {header}")
        print(f"  -> Record count: {header.split()[4]}")
        print()

        # Read first 5 data lines and split on pipe
        lines = []
        for i in range(5):
            line = f.readline().decode('utf-8', errors='replace').strip()
            fields = line.split('|')
            lines.append(fields)

        # Show column index -> value for first record
        print(f"=== COLUMN MAP (first record has {len(lines[0])} fields) ===")
        for i, val in enumerate(lines[0]):
            # Show all 5 rows' values for this column
            vals = [l[i] if i < len(l) else '?' for l in lines]
            sample = ' | '.join(v[:40] for v in vals)
            print(f"  [{i:3d}] {sample}")

        print()
        print("=== KEY FIELD IDENTIFICATION ===")
        # Based on SAM V2 spec, map known positions
        # Count total records
        print("Counting total records...")
        count = 5  # already read 5
        for line in f:
            count += 1
        print(f"Total data records: {count:,}")
