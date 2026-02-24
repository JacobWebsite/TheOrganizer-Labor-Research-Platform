"""
Pydantic models for request/response validation.
"""
from pydantic import BaseModel
from typing import Optional


class FlagCreate(BaseModel):
    source_type: str
    source_id: str
    flag_type: str
    priority: Optional[str] = None
    notes: Optional[str] = None
