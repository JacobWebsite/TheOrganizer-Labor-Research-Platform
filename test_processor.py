import os
import sys
from src.python.cba_tool.cba_processor import CBAProcessor

def test_single_document():
    # Use the League CBA found in archives
    sample_path = r"C:\Users\jakew\.local\bin\labor-data-project\archive\Claude Ai union project\2021-2024_League_CBA_Booklet_PDF_1.pdf"
    
    if not os.path.exists(sample_path):
        print(f"Sample not found at {sample_path}")
        return

    metadata = {
        "employer_name": "League of Voluntary Hospitals",
        "union_name": "1199SEIU United Healthcare Workers East",
        "source": "Local Archive",
        "url": "local://2021-2024_League_CBA_Booklet_PDF_1.pdf"
    }

    processor = CBAProcessor()
    
    print("--- Starting Assessment ---")
    assessment = processor.assess_document(sample_path)
    print(f"Assessment: {assessment}")

    print("\n--- Starting Processing ---")
    cba_id = processor.process_cba(sample_path, metadata)
    
    if cba_id:
        print(f"SUCCESS: CBA processed and saved with ID {cba_id}")
    else:
        print("FAILURE: CBA processing failed or document is scanned and requires OCR.")

if __name__ == "__main__":
    test_single_document()
