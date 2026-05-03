"""
Entity-context resolution for employer profiles (#44).

Produces a uniform `entity_context` block across all three profile routes
(F7, Master, non-F7) so the frontend can distinguish:

  - Unit size: workers at a single establishment
  - Group size: workers aggregated across the canonical group
  - Corporate family size: workers across the ultimate parent entity

Display-mode rules (user-confirmed 2026-04-16):
  - `group_member_count` > 1 AND family data present -> family_primary
  - otherwise (single-site or no family data) -> unit_primary

Source-priority rules:
  - Family primary prefers SEC > Mergent > PPP > RPE
  - Range is shown when SEC and Mergent both exist AND agree within 25%
  - Conflict flag is raised when spread exceeds 25% (suppresses range)

Pure helpers (`_decide_display_mode`, `_compute_spread_and_range`,
`_format_thousands`) are DB-free and covered by unit tests.
"""
from __future__ import annotations

from typing import Any, Optional


# ---------- Pure helpers (DB-free; unit-tested) ----------

CONFLICT_THRESHOLD = 0.25  # 25% spread -> "sources disagree"


def _format_thousands(n: Optional[int]) -> Optional[str]:
    """Render 402000 as '402K'. Returns None for None. Keeps 6-figure precision below 10K."""
    if n is None:
        return None
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 10_000:
        return f"{round(n / 1000)}K"
    if n >= 1000:
        return f"{n / 1000:.1f}K".replace(".0K", "K")
    return f"{n:,}"


def _compute_spread_and_range(
    sec_count: Optional[int], mergent_count: Optional[int]
) -> dict[str, Any]:
    """
    Given SEC and Mergent corp-family counts, compute:
      - primary_count, primary_source (prefer SEC when both exist)
      - range dict {low, high, display} when both exist AND within threshold
      - conflict dict {present, spread_pct, sources_disagreeing}

    Returns dict with keys: primary_count, primary_source, range, conflict.
    Either count may be None; function returns minimal block then.
    """
    primary_count: Optional[int] = None
    primary_source: Optional[str] = None
    range_block: Optional[dict[str, Any]] = None
    conflict_block: dict[str, Any] = {
        "present": False,
        "spread_pct": None,
        "sources_disagreeing": [],
    }

    if sec_count is not None and mergent_count is not None:
        spread = abs(sec_count - mergent_count) / max(sec_count, mergent_count)
        primary_count = sec_count  # SEC > Mergent user-confirmed
        primary_source = "sec_10k"
        if spread < CONFLICT_THRESHOLD:
            low = min(sec_count, mergent_count)
            high = max(sec_count, mergent_count)
            range_block = {
                "low": low,
                "high": high,
                "display": f"{_format_thousands(low)}\u2013{_format_thousands(high)}",
            }
        else:
            conflict_block = {
                "present": True,
                "spread_pct": round(spread * 100, 1),
                "sources_disagreeing": ["sec_10k", "mergent_company"],
            }
    elif sec_count is not None:
        primary_count = sec_count
        primary_source = "sec_10k"
    elif mergent_count is not None:
        primary_count = mergent_count
        primary_source = "mergent_company"

    return {
        "primary_count": primary_count,
        "primary_source": primary_source,
        "range": range_block,
        "conflict": conflict_block,
    }


def _decide_display_mode(
    group_member_count: Optional[int],
    unit_count: Optional[int],
    family_primary_count: Optional[int],
) -> str:
    """family_primary when canonical group has >1 member AND family data exists; else unit_primary."""
    has_multi_member_group = group_member_count is not None and group_member_count > 1
    if has_multi_member_group and family_primary_count is not None:
        return "family_primary"
    if family_primary_count is not None and unit_count is None:
        return "family_primary"
    return "unit_primary"


def _label(kind: str) -> str:
    return {
        "unit": "This unit",
        "group": "Group",
        "family": "Corp. Family",
    }[kind]


