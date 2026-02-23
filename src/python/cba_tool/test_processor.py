from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.python.cba_tool.cba_processor import CBAProcessor, default_test_pdf_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run CBA extraction test harness.")
    parser.add_argument("--pdf", type=str, default=str(default_test_pdf_path()))
    parser.add_argument("--employer-name", type=str, default="League of Voluntary Hospitals")
    parser.add_argument("--union-name", type=str, default="1199SEIU United Healthcare Workers East")
    parser.add_argument("--source-name", type=str, default="Local Archive")
    parser.add_argument("--source-url", type=str, default="local://2021-2024_League_CBA_Booklet_PDF_1.pdf")
    parser.add_argument("--model-id", type=str, default="models/gemini-flash-latest")
    parser.add_argument("--max-pages", type=int, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    processor = CBAProcessor(model_id=args.model_id)
    result = processor.process_pdf(
        pdf_path=Path(args.pdf),
        employer_name=args.employer_name,
        union_name=args.union_name,
        source_name=args.source_name,
        source_url=args.source_url,
        max_pages=args.max_pages,
    )
    print(result)


if __name__ == "__main__":
    main()
