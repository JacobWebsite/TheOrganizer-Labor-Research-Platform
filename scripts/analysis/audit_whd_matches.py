import argparse
import os
import random
import sys
from collections import defaultdict

from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection

FUZZY_METHODS = {"FUZZY_SPLINK_ADAPTIVE", "FUZZY_TRIGRAM"}
SIM_BANDS = [(0.80, 0.84), (0.85, 0.89), (0.90, 0.94), (0.95, 1.00)]


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


def band_label(sim):
    if sim is None:
        return None
    for lo, hi in SIM_BANDS:
        if lo <= sim <= hi:
            return f"{lo:.2f}-{hi:.2f}"
    if sim < 0.80:
        return "<0.80"
    if sim > 1.00:
        return ">1.00"
    return None


def pick_whd_table(cur):
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name IN ('flsa_cases', 'whd_cases')
        ORDER BY CASE WHEN table_name = 'flsa_cases' THEN 0 ELSE 1 END
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("No WHD source table found (expected flsa_cases or whd_cases)")
    return row["table_name"]


def table_has_column(cur, table_name: str, column_name: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        """,
        (table_name, column_name),
    )
    return cur.fetchone() is not None


def main():
    parser = argparse.ArgumentParser(description="Audit WHD matching quality")
    parser.add_argument(
        "--output",
        default="docs/investigations/I15_whd_matching_quality.md",
        help="Output markdown path",
    )
    args = parser.parse_args()

    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    random.seed(42)

    try:
        whd_table = pick_whd_table(cur)

        has_ein = table_has_column(cur, whd_table, "ein")
        ein_select = "w.ein," if has_ein else "NULL::text AS ein,"

        cur.execute(
            f"""
            SELECT uml.id, uml.source_id, uml.target_id, uml.match_method,
                   COALESCE(uml.confidence_score, 0) AS confidence_score,
                   uml.evidence,
                   w.trade_name,
                   w.legal_name,
                   w.state AS source_state,
                   {ein_select}
                   f.employer_name
            FROM unified_match_log uml
            LEFT JOIN {whd_table} w ON w.case_id::text = uml.source_id
            LEFT JOIN f7_employers_deduped f ON f.employer_id = uml.target_id
            WHERE uml.source_system = 'whd' AND uml.status = 'active'
            """
        )
        rows = cur.fetchall()
        total = len(rows)

        by_method = defaultdict(list)
        for r in rows:
            by_method[r["match_method"]].append(r)

        fuzzy_rows = [r for r in rows if r["match_method"] in FUZZY_METHODS]
        fuzzy_bands = defaultdict(list)
        for r in fuzzy_rows:
            sim = extract_similarity(r.get("evidence"))
            r["name_similarity"] = sim
            lbl = band_label(sim)
            if lbl:
                fuzzy_bands[lbl].append(r)

        cur.execute(
            f"""
            SELECT w.case_id,
                   COALESCE(w.legal_name, w.trade_name) AS source_name,
                   w.state,
                   f.employer_id,
                   f.employer_name
            FROM {whd_table} w
            JOIN f7_employers_deduped f
              ON f.state = w.state
             AND COALESCE(NULLIF(f.name_standard, ''), lower(regexp_replace(f.employer_name, '\\s+', ' ', 'g')))
                 = COALESCE(NULLIF(w.legal_name_normalized, ''), NULLIF(w.trade_name_normalized, ''),
                            lower(regexp_replace(COALESCE(w.legal_name, w.trade_name), '\\s+', ' ', 'g')))
            WHERE w.state IS NOT NULL
              AND COALESCE(w.legal_name, w.trade_name) IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM unified_match_log uml
                  WHERE uml.source_system = 'whd'
                    AND uml.source_id = w.case_id::text
                    AND uml.status = 'active'
              )
            LIMIT 20
            """
        )
        unmatched_exact = cur.fetchall()

        cur.execute(
            """
            SELECT COUNT(*) AS ein_exact_matches
            FROM unified_match_log
            WHERE source_system = 'whd'
              AND status = 'active'
              AND match_method = 'EIN_EXACT'
            """
        )
        ein_exact_matches = cur.fetchone()["ein_exact_matches"]

        if has_ein:
            cur.execute(
                f"""
                SELECT COUNT(*) AS total_with_ein
                FROM {whd_table}
                WHERE ein IS NOT NULL AND btrim(ein) <> ''
                """
            )
            total_with_ein = cur.fetchone()["total_with_ein"]

            cur.execute(
                f"""
                SELECT COUNT(*) AS matched_with_source_ein
                FROM unified_match_log uml
                JOIN {whd_table} w ON w.case_id::text = uml.source_id
                WHERE uml.source_system = 'whd'
                  AND uml.status = 'active'
                  AND w.ein IS NOT NULL
                  AND btrim(w.ein) <> ''
                """
            )
            matched_with_source_ein = cur.fetchone()["matched_with_source_ein"]

            cur.execute(
                f"""
                SELECT uml.id, uml.source_id, uml.target_id, w.ein AS whd_ein,
                       uml.evidence->>'ein' AS evidence_ein,
                       uml.evidence->>'matched_ein' AS evidence_matched_ein
                FROM unified_match_log uml
                JOIN {whd_table} w ON w.case_id::text = uml.source_id
                WHERE uml.source_system = 'whd'
                  AND uml.status = 'active'
                  AND (
                       (uml.evidence ? 'ein' AND w.ein IS NOT NULL AND uml.evidence->>'ein' <> w.ein)
                    OR (uml.evidence ? 'matched_ein' AND w.ein IS NOT NULL AND uml.evidence->>'matched_ein' <> w.ein)
                  )
                LIMIT 20
                """
            )
            ein_conflicts = cur.fetchall()
        else:
            total_with_ein = 0
            matched_with_source_ein = 0
            ein_conflicts = []

        lines = []
        lines.append("# I15 WHD Matching Quality Audit")
        lines.append("")
        lines.append("## Summary")
        lines.append(f"- Source table used: `{whd_table}`")
        lines.append(f"- Active WHD matches: **{total:,}**")
        lines.append(f"- Match methods observed: **{len(by_method):,}**")
        lines.append(f"- Fuzzy rows (Splink+Trigram): **{len(fuzzy_rows):,}**")
        lines.append("")

        lines.append("## Method Distribution")
        lines.append("| Method | Count | Percent | Avg confidence |")
        lines.append("|---|---:|---:|---:|")
        for method, method_rows in sorted(by_method.items(), key=lambda kv: len(kv[1]), reverse=True):
            count = len(method_rows)
            pct = (count / total * 100.0) if total else 0.0
            avg_conf = sum(float(r["confidence_score"] or 0) for r in method_rows) / count
            lines.append(f"| {method} | {count:,} | {pct:.1f}% | {avg_conf:.3f} |")

        lines.append("")
        lines.append("## Method Samples (5 each)")
        for method, method_rows in sorted(by_method.items(), key=lambda kv: len(kv[1]), reverse=True):
            lines.append(f"### {method}")
            sample = random.sample(method_rows, k=min(5, len(method_rows)))
            for r in sample:
                ev = r.get("evidence") or {}
                src = r.get("legal_name") or r.get("trade_name") or ev.get("source_name") or "<missing source>"
                tgt = r.get("employer_name") or ev.get("target_name") or "<missing target>"
                lines.append(f"- `{r['source_id']}` -> `{r['target_id']}` | conf={float(r['confidence_score'] or 0):.3f} | {src} => {tgt}")
            lines.append("")

        lines.append("## Fuzzy Similarity Distribution")
        lines.append("| Band | Count | Percent of fuzzy |")
        lines.append("|---|---:|---:|")
        fuzzy_total = len(fuzzy_rows)
        for lbl in ["<0.80", "0.80-0.84", "0.85-0.89", "0.90-0.94", "0.95-1.00"]:
            cnt = len(fuzzy_bands.get(lbl, []))
            pct = (cnt / fuzzy_total * 100.0) if fuzzy_total else 0.0
            lines.append(f"| {lbl} | {cnt:,} | {pct:.1f}% |")

        lines.append("")
        lines.append("### Fuzzy Band Samples (3 each)")
        for lbl in ["<0.80", "0.80-0.84", "0.85-0.89", "0.90-0.94", "0.95-1.00"]:
            lines.append(f"#### {lbl}")
            bucket = fuzzy_bands.get(lbl, [])
            if not bucket:
                lines.append("- No rows in this band.")
                continue
            for r in random.sample(bucket, k=min(3, len(bucket))):
                ev = r.get("evidence") or {}
                src = r.get("legal_name") or r.get("trade_name") or ev.get("source_name") or "<missing source>"
                tgt = r.get("employer_name") or ev.get("target_name") or "<missing target>"
                lines.append(f"- sim={r.get('name_similarity')} | `{r['source_id']}` -> `{r['target_id']}` | {src} => {tgt}")

        lines.append("")
        lines.append("## EIN Checks")
        lines.append(f"- WHD source has EIN column: **{has_ein}**")
        lines.append(f"- WHD records with EIN present: **{total_with_ein:,}**")
        lines.append(f"- Active WHD matches with method `EIN_EXACT`: **{ein_exact_matches:,}**")
        lines.append(f"- Active WHD matches where source record has EIN present: **{matched_with_source_ein:,}**")
        if total_with_ein:
            lines.append(f"- EIN exact rate among EIN-present records: **{(ein_exact_matches / total_with_ein) * 100:.2f}%**")
        lines.append(f"- Potential EIN conflicts found (sampled): **{len(ein_conflicts):,}**")
        for r in ein_conflicts:
            lines.append(
                f"- UML `{r['id']}` source `{r['source_id']}` target `{r['target_id']}` | whd_ein={r['whd_ein']} evidence_ein={r['evidence_ein']} evidence_matched_ein={r['evidence_matched_ein']}"
            )

        lines.append("")
        lines.append("## Potential Deterministic Gaps (Exact Name+State but No Active Match)")
        lines.append(f"- Found examples: **{len(unmatched_exact):,}** (limited to top 20)")
        for r in unmatched_exact:
            lines.append(
                f"- WHD `{r['case_id']}` ({r['state']}) {r['source_name']} -> F7 `{r['employer_id']}` {r['employer_name']}"
            )

        lines.append("")
        lines.append("## Recommended Actions")
        lines.append("- Expand deterministic pass to capture exact name+state WHD rows without active matches.")
        lines.append("- If EIN matching is intended, wire WHD EINs into a crosswalk table; `f7_employers_deduped` has no EIN field.")
        lines.append("- Keep duplicate-source resolution in place to prevent one case_id from staying linked to multiple targets.")

        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        print(f"Wrote {args.output}")
        print(f"Active WHD matches: {total:,}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
