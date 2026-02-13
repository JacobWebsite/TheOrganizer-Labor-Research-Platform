from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from ..database import get_db

router = APIRouter()


@router.get("/api/multi-employer/stats")
def get_multi_employer_stats():
    """Get multi-employer agreement deduplication statistics"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Summary stats
            cur.execute("""
                SELECT
                    COUNT(*) as total_employers,
                    SUM(latest_unit_size) as total_workers_raw,
                    SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted_workers,
                    SUM(CASE WHEN exclude_from_counts = TRUE THEN latest_unit_size ELSE 0 END) as excluded_workers,
                    COUNT(CASE WHEN exclude_from_counts = TRUE THEN 1 END) as excluded_records,
                    ROUND(100.0 * SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) / 7200000, 1) as bls_coverage_pct
                FROM f7_employers_deduped
            """)
            summary = cur.fetchone()

            # By exclusion reason
            cur.execute("""
                SELECT COALESCE(exclude_reason, 'INCLUDED') as reason,
                       COUNT(*) as employers,
                       SUM(latest_unit_size) as workers
                FROM f7_employers_deduped
                GROUP BY exclude_reason
                ORDER BY SUM(latest_unit_size) DESC
            """)
            by_reason = cur.fetchall()

            # Top multi-employer groups
            cur.execute("""
                SELECT multi_employer_group_id,
                       MAX(latest_union_name) as union_name,
                       COUNT(*) as employers_in_group,
                       SUM(latest_unit_size) as total_workers,
                       SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted_workers
                FROM f7_employers_deduped
                WHERE multi_employer_group_id IS NOT NULL
                GROUP BY multi_employer_group_id
                ORDER BY SUM(latest_unit_size) DESC
                LIMIT 20
            """)
            top_groups = cur.fetchall()

            return {
                "summary": summary,
                "by_reason": by_reason,
                "top_groups": top_groups
            }


@router.get("/api/multi-employer/groups")
def get_multi_employer_groups(limit: int = Query(50, le=200)):
    """Get list of multi-employer agreement groups"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM v_multi_employer_groups
                ORDER BY total_reported_workers DESC
                LIMIT %s
            """, [limit])
            return {"groups": cur.fetchall()}


@router.get("/api/employer/{employer_id}/agreement")
def get_employer_agreement_info(employer_id: str):
    """Get multi-employer agreement context for an employer"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT employer_id, employer_name, multi_employer_group_id,
                       is_primary_in_group, exclude_from_counts, exclude_reason,
                       latest_unit_size, latest_union_name
                FROM f7_employers_deduped
                WHERE employer_id = %s
            """, [employer_id])
            employer = cur.fetchone()

            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")

            # Get other employers in same group
            group_members = []
            if employer.get('multi_employer_group_id'):
                cur.execute("""
                    SELECT employer_id, employer_name, city, state,
                           latest_unit_size, is_primary_in_group, exclude_from_counts
                    FROM f7_employers_deduped
                    WHERE multi_employer_group_id = %s
                    ORDER BY latest_unit_size DESC
                    LIMIT 20
                """, [employer['multi_employer_group_id']])
                group_members = cur.fetchall()

            return {
                "employer": employer,
                "group_members": group_members,
                "group_size": len(group_members)
            }


@router.get("/api/corporate/family/{employer_id}")
def get_corporate_family(employer_id: str):
    """Get related employers (corporate family) - ownership hierarchy + name similarity + multi-employer groups"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get employer info (only columns that exist on f7_employers_deduped)
            cur.execute("""
                SELECT employer_id, employer_name, employer_name_aggressive, state, naics,
                       multi_employer_group_id, latest_union_name, latest_unit_size,
                       city, latitude, longitude, street
                FROM f7_employers_deduped WHERE employer_id = %s
            """, [employer_id])
            employer = cur.fetchone()

            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")

            # Get crosswalk data for this employer (SEC, GLEIF, corporate family)
            cur.execute("""
                SELECT corporate_family_id, sec_cik, gleif_lei, mergent_duns,
                       ein, ticker, is_public, canonical_name
                FROM corporate_identifier_crosswalk
                WHERE f7_employer_id = %s
                LIMIT 1
            """, [employer_id])
            xwalk = cur.fetchone()

            family_members = []
            hierarchy_source = "NAME_SIMILARITY"

            # Priority 1: Corporate hierarchy via crosswalk corporate_family_id
            corporate_family_id = xwalk['corporate_family_id'] if xwalk else None
            if corporate_family_id:
                hierarchy_source = "CORPORATE_HIERARCHY"
                cur.execute("""
                    SELECT f.employer_id, f.employer_name, f.city, f.state, f.naics,
                           f.latest_unit_size, f.latest_union_name,
                           'CORPORATE_FAMILY' as relationship,
                           f.latitude, f.longitude,
                           c.ticker, c.is_public
                    FROM corporate_identifier_crosswalk c
                    JOIN f7_employers_deduped f ON c.f7_employer_id = f.employer_id
                    WHERE c.corporate_family_id = %s AND f.employer_id != %s
                    ORDER BY f.latest_unit_size DESC NULLS LAST
                    LIMIT 50
                """, [corporate_family_id, employer_id])
                family_members.extend(cur.fetchall())

                # Also include Mergent employers in same family via crosswalk
                cur.execute("""
                    SELECT m.duns as employer_id, m.company_name as employer_name,
                           m.city, m.state, m.naics_primary as naics,
                           m.employees_site as latest_unit_size,
                           CASE WHEN m.has_union THEN m.f7_union_name ELSE NULL END as latest_union_name,
                           'MERGENT_FAMILY' as relationship,
                           NULL as latitude, NULL as longitude,
                           c.ticker, c.is_public
                    FROM corporate_identifier_crosswalk c
                    JOIN mergent_employers m ON c.mergent_duns = m.duns
                    WHERE c.corporate_family_id = %s
                      AND c.f7_employer_id IS DISTINCT FROM %s
                    ORDER BY m.employees_site DESC NULLS LAST
                    LIMIT 30
                """, [corporate_family_id, employer_id])
                family_members.extend(cur.fetchall())

            # Priority 2: Multi-employer group members
            if employer.get('multi_employer_group_id'):
                existing_ids = {m['employer_id'] for m in family_members}
                cur.execute("""
                    SELECT employer_id, employer_name, city, state, naics,
                           latest_unit_size, latest_union_name, 'MULTI_EMPLOYER_GROUP' as relationship,
                           latitude, longitude, NULL as ticker, NULL as is_public
                    FROM f7_employers_deduped
                    WHERE multi_employer_group_id = %s AND employer_id != %s
                    ORDER BY latest_unit_size DESC
                    LIMIT 20
                """, [employer['multi_employer_group_id'], employer_id])
                for row in cur.fetchall():
                    if row['employer_id'] not in existing_ids:
                        family_members.append(row)

            # Priority 3: Name similarity (fallback)
            if employer.get('employer_name_aggressive') and len(family_members) < 5:
                existing_ids = {m['employer_id'] for m in family_members}
                cur.execute("""
                    SELECT employer_id, employer_name, city, state, naics,
                           latest_unit_size, latest_union_name,
                           'NAME_SIMILARITY' as relationship,
                           similarity(employer_name_aggressive, %s) as name_similarity,
                           latitude, longitude, NULL as ticker, NULL as is_public
                    FROM f7_employers_deduped
                    WHERE employer_id != %s
                      AND similarity(employer_name_aggressive, %s) > 0.5
                    ORDER BY similarity(employer_name_aggressive, %s) DESC
                    LIMIT 15
                """, [employer['employer_name_aggressive'], employer_id,
                      employer['employer_name_aggressive'],
                      employer['employer_name_aggressive']])
                for row in cur.fetchall():
                    if row['employer_id'] not in existing_ids:
                        family_members.append(row)

            # Compute summary stats
            root_name = (xwalk['canonical_name'] if xwalk and xwalk.get('canonical_name') else None) or employer['employer_name']
            states = list(set(m.get('state') for m in family_members if m.get('state')))
            states.sort()
            total_workers = sum(m.get('latest_unit_size') or 0 for m in family_members)
            total_workers += employer.get('latest_unit_size') or 0
            unions = list(set(m.get('latest_union_name') for m in family_members if m.get('latest_union_name')))
            unionized_count = sum(1 for m in family_members if m.get('latest_union_name'))

            # SEC info via crosswalk
            sec_info = None
            if xwalk and xwalk.get('sec_cik'):
                sec_info = {
                    "cik": xwalk['sec_cik'],
                    "ticker": xwalk.get('ticker'),
                    "is_public": xwalk.get('is_public', False)
                }

            return {
                "employer": employer,
                "root_name": root_name,
                "hierarchy_source": hierarchy_source,
                "family_members": family_members,
                "total_family": len(family_members),
                "total_workers": total_workers,
                "states": states,
                "unions": unions,
                "unionized_count": unionized_count,
                "sec_info": sec_info
            }


