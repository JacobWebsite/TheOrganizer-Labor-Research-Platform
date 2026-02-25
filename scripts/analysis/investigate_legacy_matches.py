"""
I14 - Legacy Match Quality Audit (Non-SAM Sources)

Samples old active matches from the earliest pipeline runs to check for
false positives ("poisoned" matches). For each source system, pulls 20
matches from the oldest run_ids and categorises them as CONFIRMED,
PLAUSIBLE, or SUSPECT based on name comparison heuristics.
"""
import argparse
import os
import random
import sys
from datetime import datetime

from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection

SOURCE_SYSTEMS = ("osha", "whd", "990", "sec", "bmf")

# Source name lookup queries per source_system
SOURCE_LOOKUPS = {
    "osha": (
        "SELECT establishment_name AS source_name, city, state "
        "FROM osha_establishments WHERE establishment_id = %s",
        None,
    ),
    "whd": (
        "SELECT trade_name AS source_name, city, state "
        "FROM whd_cases WHERE case_id = %s",
        None,
    ),
    "990": (
        "SELECT business_name AS source_name, state "
        "FROM national_990_combined WHERE id = %s::int",
        "SELECT organization_name AS source_name, state "
        "FROM national_990_filers WHERE id = %s::int",
    ),
    "sec": (
        "SELECT company_name AS source_name "
        "FROM sec_companies WHERE company_id = %s::int",
        None,
    ),
    "bmf": (
        "SELECT name AS source_name, state "
        "FROM bmf_organizations WHERE ein = %s",
        None,
    ),
}


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


def categorize_match(source_name, f7_name, evidence):
    """Categorise a match as CONFIRMED, PLAUSIBLE, or SUSPECT."""
    # Check evidence for name_similarity or EIN match
    if isinstance(evidence, dict):
        name_sim = evidence.get("name_similarity")
        if name_sim is not None:
            try:
                name_sim = float(name_sim)
                if name_sim >= 0.90:
                    return "CONFIRMED"
            except (TypeError, ValueError):
                pass
        # EIN-based match is always confirmed
        match_detail = evidence.get("match_method_detail", "")
        if "ein" in str(match_detail).lower():
            return "CONFIRMED"

    if not source_name or not f7_name:
        return "SUSPECT"

    # Exact name match
    if source_name.strip().upper() == f7_name.strip().upper():
        return "CONFIRMED"

    overlap = token_overlap(source_name, f7_name)
    if overlap >= 0.70:
        return "CONFIRMED"
    if overlap >= 0.40:
        return "PLAUSIBLE"
    return "SUSPECT"


def get_source_name(cur, source_system, source_id):
    """Look up the source record name for a given source_system and source_id."""
    primary_sql, fallback_sql = SOURCE_LOOKUPS.get(source_system, (None, None))
    if not primary_sql:
        return None

    try:
        cur.execute(primary_sql, (source_id,))
        row = cur.fetchone()
        if row:
            return row.get("source_name", None)
    except Exception:
        # Rollback after error to continue using the cursor
        cur.connection.rollback()

    if fallback_sql:
        try:
            cur.execute(fallback_sql, (source_id,))
            row = cur.fetchone()
            if row:
                return row.get("source_name", None)
        except Exception:
            cur.connection.rollback()

    return None