# ---------- DB-backed helpers ----------

def _fetch_family_sizes_for_f7(cur, f7_id: str) -> dict[str, Any]:
    """
    Return raw size counts reachable from an F7 employer via
    corporate_identifier_crosswalk joins. Mirrors the CTE joins used in
    scripts/scoring/build_unified_scorecard.py:235-254.

    Returns dict with keys: sec_count, mergent_count, ppp_count, rpe_count,
    mergent_duns, sec_cik.
    """
    cur.execute(
        """
        SELECT
            cw.mergent_duns,
            cw.sec_cik,
            (
                SELECT MAX(me.employees_all_sites)
                FROM mergent_employers me
                WHERE me.duns = cw.mergent_duns
                  AND me.employees_all_sites IS NOT NULL
                  AND me.employees_all_sites > 0
            ) AS mergent_count,
            (
                SELECT (ARRAY_AGG(x.employee_count ORDER BY x.fiscal_year_end DESC))[1]
                FROM sec_xbrl_financials x
                WHERE x.cik = cw.sec_cik
                  AND x.employee_count IS NOT NULL
                  AND x.employee_count > 0
            ) AS sec_count
        FROM corporate_identifier_crosswalk cw
        WHERE cw.f7_employer_id = %s
        ORDER BY cw.federal_obligations DESC NULLS LAST
        LIMIT 1
        """,
        [str(f7_id)],
    )
    row = cur.fetchone()
    if not row:
        return {
            "sec_count": None,
            "mergent_count": None,
            "ppp_count": None,
            "rpe_count": None,
            "mergent_duns": None,
            "sec_cik": None,
        }
    return {
        "sec_count": row.get("sec_count") if hasattr(row, "get") else row["sec_count"],
        "mergent_count": row.get("mergent_count") if hasattr(row, "get") else row["mergent_count"],
        "ppp_count": None,  # reserved; PPP join not done here to keep response fast
        "rpe_count": None,
        "mergent_duns": row.get("mergent_duns") if hasattr(row, "get") else row["mergent_duns"],
        "sec_cik": row.get("sec_cik") if hasattr(row, "get") else row["sec_cik"],
    }


def _fetch_family_sizes_for_master(cur, master_id: int) -> dict[str, Any]:
    """
    Resolve family sizes for a master employer via master_employer_source_ids
    -> mergent/sec source systems.

    Note: seeders store `COALESCE(me.duns, me.id::TEXT)` for mergent, so a
    `source_id` may be either a DUNS string or a numeric Mergent row id. We
    pick the row with highest `match_confidence` (tie-broken by latest
    matched_at) and treat the source_id as an opaque key — the Mergent lookup
    then resolves via either `duns` or `id::text` so fallback-ID rows still
    produce a count.
    """
    cur.execute(
        """
        SELECT
            (
                SELECT source_id FROM master_employer_source_ids
                WHERE master_id = %s AND source_system = 'mergent'
                ORDER BY match_confidence DESC NULLS LAST, matched_at DESC NULLS LAST
                LIMIT 1
            ) AS mergent_source_id,
            (
                SELECT source_id FROM master_employer_source_ids
                WHERE master_id = %s AND source_system = 'sec'
                ORDER BY match_confidence DESC NULLS LAST, matched_at DESC NULLS LAST
                LIMIT 1
            ) AS sec_source_id
        """,
        [master_id, master_id],
    )
    row = cur.fetchone()
    if not row:
        return {
            "sec_count": None,
            "mergent_count": None,
            "ppp_count": None,
            "rpe_count": None,
            "mergent_duns": None,
            "sec_cik": None,
        }
    mergent_source_id = row["mergent_source_id"]
    sec_source = row["sec_source_id"]
    sec_cik = None
    if sec_source:
        try:
            sec_cik = int(sec_source)
        except (TypeError, ValueError):
            sec_cik = None

    # Resolve the Mergent row by DUNS first (common path), falling back to
    # id::text. This mirrors the seed-time `COALESCE(duns, id::TEXT)` so we
    # don't silently drop fallback-ID rows.
    mergent_count = None
    mergent_duns = None
    if mergent_source_id:
        cur.execute(
            """
            SELECT duns, employees_all_sites
            FROM mergent_employers
            WHERE (duns = %s OR id::text = %s)
              AND employees_all_sites IS NOT NULL
              AND employees_all_sites > 0
            ORDER BY employees_all_sites DESC
            LIMIT 1
            """,
            [mergent_source_id, mergent_source_id],
        )
        r = cur.fetchone()
        if r:
            mergent_count = r["employees_all_sites"]
            mergent_duns = r["duns"]

    sec_count = None
    if sec_cik is not None:
        cur.execute(
            """
            SELECT (ARRAY_AGG(employee_count ORDER BY fiscal_year_end DESC))[1] AS c
            FROM sec_xbrl_financials
            WHERE cik = %s AND employee_count IS NOT NULL AND employee_count > 0
            """,
            [sec_cik],
        )
        r = cur.fetchone()
        if r:
            sec_count = r["c"]

    return {
        "sec_count": sec_count,
        "mergent_count": mergent_count,
        "ppp_count": None,
        "rpe_count": None,
        "mergent_duns": mergent_duns,
        "sec_cik": sec_cik,
    }