@router.get("/api/corporate/hierarchy/stats")
def get_corporate_hierarchy_stats():
    """Get overall corporate hierarchy statistics"""
    with get_db() as conn:
        with conn.cursor() as cur:
            stats = {}

            cur.execute("SELECT COUNT(*) as cnt FROM corporate_hierarchy")
            stats['total_hierarchy_links'] = cur.fetchone()['cnt']

            cur.execute("""
                SELECT source, COUNT(*) as cnt
                FROM corporate_hierarchy GROUP BY source ORDER BY cnt DESC
            """)
            stats['by_source'] = [dict(r) for r in cur.fetchall()]

            # Count distinct ultimate parents from hierarchy
            cur.execute("SELECT COUNT(DISTINCT parent_duns) FROM corporate_hierarchy WHERE is_direct = false")
            stats['total_ultimate_parents'] = cur.fetchone()[0]

            # Corporate families and SEC linkages via crosswalk
            cur.execute("SELECT COUNT(DISTINCT corporate_family_id) FROM corporate_identifier_crosswalk WHERE corporate_family_id IS NOT NULL")
            stats['f7_families'] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE sec_cik IS NOT NULL")
            stats['f7_with_sec'] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE is_public = TRUE")
            stats['f7_public_companies'] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM sec_companies")
            stats['total_sec_companies'] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM gleif_us_entities")
            stats['total_gleif_us_entities'] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk")
            stats['total_crosswalk_entries'] = cur.fetchone()[0]

            return stats