def md_table(headers, rows):
    """Build a markdown table string."""
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def analyze_source(cur, source_system):
    """Analyze one source system. Returns dict with results."""
    result = {
        "source_system": source_system,
        "oldest_run_ids": [],
        "sample_rows": [],
        "counts": {"CONFIRMED": 0, "PLAUSIBLE": 0, "SUSPECT": 0},
        "error": None,
    }

    try:
        # 1. Find oldest run_ids
        cur.execute("""
            SELECT DISTINCT run_id
            FROM unified_match_log
            WHERE source_system = %s AND status = 'active'
            ORDER BY run_id
            LIMIT 3
        """, (source_system,))
        run_rows = cur.fetchall()
        if not run_rows:
            result["error"] = "No active matches found"
            return result

        run_ids = tuple(r["run_id"] for r in run_rows)
        result["oldest_run_ids"] = list(run_ids)

        # 2. Sample 20 active matches from those oldest runs
        cur.execute("""
            SELECT uml.id, uml.source_id, uml.target_id, uml.match_method,
                   uml.confidence_score, uml.evidence, uml.run_id,
                   f.employer_name AS f7_name, f.city AS f7_city, f.state AS f7_state
            FROM unified_match_log uml
            LEFT JOIN f7_employers_deduped f ON f.employer_id = uml.target_id
            WHERE uml.source_system = %s
              AND uml.status = 'active'
              AND uml.run_id IN %s
            ORDER BY RANDOM()
            LIMIT 20
        """, (source_system, run_ids))
        samples = cur.fetchall()

        # 3. For each sample, look up source name and categorise
        for s in samples:
            source_name = get_source_name(cur, source_system, s["source_id"])
            f7_name = s.get("f7_name", "")
            evidence = s.get("evidence")
            category = categorize_match(source_name, f7_name, evidence)
            result["counts"][category] += 1

            result["sample_rows"].append({
                "source_name": source_name or "(not found)",
                "f7_name": f7_name or "(not found)",
                "method": s.get("match_method", ""),
                "confidence": s.get("confidence_score", ""),
                "run_id": s.get("run_id", ""),
                "category": category,
            })

    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="I14 - Legacy Match Quality Audit (Non-SAM Sources)"
    )
    parser.add_argument(
        "--output",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "docs", "investigations", "I14_legacy_poisoned_matches.md",
        ),
        help="Output markdown path",
    )
    args = parser.parse_args()

    random.seed(42)

    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        lines = []
        lines.append("# I14 - Legacy Match Quality Audit (Non-SAM Sources)")
        lines.append("")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # ------------------------------------------------------------------
        # Summary
        # ------------------------------------------------------------------
        lines.append("## Summary")
        lines.append("")
        lines.append("This audit samples active matches from the **oldest pipeline runs** "
                     "for each source system to assess whether early matches contain "
                     "false positives that have persisted uncorrected.")
        lines.append("")

        # ------------------------------------------------------------------
        # Methodology
        # ------------------------------------------------------------------
        lines.append("## Methodology")
        lines.append("")
        lines.append("For each source system (`osha`, `whd`, `990`, `sec`, `bmf`):")
        lines.append("")
        lines.append("1. Identify the 3 oldest `run_id` values with active matches")
        lines.append("2. Sample 20 active matches from those runs (random, seed=42)")
        lines.append("3. Look up the source record name from the source table")
        lines.append("4. Compare source name vs F7 employer name using:")
        lines.append("   - Evidence `name_similarity` if available (>=0.90 = CONFIRMED)")
        lines.append("   - EIN-based match method = CONFIRMED")
        lines.append("   - Token overlap >=0.70 = CONFIRMED, >=0.40 = PLAUSIBLE, else SUSPECT")
        lines.append("")

        # ------------------------------------------------------------------
        # Per-Source Results
        # ------------------------------------------------------------------
        lines.append("## Per-Source Results")
        lines.append("")

        all_results = []

        for source_system in SOURCE_SYSTEMS:
            print(f"  Analyzing {source_system}...")
            result = analyze_source(cur, source_system)
            all_results.append(result)

            lines.append(f"### {source_system.upper()}")
            lines.append("")

            if result["error"]:
                lines.append(f"**ERROR:** {result['error']}")
                lines.append("")
                continue

            lines.append(f"Oldest run_ids: `{', '.join(str(r) for r in result['oldest_run_ids'])}`")
            lines.append("")

            if result["sample_rows"]:
                sample_headers = ["Source_Name", "F7_Name", "Method", "Confidence", "Category"]
                sample_data = []
                for sr in result["sample_rows"]:
                    sample_data.append((
                        sr["source_name"][:40],
                        sr["f7_name"][:40],
                        sr["method"],
                        sr["confidence"],
                        sr["category"],
                    ))
                lines.append(md_table(sample_headers, sample_data))
                lines.append("")

                total_sampled = len(result["sample_rows"])
                lines.append(f"**{source_system.upper()} sample counts:** "
                             f"CONFIRMED={result['counts']['CONFIRMED']}, "
                             f"PLAUSIBLE={result['counts']['PLAUSIBLE']}, "
                             f"SUSPECT={result['counts']['SUSPECT']} "
                             f"(n={total_sampled})")
                lines.append("")
            else:
                lines.append("No samples available.")
                lines.append("")

        # ------------------------------------------------------------------
        # Aggregate Quality
        # ------------------------------------------------------------------
        lines.append("## Aggregate Quality")
        lines.append("")

        agg_headers = ["Source", "Sampled", "Confirmed", "Plausible", "Suspect", "Est. FP Rate"]
        agg_data = []
        total_confirmed = 0
        total_plausible = 0
        total_suspect = 0
        total_sampled_all = 0

        for result in all_results:
            if result["error"]:
                agg_data.append((
                    result["source_system"].upper(),
                    "ERROR", "-", "-", "-", "-",
                ))
                continue

            sampled = len(result["sample_rows"])
            c = result["counts"]["CONFIRMED"]
            p = result["counts"]["PLAUSIBLE"]
            s = result["counts"]["SUSPECT"]
            fp_rate = f"{s/sampled*100:.1f}%" if sampled else "N/A"

            total_confirmed += c
            total_plausible += p
            total_suspect += s
            total_sampled_all += sampled

            agg_data.append((
                result["source_system"].upper(),
                sampled, c, p, s, fp_rate,
            ))

        # Totals row
        overall_fp = (f"{total_suspect/total_sampled_all*100:.1f}%"
                      if total_sampled_all else "N/A")
        agg_data.append((
            "**TOTAL**",
            total_sampled_all, total_confirmed, total_plausible,
            total_suspect, overall_fp,
        ))

        lines.append(md_table(agg_headers, agg_data))
        lines.append("")

        # ------------------------------------------------------------------
        # Overall False Positive Estimate
        # ------------------------------------------------------------------
        lines.append("## Overall False Positive Estimate")
        lines.append("")
        if total_sampled_all > 0:
            fp_pct = total_suspect / total_sampled_all * 100
            lines.append(f"Across all {total_sampled_all} sampled matches from oldest runs:")
            lines.append("")
            lines.append(f"- **CONFIRMED:** {total_confirmed} ({total_confirmed/total_sampled_all*100:.1f}%)")
            lines.append(f"- **PLAUSIBLE:** {total_plausible} ({total_plausible/total_sampled_all*100:.1f}%)")
            lines.append(f"- **SUSPECT:** {total_suspect} ({fp_pct:.1f}%)")
            lines.append("")
            if fp_pct > 20:
                lines.append("**WARNING:** High false-positive rate in legacy matches. "
                             "Oldest runs may contain low-quality matches that were never "
                             "cleaned up by subsequent pipeline improvements.")
            elif fp_pct > 10:
                lines.append("**CAUTION:** Moderate false-positive rate. Some legacy matches "
                             "warrant review, particularly SUSPECT entries.")
            else:
                lines.append("Legacy match quality appears reasonable. SUSPECT matches are "
                             "within acceptable bounds for fuzzy matching.")
        else:
            lines.append("No matches were sampled -- cannot estimate false positive rate.")
        lines.append("")

        # ------------------------------------------------------------------
        # Recommendations
        # ------------------------------------------------------------------
        lines.append("## Recommendations")
        lines.append("")
        lines.append("1. **Review SUSPECT matches** -- Manually inspect flagged matches, "
                     "especially from the oldest run_ids, to confirm or reject them.")
        lines.append("2. **Re-run deterministic matcher** -- Use `--rematch-all` on "
                     "source systems with high FP rates to supersede old matches with "
                     "improved matching logic.")
        lines.append("3. **Apply name similarity floor** -- Ensure all active matches "
                     "meet minimum name similarity thresholds (0.75 for trigram, 0.80 "
                     "for RapidFuzz).")
        lines.append("4. **Version tracking** -- Compare match quality across run_ids "
                     "to verify that newer runs produce fewer false positives.")
        lines.append("5. **Automate periodic audits** -- Run this script after each "
                     "major pipeline update to track quality trends over time.")
        lines.append("")

        # Write output
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        # Print summary to stdout
        print()
        print("I14 Legacy Match Quality Audit complete.")
        print()
        for result in all_results:
            if result["error"]:
                print(f"  {result['source_system'].upper()}: ERROR - {result['error']}")
            else:
                sampled = len(result["sample_rows"])
                c = result["counts"]["CONFIRMED"]
                p = result["counts"]["PLAUSIBLE"]
                s = result["counts"]["SUSPECT"]
                fp = f"{s/sampled*100:.1f}%" if sampled else "N/A"
                print(f"  {result['source_system'].upper()}: {sampled} sampled, "
                      f"CONFIRMED={c}, PLAUSIBLE={p}, SUSPECT={s}, FP={fp}")
        print()
        print(f"  Overall: {total_sampled_all} sampled, "
              f"CONFIRMED={total_confirmed}, PLAUSIBLE={total_plausible}, "
              f"SUSPECT={total_suspect}, FP={overall_fp}")
        print(f"  Report: {args.output}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
