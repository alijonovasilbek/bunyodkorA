from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel
from app.models.enums import StudentStatus


class StudentRead(BaseModel):
    id: int
    first_name: str
    last_name: str
    date_of_birth: date
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


class StudentDebtInfo(BaseModel):
    student: StudentRead
    total_expected: float
    total_paid: float
    debt_amount: float
    active_contracts_count: int

    class Config:
        from_attributes = True


# Import related schemas at the end to avoid circular imports
from app.schemas.contract import ContractRead
from app.schemas.transaction import TransactionRead
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
    transactions: list[TransactionRead]
    attendances: list[AttendanceRead]
    total_payments: float = 0.0  # Total of all successful payments
    active_contracts_count: int = 0  # Number of active contracts
