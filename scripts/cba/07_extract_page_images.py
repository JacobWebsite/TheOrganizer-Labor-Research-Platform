"""Script 7: Extract PDF pages as PNG images for complex content.

Extracts selected pages (wage tables, schedules, etc.) as high-resolution
PNG images and stores metadata in cba_page_images.

Usage:
    py scripts/cba/07_extract_page_images.py --cba-id 26 --pages 139-142
    py scripts/cba/07_extract_page_images.py --cba-id 26 --auto
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection

import pdfplumber

# Output directory for images
IMAGE_BASE_DIR = Path(__file__).resolve().parents[2] / "data" / "cba_images"

# Patterns that indicate wage table content worth imaging
WAGE_TABLE_RE = re.compile(r"\$\s*\d+[.,]\d{2}")


def extract_page_images(
    pdf_path: str,
    cba_id: int,
    pages: list[int],
    resolution: int = 200,
    verbose: bool = False,
) -> list[dict]:
    """Extract specified pages as PNG images.

    Returns list of dicts with image metadata.
    """
    output_dir = IMAGE_BASE_DIR / str(cba_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num in pages:
            if page_num < 1 or page_num > len(pdf.pages):
                if verbose:
                    print(f"  Skipping page {page_num} (out of range)")
                continue

            page = pdf.pages[page_num - 1]  # 0-indexed
            img = page.to_image(resolution=resolution)

            filename = f"page_{page_num:03d}.png"
            filepath = output_dir / filename
            img.save(str(filepath))

            # Get dimensions
            width = img.original.width if hasattr(img, 'original') else None
            height = img.original.height if hasattr(img, 'original') else None

            results.append({
                "cba_id": cba_id,
                "page_number": page_num,
                "file_path": str(filepath),
                "image_format": "png",
                "width_px": width,
                "height_px": height,
            })

            if verbose:
                print(f"  Extracted page {page_num} -> {filepath.name} ({width}x{height})")

    return results


def detect_wage_table_pages(cba_id: int) -> list[int]:
    """Auto-detect pages that likely contain wage tables.

    Looks at cba_sections for sections with dollar amount patterns.
    """
    pages = set()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT section_text, page_start, page_end
                FROM cba_sections
                WHERE cba_id = %s
                """,
                [cba_id],
            )
            for row in cur.fetchall():
                text, page_start, page_end = row
                if text and WAGE_TABLE_RE.search(text):
                    # Count dollar patterns -- if many, it's likely a table
                    count = len(WAGE_TABLE_RE.findall(text))
                    if count >= 3 and page_start:
                        for p in range(page_start, (page_end or page_start) + 1):
                            pages.add(p)
    return sorted(pages)


def insert_page_images(images: list[dict]) -> int:
    """Insert page image records into cba_page_images."""
    if not images:
        return 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            inserted = 0
            for img in images:
                cur.execute(
                    """
                    INSERT INTO cba_page_images (
                        cba_id, page_number, file_path,
                        image_format, width_px, height_px
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (cba_id, page_number) DO UPDATE SET
                        file_path = EXCLUDED.file_path,
                        width_px = EXCLUDED.width_px,
                        height_px = EXCLUDED.height_px
                    """,
                    [
                        img["cba_id"], img["page_number"], img["file_path"],
                        img["image_format"], img["width_px"], img["height_px"],
                    ],
                )
                inserted += 1
            conn.commit()
    return inserted


def link_images_to_sections(cba_id: int) -> int:
    """Link page images to their containing sections and update flags."""
    updated = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get all images for this document
            cur.execute(
                "SELECT image_id, page_number, file_path FROM cba_page_images WHERE cba_id = %s",
                [cba_id],
            )
            images = cur.fetchall()

            # Get all sections with page ranges
            cur.execute(
                "SELECT section_id, page_start, page_end FROM cba_sections WHERE cba_id = %s",
                [cba_id],
            )
            sections = cur.fetchall()

            for image_id, img_page, img_path in images:
                for section_id, sec_start, sec_end in sections:
                    if sec_start and sec_end and sec_start <= img_page <= sec_end:
                        # Link image to section
                        cur.execute(
                            "UPDATE cba_page_images SET section_id = %s WHERE image_id = %s",
                            [section_id, image_id],
                        )

                        # Update section flags
                        cur.execute(
                            """
                            UPDATE cba_sections SET
                                has_page_images = TRUE,
                                page_image_paths = (
                                    SELECT COALESCE(jsonb_agg(pi.file_path), '[]'::jsonb)
                                    FROM cba_page_images pi
                                    WHERE pi.section_id = %s
                                )
                            WHERE section_id = %s
                            """,
                            [section_id, section_id],
                        )
                        updated += 1
                        break

            conn.commit()
    return updated


def parse_page_range(page_str: str) -> list[int]:
    """Parse page range string like '139-142' or '1,5,10-15'."""
    pages = []
    for part in page_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))
    return sorted(set(pages))


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract PDF pages as PNG images")
    parser.add_argument("--cba-id", type=int, required=True, help="cba_id to process")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pages", help="Page range (e.g., '139-142' or '1,5,10-15')")
    group.add_argument("--auto", action="store_true", help="Auto-detect wage table pages")
    parser.add_argument("--resolution", type=int, default=200, help="DPI resolution (default: 200)")
    parser.add_argument("--verbose", action="store_true", help="Print detailed output")
    args = parser.parse_args()

    # Get PDF path
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT file_path FROM cba_documents WHERE cba_id = %s",
                [args.cba_id],
            )
            row = cur.fetchone()
            if not row or not row[0]:
                print(f"ERROR: No file_path found for cba_id={args.cba_id}")
                sys.exit(1)
            pdf_path = row[0]

    if not Path(pdf_path).exists():
        print(f"ERROR: PDF not found at: {pdf_path}")
        sys.exit(1)

    # Determine which pages to extract
    if args.auto:
        pages = detect_wage_table_pages(args.cba_id)
        if not pages:
            print("  No wage table pages auto-detected.")
            sys.exit(0)
        print(f"  Auto-detected {len(pages)} wage table pages: {pages}")
    else:
        pages = parse_page_range(args.pages)

    print(f"Extracting {len(pages)} pages from cba_id={args.cba_id}")

    images = extract_page_images(
        pdf_path, args.cba_id, pages,
        resolution=args.resolution, verbose=args.verbose,
    )
    print(f"  Extracted {len(images)} page images")

    inserted = insert_page_images(images)
    print(f"  Inserted {inserted} records into cba_page_images")

    linked = link_images_to_sections(args.cba_id)
    print(f"  Linked {linked} images to sections")


if __name__ == "__main__":
    main()
