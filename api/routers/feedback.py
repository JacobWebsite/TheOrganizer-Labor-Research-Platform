"""Beta feedback capture endpoint (roadmap W8 onboarding). [plumbing]

POST /api/feedback  -- a beta tester submits free-text feedback from any page.
GET  /api/feedback  -- list recent submissions (daily soft-launch monitoring).

Backed by the feedback_submissions table (scripts/etl/create_feedback_submissions.py).
"""
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..database import get_db

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

FeedbackCategory = Literal[
    "bug", "confusing", "data_issue", "feature_request", "praise", "other"
]


class FeedbackCreateRequest(BaseModel):
    category: FeedbackCategory
    message: str = Field(..., min_length=1, max_length=5000)
    page_url: Optional[str] = None
    employer_id: Optional[str] = None
    submitted_by: Optional[str] = None
    user_agent: Optional[str] = None


@router.post("")
def create_feedback(request: FeedbackCreateRequest):
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="message is required")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback_submissions (
                    category, message, page_url, employer_id, submitted_by, user_agent
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
                """,
                (
                    request.category,
                    message,
                    request.page_url,
                    request.employer_id,
                    request.submitted_by.strip() if request.submitted_by else None,
                    request.user_agent,
                ),
            )
            row = cur.fetchone()

    return {"id": row["id"], "created_at": row["created_at"], "status": "received"}


@router.get("")
def list_feedback(limit: int = 100, status: Optional[str] = None):
    limit = max(1, min(limit, 500))
    clauses = []
    params = []
    if status:
        clauses.append("status = %s")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, category, message, page_url, employer_id, submitted_by,
                       status, created_at
                FROM feedback_submissions
                {where}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cur.fetchall()

    return {"count": len(rows), "feedback": [dict(r) for r in rows]}