def _fetch_ultimate_parent(cur, duns: Optional[str]) -> dict[str, Any]:
    """Returns {ultimate_parent_name, is_ultimate_parent_rollup}."""
    if not duns:
        return {"ultimate_parent_name": None, "is_ultimate_parent_rollup": False}
    cur.execute(
        """
        SELECT ultimate_parent_name, ultimate_parent_duns
        FROM corporate_ultimate_parents
        WHERE entity_duns = %s
        LIMIT 1
        """,
        [duns],
    )
    row = cur.fetchone()
    if not row or not row["ultimate_parent_name"]:
        return {"ultimate_parent_name": None, "is_ultimate_parent_rollup": False}
    return {
        "ultimate_parent_name": row["ultimate_parent_name"],
        "is_ultimate_parent_rollup": True,
    }


def _fetch_canonical_group_info(cur, canonical_group_id: Optional[int]) -> dict[str, Any]:
    """Look up group_member_count, consolidated_workers, canonical_name."""
    if canonical_group_id is None:
        return {"member_count": None, "consolidated_workers": None, "canonical_name": None}
    cur.execute(
        """
        SELECT member_count, consolidated_workers, canonical_name
        FROM employer_canonical_groups
        WHERE group_id = %s
        """,
        [canonical_group_id],
    )
    row = cur.fetchone()
    if not row:
        return {"member_count": None, "consolidated_workers": None, "canonical_name": None}
    return {
        "member_count": row["member_count"],
        "consolidated_workers": row["consolidated_workers"],
        "canonical_name": row["canonical_name"],
    }


# ---------- Builders ----------

