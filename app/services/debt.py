from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, cast, or_
from sqlalchemy.dialects.postgresql import JSONB
from app.models.domain import Student, Contract
from app.models.finance import Transaction
from app.models.enums import ContractStatus, PaymentStatus, PaymentSettlementType


async def calculate_student_debt(db: AsyncSession, student_id: int, as_of_date: date = None) -> float:
    if as_of_date is None:
        as_of_date = date.today()

    result = await db.execute(
        select(Contract).where(
            and_(
                Contract.student_id == student_id,
                Contract.status == ContractStatus.ACTIVE,
                Contract.start_date <= as_of_date,
                Contract.end_date >= as_of_date,
            )
        )
    )
    contract = result.scalar_one_or_none()

    if not contract:
        return 0.0

    months_elapsed = 0
    current_date = contract.start_date
    while current_date <= as_of_date and current_date <= contract.end_date:
        months_elapsed += 1
        current_date = current_date + relativedelta(months=1)

    total_expected = float(contract.monthly_fee) * months_elapsed

    txn_result = await db.execute(
        select(Transaction).where(
            and_(
                Transaction.contract_id == contract.id,
                Transaction.status == PaymentStatus.SUCCESS,
            )
        )
    )
    transactions = txn_result.scalars().all()
    total_paid = sum(
        float(txn.amount)
        for txn in transactions
        if txn.settlement_type != PaymentSettlementType.WAIVER_SPRAVKA
    )
    period_end = min(as_of_date, contract.end_date)
    contract_start_month = contract.start_date.replace(day=1)
    period_end_month = period_end.replace(day=1)
    waived_months: set[tuple[int, int]] = set()
    for txn in transactions:
        if txn.settlement_type != PaymentSettlementType.WAIVER_SPRAVKA:
            continue
        if txn.payment_year is None:
            continue
        for month_number in txn.payment_months or []:
            try:
                month_value = int(month_number)
            except (TypeError, ValueError):
                continue
            if not (1 <= month_value <= 12):
                continue
            month_date = date(txn.payment_year, month_value, 1)
            if contract_start_month <= month_date <= period_end_month:
                waived_months.add((txn.payment_year, month_value))

    total_paid += float(contract.monthly_fee) * len(waived_months)

    debt = total_expected - total_paid
    return max(debt, 0.0)


async def calculate_student_previous_months_debt(
    db: AsyncSession,
    student_id: int,
    as_of_date: date = None,
) -> tuple[float, list[tuple[int, int, float]]]:
    """
    Calculate debt only for fully elapsed months (up to previous month).

    Example:
    - As of 2026-03-03, only months <= 2026-02 are considered due.
    - Current month is excluded from debt calculation.
    """
    if as_of_date is None:
        as_of_date = date.today()

    contract_result = await db.execute(
        select(Contract)
        .where(
            and_(
                Contract.student_id == student_id,
                Contract.status == ContractStatus.ACTIVE,
                Contract.start_date <= as_of_date,
                Contract.end_date >= as_of_date,
            )
        )
        .order_by(Contract.created_at.desc())
    )
    contract = contract_result.scalars().first()

    if not contract:
        return 0.0, []

    contract_start_month = contract.start_date.replace(day=1)
    contract_end_month = contract.end_date.replace(day=1)
    current_month_start = as_of_date.replace(day=1)
    previous_month_start = current_month_start - relativedelta(months=1)
    period_end_month = min(previous_month_start, contract_end_month)

    if period_end_month < contract_start_month:
        return 0.0, []

    due_months: list[tuple[int, int]] = []
    current_month = contract_start_month
    while current_month <= period_end_month:
        due_months.append((current_month.year, current_month.month))
        current_month = current_month + relativedelta(months=1)

    due_months_set = set(due_months)

    txn_result = await db.execute(
        select(
            Transaction.payment_year,
            Transaction.payment_months,
        ).where(
            and_(
                Transaction.contract_id == contract.id,
                Transaction.status == PaymentStatus.SUCCESS,
                Transaction.payment_year.isnot(None),
            )
        )
    )

    covered_months: set[tuple[int, int]] = set()
    for tx in txn_result.all():
        if tx.payment_year is None:
            continue
        for raw_month in tx.payment_months or []:
            try:
                month_value = int(raw_month)
            except (TypeError, ValueError):
                continue
            if not (1 <= month_value <= 12):
                continue
            month_key = (int(tx.payment_year), month_value)
            if month_key in due_months_set:
                covered_months.add(month_key)

    unpaid_months = [month for month in due_months if month not in covered_months]
    monthly_fee = float(contract.monthly_fee)
    debt_amount = monthly_fee * len(unpaid_months)
    overdue_months = [(year, month, monthly_fee) for year, month in unpaid_months]

    return max(debt_amount, 0.0), overdue_months


async def check_current_month_payment(db: AsyncSession, student_id: int) -> bool:
    today = date.today()
    first_day_of_month = today.replace(day=1)

    result = await db.execute(
        select(Contract).where(
            and_(
                Contract.student_id == student_id,
                Contract.status == ContractStatus.ACTIVE,
                Contract.start_date <= today,
                Contract.end_date >= today,
            )
        )
    )
    contract = result.scalar_one_or_none()

    if not contract:
        return False

    txn_result = await db.execute(
        select(func.sum(Transaction.amount)).where(
            and_(
                Transaction.contract_id == contract.id,
                Transaction.status == PaymentStatus.SUCCESS,
                or_(
                    Transaction.settlement_type.is_(None),
                    Transaction.settlement_type == PaymentSettlementType.PAYMENT,
                ),
                or_(
                    and_(
                        Transaction.payment_year == today.year,
                        cast(Transaction.payment_months, JSONB).op('@>')(cast([today.month], JSONB)),
                    ),
                    and_(
                        Transaction.payment_year.is_(None),
                        Transaction.paid_at >= first_day_of_month,
                    ),
                ),
            )
        )
    )
    total_paid_this_month = float(txn_result.scalar() or 0.0)

    waiver_result = await db.execute(
        select(func.count(Transaction.id)).where(
            and_(
                Transaction.contract_id == contract.id,
                Transaction.status == PaymentStatus.SUCCESS,
                Transaction.settlement_type == PaymentSettlementType.WAIVER_SPRAVKA,
                Transaction.payment_year == today.year,
                cast(Transaction.payment_months, JSONB).op('@>')(cast([today.month], JSONB)),
            )
        )
    )
    has_waiver_this_month = (waiver_result.scalar() or 0) > 0

    return has_waiver_this_month or total_paid_this_month >= float(contract.monthly_fee)
