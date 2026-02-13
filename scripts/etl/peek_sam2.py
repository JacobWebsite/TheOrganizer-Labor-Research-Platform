"""Peek at SAM.gov raw data format."""
import zipfile
import os

SAM_ZIP = r"C:\Users\jakew\Downloads\SAM_PUBLIC_UTF-8_MONTHLY_V2_20260201.zip"

with zipfile.ZipFile(SAM_ZIP, 'r') as zf:
    fname = zf.infolist()[0].filename
    with zf.open(fname) as f:
        # Read first 20 lines raw
        print("=== FIRST 20 RAW LINES ===")
        for i in range(20):
            line = f.readline().decode('utf-8', errors='replace').rstrip('\n').rstrip('\r')
            if len(line) > 200:
                print(f"Line {i}: [{len(line)} chars] {line[:200]}...")
            else:
                print(f"Line {i}: [{len(line)} chars] {line}")
        print()

        # Read more to find the actual data pattern
        print("=== LINES 20-40 ===")
        for i in range(20):
            line = f.readline().decode('utf-8', errors='replace').rstrip('\n').rstrip('\r')
            if len(line) > 200:
                print(f"Line {i+20}: [{len(line)} chars] {line[:200]}...")
            else:
                print(f"Line {i+20}: [{len(line)} chars] {line}")
