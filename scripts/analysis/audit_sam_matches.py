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


def assess_method(method, avg_conf, low_sim_share):
    if method in FUZZY_METHODS:
        if low_sim_share > 0.25:
            return "concerning"
        if avg_conf >= 0.9:
            return "good"
        return "concerning"
    if avg_conf >= 0.9:
        return "good"
    if avg_conf >= 0.75:
        return "acceptable"
    return "concerning"


def main():
    parser = argparse.ArgumentParser(description="Audit SAM matching quality")
    parser.add_argument(
        "--output",
        default="docs/investigations/I14_sam_matching_quality.md",
        help="Output markdown path",
    )
    args = parser.parse_args()

    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    random.seed(42)

    try:
        cur.execute(
            """
            SELECT uml.id, uml.source_id, uml.target_id, uml.match_method,
                   COALESCE(uml.confidence_score, 0) AS confidence_score,
                   uml.evidence,
                   s.legal_business_name,
                   f.employer_name
            FROM unified_match_log uml
            LEFT JOIN sam_entities s ON s.uei = uml.source_id
            LEFT JOIN f7_employers_deduped f ON f.employer_id = uml.target_id
            WHERE uml.source_system = 'sam' AND uml.status = 'active'
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
            """
            SELECT employer_id,
                   employer_name,
                   state,
                   COALESCE(NULLIF(name_standard, ''), lower(regexp_replace(employer_name, '\\s+', ' ', 'g'))) AS norm_name
            FROM f7_employers_deduped
            WHERE employer_name IS NOT NULL
              AND state IS NOT NULL
            """
        )
        f7_rows = cur.fetchall()
        f7_lookup = {}
        for f in f7_rows:
            key = (f["state"], f["norm_name"])
            if key not in f7_lookup:
                f7_lookup[key] = f

        cur.execute(
            """
            SELECT s.uei,
                   s.legal_business_name,
                   s.physical_state,
                   COALESCE(NULLIF(s.name_normalized, ''), lower(regexp_replace(s.legal_business_name, '\\s+', ' ', 'g'))) AS norm_name
            FROM sam_entities s
            WHERE s.legal_business_name IS NOT NULL
              AND s.physical_state IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM unified_match_log uml
                  WHERE uml.source_system = 'sam'
                    AND uml.source_id = s.uei
                    AND uml.status = 'active'
              )
            LIMIT 5000
            """
        )
        sam_unmatched = cur.fetchall()

        unmatched_exact = []
        for s in sam_unmatched:
            key = (s["physical_state"], s["norm_name"])
            f = f7_lookup.get(key)
            if not f:
                continue
            unmatched_exact.append(
                {
                    "uei": s["uei"],
                    "legal_business_name": s["legal_business_name"],
                    "physical_state": s["physical_state"],
                    "employer_id": f["employer_id"],
                    "employer_name": f["employer_name"],
                }
            )
            if len(unmatched_exact) >= 20:
                break

        lines = []
        lines.append("# I14 SAM Matching Quality Audit")
        lines.append("")
        lines.append("## Summary")
        lines.append(f"- Active SAM matches: **{total:,}**")
        lines.append(f"- Match methods observed: **{len(by_method):,}**")
        lines.append(f"- Fuzzy rows (Splink+Trigram): **{len(fuzzy_rows):,}**")
        lines.append("")

        lines.append("## Method Distribution")
        lines.append("| Method | Count | Percent | Avg confidence | Quality |")
        lines.append("|---|---:|---:|---:|---|")
        for method, method_rows in sorted(by_method.items(), key=lambda kv: len(kv[1]), reverse=True):
            count = len(method_rows)
            pct = (count / total * 100.0) if total else 0.0
            avg_conf = sum(float(r["confidence_score"] or 0) for r in method_rows) / count
            if method in FUZZY_METHODS:
                sims = [extract_similarity(r.get("evidence")) for r in method_rows]
                known = [s for s in sims if s is not None]
                low_share = (sum(1 for s in known if s < 0.85) / len(known)) if known else 0.0
            else:
                low_share = 0.0
            quality = assess_method(method, avg_conf, low_share)
            lines.append(f"| {method} | {count:,} | {pct:.1f}% | {avg_conf:.3f} | {quality} |")

        lines.append("")
        lines.append("## Method Samples (5 each)")
        for method, method_rows in sorted(by_method.items(), key=lambda kv: len(kv[1]), reverse=True):
            lines.append(f"### {method}")
            sample = random.sample(method_rows, k=min(5, len(method_rows)))
            for r in sample:
                ev = r.get("evidence") or {}
                src = r.get("legal_business_name") or ev.get("source_name") or "<missing source>"
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
                src = r.get("legal_business_name") or ev.get("source_name") or "<missing source>"
                tgt = r.get("employer_name") or ev.get("target_name") or "<missing target>"
                lines.append(f"- sim={r.get('name_similarity')} | `{r['source_id']}` -> `{r['target_id']}` | {src} => {tgt}")

        lines.append("")
        lines.append("## Potential Deterministic Gaps (Exact Name+State but No Active Match)")
        lines.append(f"- Found examples: **{len(unmatched_exact):,}** (limited to top 20)")
        for r in unmatched_exact:
            lines.append(
                f"- SAM `{r['uei']}` ({r['physical_state']}) {r['legal_business_name']} -> F7 `{r['employer_id']}` {r['employer_name']}"
            )

        lines.append("")
        lines.append("## Recommended Actions")
        lines.append("- Prioritize review of fuzzy matches below 0.85 similarity.")
        lines.append("- Backfill deterministic exact-name+state pass for unmatched SAM examples.")
        lines.append("- Keep cross-method dedupe enabled so one SAM source_id maps to exactly one active target.")

        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        print(f"Wrote {args.output}")
        print(f"Active SAM matches: {total:,}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
