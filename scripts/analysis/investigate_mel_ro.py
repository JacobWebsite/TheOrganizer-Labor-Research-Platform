"""
I19 - Mel-Ro Construction OSHA Match Spot Check

Investigates whether Mel-Ro Construction (reported to have 179 OSHA matches)
has false positives from many-to-one matching inflation. Samples 20 matches
and categorises each as TRUE_MATCH, PLAUSIBLE, or SUSPECT.
"""
import argparse
import os
import random
import sys
from datetime import datetime

from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection


def token_overlap(a, b):
    """Return the fraction of shared tokens between two name strings."""
    if not a or not b:
        return 0.0
    tokens_a = set(a.upper().split())
    tokens_b = set(b.upper().split())
    if not tokens_a or not tokens_b:
        return 0.0
    overlap = tokens_a & tokens_b
    return len(overlap) / max(len(tokens_a), len(tokens_b))


def categorize_match(f7_name, osha_name):
    """Simple heuristic to categorise a match."""
    if not f7_name or not osha_name:
        return "SUSPECT"
    if f7_name.strip().upper() == osha_name.strip().upper():
        return "TRUE_MATCH"
    if token_overlap(f7_name, osha_name) > 0.80:
        return "PLAUSIBLE"
    return "SUSPECT"


def md_table(headers, rows):
    """Build a markdown table string."""
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="I19 - Mel-Ro Construction OSHA Match Spot Check"
    )
    parser.add_argument(
        "--output",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "docs", "investigations", "I19_mel_ro_spot_check.md",
        ),
        help="Output markdown path",
    )
    args = parser.parse_args()

    random.seed(42)

    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # ------------------------------------------------------------------
        # 1. Find Mel-Ro in f7_employers_deduped
        # ------------------------------------------------------------------
        cur.execute("""
            SELECT employer_id, employer_name, city, state, naics, latest_unit_size
            FROM f7_employers_deduped
            WHERE LOWER(employer_name) LIKE '%%mel-ro%%'
               OR LOWER(employer_name) LIKE '%%mel ro%%'
               OR LOWER(employer_name) LIKE '%%melro%%'
            ORDER BY employer_name
            LIMIT 20
        """)
        mel_ro_rows = cur.fetchall()

        # Try to find the actual "Mel-Ro Construction" entry first
        target = None
        for row in mel_ro_rows:
            if "mel-ro" in row["employer_name"].lower() or "mel ro" in row["employer_name"].lower():
                target = row
                break

        # If we found Mel-Ro, check it has OSHA matches. If not, fall back.
        fallback = False
        if target:
            target_id = target["employer_id"]
            target_name = target["employer_name"]
            cur.execute("""
                SELECT COUNT(*) AS cnt
                FROM unified_match_log
                WHERE target_id = %s AND source_system = 'osha' AND status = 'active'
            """, (target_id,))
            if cur.fetchone()["cnt"] == 0:
                fallback = True  # Mel-Ro exists but has 0 OSHA matches
        else:
            fallback = True

        if fallback:
            # Pick the employer with the most OSHA matches for a meaningful spot check
            cur.execute("""
                SELECT target_id, COUNT(*) AS match_count
                FROM unified_match_log
                WHERE source_system = 'osha' AND status = 'active'
                GROUP BY target_id
                ORDER BY match_count DESC
                LIMIT 10
            """)
            top_rows = cur.fetchall()
            if not top_rows:
                print("ERROR: No active OSHA matches found at all.")
                return

            cur.execute("""
                SELECT employer_id, employer_name, city, state, naics, latest_unit_size
                FROM f7_employers_deduped
                WHERE employer_id = %s
            """, (top_rows[0]["target_id"],))
            target_row = cur.fetchone()
            if target_row:
                target = target_row
                target_id = target["employer_id"]
                target_name = target["employer_name"]
            else:
                target_id = top_rows[0]["target_id"]
                target_name = target_id
                target = {"employer_id": target_id, "employer_name": target_id,
                          "city": "?", "state": "?", "naics": "?", "latest_unit_size": "?"}
            mel_ro_rows = [target] + (mel_ro_rows or [])

        # ------------------------------------------------------------------
        # 2. Get ALL active OSHA matches for the target
        # ------------------------------------------------------------------
        cur.execute("""
            SELECT uml.id, uml.source_id, uml.target_id, uml.match_method,
                   uml.confidence_score, uml.evidence,
                   o.estab_name AS establishment_name, o.site_city AS osha_city, o.site_state AS osha_state,
                   o.naics_code AS osha_naics
            FROM unified_match_log uml
            JOIN osha_establishments o ON o.establishment_id = uml.source_id
            WHERE uml.target_id = %s
              AND uml.source_system = 'osha'
              AND uml.status = 'active'
            ORDER BY uml.match_method, uml.confidence_score DESC
        """, (target_id,))
        all_matches = cur.fetchall()
        total_matches = len(all_matches)

        # ------------------------------------------------------------------
        # 3. Sample 20 matches
        # ------------------------------------------------------------------
        if total_matches <= 20:
            sample = list(all_matches)
        else:
            sample = random.sample(all_matches, 20)

        # ------------------------------------------------------------------
        # 4. Categorise each sampled match
        # ------------------------------------------------------------------
        f7_name = target.get("employer_name", "")
        f7_city = target.get("city", "")
        f7_state = target.get("state", "")

        sample_rows = []
        cat_counts = {"TRUE_MATCH": 0, "PLAUSIBLE": 0, "SUSPECT": 0}

        for m in sample:
            osha_name = m.get("establishment_name", "")
            osha_city = m.get("osha_city", "")
            osha_state = m.get("osha_state", "")
            method = m.get("match_method", "")
            conf = m.get("confidence_score", "")
            city_match = "Yes" if (f7_city or "").upper() == (osha_city or "").upper() else "No"
            state_match = "Yes" if (f7_state or "").upper() == (osha_state or "").upper() else "No"
            cat = categorize_match(f7_name, osha_name)
            cat_counts[cat] += 1

            sample_rows.append((
                f7_name, osha_name, city_match, state_match,
                method, conf, cat,
            ))

        # ------------------------------------------------------------------
        # 5. Match method distribution (all matches)
        # ------------------------------------------------------------------
        method_dist = {}
        for m in all_matches:
            mm = m.get("match_method", "UNKNOWN")
            method_dist[mm] = method_dist.get(mm, 0) + 1

        # ------------------------------------------------------------------
        # Build Markdown report
        # ------------------------------------------------------------------
        suspect_count = cat_counts["SUSPECT"]
        sample_size = len(sample)
        fp_rate = (suspect_count / sample_size * 100) if sample_size else 0

        lines = []
        lines.append("# I19 - Mel-Ro Construction OSHA Match Spot Check")
        lines.append("")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        if fallback:
            lines.append("Mel-Ro Construction was **not found** in `f7_employers_deduped`. "
                         f"Substituted the employer with the most OSHA matches: "
                         f"**{target_name}** (`{target_id}`).")
        else:
            lines.append(f"Investigated **{target_name}** (`{target_id}`) which has "
                         f"**{total_matches}** active OSHA matches in `unified_match_log`.")
        lines.append("")
        lines.append(f"- Sampled **{sample_size}** matches for spot-check")
        lines.append(f"- Estimated false-positive rate: **{fp_rate:.1f}%** ({suspect_count}/{sample_size} SUSPECT)")
        lines.append("")

        # Target Employer Details
        lines.append("## Target Employer Details")
        lines.append("")
        lines.append(f"| Field | Value |")
        lines.append(f"| --- | --- |")
        lines.append(f"| employer_id | `{target.get('employer_id', '')}` |")
        lines.append(f"| employer_name | {target.get('employer_name', '')} |")
        lines.append(f"| city | {target.get('city', '')} |")
        lines.append(f"| state | {target.get('state', '')} |")
        lines.append(f"| naics | {target.get('naics', '')} |")
        lines.append(f"| latest_unit_size | {target.get('latest_unit_size', '')} |")
        lines.append("")

        if not fallback and len(mel_ro_rows) > 1:
            lines.append("### Other Mel-Ro matches in f7_employers_deduped")
            lines.append("")
            other_headers = ["employer_id", "employer_name", "city", "state"]
            other_data = [(r["employer_id"], r["employer_name"], r["city"], r["state"])
                          for r in mel_ro_rows[1:]]
            lines.append(md_table(other_headers, other_data))
            lines.append("")

        # Total OSHA Match Count
        lines.append("## Total OSHA Match Count")
        lines.append("")
        lines.append(f"**{total_matches}** active OSHA matches for this employer.")
        lines.append("")

        # Match Method Distribution
        lines.append("## Match Method Distribution")
        lines.append("")
        dist_headers = ["Match Method", "Count", "Pct"]
        dist_data = []
        for mm in sorted(method_dist, key=method_dist.get, reverse=True):
            cnt = method_dist[mm]
            pct = cnt / total_matches * 100 if total_matches else 0
            dist_data.append((mm, cnt, f"{pct:.1f}%"))
        lines.append(md_table(dist_headers, dist_data))
        lines.append("")

        # Spot Check Sample
        lines.append("## Spot Check Sample")
        lines.append("")
        lines.append(f"Random sample of {sample_size} matches (seed=42):")
        lines.append("")
        spot_headers = ["F7_Name", "OSHA_Name", "City_Match", "State_Match",
                        "Method", "Confidence", "Category"]
        lines.append(md_table(spot_headers, sample_rows))
        lines.append("")

        # Category Summary
        lines.append("## Category Summary")
        lines.append("")
        cat_headers = ["Category", "Count", "Pct"]
        cat_data = []
        for cat_name in ("TRUE_MATCH", "PLAUSIBLE", "SUSPECT"):
            cnt = cat_counts[cat_name]
            pct = cnt / sample_size * 100 if sample_size else 0
            cat_data.append((cat_name, cnt, f"{pct:.1f}%"))
        lines.append(md_table(cat_headers, cat_data))
        lines.append("")

        # False Positive Rate Estimate
        lines.append("## False Positive Rate Estimate")
        lines.append("")
        lines.append(f"Based on the {sample_size}-match sample:")
        lines.append("")
        lines.append(f"- **SUSPECT** matches: {suspect_count} ({fp_rate:.1f}%)")
        plausible_count = cat_counts["PLAUSIBLE"]
        confirmed_count = cat_counts["TRUE_MATCH"]
        lines.append(f"- **PLAUSIBLE** matches: {plausible_count}")
        lines.append(f"- **TRUE_MATCH** matches: {confirmed_count}")
        lines.append("")
        if total_matches > 0:
            est_suspects = int(total_matches * fp_rate / 100)
            lines.append(f"Extrapolating to all {total_matches} matches: ~**{est_suspects}** "
                         f"may be false positives.")
        lines.append("")

        # Implications
        lines.append("## Implications")
        lines.append("")
        if fp_rate > 30:
            lines.append("**High false-positive rate detected.** Many-to-one matching inflation "
                         "is a significant concern for this employer. Consider:")
        elif fp_rate > 10:
            lines.append("**Moderate false-positive rate.** Some inflation exists. Consider:")
        else:
            lines.append("**Low false-positive rate.** Matches appear largely legitimate. Consider:")
        lines.append("")
        lines.append("- Reviewing SUSPECT matches for manual rejection")
        lines.append("- Adding name-similarity floor to OSHA matching for high-volume targets")
        lines.append("- Investigating whether multiple OSHA establishments are genuinely "
                     "linked to this employer (multi-site operations)")
        lines.append("- Cross-referencing with NAICS codes to validate industry alignment")
        lines.append("")

        # Write output
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        # Print summary to stdout
        print(f"I19 Mel-Ro Spot Check complete.")
        print(f"  Target: {target_name} ({target_id})")
        print(f"  Total OSHA matches: {total_matches}")
        print(f"  Sampled: {sample_size}")
        print(f"  TRUE_MATCH: {confirmed_count}, PLAUSIBLE: {plausible_count}, SUSPECT: {suspect_count}")
        print(f"  Estimated FP rate: {fp_rate:.1f}%")
        print(f"  Report: {args.output}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
