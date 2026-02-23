"""
Misclassification sweep: identify f7_employers_deduped records that are
actually labor organizations, not employers.

Signals:
  T1 (HIGH): employer_name = its own latest_union_name (self-referencing)
  T2 (CORROBORATIVE ONLY): employer_name exact-matches a union name from
      unions_master. NOT reliable alone -- employers are often named after
      unions (e.g., hospitals, universities).
  T3 (MEDIUM): employer_name's PRIMARY part (before parenthetical/slash)
      matches structural union patterns (Local 123, AFL-CIO, union acronyms).
      Excludes names where union ref is only in a parenthetical/qualifier.
  T4 (MEDIUM): BMF EIN bridge via 990 matches -- employer linked to a BMF
      record classified as labor org (NTEE J40* = Labor Unions/Organizations)

Confidence assignment:
  HIGH:   T1 (self-ref), or T2+T3 (union name + structural pattern)
  MEDIUM: T3+T4 (keyword + BMF), or T3+T2 already covered above
  LOW:    any single signal alone (except T1)

Only HIGH and MEDIUM (2+ signals) get auto-flagged. LOW = review list.

Usage:
  py scripts/analysis/misclass_sweep.py                  # dry-run analysis
  py scripts/analysis/misclass_sweep.py --flag            # add is_labor_org column + flag
  py scripts/analysis/misclass_sweep.py --flag --commit   # actually commit changes
"""
import sys
import os
import argparse
import re
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection


def load_union_names(cur):
    """Load all known union names from unions_master into a set."""
    cur.execute("""
        SELECT DISTINCT LOWER(TRIM(union_name)) AS n FROM unions_master
        WHERE union_name IS NOT NULL
        UNION
        SELECT DISTINCT LOWER(TRIM(f7_union_name)) FROM unions_master
        WHERE f7_union_name IS NOT NULL
    """)
    return {row[0] for row in cur.fetchall() if row[0]}


def load_employers(cur):
    """Load all employer records we need to check."""
    cur.execute("""
        SELECT employer_id, employer_name, latest_union_name,
               latest_unit_size, state, is_historical,
               exclude_from_counts, exclude_reason
        FROM f7_employers_deduped
    """)
    return cur.fetchall()


def load_bmf_labor_eins(cur):
    """Load EINs of high-confidence labor orgs from BMF (NTEE J40*)."""
    cur.execute("""
        SELECT DISTINCT ein FROM irs_bmf
        WHERE ntee_code LIKE 'J4%%'
          AND ein IS NOT NULL
    """)
    return {row[0] for row in cur.fetchall()}


def load_990_ein_bridge(cur):
    """Load f7_employer_id -> EIN mappings from 990 match table."""
    cur.execute("""
        SELECT f7_employer_id, ein FROM national_990_f7_matches
        WHERE ein IS NOT NULL
    """)
    bridge = defaultdict(set)
    for row in cur.fetchall():
        bridge[row[0]].add(row[1])
    return bridge


def extract_primary_name(name):
    """Extract the primary employer name before any parenthetical or slash qualifier.

    F7 employer names often include union info:
      "Nursing Homes NYC (SEIU/UHWE Local 1199)"  -> "Nursing Homes NYC"
      "UPS / Local Union No. 710"                  -> "UPS"
      "AFGE LOCAL 2145"                            -> "AFGE LOCAL 2145" (no qualifier)
    """
    # Strip parenthetical at end
    primary = re.sub(r'\s*\([^)]*\)\s*$', '', name).strip()
    # If name has " / " or " - " separator, take first part
    # But only if the first part is substantial (>3 chars)
    for sep in [' / ', ' - ', ' -- ']:
        if sep in primary:
            first = primary.split(sep)[0].strip()
            if len(first) > 3:
                primary = first
                break
    return primary


