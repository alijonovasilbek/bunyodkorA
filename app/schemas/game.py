from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel
from app.models.enums import CoachDocType


class GameCreate(BaseModel):
    group_id: int
    game_date: date
    game_name: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    stadium: Optional[str] = None
    description: Optional[str] = None


class GameUpdate(BaseModel):
    game_date: Optional[date] = None
    game_name: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    stadium: Optional[str] = None
    description: Optional[str] = None


class GameRead(BaseModel):
    id: int
    group_id: int
    game_date: date
    game_name: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    stadium: Optional[str] = None
    description: Optional[str] = None
    created_by_user_id: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GameDocumentRead(BaseModel):
    id: int
    game_id: int
    coach_id: int
    doc_type: CoachDocType
    file_url: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
