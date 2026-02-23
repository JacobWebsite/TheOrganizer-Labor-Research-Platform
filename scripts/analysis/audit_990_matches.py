import argparse
import os
import random
import sys
from collections import defaultdict

from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection

FUZZY_METHODS = {"FUZZY_SPLINK_ADAPTIVE", "FUZZY_TRIGRAM"}


def extract_similarity(evidence):
    if not isinstance(evidence, dict):
        return None
    for key in ("name_similarity", "trigram_sim", "similarity"):
        val = evidence.get(key)
        if val is None:
            continue
        try:
            return float(val)
        except (TypeError, ValueError):
            pass
    return None


def pick_990_table(cur):
    for candidate in ("national_990_combined", "national_990_filers"):
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (candidate,),
        )
        if cur.fetchone():
            return candidate
    raise RuntimeError("No 990 source table found (expected national_990_combined or national_990_filers)")


def main():
    parser = argparse.ArgumentParser(description="Audit 990/BMF matching quality")
    parser.add_argument(
        "--output",
        default="docs/investigations/I16_990_matching_quality.md",
        help="Output markdown path",
    )
    args = parser.parse_args()

    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    random.seed(42)
    try:
        source_990_table = pick_990_table(cur)

        cur.execute(
            """
            SELECT source_system, COUNT(*) AS cnt
            FROM unified_match_log
            WHERE status = 'active' AND source_system IN ('990', 'bmf')
            GROUP BY source_system
            ORDER BY cnt DESC
            """
        )
        src_counts = {r["source_system"]: r["cnt"] for r in cur.fetchall()}

        cur.execute(
            f"""
            SELECT uml.id, uml.source_system, uml.source_id, uml.target_id, uml.match_method,
                   COALESCE(uml.confidence_score, 0) AS confidence_score,
                   uml.evidence,
                   f.employer_name,
                   n.business_name AS org_name,
                   n.state,
                   n.ein,
                   n.ntee_code
            FROM unified_match_log uml
            LEFT JOIN {source_990_table} n ON n.id::text = uml.source_id
            LEFT JOIN f7_employers_deduped f ON f.employer_id = uml.target_id
            WHERE uml.status = 'active' AND uml.source_system = '990'
            """
        )
        rows_990 = cur.fetchall()
        total_990 = len(rows_990)

        by_method = defaultdict(list)
        for r in rows_990:
            by_method[r["match_method"]].append(r)

        ein_exact_count = len(by_method.get("EIN_EXACT", []))

        # Verify EIN path via legacy table (closest available target-side EIN path in this DB)
        cur.execute(
            """
            SELECT COUNT(*) AS verified
            FROM unified_match_log uml
            JOIN national_990_f7_matches l
              ON l.n990_id::text = uml.source_id
             AND l.f7_employer_id = uml.target_id
            WHERE uml.status = 'active'
              AND uml.source_system = '990'
              AND uml.match_method = 'EIN_EXACT'
              AND l.ein IS NOT NULL
              AND btrim(l.ein) <> ''
            """
        )
        ein_verified_legacy = cur.fetchone()["verified"]

        # 990 records that appear in legacy table but are not active in unified_match_log
        cur.execute(
            """
            SELECT l.n990_id, l.ein, l.f7_employer_id
            FROM national_990_f7_matches l
            LEFT JOIN unified_match_log uml
              ON uml.source_system = '990'
             AND uml.source_id = l.n990_id::text
             AND uml.target_id = l.f7_employer_id
             AND uml.status = 'active'
            WHERE uml.id IS NULL
            LIMIT 20
            """
        )
        legacy_unmatched = cur.fetchall()

        # Name+state near-match opportunities without active 990 match.
        # Use a bounded candidate set for stable runtime.
        cur.execute(
            f"""
            WITH unmatched_990 AS (
                SELECT n.id AS n990_id,
                       n.business_name AS org_name,
                       n.state
                FROM {source_990_table} n
                WHERE n.business_name IS NOT NULL
                  AND n.state IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM unified_match_log uml
                      WHERE uml.source_system = '990'
                        AND uml.source_id = n.id::text
                        AND uml.status = 'active'
                  )
                LIMIT 500
            )
            SELECT u.n990_id,
                   u.org_name,
                   u.state,
                   f.employer_id,
                   f.employer_name,
                   similarity(lower(u.org_name), lower(f.employer_name)) AS sim
            FROM unmatched_990 u
            JOIN LATERAL (
                SELECT employer_id, employer_name
                FROM f7_employers_deduped f
                WHERE f.state = u.state
                  AND f.employer_name IS NOT NULL
                  AND left(lower(f.employer_name), 1) = left(lower(u.org_name), 1)
                ORDER BY similarity(lower(u.org_name), lower(f.employer_name)) DESC
                LIMIT 1
            ) f ON true
            WHERE similarity(lower(u.org_name), lower(f.employer_name)) >= 0.75
            ORDER BY sim DESC
            LIMIT 20
            """
        )
        similar_unmatched = cur.fetchall()

        low_sim_pairs = []
        for r in rows_990:
            sim = extract_similarity(r.get("evidence"))
            if sim is not None and sim < 0.85:
                r["name_similarity"] = sim
                low_sim_pairs.append(r)

        # crude entity-type mismatch heuristic
        mismatch_examples = []
        charity_terms = ("foundation", "church", "ministr", "charit", "nonprofit", "museum", "society")
        employer_terms = ("construction", "contractor", "manufacturing", "logistics", "trucking", "restaurant", "services")
        for r in rows_990:
            org = (r.get("org_name") or "").lower()
            emp = (r.get("employer_name") or "").lower()
            if any(t in org for t in charity_terms) and any(t in emp for t in employer_terms):
                mismatch_examples.append(r)
            if len(mismatch_examples) >= 20:
                break

        lines = []
        lines.append("# I16 990/BMF Matching Quality Audit")
        lines.append("")
        lines.append("## Summary")
        lines.append(f"- 990 source table used: `{source_990_table}`")
        lines.append(f"- Active 990 matches: **{src_counts.get('990', 0):,}**")
        lines.append(f"- Active BMF matches: **{src_counts.get('bmf', 0):,}**")
        lines.append(f"- 990 methods observed: **{len(by_method):,}**")
        lines.append("")

        lines.append("## Method Distribution (990)")
        lines.append("| Method | Count | Percent | Avg confidence |")
        lines.append("|---|---:|---:|---:|")
        for method, method_rows in sorted(by_method.items(), key=lambda kv: len(kv[1]), reverse=True):
            count = len(method_rows)
            pct = (count / total_990 * 100.0) if total_990 else 0.0
            avg_conf = sum(float(r["confidence_score"] or 0) for r in method_rows) / count
            lines.append(f"| {method} | {count:,} | {pct:.1f}% | {avg_conf:.3f} |")

        lines.append("")
        lines.append("## EIN Validation")
        lines.append(f"- 990 active matches with `EIN_EXACT`: **{ein_exact_count:,}**")
        lines.append(f"- `EIN_EXACT` matches verifiable via `national_990_f7_matches` EIN path: **{ein_verified_legacy:,}**")
        if ein_exact_count:
            lines.append(f"- Legacy-EIN verification rate: **{(ein_verified_legacy / ein_exact_count) * 100:.1f}%**")
        lines.append("- Note: `f7_employers_deduped` has no EIN column; target-side EIN validation uses `national_990_f7_matches` as proxy.")

        lines.append("")
        lines.append("## Potential Coverage Gaps")
        lines.append(f"- Legacy 990->F7 links not present as active UML rows (sampled): **{len(legacy_unmatched):,}**")
        for r in legacy_unmatched:
            lines.append(f"- n990_id={r['n990_id']} ein={r['ein']} -> f7={r['f7_employer_id']}")

        lines.append("")
        lines.append(f"- High-similarity name+state candidates with no active 990 match (sampled): **{len(similar_unmatched):,}**")
        for r in similar_unmatched:
            lines.append(
                f"- n990 `{r['n990_id']}` ({r['state']}) {r['org_name']} -> f7 `{r['employer_id']}` {r['employer_name']} (sim={float(r['sim']):.3f})"
            )

        lines.append("")
        lines.append("## Quality Risks")
        lines.append(f"- Active 990 matches with extracted name_similarity < 0.85: **{len(low_sim_pairs):,}**")
        for r in random.sample(low_sim_pairs, k=min(20, len(low_sim_pairs))):
            lines.append(
                f"- UML `{r['id']}` sim={r['name_similarity']:.3f} | {r.get('org_name') or '<org>'} -> {r.get('employer_name') or '<employer>'}"
            )

        lines.append("")
        lines.append(f"- Potential entity-type mismatches (heuristic sample): **{len(mismatch_examples):,}**")
        for r in mismatch_examples:
            lines.append(
                f"- UML `{r['id']}` ntee={r.get('ntee_code')} | {r.get('org_name') or '<org>'} -> {r.get('employer_name') or '<employer>'}"
            )

        lines.append("")
        lines.append("## Recommendations")
        lines.append("- Resolve low-similarity (<0.85) 990 matches with manual review or stricter floor in fallback fuzzy path.")
        lines.append("- Reconcile legacy `national_990_f7_matches` links into `unified_match_log` or formally deprecate unmatched legacy rows.")
        lines.append("- Consider adding EIN crosswalk for F7 targets to enable direct EIN validation beyond legacy bridge.")

        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        print(f"Wrote {args.output}")
        print(f"Active 990 matches: {src_counts.get('990', 0):,}; BMF: {src_counts.get('bmf', 0):,}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