# Keyword patterns that strongly indicate a labor organization
# Applied to PRIMARY name only (before parenthetical/slash)
UNION_STRUCTURAL = re.compile(
    r'(?i)'
    r'(?:'
    r'^(?:local|lodge|council|chapter|division|district)\s+(?:no\.?\s*)?\d'  # starts with Local 123
    r'|^(?:ibew|uaw|seiu|afscme|ufcw|liuna|iatse|iuoe|iam|usw|ibt)\b'  # starts with union acronym
    r'|^(?:teamsters|unite here)\b'  # starts with known union name
    r'|^(?:international brotherhood|international union|international association)\b'
    r'|^(?:united steelworkers|united auto workers)\b'
    r'|^amalgamated\s+(?:transit|clothing|meat|lithograph|worker|union|local)'
    r'|^afge\b'  # American Federation of Government Employees
    r'|\bafl[\s\-]*cio\b'  # AFL-CIO anywhere
    r'|\b(?:local|lodge)\s+(?:no\.?\s*)?\d+\s*$'  # ends with Local 123
    r'|\b(?:local|lodge)\s+(?:no\.?\s*)?\d+\s*,\s*(?:ibew|uaw|seiu|afscme|ufcw|ibt|iatse)\b'
    r'|\bjoint (?:council|board)\s+(?:no\.?\s*)?\d'
    r'|\bunion\s+(?:local|lodge)\s+(?:no\.?\s*)?\d'
    r')'
)

# False positive exclusions -- legitimate employers with union words
FALSE_POS = re.compile(
    r'(?i)'
    r'(?:'
    r'union pacific'
    r'|union hospital'
    r'|union carbide'
    r'|union bank'
    r'|credit union'
    r'|union station'
    r'|union county'
    r'|union city'
    r'|union memorial'
    r'|union square'
    r'|union league'
    r'|union rescue'
    r'|teachers? insurance'
    r'|teachers? college'
    r'|association of (?:contractor|general|plumb|build|construct)'
    r'|contractor.?s?\s+association'
    r'|\bassociation\s+of\s+(?!machinists|flight)'  # "association of" unless known union
    r')'
)


def classify_employers(employers, union_names, bmf_labor_eins, ein_bridge):
    """Classify each employer by misclassification signals."""
    results = {}

    for emp in employers:
        eid = emp[0]
        name = (emp[1] or '').strip()
        union_name = (emp[2] or '').strip()
        name_lower = name.lower()

        signals = []

        # T1: self-referencing (employer_name = own union_name)
        if union_name and name_lower == union_name.lower().strip():
            signals.append('T1_SELF_REF')

        # T2: name appears in unions_master (corroborative only)
        if name_lower in union_names:
            signals.append('T2_UNION_NAME')

        # T3: structural union pattern in PRIMARY name part
        primary = extract_primary_name(name)
        if UNION_STRUCTURAL.search(primary) and not FALSE_POS.search(primary):
            signals.append('T3_KEYWORD')

        # T4: BMF EIN bridge (NTEE J40* = actual labor unions)
        eins = ein_bridge.get(eid, set())
        if eins & bmf_labor_eins:
            signals.append('T4_BMF_EIN')

        if signals:
            # Confidence tiers:
            # - T1 (self-ref) or T3 (structural keyword) = HIGH
            #   (structural patterns like "Local 123", "IBEW" on primary
            #   name are unambiguously union identifiers)
            # - 2+ signals without T3 = MEDIUM
            # - T2 or T4 alone = LOW (T2 catches hospitals named after
            #   unions; T4 catches employer associations in BMF)
            if 'T1_SELF_REF' in signals or 'T3_KEYWORD' in signals:
                confidence = 'HIGH'
            elif len(signals) >= 2:
                confidence = 'MEDIUM'
            else:
                confidence = 'LOW'

            results[eid] = {
                'employer_name': name,
                'primary_name': primary,
                'state': emp[4],
                'unit_size': emp[3],
                'is_historical': emp[5],
                'exclude_from_counts': emp[6],
                'signals': signals,
                'confidence': confidence,
            }

    return results


