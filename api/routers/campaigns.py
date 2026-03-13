from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..database import get_db

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


class CampaignOutcomeCreateRequest(BaseModel):
    employer_id: str
    employer_name: Optional[str] = None
    outcome: Literal["won", "lost", "abandoned", "in_progress"]
    notes: Optional[str] = None
    reported_by: Optional[str] = None
    outcome_date: Optional[str] = None


@router.get("/outcomes/{employer_id}")
def get_campaign_outcomes(employer_id: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, employer_id, employer_name, outcome, notes, reported_by,
                       outcome_date, created_at, updated_at
                FROM campaign_outcomes
                WHERE employer_id = %s
                ORDER BY outcome_date DESC NULLS LAST, created_at DESC
            """, (employer_id,))
            rows = cur.fetchall()

    return {
        "employer_id": employer_id,
        "outcomes": [dict(row) for row in rows],
    }


@router.post("/outcomes")
def create_campaign_outcome(request: CampaignOutcomeCreateRequest):
    if not request.employer_id.strip():
        raise HTTPException(status_code=422, detail="employer_id is required")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO campaign_outcomes (
                    employer_id, employer_name, outcome, notes, reported_by, outcome_date
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
            """, (
                request.employer_id.strip(),
                request.employer_name.strip() if request.employer_name else None,
                request.outcome,
                request.notes.strip() if request.notes else None,
                request.reported_by.strip() if request.reported_by else None,
                request.outcome_date,
            ))
            row = cur.fetchone()

    return {
        "id": row["id"],
        "created_at": row["created_at"],
    }
