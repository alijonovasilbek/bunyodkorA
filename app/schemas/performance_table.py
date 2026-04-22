from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class PerformanceMatchInput(BaseModel):
    tour_label: Optional[str] = Field(default=None, description="Tour or round label, e.g. 1-T")
    match_date: Optional[date] = Field(default=None, description="Match date")
    opponent: Optional[str] = Field(default=None, description="Opponent team name")


class PerformanceColumnCellInput(BaseModel):
    student_id: int
    value: Optional[str] = None


class PerformanceColumnCreate(BaseModel):
    season_year: int = Field(description="Season year, e.g. 2026")
    tour_label: Optional[str] = Field(default=None, description="Tour or round label, e.g. 1-T")
    match_date: Optional[date] = Field(default=None, description="Match date")
    opponent: Optional[str] = Field(default=None, description="Opponent team name")
    values: list[PerformanceColumnCellInput] = Field(default_factory=list)


class PerformanceColumnUpdate(BaseModel):
    tour_label: Optional[str] = Field(default=None, description="Tour or round label, e.g. 1-T")
    match_date: Optional[date] = Field(default=None, description="Match date")
    opponent: Optional[str] = Field(default=None, description="Opponent team name")
    values: Optional[list[PerformanceColumnCellInput]] = None


class PerformanceColumnReorder(BaseModel):
    season_year: int = Field(description="Season year, e.g. 2026")
    match_ids: list[int] = Field(default_factory=list, description="Ordered list of match IDs")


class PerformanceRowInput(BaseModel):
    student_id: int
    cells: list[Optional[str]] = Field(default_factory=list, description="Cell values aligned to match order")


class PerformanceTableUpsert(BaseModel):
    title: Optional[str] = Field(default=None, description="Custom table title")
    season_year: int = Field(description="Season year, e.g. 2026")
    matches: list[PerformanceMatchInput] = Field(default_factory=list)
    rows: list[PerformanceRowInput] = Field(default_factory=list)


class PerformanceMatchRead(BaseModel):
    id: int
    position: int
    tour_label: Optional[str] = None
    match_date: Optional[date] = None
    opponent: Optional[str] = None


class PerformanceRowRead(BaseModel):
    student_id: int
    student_name: str
    millati: Optional[str] = None
    cells: list[Optional[str]] = Field(default_factory=list)


class PerformanceTableRead(BaseModel):
    table_id: Optional[int] = None
    group_id: int
    group_name: str
    coach_id: Optional[int] = None
    coach_name: Optional[str] = None
    title: str
    season_year: int
    matches: list[PerformanceMatchRead] = Field(default_factory=list)
    rows: list[PerformanceRowRead] = Field(default_factory=list)
    updated_at: Optional[datetime] = None
