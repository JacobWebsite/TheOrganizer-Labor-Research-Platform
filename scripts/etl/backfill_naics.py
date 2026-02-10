"""
Backfill missing NAICS codes for F7 employers.

4 tiers in priority order:
  Tier 1: Mergent crosswalk (6-digit NAICS -> 2-digit)
  Tier 2: OSHA high-confidence pg_trgm match (similarity >= 0.7)
  Tier 3: Union peer inference (same union local -> same industry)
  Tier 4: Keyword pattern matching on employer name

Usage:
    py scripts/etl/backfill_naics.py              # Dry run (show what would change)
    py scripts/etl/backfill_naics.py --apply       # Apply changes to database

Target: < 500 employers with NULL NAICS (< 1% of ~61K)
"""
import os
import sys
import re
import argparse
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from db_config import get_connection


# ============================================================================
# Tier 4: Keyword -> 2-digit NAICS mapping
# ============================================================================

# Order matters: first match wins. More specific patterns go first.
KEYWORD_RULES = [
    # Healthcare (62)
    (r'\bHOSPITAL\b', '62', 'KEYWORD_HOSPITAL'),
    (r'\bMEDICAL CENTER\b', '62', 'KEYWORD_MEDICAL'),
    (r'\bMEDICAL\b', '62', 'KEYWORD_MEDICAL'),
    (r'\bNURSING\b', '62', 'KEYWORD_NURSING'),
    (r'\bPHARMAC', '62', 'KEYWORD_PHARMACY'),
    (r'\bHEALTH\s*(CARE|SYSTEM|SERVICE)', '62', 'KEYWORD_HEALTHCARE'),
    (r'\bCLINIC\b', '62', 'KEYWORD_CLINIC'),
    (r'\bRESIDENTIAL\s*CARE\b', '62', 'KEYWORD_RESCARE'),
    (r'\bHOME\s*CARE\b', '62', 'KEYWORD_HOMECARE'),
    (r'\bHOME\s*HEALTH\b', '62', 'KEYWORD_HOMEHEALTH'),
    (r'\bAMBULANCE\b', '62', 'KEYWORD_AMBULANCE'),
    (r'\bREHAB', '62', 'KEYWORD_REHAB'),

    # Education (61)
    (r'\bSCHOOL DIST', '61', 'KEYWORD_SCHOOLDIST'),
    (r'\bSCHOOL\b', '61', 'KEYWORD_SCHOOL'),
    (r'\bUNIVERSIT', '61', 'KEYWORD_UNIVERSITY'),
    (r'\bCOLLEGE\b', '61', 'KEYWORD_COLLEGE'),
    (r'\bACADEMY\b', '61', 'KEYWORD_ACADEMY'),

    # Government / Public (92)
    (r'\bCITY OF\b', '92', 'KEYWORD_CITYOF'),
    (r'\bTOWN OF\b', '92', 'KEYWORD_TOWNOF'),
    (r'\bCOUNTY OF\b', '92', 'KEYWORD_COUNTYOF'),
    (r'\bCOUNTY\b', '92', 'KEYWORD_COUNTY'),
    (r'\bTOWNSHIP\b', '92', 'KEYWORD_TOWNSHIP'),
    (r'\bBOROUGH\b', '92', 'KEYWORD_BOROUGH'),
    (r'\bVILLAGE OF\b', '92', 'KEYWORD_VILLAGEOF'),
    (r'\bPOLICE\b', '92', 'KEYWORD_POLICE'),
    (r'\bSHERIFF\b', '92', 'KEYWORD_SHERIFF'),
    (r'\bFIRE\s*(?:DEPT|DEPARTMENT|DISTRICT|PROTECTION)\b', '92', 'KEYWORD_FIRE'),
    (r'\bPARK\s*DIST', '92', 'KEYWORD_PARKDIST'),
    (r'\bWATER\s*(?:DIST|DEPT|AUTH|UTILITY)', '22', 'KEYWORD_WATERUTIL'),
    (r'\bSEWER', '22', 'KEYWORD_SEWER'),
    (r'\bSANIT\w*\s*DIST', '92', 'KEYWORD_SANITDIST'),
    (r'\bHOUSING\s*AUTH', '92', 'KEYWORD_HOUSINGAUTH'),
    (r'\bTRANSIT\s*AUTH', '48', 'KEYWORD_TRANSITAUTH'),
    (r'\bPORT\s*AUTH', '92', 'KEYWORD_PORTAUTH'),

    # Transportation (48-49)
    (r'\bTRUCK(ING|LINE)', '48', 'KEYWORD_TRUCKING'),
    (r'\bFREIGHT\b', '48', 'KEYWORD_FREIGHT'),
    (r'\bTRANSIT\b', '48', 'KEYWORD_TRANSIT'),
    (r'\bAIRLINE', '48', 'KEYWORD_AIRLINE'),
    (r'\bAIRPORT\b', '48', 'KEYWORD_AIRPORT'),
    (r'\bLOGISTICS\b', '48', 'KEYWORD_LOGISTICS'),
    (r'\bTRANSPORT', '48', 'KEYWORD_TRANSPORT'),
    (r'\bBUS\s*(LINE|SERVICE|COMPANY|CORP)', '48', 'KEYWORD_BUSLINE'),
    (r'\bRAILROAD\b', '48', 'KEYWORD_RAILROAD'),
    (r'\bRAILWAY\b', '48', 'KEYWORD_RAILWAY'),
    (r'\bMOVING\s*(AND|&)\s*STORAGE', '48', 'KEYWORD_MOVING'),
    (r'\bCOURIER\b', '49', 'KEYWORD_COURIER'),

    # Accommodation & Food (72)
    (r'\bHOTEL\b', '72', 'KEYWORD_HOTEL'),
    (r'\bCASINO\b', '72', 'KEYWORD_CASINO'),
    (r'\bRESORT\b', '72', 'KEYWORD_RESORT'),
    (r'\bMOTEL\b', '72', 'KEYWORD_MOTEL'),
    (r'\bRESTAURANT\b', '72', 'KEYWORD_RESTAURANT'),
    (r'\bCAFETERIA\b', '72', 'KEYWORD_CAFETERIA'),
    (r'\bHOSPITALIT', '72', 'KEYWORD_HOSPITALITY'),
    (r'\bCANTEEN\b', '72', 'KEYWORD_CANTEEN'),
    (r'\bARAMARK\b', '72', 'KEYWORD_ARAMARK'),
    (r'\bSODEXO\b', '72', 'KEYWORD_SODEXO'),
    (r'\bCOMPASS\s*GROUP\b', '72', 'KEYWORD_COMPASSGROUP'),

    # Construction (23)
    (r'\bCONSTRUCT', '23', 'KEYWORD_CONSTRUCTION'),
    (r'\bCONTRACTOR', '23', 'KEYWORD_CONTRACTOR'),
    (r'\bPLUMB', '23', 'KEYWORD_PLUMBING'),
    (r'\bELECTRICAL\s*CONTRACTOR', '23', 'KEYWORD_ELECCONTRACT'),
    (r'\bROOF', '23', 'KEYWORD_ROOFING'),
    (r'\bPAVING\b', '23', 'KEYWORD_PAVING'),
    (r'\bDEMOLITION\b', '23', 'KEYWORD_DEMOLITION'),
    (r'\bEXCAVAT', '23', 'KEYWORD_EXCAVATING'),
    (r'\bIRONWORKER', '23', 'KEYWORD_IRONWORKER'),
    (r'\bBRICKLAY', '23', 'KEYWORD_BRICKLAYER'),

    # Retail (44-45)
    (r'\bGROCER', '44', 'KEYWORD_GROCERY'),
    (r'\bSUPERMARKET\b', '44', 'KEYWORD_SUPERMARKET'),
    (r'\bDRUGSTORE\b', '44', 'KEYWORD_DRUGSTORE'),
    (r'\bCHEVROLET\b', '44', 'KEYWORD_AUTODEAL'),
    (r'\bFORD\b(?!\s*(FOUNDAT|MOTOR))', '44', 'KEYWORD_AUTODEAL'),
    (r'\bTOYOTA\b', '44', 'KEYWORD_AUTODEAL'),
    (r'\bHONDA\b', '44', 'KEYWORD_AUTODEAL'),
    (r'\bDODGE\b', '44', 'KEYWORD_AUTODEAL'),
    (r'\bBUICK\b', '44', 'KEYWORD_AUTODEAL'),
    (r'\bCHRYSLER\b', '44', 'KEYWORD_AUTODEAL'),
    (r'\bNISSAN\b', '44', 'KEYWORD_AUTODEAL'),
    (r'\bHYUNDAI\b', '44', 'KEYWORD_AUTODEAL'),
    (r'\bKIA\b', '44', 'KEYWORD_AUTODEAL'),
    (r'\bSUBARU\b', '44', 'KEYWORD_AUTODEAL'),
    (r'\bVOLKSWAGEN\b', '44', 'KEYWORD_AUTODEAL'),
    (r'\bAUDI\b', '44', 'KEYWORD_AUTODEAL'),
    (r'\bBMW\b', '44', 'KEYWORD_AUTODEAL'),
    (r'\bMERCEDES\b', '44', 'KEYWORD_AUTODEAL'),
    (r'\bLEXUS\b', '44', 'KEYWORD_AUTODEAL'),
    (r'\bAUTO\s*(DEALER|SALES|GROUP|MALL|NATION)', '44', 'KEYWORD_AUTODEAL'),
    (r'\bDEALER', '44', 'KEYWORD_DEALER'),
    (r'\bRETAIL\b', '44', 'KEYWORD_RETAIL'),

    # Manufacturing (31-33)
    (r'\bMANUFACTUR', '31', 'KEYWORD_MANUFACTURING'),
    (r'\bFOUNDRY\b', '33', 'KEYWORD_FOUNDRY'),
    (r'\bSTEEL\b', '33', 'KEYWORD_STEEL'),
    (r'\bFORGE\b', '33', 'KEYWORD_FORGE'),
    (r'\bMACHINE\s*SHOP\b', '33', 'KEYWORD_MACHINESHOP'),
    (r'\bPACKAGING\b', '32', 'KEYWORD_PACKAGING'),
    (r'\bBREWER', '31', 'KEYWORD_BREWERY'),
    (r'\bBAKER', '31', 'KEYWORD_BAKERY'),
    (r'\bBOTTLING\b', '31', 'KEYWORD_BOTTLING'),
    (r'\bREFINER', '32', 'KEYWORD_REFINERY'),
    (r'\bCHEMICAL\b', '32', 'KEYWORD_CHEMICAL'),
    (r'\bPRINTING\b', '32', 'KEYWORD_PRINTING'),

    # Utilities (22)
    (r'\bELECTRIC\s*(CO|COMPANY|COOP|UTILITY|POWER)', '22', 'KEYWORD_ELECTRIC'),
    (r'\bPOWER\s*(PLANT|STATION|COMPAN|AUTH)', '22', 'KEYWORD_POWER'),
    (r'\bENERGY\b', '22', 'KEYWORD_ENERGY'),
    (r'\bGAS\s*(COMPANY|UTILITY|DIST|LIGHT)', '22', 'KEYWORD_GAS'),
    (r'\bWATER\b', '22', 'KEYWORD_WATER'),

    # Admin/Support/Waste (56)
    (r'\bSECURIT\w+\s*(SERVICE|GUARD|OFFICER|PATROL)', '56', 'KEYWORD_SECURITY'),
    (r'\bSECURITAS\b', '56', 'KEYWORD_SECURITAS'),
    (r'\bALLIED\s*UNIVERSAL\b', '56', 'KEYWORD_ALLIEDUNIV'),
    (r'\bGUARD\b', '56', 'KEYWORD_GUARD'),
    (r'\bJANITOR', '56', 'KEYWORD_JANITORIAL'),
    (r'\bCLEANING\b', '56', 'KEYWORD_CLEANING'),
    (r'\bBUILDING\s*(SERVICE|MAINT)', '56', 'KEYWORD_BLDGSERVICE'),
    (r'\bLANDSCAP', '56', 'KEYWORD_LANDSCAPE'),
    (r'\bTREE\s*(SERVICE|CARE|EXPERT|SURGEON)', '56', 'KEYWORD_TREESERVICE'),
    (r'\bWASTE\b', '56', 'KEYWORD_WASTE'),
    (r'\bDISPOSAL\b', '56', 'KEYWORD_DISPOSAL'),
    (r'\bSANIT', '56', 'KEYWORD_SANITATION'),
    (r'\bRECYCL', '56', 'KEYWORD_RECYCLING'),
    (r'\bPARKING\b', '56', 'KEYWORD_PARKING'),
    (r'\bLINEN\b', '56', 'KEYWORD_LINEN'),
    (r'\bUNIFORM\b', '56', 'KEYWORD_UNIFORM'),
    (r'\bLAUNDR', '56', 'KEYWORD_LAUNDRY'),
    (r'\bABM\b', '56', 'KEYWORD_ABM'),
    (r'\bTEMP\s*(AGENCY|SERVICE|STAFF)', '56', 'KEYWORD_TEMP'),
    (r'\bSTAFFING\b', '56', 'KEYWORD_STAFFING'),
    (r'\bPEST\s*CONTROL\b', '56', 'KEYWORD_PEST'),
    (r'\bEXTERMINAT', '56', 'KEYWORD_EXTERMINATOR'),

    # Other Services (81)
    (r'\bFUNERAL\b', '81', 'KEYWORD_FUNERAL'),
    (r'\bCEMETER', '81', 'KEYWORD_CEMETERY'),
    (r'\bMEMORIAL\s*PARK\b', '81', 'KEYWORD_CEMETERY'),
    (r'\bAUTO\s*(BODY|REPAIR|SERVICE)', '81', 'KEYWORD_AUTOREPAIR'),
    (r'\bCOLLISION\b', '81', 'KEYWORD_COLLISION'),

    # Rental / Leasing (53)
    (r'\bHERTZ\b', '53', 'KEYWORD_HERTZ'),
    (r'\bAVIS\b', '53', 'KEYWORD_AVIS'),
    (r'\bBUDGET\s*(?:RENT|CAR|TRUCK)', '53', 'KEYWORD_BUDGETRENT'),
    (r'\bENTERPRISE\s*RENT', '53', 'KEYWORD_ENTERPRISE'),
    (r'\bRENTAL\b', '53', 'KEYWORD_RENTAL'),

    # Arts / Entertainment (71)
    (r'\bTHEAT', '71', 'KEYWORD_THEATER'),
    (r'\bORCHESTRA\b', '71', 'KEYWORD_ORCHESTRA'),
    (r'\bOPERA\b', '71', 'KEYWORD_OPERA'),
    (r'\bMUSEUM\b', '71', 'KEYWORD_MUSEUM'),
    (r'\bBALLET\b', '71', 'KEYWORD_BALLET'),
    (r'\bSYMPHONY\b', '71', 'KEYWORD_SYMPHONY'),
    (r'\bSTADIUM\b', '71', 'KEYWORD_STADIUM'),
    (r'\bARENA\b', '71', 'KEYWORD_ARENA'),

    # Information (51)
    (r'\bNEWSPAPER', '51', 'KEYWORD_NEWSPAPER'),
    (r'\bPUBLISH', '51', 'KEYWORD_PUBLISHING'),
    (r'\bBROADCAST', '51', 'KEYWORD_BROADCAST'),
    (r'\bRADIO\s*STATION', '51', 'KEYWORD_RADIO'),
    (r'\bTELEVISION\b', '51', 'KEYWORD_TV'),
    (r'\bTELECOM', '51', 'KEYWORD_TELECOM'),
    (r'\bTELEPHONE', '51', 'KEYWORD_TELEPHONE'),
    (r'\bMEDIA\b', '51', 'KEYWORD_MEDIA'),

    # Professional Services (54)
    (r'\bLAW\s*(FIRM|OFFICE)', '54', 'KEYWORD_LAWFIRM'),
    (r'\bLEGAL\b', '54', 'KEYWORD_LEGAL'),
    (r'\bACCOUNTING\b', '54', 'KEYWORD_ACCOUNTING'),
    (r'\bENGINEER', '54', 'KEYWORD_ENGINEERING'),
    (r'\bARCHITECT', '54', 'KEYWORD_ARCHITECT'),

    # Finance / Insurance (52)
    (r'\bBANK\b', '52', 'KEYWORD_BANK'),
    (r'\bCREDIT\s*UNION\b', '52', 'KEYWORD_CREDITUNION'),
    (r'\bINSURANC', '52', 'KEYWORD_INSURANCE'),

    # Food / Grocery (specific companies)
    (r'\bSTARBUCKS\b', '72', 'KEYWORD_STARBUCKS'),
    (r'\bMCDONALD', '72', 'KEYWORD_MCDONALDS'),
    (r'\bSAFEWAY\b', '44', 'KEYWORD_SAFEWAY'),
    (r'\bKROGER\b', '44', 'KEYWORD_KROGER'),
    (r'\bALBERTSON', '44', 'KEYWORD_ALBERTSONS'),

    # Membership organizations / unions themselves (81)
    (r'\bLOCAL\s+\d', '81', 'KEYWORD_UNIONLOCAL'),
    (r'\bUNION\b', '81', 'KEYWORD_UNION'),
    (r'\bASSOCIATION\b', '81', 'KEYWORD_ASSOC'),
    (r'\bFOUNDATION\b', '81', 'KEYWORD_FOUNDATION'),

    # Wholesale (42)
    (r'\bWHOLESALE\b', '42', 'KEYWORD_WHOLESALE'),
    (r'\bDISTRIBUT', '42', 'KEYWORD_DISTRIBUTOR'),
    (r'\bSUPPLY\s*(COMPANY|HOUSE|CO\b)', '42', 'KEYWORD_SUPPLY'),

    # Warehousing (49)
    (r'\bWAREHOUS', '49', 'KEYWORD_WAREHOUSE'),

    # Mining (21)
    (r'\bMINING\b', '21', 'KEYWORD_MINING'),
    (r'\bQUARR', '21', 'KEYWORD_QUARRY'),

    # Agriculture (11)
    (r'\bFARM\b', '11', 'KEYWORD_FARM'),
    (r'\bDAIRY\b', '11', 'KEYWORD_DAIRY'),
    (r'\bRANCH\b', '11', 'KEYWORD_RANCH'),

    # Real Estate (53)
    (r'\bREAL\s*ESTATE\b', '53', 'KEYWORD_REALESTATE'),
    (r'\bPROPERTY\s*MANAG', '53', 'KEYWORD_PROPMGMT'),
]


