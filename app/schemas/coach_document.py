from datetime import datetime
from pydantic import BaseModel
from app.models.enums import CoachDocType


class CoachMonthlyDocumentRead(BaseModel):
    id: int
    coach_id: int
    group_id: int
    year: int
    month: int
    doc_type: CoachDocType
    file_url: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MonthlyWindowInfo(BaseModel):
    start_day: int
    end_day: int
    is_open: bool


class GroupMonthlyStatus(BaseModel):
    group_id: int
    group_name: str
    plan_uploaded: bool
    report_uploaded: bool


class CoachMonthlyStatusResponse(BaseModel):
    year: int
    month: int
    plan_window: MonthlyWindowInfo
    report_window: MonthlyWindowInfo
    groups: list[GroupMonthlyStatus]
