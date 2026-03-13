"""Script 10: Link provisions to their containing sections via section_id FK.

For each provision, finds the section (same cba_id) with the best char-offset
overlap and sets provision.section_id.

Usage:
    py scripts/cba/10_link_provisions_sections.py                  # All contracts
    py scripts/cba/10_link_provisions_sections.py --cba-id 26     # Single contract
    py scripts/cba/10_link_provisions_sections.py --verbose        # Detailed output
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection


def link_provisions(cba_id: int, *, verbose: bool = False) -> tuple[int, int]:
    """Link provisions to sections for a given cba_id. Returns (linked, total)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Fetch all sections for this contract
            cur.execute(
                """SELECT section_id, char_start, char_end
                   FROM cba_sections
                   WHERE cba_id = %s
                   ORDER BY char_start""",
                [cba_id],
            )
            sections = cur.fetchall()

            if not sections:
                if verbose:
                    print(f"  cba_id={cba_id}: no sections found, skipping")
                return 0, 0

            # Fetch all provisions for this contract
            cur.execute(
                """SELECT provision_id, char_start, char_end
                   FROM cba_provisions
                   WHERE cba_id = %s""",
                [cba_id],
            )
            provisions = cur.fetchall()

            if not provisions:
                if verbose:
                    print(f"  cba_id={cba_id}: no provisions found, skipping")
                return 0, 0

            linked = 0
            for prov in provisions:
                prov_id = prov[0]
                prov_start = prov[1] or 0
                prov_end = prov[2] or prov_start

                best_section_id = None
                best_overlap = 0

                for sec in sections:
                    sec_id, sec_start, sec_end = sec[0], sec[1], sec[2]
                    # Calculate overlap
                    overlap_start = max(prov_start, sec_start)
                    overlap_end = min(prov_end, sec_end)
                    overlap = max(0, overlap_end - overlap_start)

                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_section_id = sec_id

                # If no char overlap, fall back to containment (provision start within section)
                if best_section_id is None:
                    for sec in sections:
                        sec_id, sec_start, sec_end = sec[0], sec[1], sec[2]
                        if sec_start <= prov_start <= sec_end:
                            best_section_id = sec_id
                            break

                if best_section_id is not None:
                    cur.execute(
                        "UPDATE cba_provisions SET section_id = %s WHERE provision_id = %s",
                        [best_section_id, prov_id],
                    )
                    linked += 1

            conn.commit()

    if verbose:
        print(f"  cba_id={cba_id}: linked {linked}/{len(provisions)} provisions to sections")

    return linked, len(provisions)


def main() -> None:
    parser = argparse.ArgumentParser(description="Link provisions to their containing sections")
    parser.add_argument("--cba-id", type=int, help="Process specific cba_id (default: all)")
    parser.add_argument("--verbose", action="store_true", help="Detailed output")
    args = parser.parse_args()

    with get_connection() as conn:
        with conn.cursor() as cur:
            if args.cba_id:
                cba_ids = [args.cba_id]
            else:
                cur.execute(
                    """SELECT DISTINCT cba_id FROM cba_sections ORDER BY cba_id"""
                )
                cba_ids = [row[0] for row in cur.fetchall()]

    if not cba_ids:
        print("No contracts with sections found.")
        return

    print(f"Linking provisions to sections for {len(cba_ids)} contract(s)")
    print("=" * 60)

    total_linked = 0
    total_provisions = 0

    for cba_id in cba_ids:
        linked, total = link_provisions(cba_id, verbose=args.verbose)
        total_linked += linked
        total_provisions += total

    pct = (total_linked / total_provisions * 100) if total_provisions else 0
    print(f"\nDone: {total_linked}/{total_provisions} provisions linked ({pct:.1f}%)")


if __name__ == "__main__":
    main()
