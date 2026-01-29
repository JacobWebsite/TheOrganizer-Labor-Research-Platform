"""
CHECKPOINT A1: API Updates for Sector Toggle
Adds unified employer search endpoint supporting private + federal sectors
"""

# Add these new endpoints to labor_api_v4.py
# Insert after the existing /api/lookups/sectors endpoint

CHECKPOINT_A1_CODE = '''
# ============================================================================
# UNIFIED SECTOR SEARCH - v5.0 with Private + Federal Toggle
# ============================================================================

@app.get("/api/v5/sectors/summary")
def get_sector_summary():
    """Get summary stats for all sectors from unified view"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM sector_summary ORDER BY total_workers DESC
            """)
            sectors = cur.fetchall()
            
            # Get total
            cur.execute("""
                SELECT 
                    COUNT(*) as total_employers,
                    SUM(workers_covered) as total_workers
                FROM all_employers_unified
            """)
            totals = cur.fetchone()
            
            return {
                "sectors": sectors,
                "totals": totals
            }


@app.get("/api/v5/employers/search")
def search_unified_employers(
    # Sector filter (NEW!)
    sector: Optional[str] = Query(None, description="PRIVATE, FEDERAL, or ALL"),
    
    # Search terms
    name: Optional[str] = Query(None, description="Employer name (fuzzy match)"),
    
    # Union filters  
    union: Optional[str] = Query(None, description="Union acronym (e.g., SEIU, AFGE)"),
    
    # Geographic filters
    state: Optional[str] = Query(None, description="State abbreviation"),
    
    # Pagination
    limit: int = Query(50, le=500),
    offset: int = 0,
    
    # Sorting
    sort_by: str = Query("workers", description="Sort by: workers, name")
):
    """
    Search employers across ALL sectors (private + federal) using unified view.
    
    Sector options:
    - PRIVATE: F-7 private sector employers (cleaned, ~6.6M workers)
    - FEDERAL: FLRA federal bargaining units (~1.3M workers)
    - ALL: Both sectors combined (~7.9M workers)
    """
    conditions = ["1=1"]
    params = []
    
    # Sector filter
    if sector and sector.upper() != 'ALL':
        conditions.append("sector_code = %s")
        params.append(sector.upper())
    
    # Name search
    if name:
        conditions.append("LOWER(employer_name) LIKE %s")
        params.append(f"%{name.lower()}%")
    
    # Union filter
    if union:
        conditions.append("union_acronym = %s")
        params.append(union.upper())
    
    # State filter
    if state:
        conditions.append("state = %s")
        params.append(state.upper())
    
    where_clause = " AND ".join(conditions)
    
    # Sorting
    order_map = {
        "workers": "workers_covered DESC NULLS LAST",
        "name": "employer_name ASC"
    }
    order_by = order_map.get(sort_by, order_map["workers"])
    
    with get_db() as conn:
        with conn.cursor() as cur:
            # Count
            cur.execute(f"""
                SELECT COUNT(*) as total, SUM(workers_covered) as total_workers
                FROM all_employers_unified
                WHERE {where_clause}
            """, params)
            counts = cur.fetchone()
            
            # Results
            params_with_pagination = params + [limit, offset]
            cur.execute(f"""
                SELECT 
                    unified_id,
                    employer_name,
                    sub_employer,
                    location_description,
                    employer_type,
                    sector_code,
                    state,
                    lat,
                    lon,
                    union_acronym,
                    union_name,
                    workers_covered,
                    governing_law,
                    data_source
                FROM all_employers_unified
                WHERE {where_clause}
                ORDER BY {order_by}
                LIMIT %s OFFSET %s
            """, params_with_pagination)
            
            employers = cur.fetchall()
            
            return {
                "total": counts['total'],
                "total_workers": counts['total_workers'],
                "sector_filter": sector or 'ALL',
                "limit": limit,
                "offset": offset,
                "employers": employers
            }


@app.get("/api/v5/unions/by-sector")
def get_unions_by_sector(
    sector: Optional[str] = Query(None, description="PRIVATE, FEDERAL, or ALL"),
    min_workers: int = Query(1000, description="Minimum workers to include")
):
    """Get unions with their worker counts by sector"""
    with get_db() as conn:
        with conn.cursor() as cur:
            if sector and sector.upper() != 'ALL':
                cur.execute("""
                    SELECT 
                        union_acronym,
                        sector_code,
                        employer_count,
                        workers_covered
                    FROM union_sector_coverage
                    WHERE sector_code = %s AND workers_covered >= %s
                    ORDER BY workers_covered DESC
                """, [sector.upper(), min_workers])
            else:
                cur.execute("""
                    SELECT 
                        union_acronym,
                        SUM(CASE WHEN sector_code = 'PRIVATE' THEN workers_covered ELSE 0 END) as private_workers,
                        SUM(CASE WHEN sector_code = 'FEDERAL' THEN workers_covered ELSE 0 END) as federal_workers,
                        SUM(workers_covered) as total_workers,
                        SUM(employer_count) as total_employers
                    FROM union_sector_coverage
                    WHERE union_acronym IS NOT NULL AND union_acronym != 'UNKNOWN'
                    GROUP BY union_acronym
                    HAVING SUM(workers_covered) >= %s
                    ORDER BY SUM(workers_covered) DESC
                """, [min_workers])
            
            return {"unions": cur.fetchall()}


@app.get("/api/v5/stats/overview")
def get_unified_overview():
    """Get platform stats including both sectors"""
    with get_db() as conn:
        with conn.cursor() as cur:
            stats = {}
            
            # Sector summary
            cur.execute("SELECT * FROM sector_summary ORDER BY total_workers DESC")
            stats['sectors'] = cur.fetchall()
            
            # Top unions across both sectors
            cur.execute("""
                SELECT 
                    union_acronym,
                    SUM(CASE WHEN sector_code = 'PRIVATE' THEN workers_covered ELSE 0 END) as private,
                    SUM(CASE WHEN sector_code = 'FEDERAL' THEN workers_covered ELSE 0 END) as federal,
                    SUM(workers_covered) as total
                FROM all_employers_unified
                WHERE union_acronym IS NOT NULL AND union_acronym != 'UNKNOWN'
                GROUP BY union_acronym
                ORDER BY SUM(workers_covered) DESC
                LIMIT 15
            """)
            stats['top_unions'] = cur.fetchall()
            
            # Top employers by sector
            cur.execute("""
                SELECT sector_code, employer_name, union_acronym, workers_covered
                FROM all_employers_unified
                WHERE workers_covered > 0 AND union_acronym IS NOT NULL AND union_acronym != 'UNKNOWN'
                ORDER BY workers_covered DESC
                LIMIT 20
            """)
            stats['top_employers'] = cur.fetchall()
            
            return stats
'''

print("=" * 80)
print("CHECKPOINT A1: API Sector Filtering Endpoints")
print("=" * 80)
print("""
New endpoints to add to labor_api_v4.py:

1. GET /api/v5/sectors/summary
   - Returns sector breakdown (PRIVATE vs FEDERAL)
   - Worker counts, employer counts per sector

2. GET /api/v5/employers/search
   - Unified search across both sectors
   - Parameters: sector (PRIVATE/FEDERAL/ALL), name, union, state
   - Returns employers from all_employers_unified view

3. GET /api/v5/unions/by-sector  
   - Union worker counts broken down by sector
   - Shows which unions operate in both sectors

4. GET /api/v5/stats/overview
   - Dashboard stats for both sectors
   - Top unions, top employers across sectors
""")

# Write the actual code to a file
with open("C:/Users/jakew/Downloads/checkpoint_a1_api_additions.py", "w") as f:
    f.write(CHECKPOINT_A1_CODE)

print("\nCode saved to: C:/Users/jakew/Downloads/checkpoint_a1_api_additions.py")
print("\nTo apply: Copy the code block into labor_api_v4.py")