@router.get("/api/corporate/hierarchy/{employer_id}")
def get_corporate_hierarchy(employer_id: str, source: str = Query("f7")):
    """Get ownership-based corporate hierarchy for an employer.

    source: 'f7' (employer_id is F7 ID) or 'mergent' (employer_id is DUNS)
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Find the employer basic info
            if source == 'f7':
                cur.execute("""
                    SELECT f.employer_id, f.employer_name, f.city, f.state
                    FROM f7_employers_deduped f WHERE f.employer_id = %s
                """, [employer_id])
            else:
                cur.execute("""
                    SELECT m.duns as employer_id, m.company_name as employer_name,
                           m.city, m.state,
                           COALESCE(m.domestic_parent_duns, m.parent_duns) as parent_duns_val
                    FROM mergent_employers m WHERE m.duns = %s
                """, [employer_id])

            employer = cur.fetchone()
            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")

            # Get crosswalk data
            cur.execute("""
                SELECT corporate_family_id, sec_cik, gleif_lei, mergent_duns,
                       ein, ticker, is_public, canonical_name
                FROM corporate_identifier_crosswalk
                WHERE f7_employer_id = %s
                LIMIT 1
            """, [employer_id])
            xwalk = cur.fetchone()

            result = {
                "employer": employer,
                "crosswalk": dict(xwalk) if xwalk else None,
                "ultimate_parent": None,
                "parent_chain": [],
                "siblings": [],
                "subsidiaries": [],
                "total_family_size": 0,
                "family_union_status": {"unionized_count": 0, "total_count": 0}
            }

            # Get hierarchy links where this employer is involved
            duns = xwalk['mergent_duns'] if xwalk and xwalk.get('mergent_duns') else (employer.get('parent_duns_val') if source == 'mergent' else None)
            family_id = xwalk['corporate_family_id'] if xwalk else None

            # Also check hierarchy directly by f7_employer_id
            cur.execute("""
                SELECT parent_name, parent_duns, parent_lei, parent_cik,
                       relationship_type, is_direct, source, confidence
                FROM corporate_hierarchy
                WHERE child_f7_employer_id = %s
                ORDER BY is_direct DESC
            """, [employer_id])
            result['parent_chain'] = [dict(r) for r in cur.fetchall()]

            if duns and not result['parent_chain']:
                cur.execute("""
                    SELECT parent_name, parent_duns, parent_lei, parent_cik,
                           relationship_type, is_direct, source, confidence
                    FROM corporate_hierarchy
                    WHERE child_duns = %s
                    ORDER BY is_direct DESC
                """, [duns])
                result['parent_chain'] = [dict(r) for r in cur.fetchall()]

            # Find siblings (same parent)
            if result['parent_chain']:
                parent_duns = result['parent_chain'][0].get('parent_duns')
                if parent_duns:
                    cur.execute("""
                        SELECT h.child_name, h.child_duns,
                               m.has_union, m.employees_site, m.city, m.state
                        FROM corporate_hierarchy h
                        LEFT JOIN mergent_employers m ON h.child_duns = m.duns
                        WHERE h.parent_duns = %s AND COALESCE(h.child_duns, '') != COALESCE(%s, '')
                        LIMIT 50
                    """, [parent_duns, duns])
                    result['siblings'] = [dict(r) for r in cur.fetchall()]

            # Find subsidiaries
            if duns:
                cur.execute("""
                    SELECT h.child_name, h.child_duns,
                           m.has_union, m.employees_site, m.city, m.state
                    FROM corporate_hierarchy h
                    LEFT JOIN mergent_employers m ON h.child_duns = m.duns
                    WHERE h.parent_duns = %s
                    LIMIT 50
                """, [duns])
                result['subsidiaries'] = [dict(r) for r in cur.fetchall()]

            # Ultimate parent info
            if result['parent_chain']:
                top = result['parent_chain'][-1]  # Last in chain = ultimate parent
                result['ultimate_parent'] = {
                    "name": top.get('parent_name'),
                    "duns": top.get('parent_duns'),
                    "cik": top.get('parent_cik') or (xwalk['sec_cik'] if xwalk else None),
                    "ticker": xwalk.get('ticker') if xwalk else None,
                    "is_public": xwalk.get('is_public', False) if xwalk else False
                }

            # Family stats via crosswalk
            if family_id:
                cur.execute("""
                    SELECT COUNT(*) as total,
                           COUNT(*) FILTER (WHERE f.latest_union_name IS NOT NULL) as unionized
                    FROM corporate_identifier_crosswalk c
                    JOIN f7_employers_deduped f ON c.f7_employer_id = f.employer_id
                    WHERE c.corporate_family_id = %s
                """, [family_id])
                fam = cur.fetchone()
                result['total_family_size'] = fam['total']
                result['family_union_status'] = {
                    "unionized_count": fam['unionized'],
                    "total_count": fam['total']
                }

            return result


@router.get("/api/corporate/hierarchy/search")
def search_corporate_hierarchy(
    name: str = Query(None),
    ein: str = Query(None),
    ticker: str = Query(None),
    limit: int = Query(20, le=100)
):
    """Search corporate hierarchy by name, EIN, or ticker"""
    with get_db() as conn:
        with conn.cursor() as cur:
            if ticker:
                cur.execute("""
                    SELECT cik, company_name, ein, lei, sic_code, sic_description,
                           state, city, ticker, exchange, is_public
                    FROM sec_companies WHERE UPPER(ticker) = UPPER(%s)
                    LIMIT %s
                """, [ticker, limit])
            elif ein:
                clean = ein.replace('-', '')
                cur.execute("""
                    SELECT cik, company_name, ein, lei, sic_code, sic_description,
                           state, city, ticker, exchange, is_public
                    FROM sec_companies WHERE ein = %s
                    LIMIT %s
                """, [clean, limit])
            elif name:
                cur.execute("""
                    SELECT cik, company_name, ein, lei, sic_code, sic_description,
                           state, city, ticker, exchange, is_public,
                           similarity(name_normalized, %s) as sim
                    FROM sec_companies
                    WHERE name_normalized %% %s
                    ORDER BY similarity(name_normalized, %s) DESC
                    LIMIT %s
                """, [name.lower(), name.lower(), name.lower(), limit])
            else:
                return {"results": [], "total": 0}

            results = [dict(r) for r in cur.fetchall()]
            return {"results": results, "total": len(results)}


@router.get("/api/corporate/sec/{cik}")
def get_sec_company(cik: int):
    """Get SEC company profile by CIK number"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT cik, company_name, ein, lei, sic_code, sic_description,
                       entity_type, state_of_incorporation, state, city, zip,
                       street_address, ticker, exchange, is_public
                FROM sec_companies WHERE cik = %s
            """, [cik])
            company = cur.fetchone()
            if not company:
                raise HTTPException(status_code=404, detail="SEC company not found")

            # Find linked F7 employers via crosswalk
            cur.execute("""
                SELECT f.employer_id, f.employer_name, f.city, f.state,
                       f.latest_union_name, f.latest_unit_size
                FROM corporate_identifier_crosswalk c
                JOIN f7_employers_deduped f ON c.f7_employer_id = f.employer_id
                WHERE c.sec_cik = %s
                ORDER BY f.latest_unit_size DESC NULLS LAST
            """, [cik])
            f7_employers = [dict(r) for r in cur.fetchall()]

            # Find linked Mergent employers via crosswalk
            cur.execute("""
                SELECT m.duns, m.company_name, m.city, m.state,
                       m.has_union, m.employees_site, m.sector_category
                FROM corporate_identifier_crosswalk c
                JOIN mergent_employers m ON c.mergent_duns = m.duns
                WHERE c.sec_cik = %s
                ORDER BY m.employees_site DESC NULLS LAST
            """, [cik])
            mergent_employers = [dict(r) for r in cur.fetchall()]

            return {
                "company": dict(company),
                "f7_employers": f7_employers,
                "mergent_employers": mergent_employers
            }
