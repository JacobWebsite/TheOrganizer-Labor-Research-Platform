"""
Target scorecard API — signal inventory for non-union employers.

No composite score. Discovery is filter-driven: state, industry, size,
enforcement flags. Default sort is by signal count, then alphabetically.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from ..database import get_db
from ..helpers import safe_order_dir, safe_sort_col, TTLCache

router = APIRouter()
_stats_cache = TTLCache(ttl_seconds=300)

# Column allowlists for safety
_SORT_MAP = {
    "signals": "ts.signals_present",
    "name": "ts.display_name",
    "employees": "ts.employee_count",
    "enforcement": "ts.enforcement_count",
    "source_count": "ts.source_count",
}

_MV_EXISTS: Optional[bool] = None


def _check_mv(cur) -> bool:
    global _MV_EXISTS
    if _MV_EXISTS is not None:
        return _MV_EXISTS
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_matviews WHERE matviewname = 'mv_target_scorecard') AS e"
    )
    _MV_EXISTS = bool(cur.fetchone()["e"])
    return _MV_EXISTS


@router.get("/api/targets/scorecard")
def target_scorecard_list(
    q: Optional[str] = None,
    state: Optional[str] = None,
    naics: Optional[str] = None,
    min_signals: Optional[int] = Query(default=None, ge=0, le=8),
    has_enforcement: Optional[bool] = None,
    has_recent_violations: Optional[bool] = None,
    min_employees: Optional[int] = Query(default=None, ge=0),
    max_employees: Optional[int] = Query(default=None, ge=0),
    is_federal_contractor: Optional[bool] = None,
    is_nonprofit: Optional[bool] = None,
    source_origin: Optional[str] = None,
    sort: str = Query(default="signals", pattern="^(signals|name|employees|enforcement|source_count)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Paginated signal inventory list for non-union target employers."""
    with get_db() as conn:
        with conn.cursor() as cur:
            if not _check_mv(cur):
                raise HTTPException(status_code=503, detail="Target scorecard not yet built. Run build_target_scorecard.py first.")

            conditions = ["1=1"]
            params = []

            if q:
                conditions.append("ts.display_name ILIKE %s")
                params.append(f"%{q}%")
            if state:
                conditions.append("ts.state = %s")
                params.append(state.upper())
            if naics:
                conditions.append("ts.naics LIKE %s")
                params.append(f"{naics}%")
            if min_signals is not None:
                conditions.append("ts.signals_present >= %s")
                params.append(min_signals)
            if has_enforcement is not None:
                conditions.append("ts.has_enforcement = %s")
                params.append(has_enforcement)
            if has_recent_violations is not None:
                conditions.append("ts.has_recent_violations = %s")
                params.append(has_recent_violations)
            if min_employees is not None:
                conditions.append("ts.employee_count >= %s")
                params.append(min_employees)
            if max_employees is not None:
                conditions.append("ts.employee_count <= %s")
                params.append(max_employees)
            if is_federal_contractor is not None:
                conditions.append("ts.is_federal_contractor = %s")
                params.append(is_federal_contractor)
            if is_nonprofit is not None:
                conditions.append("ts.is_nonprofit = %s")
                params.append(is_nonprofit)
            if source_origin:
                conditions.append("ts.source_origin = %s")
                params.append(source_origin.lower())

            where = " AND ".join(conditions)
            sort_col = safe_sort_col(sort, _SORT_MAP, "signals")
            order_dir = safe_order_dir(order)

            cur.execute(f"SELECT COUNT(*) AS cnt FROM mv_target_scorecard ts WHERE {where}", params)
            total = int(cur.fetchone()["cnt"])

            offset = (page - 1) * limit
            cur.execute(
                f"""
                SELECT
                    ts.master_id,
                    ts.display_name,
                    ts.city,
                    ts.state,
                    ts.naics,
                    ts.employee_count,
                    ts.is_federal_contractor,
                    ts.is_nonprofit,
                    ts.source_origin,
                    ts.source_count,
                    ts.signal_osha,
                    ts.signal_whd,
                    ts.signal_nlrb,
                    ts.signal_contracts,
                    ts.signal_financial,
                    ts.signal_industry_growth,
                    ts.signal_union_density,
                    ts.signal_size,
                    ts.signals_present,
                    ts.has_enforcement,
                    ts.enforcement_count,
                    ts.has_recent_violations,
                    ts.pillar_anger,
                    ts.pillar_leverage,
                    ts.pillar_stability
                FROM mv_target_scorecard ts
                WHERE {where}
                ORDER BY {sort_col} {order_dir} NULLS LAST, ts.display_name ASC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            results = cur.fetchall()
            pages = int(math.ceil(total / limit)) if limit else 1

            return {
                "total": total,
                "page": page,
                "pages": pages,
                "results": results,
            }


@router.get("/api/targets/scorecard/stats")
def target_scorecard_stats():
    """Aggregate stats for the target scorecard."""
    cached = _stats_cache.get("target_scorecard_stats")
    if cached is not None:
        return cached

    with get_db() as conn:
        with conn.cursor() as cur:
            if not _check_mv(cur):
                raise HTTPException(status_code=503, detail="Target scorecard not yet built.")

            cur.execute("SELECT COUNT(*) AS total FROM mv_target_scorecard")
            total = int(cur.fetchone()["total"])

            # Signal coverage
            signal_cols = [
                'signal_osha', 'signal_whd', 'signal_nlrb', 'signal_contracts',
                'signal_financial', 'signal_industry_growth', 'signal_union_density', 'signal_size'
            ]
            signal_coverage = {}
            for col in signal_cols:
                cur.execute(
                    f"SELECT COUNT(*) AS cnt, ROUND(AVG({col})::numeric, 2) AS avg_val "
                    f"FROM mv_target_scorecard WHERE {col} IS NOT NULL"
                )
                row = cur.fetchone()
                signal_coverage[col] = {
                    "count": int(row["cnt"]),
                    "pct": round(100.0 * int(row["cnt"]) / total, 1) if total else 0,
                    "avg": float(row["avg_val"]) if row["avg_val"] is not None else None,
                }

            # Signal count distribution
            cur.execute("""
                SELECT signals_present, COUNT(*) AS cnt
                FROM mv_target_scorecard
                GROUP BY signals_present
                ORDER BY signals_present
            """)
            signal_distribution = [
                {"signals": r["signals_present"], "count": int(r["cnt"])}
                for r in cur.fetchall()
            ]

            # Enforcement
            cur.execute("SELECT COUNT(*) AS cnt FROM mv_target_scorecard WHERE has_enforcement")
            enforcement_count = int(cur.fetchone()["cnt"])
            cur.execute("SELECT COUNT(*) AS cnt FROM mv_target_scorecard WHERE has_recent_violations")
            recent_count = int(cur.fetchone()["cnt"])

            # Top states
            cur.execute("""
                SELECT state, COUNT(*) AS cnt
                FROM mv_target_scorecard
                WHERE state IS NOT NULL
                GROUP BY state
                ORDER BY cnt DESC
                LIMIT 10
            """)
            top_states = cur.fetchall()

            # Top industries (2-digit NAICS)
            cur.execute("""
                SELECT LEFT(naics, 2) AS naics_2, COUNT(*) AS cnt
                FROM mv_target_scorecard
                WHERE naics IS NOT NULL
                GROUP BY LEFT(naics, 2)
                ORDER BY cnt DESC
                LIMIT 10
            """)
            top_industries = cur.fetchall()

            result = {
                "total_scored": total,
                "signal_coverage": signal_coverage,
                "signal_distribution": signal_distribution,
                "enforcement": {
                    "has_enforcement": enforcement_count,
                    "has_recent_violations": recent_count,
                },
                "top_states": top_states,
                "top_industries": top_industries,
            }
            _stats_cache.set("target_scorecard_stats", result)
            return result


@router.get("/api/targets/scorecard/{master_id:int}")
def target_scorecard_detail(master_id: int):
    """Detailed signal inventory for a single non-union employer."""
    with get_db() as conn:
        with conn.cursor() as cur:
            if not _check_mv(cur):
                raise HTTPException(status_code=503, detail="Target scorecard not yet built.")

            cur.execute("SELECT * FROM mv_target_scorecard WHERE master_id = %s", [master_id])
            scorecard = cur.fetchone()
            if not scorecard:
                raise HTTPException(status_code=404, detail="Employer not found in target scorecard")

            # Build signal explanations
            signals = []
            _add_signal = lambda name, cat, val, expl: signals.append(
                {"signal": name, "category": cat, "value": val, "strength": _strength(val), "explanation": expl}
            ) if val is not None else None

            # Enforcement signals
            osha_val = scorecard.get("signal_osha")
            if osha_val is not None:
                estab = scorecard.get("osha_estab_count", 0) or 0
                viol = scorecard.get("osha_total_violations", 0) or 0
                pen = scorecard.get("osha_total_penalties", 0) or 0
                _add_signal("OSHA Safety", "enforcement", float(osha_val),
                            f"{viol} violations across {estab} establishments, ${float(pen):,.0f} in penalties")

            whd_val = scorecard.get("signal_whd")
            if whd_val is not None:
                cases = scorecard.get("whd_case_count", 0) or 0
                bw = scorecard.get("whd_total_backwages", 0) or 0
                _add_signal("Wage & Hour", "enforcement", float(whd_val),
                            f"{cases} WHD cases, ${float(bw):,.0f} in backwages")

            nlrb_val = scorecard.get("signal_nlrb")
            if nlrb_val is not None:
                elec = scorecard.get("nlrb_election_count", 0) or 0
                ulp = scorecard.get("nlrb_ulp_count", 0) or 0
                _add_signal("NLRB Activity", "enforcement", float(nlrb_val),
                            f"{elec} elections, {ulp} ULP charges at this employer")

            # Leverage signals
            contracts_val = scorecard.get("signal_contracts")
            if contracts_val is not None:
                _add_signal("Federal Contracts", "leverage", float(contracts_val),
                            "Active federal contractor registered in SAM.gov")

            fin_val = scorecard.get("signal_financial")
            if fin_val is not None:
                rev = scorecard.get("n990_revenue")
                expl = f"990 revenue: ${float(rev):,.0f}" if rev else "Public company"
                _add_signal("Financial Profile", "leverage", float(fin_val), expl)

            density_val = scorecard.get("signal_union_density")
            if density_val is not None:
                state_d = scorecard.get("state_union_density_pct", 0) or 0
                ind_d = scorecard.get("industry_union_density_pct", 0) or 0
                _add_signal("Union Density", "context", float(density_val),
                            f"State density: {float(state_d):.1f}%, Industry density: {float(ind_d):.1f}%")

            # Context signals
            growth_val = scorecard.get("signal_industry_growth")
            if growth_val is not None:
                pct = scorecard.get("bls_growth_pct", 0) or 0
                _add_signal("Industry Growth", "context", float(growth_val),
                            f"BLS projected employment change: {float(pct):+.1f}%")

            size_val = scorecard.get("signal_size")
            if size_val is not None:
                emp = scorecard.get("employee_count", 0) or 0
                _add_signal("Employer Size", "filter", float(size_val),
                            f"{emp:,} employees (filter dimension, not a scoring signal)")

            return {
                "scorecard": scorecard,
                "signals": signals,
                "summary": {
                    "signals_present": scorecard.get("signals_present", 0),
                    "has_enforcement": scorecard.get("has_enforcement", False),
                    "enforcement_count": scorecard.get("enforcement_count", 0),
                    "has_recent_violations": scorecard.get("has_recent_violations", False),
                    "pillar_anger": scorecard.get("pillar_anger"),
                    "pillar_leverage": scorecard.get("pillar_leverage"),
                    "pillar_stability": scorecard.get("pillar_stability"),
                },
            }


def _strength(val: Optional[float]) -> str:
    if val is None:
        return "none"
    if val >= 7:
        return "HIGH"
    if val >= 4:
        return "MEDIUM"
    return "LOW"
