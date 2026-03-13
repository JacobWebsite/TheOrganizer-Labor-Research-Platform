"""
Validation reporting for union web scraper extraction pipeline.

Reports:
  - Coverage by extraction_method
  - Profile-level summary
  - PDF catalog
  - Tier funnel

Usage:
    py scripts/scraper/extraction_report.py
    py scripts/scraper/extraction_report.py --csv
    py scripts/scraper/extraction_report.py --html
"""
import sys
import os
import csv
import argparse
from io import StringIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


# ── Report Functions ─────────────────────────────────────────────────────

def report_method_coverage(cur):
    """Coverage by extraction_method."""
    cur.execute("""
        SELECT extraction_method,
               COUNT(*) as employer_count,
               COUNT(DISTINCT web_profile_id) as profile_count,
               ROUND(AVG(confidence_score)::numeric, 2) as avg_confidence
        FROM web_union_employers
        GROUP BY extraction_method
        ORDER BY employer_count DESC
    """)
    rows = cur.fetchall()

    print("\n=== COVERAGE BY EXTRACTION METHOD ===")
    print(f"  {'Method':<25} {'Employers':>10} {'Profiles':>10} {'Avg Conf':>10}")
    print(f"  {'-'*25} {'-'*10} {'-'*10} {'-'*10}")
    total_emp = 0
    total_prof = set()
    for method, emp_cnt, prof_cnt, avg_conf in rows:
        print(f"  {method:<25} {emp_cnt:>10} {prof_cnt:>10} {avg_conf or 0:>10.2f}")
        total_emp += emp_cnt
    print(f"  {'TOTAL':<25} {total_emp:>10}")
    return rows


def report_profile_summary(cur):
    """Profile-level summary: employers found, breakdown by method, tier reached."""
    cur.execute("""
        SELECT p.id, p.union_name, p.state,
               p.extraction_tier_reached, p.gemini_used,
               COUNT(e.id) as employer_count,
               COUNT(DISTINCT e.extraction_method) as method_count,
               ARRAY_AGG(DISTINCT e.extraction_method) as methods
        FROM web_union_profiles p
        LEFT JOIN web_union_employers e ON e.web_profile_id = p.id
        WHERE p.scrape_status IN ('FETCHED', 'EXTRACTED')
        GROUP BY p.id, p.union_name, p.state, p.extraction_tier_reached, p.gemini_used
        ORDER BY employer_count DESC
    """)
    rows = cur.fetchall()

    print("\n=== PROFILE SUMMARY (top 30) ===")
    print(f"  {'ID':<5} {'Union':<45} {'ST':<4} {'Emp':>5} {'Methods':>8} {'Tier':>5} {'Gemini':>7}")
    print(f"  {'-'*5} {'-'*45} {'-'*4} {'-'*5} {'-'*8} {'-'*5} {'-'*7}")

    zero_emp = 0
    for row in rows[:30]:
        pid, name, st, tier, gemini, emp_cnt, method_cnt, methods = row
        gmn = 'Y' if gemini else ''
        print(f"  {pid:<5} {(name or '')[:45]:<45} {st or '':<4} {emp_cnt:>5} "
              f"{method_cnt:>8} {tier or 0:>5} {gmn:>7}")

    for row in rows:
        if row[5] == 0:
            zero_emp += 1

    print(f"\n  Total profiles: {len(rows)}")
    print(f"  With employers: {len(rows) - zero_emp}")
    print(f"  Zero employers: {zero_emp}")
    return rows


def report_pdf_catalog(cur):
    """PDF catalog by union."""
    cur.execute("""
        SELECT p.union_name, pl.pdf_url, pl.link_text, pl.pdf_type
        FROM web_union_pdf_links pl
        JOIN web_union_profiles p ON pl.profile_id = p.id
        ORDER BY p.union_name, pl.pdf_type
    """)
    rows = cur.fetchall()

    print(f"\n=== PDF CATALOG ({len(rows)} total) ===")

    contracts = [r for r in rows if r[3] == 'contract']
    others = [r for r in rows if r[3] != 'contract']

    print(f"  Contract PDFs: {len(contracts)}")
    print(f"  Other PDFs:    {len(others)}")

    if contracts:
        print(f"\n  Contract PDFs:")
        for union, url, text, ptype in contracts[:20]:
            print(f"    {(union or '')[:35]:<35} {(text or '')[:40]:<40}")
        if len(contracts) > 20:
            print(f"    ... and {len(contracts) - 20} more")

    return rows


