"""
Plausibility bounds for demographics API responses.

Background: R7-1 (2026-04-26 audit) found `/api/demographics/NY/6111`
returning total_workers = 145,000,000 — roughly 17x the entire NY State
workforce. The IPUMS GROUP-BY collapsed across 9 sample-years, inflating
totals 9x. The bug went unnoticed for weeks because no test asserted
that demographics outputs were even physically possible.

This module provides cheap, self-contained checks that run on every
demographics response. Anything outside these bounds is a sign of a
bigger problem in the ETL or query, not a fact about the world.

Usage:
    from api.services.demographics_bounds import assert_demographics_plausible
    warnings = assert_demographics_plausible(payload, state_abbr="NY")
    for w in warnings:
        logger.warning("demographics implausible: %s", w)
"""
from __future__ import annotations

import functools
import logging
from typing import Any, Iterable

_logger = logging.getLogger(__name__)

# US civilian employed (BLS CPS, latest year in bls_state_density). Used as
# a hard ceiling when state-specific data is unavailable. The 1.30 multiplier
# allows for ACS counting self-employed + small grain noise (~10-15% gap
# between BLS CPS and ACS by design).
_US_TOTAL_EMPLOYED = 144_540_000
_CEILING_MULTIPLIER = 1.30
# Per-pct-sum tolerance: distributions over enums (gender/race/etc.) should
# sum to ~100. Allow +/-3pp for rounding (we round each bucket to 1dp).
_PCT_SUM_TOLERANCE = 3.0


def _state_ceilings_from_db() -> dict[str, int]:
    """Fetch latest-year state employment from bls_state_density.

    Returns dict mapping state abbr (e.g. "NY") to ceiling = employed * 1.30.
    On any DB error returns empty dict — caller falls back to US-wide cap.
    """
    try:
        from db_config import get_connection
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT state, total_employed_thousands "
                "FROM bls_state_density "
                "WHERE year = (SELECT MAX(year) FROM bls_state_density) "
                "  AND total_employed_thousands IS NOT NULL"
            )
            return {
                state: int(float(emp_k) * 1000 * _CEILING_MULTIPLIER)
                for state, emp_k in cur.fetchall()
            }
        finally:
            conn.close()
    except Exception:
        _logger.exception("state ceilings lookup failed; using US-wide cap")
        return {}


@functools.lru_cache(maxsize=1)
def _ceilings() -> dict[str, int]:
    """Cached per-process. Demographics ceilings change at most once a year
    (when BLS publishes new state-level CPS) — no need to re-query per call."""
    return _state_ceilings_from_db()


def reset_cache() -> None:
    """For tests that need to invalidate the per-process cache."""
    _ceilings.cache_clear()


def _pct_iter(value: Any) -> Iterable[float]:
    """Pull pct floats out of either a list of dicts (gender/race shape)
    or a list with `pct` keys (age/education shape). Tolerates None."""
    if not isinstance(value, list):
        return ()
    out = []
    for item in value:
        if isinstance(item, dict) and "pct" in item:
            try:
                out.append(float(item["pct"]))
            except (TypeError, ValueError):
                pass
    return out


def assert_demographics_plausible(
    payload: dict | None,
    *,
    state_abbr: str | None = None,
    context: str = "",
) -> list[str]:
    """Check a demographics API payload against physical-possibility bounds.

    Returns list of warning strings (empty when all bounds hold). Does NOT
    raise — caller decides whether to log, surface, or fail.

    Args:
        payload: A demographics response dict (the full thing the endpoint
            would return). Tolerates None / missing keys.
        state_abbr: 2-letter state code if known. Tightens the
            total_workers ceiling.
        context: Free-form string for log readability (e.g.
            "GET /api/demographics/NY/6111").
    """
    if not payload:
        return []
    warnings: list[str] = []

    total = payload.get("total_workers")
    if total is not None:
        try:
            total_int = int(total)
        except (TypeError, ValueError):
            warnings.append(f"total_workers is not numeric: {total!r}")
            total_int = None

        if total_int is not None:
            if total_int <= 0:
                warnings.append(f"total_workers must be > 0, got {total_int}")
            else:
                ceiling = _ceilings().get(state_abbr.upper()) if state_abbr else None
                if ceiling is None:
                    ceiling = int(_US_TOTAL_EMPLOYED * _CEILING_MULTIPLIER)
                if total_int > ceiling:
                    warnings.append(
                        f"total_workers {total_int:,} exceeds ceiling "
                        f"{ceiling:,} for state={state_abbr or 'US'} "
                        f"(BLS employed * {_CEILING_MULTIPLIER})"
                    )

    for dim in ("gender", "race", "hispanic", "age_distribution", "education"):
        pcts = list(_pct_iter(payload.get(dim)))
        if not pcts:
            continue
        s = sum(pcts)
        if abs(s - 100.0) > _PCT_SUM_TOLERANCE:
            warnings.append(
                f"{dim} pct sum {s:.1f}% outside [100 +/- {_PCT_SUM_TOLERANCE}]"
            )

    if context and warnings:
        warnings = [f"[{context}] {w}" for w in warnings]
    return warnings


def log_warnings(warnings: list[str], logger: logging.Logger | None = None) -> None:
    """Convenience: route warnings to the api logger at WARNING level."""
    if not warnings:
        return
    log = logger or _logger
    for w in warnings:
        log.warning("demographics implausible: %s", w)
