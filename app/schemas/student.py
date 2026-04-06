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
    pnfl: str = Field(min_length=14, max_length=14)
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None
    face_id: Optional[str] = None
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
    pnfl: str = Field(min_length=14, max_length=14)
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None
    face_id: Optional[str] = None
    status: StudentStatus = StudentStatus.ACTIVE
    group_id: Optional[int] = None


class StudentUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    height: Optional[int] = None
    weight: Optional[int] = None
    pnfl: Optional[str] = Field(default=None, min_length=14, max_length=14)
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None
    face_id: Optional[str] = None
    status: Optional[StudentStatus] = None
    group_id: Optional[int] = None


class ParentRead(BaseModel):
    id: int
    first_name: str
    last_name: str
    phone: str
    email: Optional[str] = None
    relationship_type: Optional[str] = None
    student_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ParentCreate(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: Optional[str] = None
    relationship_type: Optional[str] = None
    student_id: int


class ParentUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    relationship_type: Optional[str] = None


# Import related schemas at the end to avoid circular imports
from app.schemas.contract import ContractRead
from app.schemas.attendance import AttendanceRead
from app.schemas.group import GroupRead
from app.schemas.auth import UserRead


class StudentFullInfo(BaseModel):
    """Complete student information including all related data"""
    student: StudentRead
    parents: list[ParentRead]
    contracts: list[ContractRead]
    group: Optional[GroupRead] = None
    coach: Optional[UserRead] = None
    attendances: list[AttendanceRead]
    active_contracts_count: int = 0  # Number of active contracts