def get_missing_employers(conn):
    """Get all employers missing NAICS codes."""
    cur = conn.cursor()
    cur.execute("""
        SELECT employer_id, employer_name, employer_name_aggressive, state,
               latest_union_fnum
        FROM f7_employers_deduped
        WHERE naics IS NULL OR naics = ''
        ORDER BY employer_id
    """)
    return cur.fetchall()


def tier1_mergent_crosswalk(conn, missing_ids):
    """Tier 1: Get NAICS from Mergent via crosswalk."""
    cur = conn.cursor()
    cur.execute("""
        SELECT f.employer_id, LEFT(m.naics_primary::text, 2) as naics_2d,
               m.naics_primary, m.naics_primary_desc
        FROM f7_employers_deduped f
        JOIN corporate_identifier_crosswalk c ON c.f7_employer_id = f.employer_id
        JOIN mergent_employers m ON m.duns = c.mergent_duns
        WHERE f.employer_id = ANY(%s)
          AND c.mergent_duns IS NOT NULL
          AND m.naics_primary IS NOT NULL
    """, (list(missing_ids),))

    results = {}
    for eid, naics_2d, naics_full, desc in cur.fetchall():
        results[eid] = {
            'naics': naics_2d,
            'naics_detailed': str(naics_full),
            'source': 'MERGENT_CROSSWALK',
            'confidence': 'HIGH',
            'detail': desc or '',
        }
    return results


