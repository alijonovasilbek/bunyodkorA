from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field
from app.models.enums import StudentStatus, PaymentStatus, PaymentSource, PaymentSettlementType


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
    passport_serial: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None
    extra_file_url: Optional[str] = None
    passport_url: Optional[str] = None
    buyruq_url: Optional[str] = None
    is_resident: bool = False
    archive_year: int
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
    passport_serial: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_key: Optional[str] = None
    extra_file_key: Optional[str] = None
    passport_key: Optional[str] = None
    buyruq_key: Optional[str] = None
    is_resident: bool = False
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
    passport_serial: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_key: Optional[str] = None
    extra_file_key: Optional[str] = None
    passport_key: Optional[str] = None
    buyruq_key: Optional[str] = None
    is_resident: Optional[bool] = None
    status: Optional[StudentStatus] = None
    group_id: Optional[int] = None

from app.schemas.attendance import AttendanceRead
from app.schemas.group import GroupRead
from app.schemas.auth import UserRead


class StudentFullInfo(BaseModel):
    student: StudentRead
    group: Optional[GroupRead] = None
    coach: Optional[UserRead] = None
    attendances: list[AttendanceRead]


class TerminationCreate(BaseModel):
    terminated_at: date
    reason: Optional[str] = None


class TerminationRead(BaseModel):
    id: int
    student_id: int
    terminated_at: date
    terminated_by_user_id: Optional[int] = None
    terminated_by_name: Optional[str] = None
    reason: Optional[str] = None
    document_url: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DebtMonthInfo(BaseModel):
    year: int
    month: int
    is_paid: bool
    paid_amount: Optional[Decimal] = None


class TransactionRead(BaseModel):
    id: int
    external_id: Optional[str] = None
    amount: Decimal
    source: PaymentSource
    status: PaymentStatus
    paid_at: Optional[datetime] = None
    comment: Optional[str] = None
    payment_year: Optional[int] = None
    payment_months: Optional[list] = None
    settlement_type: Optional[PaymentSettlementType] = None
    created_at: datetime

    class Config:
        from_attributes = True
