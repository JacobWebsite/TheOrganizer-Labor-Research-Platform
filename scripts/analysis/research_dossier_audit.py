"""
Research Dossier Completeness Audit

For each run, shows every vocabulary field and whether it was filled,
with the actual value or MISSING marker.

Usage:
    py scripts/analysis/research_dossier_audit.py                 # audit all runs
    py scripts/analysis/research_dossier_audit.py --run-id 66     # audit one run
    py scripts/analysis/research_dossier_audit.py --recent 5      # last 5 runs
    py scripts/analysis/research_dossier_audit.py --summary-only  # just fill rates
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, ".")
from db_config import get_connection
from psycopg2.extras import RealDictCursor


def load_vocabulary() -> dict[str, list[str]]:
    """Load vocabulary grouped by section."""
    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("SELECT dossier_section, attribute_name FROM research_fact_vocabulary ORDER BY dossier_section, attribute_name")
    by_section: dict[str, list[str]] = {}
    for r in cur.fetchall():
        by_section.setdefault(r["dossier_section"], []).append(r["attribute_name"])
    conn.close()
    return by_section


def audit_run(run_id: int, vocab: dict[str, list[str]]) -> dict:
    """Audit a single run's dossier completeness."""
    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()

    cur.execute(
        "SELECT company_name, dossier_json, overall_quality_score, sections_filled, total_facts_found "
        "FROM research_runs WHERE id = %s",
        (run_id,),
    )
    run = cur.fetchone()
    if not run:
        conn.close()
        return {"run_id": run_id, "error": "not found"}

    # Get facts for this run
    cur.execute(
        "SELECT dossier_section, attribute_name, attribute_value, source_type "
        "FROM research_facts WHERE run_id = %s",
        (run_id,),
    )
    facts = cur.fetchall()
    conn.close()

    # Index facts by (section, attribute)
    facts_by_attr: dict[str, dict] = {}
    for f in facts:
        key = f"{f['dossier_section']}.{f['attribute_name']}"
        facts_by_attr[key] = f

    # Parse dossier JSON for body fields
    body_fields: dict[str, any] = {}
    dossier_json = run.get("dossier_json")
    if dossier_json:
        try:
            if isinstance(dossier_json, str):
                dossier_obj = json.loads(dossier_json)
            else:
                dossier_obj = dossier_json
            dossier_body = dossier_obj.get("dossier", {})
            for sec, attrs in dossier_body.items():
                if isinstance(attrs, dict):
                    for k, v in attrs.items():
                        body_fields[f"{sec}.{k}"] = v
        except (json.JSONDecodeError, TypeError):
            pass

    # Audit each vocabulary field
    total = 0
    filled = 0
    results = []
    for sec, attrs in sorted(vocab.items()):
        for attr in attrs:
            total += 1
            key = f"{sec}.{attr}"
            in_facts = key in facts_by_attr
            in_body = key in body_fields and body_fields[key] is not None and body_fields[key] != "" and body_fields[key] != []

            is_filled = in_facts or in_body
            if is_filled:
                filled += 1

            value_preview = None
            source = None
            if in_facts:
                val = facts_by_attr[key].get("attribute_value", "")
                value_preview = str(val)[:100]
                source = facts_by_attr[key].get("source_type", "")
            elif in_body:
                val = body_fields[key]
                value_preview = str(val)[:100] if val else None
                source = "dossier_body"

            results.append({
                "section": sec,
                "field": attr,
                "filled": is_filled,
                "in_facts": in_facts,
                "in_body": in_body,
                "value_preview": value_preview,
                "source": source,
            })

    return {
        "run_id": run_id,
        "company_name": run["company_name"],
        "quality_score": float(run["overall_quality_score"]) if run.get("overall_quality_score") else None,
        "total_fields": total,
        "filled_fields": filled,
        "fill_rate": round(filled / total * 100, 1) if total else 0,
        "fields": results,
    }