def tier2_osha_trgm(conn, missing_ids, batch_size=500):
    """Tier 2: OSHA high-confidence pg_trgm match (similarity >= 0.7)."""
    cur = conn.cursor()
    results = {}

    # Process in batches to avoid memory issues
    id_list = list(missing_ids)
    for i in range(0, len(id_list), batch_size):
        batch = id_list[i:i + batch_size]
        cur.execute("""
            SELECT f.employer_id, best.naics_code, best.sim, best.osha_name
            FROM f7_employers_deduped f
            CROSS JOIN LATERAL (
                SELECT o.naics_code,
                       similarity(o.estab_name_normalized, f.employer_name_aggressive) as sim,
                       o.estab_name_normalized as osha_name
                FROM osha_establishments o
                WHERE o.site_state = f.state
                  AND o.naics_code IS NOT NULL
                  AND o.estab_name_normalized %% f.employer_name_aggressive
                  AND similarity(o.estab_name_normalized, f.employer_name_aggressive) >= 0.7
                ORDER BY similarity(o.estab_name_normalized, f.employer_name_aggressive) DESC
                LIMIT 1
            ) best
            WHERE f.employer_id = ANY(%s)
        """, (batch,))

        for eid, naics, sim, osha_name in cur.fetchall():
            naics_2d = str(naics)[:2] if naics else None
            if naics_2d:
                results[eid] = {
                    'naics': naics_2d,
                    'naics_detailed': str(naics),
                    'source': 'OSHA_TRGM',
                    'confidence': 'HIGH' if sim >= 0.8 else 'MEDIUM',
                    'detail': f'sim={sim:.3f} osha={osha_name}',
                }
    return results


