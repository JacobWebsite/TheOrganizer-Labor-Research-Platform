import os
import re
import sys
import logging
import argparse
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from dotenv import load_dotenv
load_dotenv()

from db_config import get_connection
from src.python.cba_tool.cba_processor import CBAProcessor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Known union abbreviations for filename parsing
UNION_PATTERNS = [
    (r'\bAFGE\b', 'AFGE'),
    (r'\bNFFE\b', 'NFFE'),
    (r'\bNTEU\b', 'NTEU'),
    (r'\bAPWU\b', 'APWU'),
    (r'\bSEIU\b', 'SEIU'),
    (r'\bUNITE\s*HERE\b', 'UNITE HERE'),
    (r'\bPOAM\b', 'POAM'),
    (r'\bNBA\b', 'NBA Players Association'),
]

# Known employer patterns
EMPLOYER_PATTERNS = [
    (r'USDA\s+ARS', 'USDA Agricultural Research Service'),
    (r'DOT\s+SLSDC', 'DOT Saint Lawrence Seaway Development Corp'),
    (r'CFPB', 'Consumer Financial Protection Bureau'),
    (r'League.*CBA', 'League of Voluntary Hospitals'),
    (r'NBA.*Collective', 'National Basketball Association'),
    (r'Accenture', 'Accenture'),
    (r'Abbott\s*House', 'Abbott House'),
    (r'Genesee\s*County', 'Genesee County'),
    (r'10\s*Roads\s*Express', '10 Roads Express'),
    (r'New\s+Jersey\s+Insulation', 'New Jersey Insulation'),
    (r'Angelica', 'Halo OPCO LP dba Angelica'),
    (r'salmon\s*companies', 'Salmon Companies'),
]


class BulkCBALoader:
    def __init__(self, input_dir, *, dry_run=False):
        self.input_dir = Path(input_dir)
        self.processor = CBAProcessor()
        self.dry_run = dry_run

    def _get_loaded_filenames(self):
        """Return set of filenames already loaded in cba_documents."""
        loaded = set()
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT file_path FROM cba_documents WHERE extraction_status != 'failed'")
            for row in cur.fetchall():
                if row[0]:
                    loaded.add(Path(row[0]).name.lower())
            cur.close()
        finally:
            conn.close()
        return loaded

    def parse_filename(self, filename):
        """Extract employer/union metadata from filename using pattern matching."""
        stem = Path(filename).stem

        # Try to detect employer
        employer_name = None
        for pattern, name in EMPLOYER_PATTERNS:
            if re.search(pattern, stem, re.IGNORECASE):
                employer_name = name
                break

        # Try to detect union
        union_name = None
        for pattern, name in UNION_PATTERNS:
            if re.search(pattern, stem, re.IGNORECASE):
                union_name = name
                break

        # Fallback: use cleaned filename
        if not employer_name:
            # Clean up the stem for display
            cleaned = re.sub(r'[-_]', ' ', stem)
            cleaned = re.sub(r'\b\d{4}\b', '', cleaned)  # remove years
            cleaned = re.sub(r'\b(cba|contract|agreement|collective|bargaining|changes|final|redacted|pdf|http)\b',
                             '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            employer_name = cleaned[:80] if cleaned else stem[:80]

        if not union_name:
            union_name = "Unknown Union"

        return {
            "employer_name": employer_name,
            "union_name": union_name,
        }

    def run(self):
        if not self.input_dir.exists():
            logger.error(f"Input directory {self.input_dir} does not exist.")
            return

        pdf_files = sorted(self.input_dir.glob("*.pdf"), key=lambda p: p.name.lower())
        pdf_files += sorted(self.input_dir.glob("*.PDF"), key=lambda p: p.name.lower())
        # Deduplicate (case-insensitive)
        seen = set()
        unique_files = []
        for f in pdf_files:
            key = f.name.lower()
            if key not in seen:
                seen.add(key)
                unique_files.append(f)
        pdf_files = unique_files

        logger.info(f"Found {len(pdf_files)} PDF files in {self.input_dir}")

        # Check for already-loaded files
        loaded = self._get_loaded_filenames()
        logger.info(f"Already loaded in DB: {len(loaded)} documents")

        results = {"success": 0, "failed": 0, "skipped": 0, "needs_ocr": 0}

        for i, file_path in enumerate(pdf_files, 1):
            fname_lower = file_path.name.lower()
            if fname_lower in loaded:
                logger.info(f"[{i}/{len(pdf_files)}] SKIP (already loaded): {file_path.name}")
                results["skipped"] += 1
                continue

            metadata = self.parse_filename(file_path.name)
            logger.info(f"[{i}/{len(pdf_files)}] Processing: {file_path.name}")
            logger.info(f"  Employer: {metadata['employer_name']} | Union: {metadata['union_name']}")

            if self.dry_run:
                logger.info(f"  [DRY RUN] Would process {file_path.name}")
                continue

            try:
                result = self.processor.process_pdf(
                    pdf_path=str(file_path),
                    employer_name=metadata["employer_name"],
                    union_name=metadata["union_name"],
                    source_name="Bulk Upload",
                    source_url=f"local://{file_path.name}",
                )
                cba_id = result["cba_id"]
                status = result["status"]
                provisions = result["provisions_inserted"]

                if status == "needs_ocr":
                    logger.warning(f"  -> cba_id={cba_id} NEEDS OCR (scanned PDF, {result.get('is_scanned')})")
                    results["needs_ocr"] += 1
                elif status == "completed":
                    logger.info(f"  -> cba_id={cba_id} OK: {provisions} provisions extracted")
                    results["success"] += 1
                elif status == "completed_empty":
                    logger.warning(f"  -> cba_id={cba_id} completed but 0 provisions")
                    results["success"] += 1
                else:
                    logger.warning(f"  -> cba_id={cba_id} status={status}")
                    results["failed"] += 1

                # Track loaded to prevent re-processing within same run
                loaded.add(fname_lower)

            except Exception as e:
                logger.error(f"  ERROR: {e}")
                results["failed"] += 1

        logger.info("")
        logger.info("=" * 50)
        logger.info("Bulk Load Complete:")
        logger.info(f"  Success:   {results['success']}")
        logger.info(f"  Needs OCR: {results['needs_ocr']}")
        logger.info(f"  Failed:    {results['failed']}")
        logger.info(f"  Skipped:   {results['skipped']}")
        logger.info(f"  Total:     {len(pdf_files)}")
        logger.info("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk load CBA PDFs from a directory.")
    parser.add_argument("--dir", default=r"C:\Users\jakew\Downloads\CBAs",
                        help="Directory containing CBA PDFs")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse filenames and show what would be processed without actually loading")
    args = parser.parse_args()

    loader = BulkCBALoader(args.dir, dry_run=args.dry_run)
    loader.run()
