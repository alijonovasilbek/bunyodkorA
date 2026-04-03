from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel
from app.models.enums import PaymentStatus, PaymentSource, PaymentSettlementType


class TransactionRead(BaseModel):
    id: int
    external_id: Optional[str] = None
    amount: float
    source: PaymentSource
    status: PaymentStatus
    settlement_type: Optional[PaymentSettlementType] = PaymentSettlementType.PAYMENT
    paid_at: Optional[datetime] = None
    comment: Optional[str] = None
    settlement_document_url: Optional[str] = None
    payment_year: Optional[int] = None
    payment_months: Optional[list[int]] = None
    student_id: Optional[int] = None
    contract_id: Optional[int] = None
    created_by_user_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ManualTransactionRead(BaseModel):
    id: int
    external_id: Optional[str] = None
    amount: float
    source: PaymentSource
    status: PaymentStatus
    paid_at: Optional[datetime] = None
    comment: Optional[str] = None
    payment_year: Optional[int] = None
    payment_months: Optional[list[int]] = None
    student_id: Optional[int] = None
    contract_id: Optional[int] = None
    created_by_user_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionReadWithStudentName(BaseModel):
    """Transaction with student full name instead of student_id"""
    id: int
    external_id: Optional[str] = None
    amount: float
    source: PaymentSource
    status: PaymentStatus
    settlement_type: Optional[PaymentSettlementType] = PaymentSettlementType.PAYMENT
    paid_at: Optional[datetime] = None
    comment: Optional[str] = None
    settlement_document_url: Optional[str] = None
    payment_year: Optional[int] = None
    payment_months: Optional[list[int]] = None
    student_id: Optional[int] = None  # Keep student_id
    student_full_name: Optional[str] = None  # Add full name
    contract_id: Optional[int] = None
    created_by_user_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionStatistics(BaseModel):
    from_date: date
    to_date: date
    total_paid: float
    successful_transactions: int
    click_transactions: int
    payme_transactions: int
    bank_transactions: int


class TransactionCreate(BaseModel):
    external_id: Optional[str] = None
    amount: float
    source: PaymentSource
    status: PaymentStatus = PaymentStatus.PENDING
    paid_at: Optional[datetime] = None
    comment: Optional[str] = None
    student_id: Optional[int] = None
    contract_id: Optional[int] = None


class TransactionUpdate(BaseModel):
    status: Optional[PaymentStatus] = None
    comment: Optional[str] = None


class TransactionAssign(BaseModel):
    student_id: int
    contract_id: int


class ManualTransactionCreate(BaseModel):
    amount: float
    source: PaymentSource
    contract_number: str
    payment_year: int
    payment_months: list[int]  # List of months (1-12) this payment covers
    settlement_type: PaymentSettlementType = PaymentSettlementType.PAYMENT
    comment: Optional[str] = None
    paid_at: Optional[datetime] = None


class ManualTransactionPayload(BaseModel):
    amount: float
    source: PaymentSource
    contract_number: str
    payment_year: int
    payment_months: list[int]
    comment: Optional[str] = None
    paid_at: Optional[datetime] = None


class PaidMonth(BaseModel):
    year: int
    month: int
    amount: float
    status: PaymentStatus
    paid_at: Optional[datetime] = None
    source: PaymentSource
    transaction_id: int
    settlement_type: Optional[PaymentSettlementType] = None
    settlement_status: Optional[str] = None
    comment: Optional[str] = None


class UnpaidMonth(BaseModel):
    year: int
    month: int
    expected_amount: float


class ContractPaymentStatus(BaseModel):
    contract_number: str
    student_name: str
    start_date: str
    end_date: str
    monthly_fee: float
    contract_status: str
    paid_months: list[PaidMonth]
    unpaid_months: list[UnpaidMonth]
    total_paid: float
    total_unpaid: float
    total_expected: float