def tier3_union_peer(conn, missing_employers, min_peers=3):
    """Tier 3: Infer NAICS from peer employers with the same union local."""
    cur = conn.cursor()
    results = {}

    # Build a map of union_fnum -> most common NAICS among its employers
    cur.execute("""
        SELECT latest_union_fnum, naics, COUNT(*) as cnt
        FROM f7_employers_deduped
        WHERE naics IS NOT NULL AND naics != ''
          AND latest_union_fnum IS NOT NULL
        GROUP BY latest_union_fnum, naics
        ORDER BY latest_union_fnum, cnt DESC
    """)

    union_naics = {}
    for fnum, naics, cnt in cur.fetchall():
        if fnum not in union_naics:
            union_naics[fnum] = (naics, cnt)

    for eid, name, name_agg, state, union_fnum in missing_employers:
        if eid in results:
            continue
        if union_fnum and union_fnum in union_naics:
            naics, peer_count = union_naics[union_fnum]
            if peer_count >= min_peers:
                if peer_count >= 10:
                    conf = 'HIGH'
                elif peer_count >= 3:
                    conf = 'MEDIUM'
                else:
                    conf = 'LOW'
                results[eid] = {
                    'naics': naics,
                    'naics_detailed': naics,
                    'source': 'UNION_PEER',
                    'confidence': conf,
                    'detail': f'union={union_fnum} peers={peer_count}',
                }

    return results