def _assemble_family_block(
    cur, sizes: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """Compose the `family` slot from raw sizes + ultimate-parent lookup."""
    sec_count = sizes.get("sec_count")
    mergent_count = sizes.get("mergent_count")
    ppp_count = sizes.get("ppp_count")
    rpe_count = sizes.get("rpe_count")

    if sec_count is None and mergent_count is None and ppp_count is None and rpe_count is None:
        return None

    spread = _compute_spread_and_range(sec_count, mergent_count)
    primary = spread["primary_count"]
    primary_source = spread["primary_source"]

    # Fall back through PPP and RPE when SEC/Mergent absent.
    if primary is None:
        if ppp_count is not None:
            primary = ppp_count
            primary_source = "ppp_2020"
        elif rpe_count is not None:
            primary = rpe_count
            primary_source = "rpe_estimate"

    if primary is None:
        return None

    up = _fetch_ultimate_parent(cur, sizes.get("mergent_duns"))

    return {
        "primary_count": int(primary),
        "primary_source": primary_source,
        "sec_count": int(sec_count) if sec_count is not None else None,
        "mergent_count": int(mergent_count) if mergent_count is not None else None,
        "ppp_count": int(ppp_count) if ppp_count is not None else None,
        "rpe_count": int(rpe_count) if rpe_count is not None else None,
        "ultimate_parent_name": up["ultimate_parent_name"],
        "is_ultimate_parent_rollup": up["is_ultimate_parent_rollup"],
        "range": spread["range"],
        "conflict": spread["conflict"],
        "label": _label("family"),
    }


def _assemble_unit_block(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    unit_count = row.get("latest_unit_size") or row.get("unit_size")
    if unit_count is None:
        return None
    return {
        "count": int(unit_count),
        "city": row.get("unit_city") or row.get("city"),
        "state": row.get("unit_state") or row.get("state"),
        "label": _label("unit"),
    }


def _assemble_group_block(group_info: dict[str, Any]) -> Optional[dict[str, Any]]:
    count = group_info.get("consolidated_workers")
    member_count = group_info.get("member_count")
    if count is None and (member_count is None or member_count <= 1):
        return None
    return {
        "count": int(count) if count is not None else None,
        "member_count": int(member_count) if member_count is not None else None,
        "canonical_name": group_info.get("canonical_name"),
        "label": _label("group"),
    }


def build_entity_context_for_f7(cur, f7_id: str, row: dict[str, Any]) -> dict[str, Any]:
    """Orchestrator for the F7 profile route."""
    canonical_group_id = row.get("canonical_group_id")
    group_info = _fetch_canonical_group_info(cur, canonical_group_id)
    sizes = _fetch_family_sizes_for_f7(cur, f7_id)
    family = _assemble_family_block(cur, sizes)
    group = _assemble_group_block(group_info)
    unit = _assemble_unit_block(row)

    display_mode = _decide_display_mode(
        group_info.get("member_count"),
        unit["count"] if unit else None,
        family["primary_count"] if family else None,
    )
    return {
        "display_mode": display_mode,
        "unit": unit,
        "group": group,
        "family": family,
    }


def build_entity_context_for_master(
    cur,
    master_id: int,
    row: dict[str, Any],
    canonical_group_info: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Orchestrator for the /api/master/{id} route."""
    group_info = canonical_group_info or {
        "member_count": None,
        "consolidated_workers": None,
        "canonical_name": None,
    }
    sizes = _fetch_family_sizes_for_master(cur, master_id)
    family = _assemble_family_block(cur, sizes)
    group = _assemble_group_block(group_info)

    # Master rows carry `employee_count` but not a single-establishment unit_size;
    # treat employee_count as a unit-equivalent only when no family data exists.
    unit: Optional[dict[str, Any]] = None
    master_emp = row.get("employee_count")
    if family is None and master_emp is not None:
        unit = {
            "count": int(master_emp),
            "city": row.get("city"),
            "state": row.get("state"),
            "label": _label("unit"),
        }

    display_mode = _decide_display_mode(
        group_info.get("member_count"),
        unit["count"] if unit else None,
        family["primary_count"] if family else None,
    )
    return {
        "display_mode": display_mode,
        "unit": unit,
        "group": group,
        "family": family,
    }


def build_entity_context_minimal(
    row: dict[str, Any], source_type: str
) -> dict[str, Any]:
    """Minimal block for NLRB / VR / MANUAL paths: unit only, no family."""
    unit_count = row.get("eligible_voters") or row.get("unit_size") or row.get("employee_count")
    unit: Optional[dict[str, Any]] = None
    if unit_count is not None:
        unit = {
            "count": int(unit_count),
            "city": row.get("city"),
            "state": row.get("state"),
            "label": _label("unit"),
        }
    return {
        "display_mode": "unit_primary",
        "unit": unit,
        "group": None,
        "family": None,
    }
