from datetime import date
from typing import Optional
from pydantic import BaseModel, Field


class DashboardSourceBreakdown(BaseModel):
    source: str
    amount: float
    transaction_count: int


class DashboardTrendPoint(BaseModel):
    date: date
    inflow: float
    outflow: float
    net_amount: float
    payme: float
    click: float
    other: float


class DashboardPeriodSummary(BaseModel):
    from_date: date
    to_date: date
    total_inflow: float
    total_outflow: float
    net_amount: float
    successful_transactions: int
    source_breakdown: list[DashboardSourceBreakdown]
    trend: list[DashboardTrendPoint]


class DashboardSummary(BaseModel):
    today_revenue: float
    active_students: int
    total_debtors: int
    today_sessions: int
    last_7_days: DashboardPeriodSummary
    last_30_days: DashboardPeriodSummary
    last_90_days: DashboardPeriodSummary


class FinanceReportItem(BaseModel):
    source: str
    total_amount: float
    transaction_count: int


class FinanceReport(BaseModel):
    from_date: date
    to_date: date
    total_revenue: float
    breakdown: list[FinanceReportItem]


class GroupAttendanceReport(BaseModel):
    group_id: int
    group_name: str
    total_sessions: int
    total_students: int
    attendance_percentage: float


class StudentAttendanceReport(BaseModel):
    student_id: int
    student_name: str
    total_sessions: int
    present_count: int
    absent_count: int
    late_count: int
    attendance_percentage: float


class CoachAttendanceReport(BaseModel):
    coach_id: int
    coach_name: str
    groups: list[GroupAttendanceReport]


class DebtorMonthItem(BaseModel):
    year: int
    month: int
    amount: float
    label: str


class DebtorItem(BaseModel):
    student_id: int
    student_name: str
    contract_number: str
    debt_amount: float
    group_name: Optional[str] = None
    primary_phone: Optional[str] = None
    father_phone: Optional[str] = None
    mother_phone: Optional[str] = None
    overdue_months: list[DebtorMonthItem] = Field(default_factory=list)
    overdue_months_count: int = 0


class PayerItem(BaseModel):
    student_id: int
    student_name: str
    contract_number: Optional[str] = None
    group_name: Optional[str] = None
    payment_year: int
    payment_months: list[int]  # List of months paid (e.g., [1, 2, 3, 12])
    total_paid: float