def tier4_keyword(missing_employers, already_matched):
    """Tier 4: Keyword pattern matching on employer name."""
    results = {}

    for eid, name, name_agg, state, union_fnum in missing_employers:
        if eid in already_matched:
            continue

        upper_name = (name or '').upper()
        for pattern, naics, source_tag in KEYWORD_RULES:
            if re.search(pattern, upper_name):
                results[eid] = {
                    'naics': naics,
                    'naics_detailed': naics,
                    'source': source_tag,
                    'confidence': 'MEDIUM',
                    'detail': f'matched: {pattern}',
                }
                break

    return results


CONFIDENCE_SCORES = {'HIGH': 0.90, 'MEDIUM': 0.70, 'LOW': 0.50}


def apply_updates(conn, all_results, dry_run=True):
    """Apply NAICS updates to the database."""
    cur = conn.cursor()

    if dry_run:
        print("\n[DRY RUN] Would update the following:")
    else:
        print("\n[APPLYING] Updating database...")

    for eid, info in sorted(all_results.items()):
        if not dry_run:
            conf_score = CONFIDENCE_SCORES.get(info['confidence'], 0.50)
            cur.execute("""
                UPDATE f7_employers_deduped
                SET naics = %s,
                    naics_detailed = COALESCE(naics_detailed, %s),
                    naics_source = %s,
                    naics_confidence = %s
                WHERE employer_id = %s
                  AND (naics IS NULL OR naics = '')
            """, (
                info['naics'],
                info['naics_detailed'],
                info['source'],
                conf_score,
                eid,
            ))

    if not dry_run:
        conn.commit()
        print(f"  Committed {len(all_results):,} updates")


