"""
Mergent executive roster endpoint for the master profile.

24Q-7: Surface execs in the UI. Q8 Management coverage was Medium because
Mergent execs were already loaded (currently 334,082 rows) but the data
never reached the frontend. This endpoint exposes the roster ranked by a
title heuristic (CEO/Chairman/President at top, then C-suite, then VPs,
then directors, then everyone else).

Schema reality check: the loaded mergent_executives table has only name +
title + gender + phone (no compensation, no tenure, no prior employer).
We hide phone numbers in the response for privacy and ignore gender on
the public card. The card therefore answers "who runs this place?" not
"how much do they earn?" — that's queued for a future ETL extension.

The bridge is master -> master_employer_source_ids (source_system='mergent',
source_id=DUNS) -> mergent_executives (matched on duns).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from ..database import get_db

router = APIRouter()

DEFAULT_LIMIT = 25
MAX_LIMIT = 200


# Title ranking heuristic. Lower number = higher rank in the C-suite. We
# evaluate in priority order (top wins) so "Executive Vice President" maps
# to EVP rank, not VP rank, even though both regexes match.
#
# We keep this in a single SQL CASE expression for portability; the patterns
# are deliberately conservative to avoid mis-ranking weird Mergent strings
# like "Chb" (chairman of the board), "EVP & GC", etc.
_TITLE_RANK_SQL = """
CASE
  WHEN me.title IS NULL OR btrim(me.title) = '' THEN 99
  -- Board Chair: must NOT be vice/deputy/asst chairman.
  WHEN (me.title ~* '\\m(chairman|chairperson|chairwoman|chair of the board)\\M'
        OR me.title ~* '\\m(chb)\\M')
       AND me.title !~* '\\m(vice|deputy|asst|assistant|former|emeritus)\\M' THEN 1
  WHEN me.title ~* '\\m(chief executive officer|ceo)\\M'                          THEN 2
  WHEN me.title ~* '\\mpresident\\M' AND me.title !~* '\\m(vice|foundation|division|region)\\M' THEN 3
  WHEN me.title ~* '\\m(chief financial officer|cfo)\\M'                          THEN 4
  WHEN me.title ~* '\\m(chief operating officer|coo)\\M'                          THEN 5
  WHEN me.title ~* '\\mchief\\M.*\\m(officer|executive)\\M'                       THEN 6
  WHEN me.title ~* '\\m(executive vice president|evp)\\M'                         THEN 7
  WHEN me.title ~* '\\m(senior vice president|svp)\\M'                            THEN 8
  WHEN me.title ~* '\\mvice president\\M' OR me.title ~* '\\mvice chairman\\M'    THEN 9
  WHEN me.title ~* '\\m(general counsel|secretary|treasurer)\\M'                  THEN 10
  WHEN me.title ~* '\\mdirector\\M'                                               THEN 11
  WHEN me.title ~* '\\mmanager\\M'                                                THEN 12
  ELSE 50
END
"""


def _format_name(first: Optional[str], last: Optional[str]) -> Optional[str]:
    parts = [(first or "").strip(), (last or "").strip()]
    parts = [p for p in parts if p]
    return " ".join(parts) if parts else None


def _title_rank_label(rank: int) -> str:
    """Human-readable label for a numeric rank, used by the frontend for grouping."""
    return {
        1: "Board Chair",
        2: "CEO",
        3: "President",
        4: "CFO",
        5: "COO",
        6: "C-Suite",
        7: "EVP",
        8: "SVP",
        9: "VP",
        10: "General Counsel / Officer",
        11: "Director",
        12: "Manager",
        50: "Other",
        99: "Unspecified",
    }.get(rank, "Other")


@router.get("/api/employers/master/{master_id}/executives")
def get_master_executives(
    master_id: int,
    limit: int = Query(
        default=DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description="Max executives returned (sorted by title rank, then last name)",
    ),
) -> Dict[str, Any]:
    """Return Mergent executive roster + summary for a master employer.

    Response shape:
        {
            "summary": {
                "total_executives": int,             # full count, not truncated
                "with_title": int,
                "by_rank": {label: count, ...},
            },
            "executives": [
                {
                    "name": "First Last",
                    "title": str | null,
                    "title_rank": int,
                    "title_rank_label": str,
                    "company_name": str | null,      # mergent's reported company
                    "duns": str,
                },
                ...
            ],
            "source_freshness": iso str | null,      # data_source_freshness.last_updated
        }
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # 404 on unknown master, mirroring epa.py.
            cur.execute("SELECT 1 FROM master_employers WHERE master_id = %s", [master_id])
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Master employer not found")

            # Pull all execs across every Mergent DUNS linked to this master.
            cur.execute(
                f"""
                SELECT
                  me.first_name,
                  me.last_name,
                  me.title,
                  me.company_name,
                  me.duns,
                  ({_TITLE_RANK_SQL}) AS title_rank
                FROM master_employer_source_ids sid
                JOIN mergent_executives me ON me.duns = sid.source_id
                WHERE sid.source_system = 'mergent'
                  AND sid.master_id = %s
                ORDER BY title_rank ASC,
                         lower(coalesce(me.last_name, '')) ASC,
                         lower(coalesce(me.first_name, '')) ASC
                """,
                [master_id],
            )
            rows = cur.fetchall() or []

            # Source freshness (Mergent is loaded as a single source, key
            # 'mergent_business_intel' in data_source_freshness).
            cur.execute(
                """
                SELECT last_updated
                FROM data_source_freshness
                WHERE source_name = 'mergent_business_intel'
                LIMIT 1
                """
            )
            fresh_row = cur.fetchone()

    if not rows:
        return {
            "summary": {
                "total_executives": 0,
                "with_title": 0,
                "by_rank": {},
            },
            "executives": [],
            "source_freshness": (
                fresh_row["last_updated"].isoformat()
                if fresh_row and fresh_row.get("last_updated")
                else None
            ),
        }

    # Aggregate summary counts across the full match set (not truncated).
    total = len(rows)
    with_title = sum(1 for r in rows if (r.get("title") or "").strip())
    by_rank: Dict[str, int] = {}
    for r in rows:
        label = _title_rank_label(int(r["title_rank"]))
        by_rank[label] = by_rank.get(label, 0) + 1

    # Truncate executives array. Already ordered by title rank ascending.
    executives = []
    for r in rows[:limit]:
        rank = int(r["title_rank"])
        executives.append(
            {
                "name": _format_name(r.get("first_name"), r.get("last_name")),
                "title": r.get("title"),
                "title_rank": rank,
                "title_rank_label": _title_rank_label(rank),
                "company_name": r.get("company_name"),
                "duns": r.get("duns"),
            }
        )

    return {
        "summary": {
            "total_executives": total,
            "with_title": with_title,
            "by_rank": by_rank,
        },
        "executives": executives,
        "source_freshness": (
            fresh_row["last_updated"].isoformat()
            if fresh_row and fresh_row.get("last_updated")
            else None
        ),
    }