def main():
    parser = argparse.ArgumentParser(description='Misclassification sweep')
    parser.add_argument('--flag', action='store_true',
                        help='Add is_labor_org column and flag records')
    parser.add_argument('--commit', action='store_true',
                        help='Actually commit changes (requires --flag)')
    parser.add_argument('--samples', type=int, default=15,
                        help='Number of samples to show per tier')
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    print('Loading union names from unions_master...')
    union_names = load_union_names(cur)
    print(f'  {len(union_names)} distinct union names loaded')

    print('Loading BMF labor org EINs (NTEE J40*)...')
    bmf_labor_eins = load_bmf_labor_eins(cur)
    print(f'  {len(bmf_labor_eins)} EINs loaded')

    print('Loading 990 EIN bridge...')
    ein_bridge = load_990_ein_bridge(cur)
    print(f'  {len(ein_bridge)} employer->EIN mappings')

    print('Loading employers...')
    employers = load_employers(cur)
    print(f'  {len(employers)} employers loaded')

    print('\nClassifying...')
    flagged = classify_employers(employers, union_names, bmf_labor_eins, ein_bridge)

    # Group by confidence
    high = {k: v for k, v in flagged.items() if v['confidence'] == 'HIGH'}
    medium = {k: v for k, v in flagged.items() if v['confidence'] == 'MEDIUM'}
    low = {k: v for k, v in flagged.items() if v['confidence'] == 'LOW'}

    # What we'll actually flag = HIGH + MEDIUM
    to_flag = {**high, **medium}

    print(f'\n=== MISCLASSIFICATION SWEEP RESULTS ===')
    print(f'Total with any signal: {len(flagged)}')
    print(f'  HIGH confidence:     {len(high):>5}  (auto-flag)')
    print(f'  MEDIUM confidence:   {len(medium):>5}  (auto-flag)')
    print(f'  LOW confidence:      {len(low):>5}  (review only)')
    print(f'  ----')
    print(f'  Will flag:           {len(to_flag):>5}')
    print(f'  Already excluded:    {sum(1 for v in flagged.values() if v["exclude_from_counts"]):>5}')
    print(f'  Historical:          {sum(1 for v in flagged.values() if v["is_historical"]):>5}')

    # Signal breakdown
    from collections import Counter
    signal_counts = Counter()
    for v in flagged.values():
        for s in v['signals']:
            signal_counts[s] += 1
    print(f'\nSignal breakdown:')
    for sig, cnt in signal_counts.most_common():
        print(f'  {sig}: {cnt}')

    # Samples for each tier
    for conf, subset in [('HIGH', high), ('MEDIUM', medium), ('LOW', low)]:
        sorted_items = sorted(subset.items(),
                              key=lambda x: x[1].get('unit_size') or 0, reverse=True)
        print(f'\n--- {conf} confidence ({len(subset)} total, top {args.samples}) ---')
        for eid, v in sorted_items[:args.samples]:
            sigs = '+'.join(v['signals'])
            hist = ' [HIST]' if v['is_historical'] else ''
            excl = ' [EXCL]' if v['exclude_from_counts'] else ''
            print(f'  {v["employer_name"][:60]:60s}  st={v["state"] or "?":2s}'
                  f'  unit={str(v["unit_size"] or "?"):>6s}  {sigs}{hist}{excl}')

    if args.flag:
        print(f'\n=== FLAGGING {len(to_flag)} RECORDS (HIGH + MEDIUM) ===')

        # Check if column exists
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name = 'f7_employers_deduped' AND column_name = 'is_labor_org'
        """)
        col_exists = cur.fetchone()[0] > 0

        if not col_exists:
            print('Adding is_labor_org column...')
            cur.execute("""
                ALTER TABLE f7_employers_deduped
                ADD COLUMN is_labor_org BOOLEAN DEFAULT FALSE
            """)

        flag_ids = list(to_flag.keys())
        print(f'Setting is_labor_org=TRUE for {len(flag_ids)} records...')
        if flag_ids:
            cur.execute("""
                UPDATE f7_employers_deduped
                SET is_labor_org = TRUE
                WHERE employer_id = ANY(%s)
            """, (flag_ids,))
            print(f'  Updated {cur.rowcount} rows')

        # Also set exclude_from_counts for newly flagged
        print(f'Setting exclude_from_counts for newly flagged records...')
        if flag_ids:
            cur.execute("""
                UPDATE f7_employers_deduped
                SET exclude_from_counts = TRUE,
                    exclude_reason = COALESCE(
                        CASE WHEN exclude_reason IS NOT NULL
                             THEN exclude_reason || '; ' ELSE '' END, ''
                    ) || 'LABOR_ORG'
                WHERE employer_id = ANY(%s)
                  AND (exclude_from_counts = FALSE OR exclude_from_counts IS NULL)
            """, (flag_ids,))
            print(f'  Newly excluded: {cur.rowcount} rows')

        # Final summary
        cur.execute("""
            SELECT is_labor_org, COUNT(*) FROM f7_employers_deduped GROUP BY 1 ORDER BY 1
        """)
        print('\nFinal distribution:')
        for row in cur.fetchall():
            print(f'  is_labor_org={row[0]}: {row[1]}')

        if args.commit:
            conn.commit()
            print('\nCHANGES COMMITTED.')
        else:
            conn.rollback()
            print('\nDRY RUN -- changes rolled back. Use --flag --commit to apply.')
    else:
        print('\nAnalysis only. Use --flag to apply, --flag --commit to persist.')

    conn.close()


if __name__ == '__main__':
    main()