def main():
    parser = argparse.ArgumentParser(description="Backfill missing NAICS codes")
    parser.add_argument('--apply', action='store_true', help='Apply changes (default: dry run)')
    args = parser.parse_args()

    conn = get_connection()

    print("=" * 60)
    print("NAICS Backfill for F7 Employers")
    print("=" * 60)

    # Get missing employers
    missing = get_missing_employers(conn)
    missing_ids = {row[0] for row in missing}
    print(f"\nMissing NAICS: {len(missing):,} employers")

    all_results = {}

    # Tier 1: Mergent crosswalk
    print("\n--- Tier 1: Mergent Crosswalk ---")
    t1 = tier1_mergent_crosswalk(conn, missing_ids)
    all_results.update(t1)
    remaining = missing_ids - set(all_results.keys())
    print(f"  Matched: {len(t1):,} | Remaining: {len(remaining):,}")

    # Tier 2: OSHA pg_trgm (high confidence)
    print("\n--- Tier 2: OSHA pg_trgm (sim >= 0.7) ---")
    t2 = tier2_osha_trgm(conn, remaining)
    all_results.update(t2)
    remaining = missing_ids - set(all_results.keys())
    print(f"  Matched: {len(t2):,} | Remaining: {len(remaining):,}")

    # Tier 3a: Union peer inference (3+ peers)
    print("\n--- Tier 3a: Union Peer Inference (3+ peers) ---")
    t3a = tier3_union_peer(conn, [e for e in missing if e[0] in remaining], min_peers=3)
    all_results.update(t3a)
    remaining = missing_ids - set(all_results.keys())
    print(f"  Matched: {len(t3a):,} | Remaining: {len(remaining):,}")

    # Tier 3b: Union peer inference (2 peers, lower confidence)
    print("\n--- Tier 3b: Union Peer Inference (2 peers) ---")
    t3b = tier3_union_peer(conn, [e for e in missing if e[0] in remaining], min_peers=2)
    all_results.update(t3b)
    remaining = missing_ids - set(all_results.keys())
    print(f"  Matched: {len(t3b):,} | Remaining: {len(remaining):,}")

    # Tier 4: Keyword matching
    print("\n--- Tier 4: Keyword Inference ---")
    t4 = tier4_keyword(missing, set(all_results.keys()))
    all_results.update(t4)
    remaining = missing_ids - set(all_results.keys())
    print(f"  Matched: {len(t4):,} | Remaining: {len(remaining):,}")

    # Summary
    total_f7 = 60953  # approximate
    new_coverage = total_f7 - len(remaining)
    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total missing before:  {len(missing):,}")
    print(f"  Tier 1 (Mergent):      {len(t1):,}")
    print(f"  Tier 2 (OSHA trgm):    {len(t2):,}")
    print(f"  Tier 3a (Peer 3+):     {len(t3a):,}")
    print(f"  Tier 3b (Peer 2):      {len(t3b):,}")
    print(f"  Tier 4 (Keyword):      {len(t4):,}")
    print(f"  Total backfilled:      {len(all_results):,}")
    print(f"  Still missing:         {len(remaining):,} ({len(remaining)/total_f7:.1%})")
    print(f"  New NAICS coverage:    {new_coverage/total_f7:.1%}")

    # Source breakdown
    sources = Counter(v['source'] for v in all_results.values())
    print(f"\n  By source:")
    for src, cnt in sources.most_common(20):
        print(f"    {src}: {cnt:,}")

    if len(remaining) > 0 and len(remaining) <= 50:
        print(f"\n  Still missing (showing all):")
        for e in missing:
            if e[0] in remaining:
                print(f"    [{e[0]}] {e[1]} ({e[3]})")
    elif len(remaining) > 50:
        print(f"\n  Sample still missing (first 20):")
        count = 0
        for e in missing:
            if e[0] in remaining:
                print(f"    [{e[0]}] {e[1]} ({e[3]})")
                count += 1
                if count >= 20:
                    break

    # Apply or dry run
    if args.apply:
        apply_updates(conn, all_results, dry_run=False)
    else:
        print(f"\n  [DRY RUN] Use --apply to write changes to database")

    conn.close()


if __name__ == '__main__':
    main()
