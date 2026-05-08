"""
Test OpenDataLoader-PDF on 5 scanned CBA PDFs.
Evaluates: OCR quality, heading detection, article structure, speed.
"""
import os
import sys
import time
import json

# Java must be on PATH for opendataloader-pdf
java_home = r"C:\Program Files\Eclipse Adoptium\jdk-21.0.10.7-hotspot"
os.environ["JAVA_HOME"] = java_home
os.environ["PATH"] = os.path.join(java_home, "bin") + os.pathsep + os.environ["PATH"]

import opendataloader_pdf

DATA_DIR = r"C:\Users\jakew\.local\bin\Labor Data Project_real\data\cba_processed"
OUTPUT_DIR = r"C:\Users\jakew\.local\bin\Labor Data Project_real\data\cba_ocr_test"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 5 scanned PDFs of varying sizes (from database query)
TEST_FILES = [
    "133_cbrp0780.pdf",           # 148 pages, 3.1 MB
    "1114_cbrp1939.pdf",          # 140 pages, 4.1 MB
    "1520_cbrp0673.pdf",          # 97 pages, 1.3 MB
    "4073_ChicagoParkDistrict.pdf",  # 52 pages, 3.5 MB
    "658_cbrp0172.pdf",           # 51 pages, unknown
]

# Verify files exist
missing = []
found = []
for f in TEST_FILES:
    path = os.path.join(DATA_DIR, f)
    if os.path.exists(path):
        size_mb = os.path.getsize(path) / (1024 * 1024)
        found.append((f, path, size_mb))
        print(f"  OK: {f} ({size_mb:.1f} MB)")
    else:
        missing.append(f)
        print(f"  MISSING: {f}")

if missing:
    print(f"\nWARNING: {len(missing)} files missing. Testing {len(found)} files.")

if not found:
    print("ERROR: No test files found!")
    sys.exit(1)

print(f"\n{'='*70}")
print(f"TESTING {len(found)} SCANNED CBAs WITH OPENDATALOADER-PDF")
print(f"{'='*70}\n")

results = []

for filename, filepath, size_mb in found:
    print(f"\n--- Processing: {filename} ({size_mb:.1f} MB) ---")

    file_output_dir = os.path.join(OUTPUT_DIR, filename.replace(".pdf", ""))
    os.makedirs(file_output_dir, exist_ok=True)

    start = time.time()

    try:
        # Run conversion via hybrid server (force_ocr enabled on server)
        opendataloader_pdf.convert(
            input_path=[filepath],
            output_dir=file_output_dir,
            format="markdown",
            hybrid="docling-fast",
            hybrid_mode="full",
        )
        elapsed = time.time() - start

        # Find the output markdown file
        md_files = [f for f in os.listdir(file_output_dir) if f.endswith(".md")]

        if not md_files:
            print("  ERROR: No markdown output produced")
            results.append({
                "file": filename,
                "status": "no_output",
                "time_sec": elapsed,
            })
            continue

        md_path = os.path.join(file_output_dir, md_files[0])
        with open(md_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()

        # Analyze quality
        total_chars = len(text)
        total_words = len(text.split())
        lines = text.split("\n")
        total_lines = len(lines)

        # Count headings (articles)
        headings = [l for l in lines if l.startswith("#")]
        article_headings = [l for l in lines if "ARTICLE" in l.upper() or "Article" in l]

        # Count tables
        table_rows = [l for l in lines if "|" in l and l.strip().startswith("|")]

        # Sample first 2000 chars for quality check
        sample = text[:2000]

        # Common English words check (OCR quality proxy)
        common_words = {"the", "and", "of", "to", "in", "a", "is", "that", "for", "it",
                       "shall", "will", "not", "with", "be", "this", "are", "or", "by",
                       "employee", "employer", "union", "agreement", "article", "section",
                       "wages", "hours", "contract", "party", "work", "pay", "benefits"}
        words_lower = [w.lower().strip(".,;:()") for w in text.split()]
        recognized = sum(1 for w in words_lower if w in common_words)
        recognition_rate = recognized / max(len(words_lower), 1)

        result = {
            "file": filename,
            "status": "success",
            "time_sec": round(elapsed, 1),
            "total_chars": total_chars,
            "total_words": total_words,
            "total_lines": total_lines,
            "headings_found": len(headings),
            "article_headings": len(article_headings),
            "table_rows": len(table_rows),
            "word_recognition_rate": round(recognition_rate, 3),
            "sample_preview": sample[:500].replace("\n", " | "),
        }
        results.append(result)

        print(f"  Time: {elapsed:.1f}s")
        print(f"  Words: {total_words:,} | Lines: {total_lines:,}")
        print(f"  Headings: {len(headings)} | Article refs: {len(article_headings)}")
        print(f"  Table rows: {len(table_rows)}")
        print(f"  Word recognition: {recognition_rate:.1%}")
        print(f"  Preview: {sample[:200]}...")

    except Exception as e:
        elapsed = time.time() - start
        print(f"  ERROR after {elapsed:.1f}s: {e}")
        results.append({
            "file": filename,
            "status": "error",
            "time_sec": round(elapsed, 1),
            "error": str(e),
        })

# Summary
print(f"\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")

successes = [r for r in results if r["status"] == "success"]
errors = [r for r in results if r["status"] != "success"]

if successes:
    total_time = sum(r["time_sec"] for r in successes)
    avg_recognition = sum(r["word_recognition_rate"] for r in successes) / len(successes)
    total_articles = sum(r["article_headings"] for r in successes)
    total_tables = sum(r["table_rows"] for r in successes)

    print(f"Successful: {len(successes)}/{len(results)}")
    print(f"Total time: {total_time:.1f}s")
    print(f"Avg word recognition: {avg_recognition:.1%}")
    print(f"Total article refs found: {total_articles}")
    print(f"Total table rows found: {total_tables}")

if errors:
    print(f"\nFailed: {len(errors)}")
    for r in errors:
        print(f"  {r['file']}: {r.get('error', r['status'])}")

# Save full results
results_path = os.path.join(OUTPUT_DIR, "test_results.json")
with open(results_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nFull results saved to: {results_path}")
