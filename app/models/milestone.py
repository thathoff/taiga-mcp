"""Milestone (sprint) models."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class Milestone(BaseModel):
    """Taiga milestone (sprint) model."""

    id: int
    name: str
    slug: str
    project: int
    owner: Optional[int] = None
    estimated_start: Optional[date] = None
    estimated_finish: Optional[date] = None
    created_date: datetime
    modified_date: datetime
    closed: bool = False
    disponibility: Optional[float] = None
    total_points: Optional[float] = None
    closed_points: Optional[float] = None
    user_stories: list = []

    class Config:
        populate_by_name = True