def report_tier_funnel(cur):
    """Tier funnel: how many employers found at each tier."""
    cur.execute("""
        SELECT extraction_tier_reached, COUNT(*) as profile_count,
               SUM(CASE WHEN id IN (SELECT DISTINCT web_profile_id FROM web_union_employers) THEN 1 ELSE 0 END) as with_employers
        FROM web_union_profiles
        WHERE scrape_status IN ('FETCHED', 'EXTRACTED')
        GROUP BY extraction_tier_reached
        ORDER BY extraction_tier_reached
    """)
    rows = cur.fetchall()

    print(f"\n=== TIER FUNNEL ===")
    print(f"  {'Tier':>5} {'Profiles':>10} {'With Emp':>10} {'Coverage':>10}")
    print(f"  {'-'*5} {'-'*10} {'-'*10} {'-'*10}")
    for tier, prof_cnt, with_emp in rows:
        pct = f"{100*with_emp/max(prof_cnt,1):.0f}%" if prof_cnt else "0%"
        print(f"  {tier or 0:>5} {prof_cnt:>10} {with_emp:>10} {pct:>10}")

    # Also show source_element breakdown
    cur.execute("""
        SELECT source_element, COUNT(*) FROM web_union_employers
        WHERE source_element IS NOT NULL
        GROUP BY source_element ORDER BY COUNT(*) DESC
    """)
    elem_rows = cur.fetchall()
    if elem_rows:
        print(f"\n  By source element:")
        for elem, cnt in elem_rows:
            print(f"    {elem:<20} {cnt:>6}")

    return rows


def report_source_urls(cur):
    """Check source_page_url population."""
    cur.execute("""
        SELECT COUNT(*) as total,
               COUNT(source_page_url) as with_url,
               COUNT(source_element) as with_element
        FROM web_union_employers
    """)
    total, with_url, with_elem = cur.fetchone()
    print(f"\n=== URL PROVENANCE ===")
    print(f"  Total employers:        {total}")
    print(f"  With source_page_url:   {with_url} ({100*with_url/max(total,1):.0f}%)")
    print(f"  With source_element:    {with_elem} ({100*with_elem/max(total,1):.0f}%)")


# ── CSV/HTML Export ──────────────────────────────────────────────────────

def export_csv(cur, filepath='extraction_report.csv'):
    """Export profile summary as CSV."""
    cur.execute("""
        SELECT p.id, p.union_name, p.state, p.website_url,
               p.extraction_tier_reached, p.gemini_used,
               COUNT(e.id) as employer_count,
               STRING_AGG(DISTINCT e.extraction_method, ', ') as methods
        FROM web_union_profiles p
        LEFT JOIN web_union_employers e ON e.web_profile_id = p.id
        WHERE p.scrape_status IN ('FETCHED', 'EXTRACTED')
        GROUP BY p.id
        ORDER BY employer_count DESC
    """)
    rows = cur.fetchall()

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['profile_id', 'union_name', 'state', 'website_url',
                         'tier_reached', 'gemini_used', 'employer_count', 'methods'])
        for row in rows:
            writer.writerow(row)

    print(f"\nCSV exported to {filepath} ({len(rows)} rows)")


def export_html(cur, filepath='extraction_report.html'):
    """Export summary as HTML report."""
    cur.execute("""
        SELECT p.id, p.union_name, p.state,
               COUNT(e.id) as employer_count,
               STRING_AGG(DISTINCT e.extraction_method, ', ') as methods,
               p.extraction_tier_reached, p.gemini_used
        FROM web_union_profiles p
        LEFT JOIN web_union_employers e ON e.web_profile_id = p.id
        WHERE p.scrape_status IN ('FETCHED', 'EXTRACTED')
        GROUP BY p.id
        ORDER BY employer_count DESC
    """)
    rows = cur.fetchall()

    html = ['<html><head><title>Extraction Report</title>',
            '<style>table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px}',
            'th{background:#f0f0f0}</style></head><body>',
            '<h1>Union Web Scraper Extraction Report</h1>',
            '<table><tr><th>ID</th><th>Union</th><th>State</th><th>Employers</th>',
            '<th>Methods</th><th>Tier</th><th>Gemini</th></tr>']

    for pid, name, st, emp_cnt, methods, tier, gemini in rows:
        gmn = 'Y' if gemini else ''
        html.append(f'<tr><td>{pid}</td><td>{name or ""}</td><td>{st or ""}</td>'
                    f'<td>{emp_cnt}</td><td>{methods or ""}</td>'
                    f'<td>{tier or 0}</td><td>{gmn}</td></tr>')

    html.append('</table></body></html>')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(html))

    print(f"\nHTML exported to {filepath} ({len(rows)} rows)")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Extraction pipeline validation report')
    parser.add_argument('--csv', action='store_true', help='Export CSV report')
    parser.add_argument('--html', action='store_true', help='Export HTML report')
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    try:
        report_method_coverage(cur)
        report_profile_summary(cur)
        report_pdf_catalog(cur)
        report_tier_funnel(cur)
        report_source_urls(cur)

        if args.csv:
            export_csv(cur)
        if args.html:
            export_html(cur)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
