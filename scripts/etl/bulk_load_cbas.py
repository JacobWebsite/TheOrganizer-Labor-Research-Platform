import os
import sys
import logging
import argparse
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.python.cba_tool.cba_processor import CBAProcessor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BulkCBALoader:
    def __init__(self, input_dir):
        self.input_dir = Path(input_dir)
        self.processor = CBAProcessor()
        
    def parse_filename(self, filename):
        """
        Attempts to guess metadata from filename.
        Format expected: 'Employer Name - Union Name - Year.pdf' or 'Employer_Union_Year.pdf'
        """
        stem = Path(filename).stem
        parts = []
        if " - " in stem:
            parts = stem.split(" - ")
        elif "_" in stem:
            parts = stem.split("_")
        
        metadata = {
            "employer_name": parts[0] if len(parts) > 0 else "Unknown Employer",
            "union_name": parts[1] if len(parts) > 1 else "Unknown Union",
            "source": "Manual Bulk Upload",
            "url": f"file://{filename}"
        }
        return metadata

    def run(self):
        if not self.input_dir.exists():
            logger.error(f"Input directory {self.input_dir} does not exist.")
            return

        files = list(self.input_dir.glob("*.pdf"))
        logger.info(f"Found {len(files)} PDF files in {self.input_dir}")

        results = {"success": 0, "failed": 0, "skipped": 0}

        for file_path in files:
            try:
                # Basic metadata from filename
                metadata = self.parse_filename(file_path.name)
                
                logger.info(f"--- Processing {file_path.name} ---")
                cba_id = self.processor.process_cba(str(file_path), metadata)
                
                if cba_id:
                    logger.info(f"Successfully loaded {file_path.name} (ID: {cba_id})")
                    results["success"] += 1
                else:
                    logger.warning(f"Failed to process {file_path.name}")
                    results["failed"] += 1
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                results["failed"] += 1

        logger.info("
Bulk Load Complete:")
        logger.info(f"Success: {results['success']}")
        logger.info(f"Failed:  {results['failed']}")
        logger.info(f"Skipped: {results['skipped']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk load CBA PDFs from a directory.")
    parser.add_argument("--dir", default=r"C:\Users\jakew\.local\bin\labor-data-project\data\cbas", 
                        help="Directory containing CBA PDFs")
    
    args = parser.parse_args()
    
    loader = BulkCBALoader(args.dir)
    loader.run()
