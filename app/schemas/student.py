from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field
from app.models.enums import StudentStatus


class StudentRead(BaseModel):
    id: int
    first_name: str
    last_name: str
    date_of_birth: date
    height: int
    weight: int
    ampula: Optional[str] = None
    millati: Optional[str] = None
    pnfl: str = Field(min_length=14, max_length=14)
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None
    extra_file_url: Optional[str] = None
    passport_url: Optional[str] = None
    status: StudentStatus
    group_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class StudentCreate(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    height: int
    weight: int
    ampula: Optional[str] = None
    millati: Optional[str] = None
    pnfl: str = Field(min_length=14, max_length=14)
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None
    extra_file_key: Optional[str] = None
    passport_key: Optional[str] = None
    status: StudentStatus = StudentStatus.ACTIVE
    group_id: Optional[int] = None


class StudentUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    height: Optional[int] = None
    weight: Optional[int] = None
    ampula: Optional[str] = None
    millati: Optional[str] = None
    pnfl: Optional[str] = Field(default=None, min_length=14, max_length=14)
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None
    extra_file_key: Optional[str] = None
    passport_key: Optional[str] = None
    status: Optional[StudentStatus] = None
    group_id: Optional[int] = None

from app.schemas.attendance import AttendanceRead
from app.schemas.group import GroupRead
from app.schemas.auth import UserRead


class StudentFullInfo(BaseModel):
    """Complete student information including all related data"""
    student: StudentRead
    group: Optional[GroupRead] = None
    coach: Optional[UserRead] = None
    attendances: list[AttendanceRead]