def print_run_audit(audit: dict, verbose: bool = True):
    print(f"\n--- Run {audit['run_id']}: {audit['company_name']} ---")
    print(f"  Quality: {audit.get('quality_score', '?')}/10")
    print(f"  Fill rate: {audit['filled_fields']}/{audit['total_fields']} ({audit['fill_rate']}%)")

    if verbose:
        current_section = ""
        for f in audit["fields"]:
            if f["section"] != current_section:
                current_section = f["section"]
                print(f"\n  [{current_section}]")
            status = "FILLED" if f["filled"] else "MISSING"
            marker = "+" if f["filled"] else "-"
            if f["value_preview"]:
                print(f"    {marker} {f['field']:<35s} {status:<8s} {f['source']:<12s} {f['value_preview'][:60]}")
            else:
                print(f"    {marker} {f['field']:<35s} {status}")


def run_summary(audits: list[dict]):
    """Print aggregate summary across all audits."""
    if not audits:
        print("No audits to summarize.")
        return

    # Aggregate field fill rates
    field_counts: dict[str, int] = {}
    total_runs = len(audits)
    for a in audits:
        for f in a["fields"]:
            key = f"{f['section']}.{f['field']}"
            if f["filled"]:
                field_counts[key] = field_counts.get(key, 0) + 1

    print(f"\n{'='*70}")
    print(f"  AGGREGATE FILL RATES ({total_runs} runs)")
    print(f"{'='*70}")

    avg_fill = sum(a["fill_rate"] for a in audits) / len(audits)
    print(f"\n  Average fill rate: {avg_fill:.1f}%")
    print(f"  Average quality:   {sum(a.get('quality_score', 0) or 0 for a in audits) / len(audits):.2f}")

    # By section
    section_rates: dict[str, list[float]] = {}
    for a in audits:
        by_sec: dict[str, tuple[int, int]] = {}
        for f in a["fields"]:
            s = f["section"]
            if s not in by_sec:
                by_sec[s] = [0, 0]
            by_sec[s][1] += 1
            if f["filled"]:
                by_sec[s][0] += 1
        for s, (filled, total) in by_sec.items():
            section_rates.setdefault(s, []).append(filled / total * 100 if total else 0)

    print(f"\n  Section fill rates:")
    for sec in sorted(section_rates.keys()):
        rates = section_rates[sec]
        avg = sum(rates) / len(rates)
        print(f"    {sec:<15s} {avg:>5.1f}%")

    # Fields sorted by fill rate
    print(f"\n  Field fill rates (sorted):")
    sorted_fields = sorted(field_counts.items(), key=lambda x: x[1], reverse=True)
    for key, count in sorted_fields:
        rate = count / total_runs * 100
        print(f"    {key:<45s} {count:>3}/{total_runs} ({rate:>5.1f}%)")

    # Never-filled fields
    all_fields = set()
    for a in audits:
        for f in a["fields"]:
            all_fields.add(f"{f['section']}.{f['field']}")
    never = all_fields - set(field_counts.keys())
    if never:
        print(f"\n  Never-filled fields ({len(never)}):")
        for nf in sorted(never):
            print(f"    {nf}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Research Dossier Completeness Audit")
    parser.add_argument("--run-id", type=int, help="Audit a specific run")
    parser.add_argument("--recent", type=int, help="Audit last N completed runs")
    parser.add_argument("--summary-only", action="store_true", help="Only print aggregate summary")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    vocab = load_vocabulary()

    if args.run_id:
        audit = audit_run(args.run_id, vocab)
        if args.json:
            print(json.dumps(audit, indent=2, default=str))
        else:
            print_run_audit(audit)
    else:
        conn = get_connection(cursor_factory=RealDictCursor)
        cur = conn.cursor()
        q = "SELECT id FROM research_runs WHERE status = 'completed' ORDER BY id DESC"
        if args.recent:
            q += f" LIMIT {args.recent}"
        cur.execute(q)
        run_ids = [r["id"] for r in cur.fetchall()]
        conn.close()

        audits = []
        for rid in run_ids:
            audit = audit_run(rid, vocab)
            if "error" not in audit:
                audits.append(audit)
                if not args.summary_only and not args.json:
                    print_run_audit(audit, verbose=not args.summary_only)

        if args.json:
            print(json.dumps(audits, indent=2, default=str))
        else:
            run_summary(audits)
