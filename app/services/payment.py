from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.finance import Transaction
from app.models.domain import Contract
from app.models.enums import PaymentStatus, PaymentSource, PaymentSettlementType
from app.schemas.transaction import ManualTransactionCreate


async def create_manual_transaction(
    db: AsyncSession,
    data: ManualTransactionCreate,
    user_id: int,
    settlement_document_url: str | None = None,
) -> Transaction:
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy import cast, func
    from app.models.enums import ContractStatus, StudentStatus
    from app.models.domain import Student

    # Find contract by contract_number
    contract_result = await db.execute(
        select(Contract).where(Contract.contract_number == data.contract_number)
    )
    contract = contract_result.scalar_one_or_none()

    if not contract:
        raise ValueError(f"Contract with number '{data.contract_number}' not found")

    # Validate contract is not DELETED
    # ACTIVE, EXPIRED, TERMINATED, and ARCHIVED contracts can receive payments for unpaid months
    if contract.status == ContractStatus.DELETED:
        raise ValueError(
            f"Contract '{data.contract_number}' is deleted and cannot receive new payments."
        )

    # Validate student status.
    # For terminated contracts we allow INACTIVE students to receive back-dated month payments.
    student_result = await db.execute(
        select(Student).where(Student.id == contract.student_id)
    )
    student = student_result.scalar_one_or_none()

    if not student:
        raise ValueError(f"Student not found for contract '{data.contract_number}'")

    if student.status in [StudentStatus.DELETED, StudentStatus.ARCHIVED]:
        raise ValueError(
            f"Student status is '{student.status.value}'. "
            f"Payments are not allowed for deleted/archived students."
        )

    # Non-terminated contracts still require ACTIVE student.
    if contract.status != ContractStatus.TERMINATED and student.status != StudentStatus.ACTIVE:
        raise ValueError(
            f"Student is not active (current status: {student.status.value}). "
            f"Only ACTIVE students can receive new payments for non-terminated contracts."
        )

    # Validate payment months
    if not data.payment_months:
        raise ValueError("Payment months are required")

    normalized_months = sorted(set(data.payment_months))
    for month in normalized_months:
        if month < 1 or month > 12:
            raise ValueError(f"Invalid month: {month}. Must be between 1 and 12")

    # Validate settlement type rules
    if data.settlement_type == PaymentSettlementType.WAIVER_SPRAVKA:
        if abs(float(data.amount)) > 0.01:
            raise ValueError("For WAIVER_SPRAVKA, amount must be 0")
        if not settlement_document_url:
            raise ValueError("Spravka file is required for WAIVER_SPRAVKA transactions")
    else:
        payment_amount = float(data.amount)
        if payment_amount <= 0:
            raise ValueError("Amount must be greater than 0 for payment transactions")

        required_amount = float(contract.monthly_fee) * len(normalized_months)
        if abs(payment_amount - required_amount) > 0.01:
            raise ValueError(
                f"Amount must match contract monthly fee exactly. Expected {required_amount:.2f} "
                f"for {len(normalized_months)} month(s) (monthly fee: {float(contract.monthly_fee):.2f}), "
                f"got {payment_amount:.2f}"
            )

    # Determine the effective end date (earliest of end_date or terminated_at)
    effective_end_date = contract.end_date
    if contract.terminated_at:
        termination_date = contract.terminated_at.date()
        if termination_date < effective_end_date:
            effective_end_date = termination_date

    # Check for duplicate payments - prevent paying for the same month twice
    for month in normalized_months:
        # Cast payment_months to JSONB to avoid type mismatch
        existing_payment = await db.execute(
            select(Transaction).where(
                Transaction.contract_id == contract.id,
                Transaction.student_id == contract.student_id,
                Transaction.status == PaymentStatus.SUCCESS,
                Transaction.payment_year == data.payment_year,
                cast(Transaction.payment_months, JSONB).op('@>')(cast([month], JSONB))
            )
        )
        existing = existing_payment.scalar_one_or_none()

        if existing:
            month_name = date(data.payment_year, month, 1).strftime('%B')
            raise ValueError(
                f"Payment for {month_name} {data.payment_year} already exists for this contract. "
                f"Cannot add duplicate payment for the same month. "
                f"Existing transaction ID: {existing.id}"
            )

    # Validate that payment months fall within contract period
    for month in normalized_months:
        # Create date for the first day of the payment month
        payment_date = date(data.payment_year, month, 1)

        # Check if payment month is before contract start
        contract_start_month = contract.start_date.replace(day=1)
        if payment_date < contract_start_month:
            raise ValueError(
                f"Payment for {payment_date.strftime('%B %Y')} is before contract start date "
                f"({contract.start_date}). Contract period: {contract.start_date} to {effective_end_date}"
            )

        # Check if payment month is after contract end/termination
        contract_end_month = effective_end_date.replace(day=1)
        if payment_date > contract_end_month:
            termination_msg = " (terminated)" if contract.terminated_at else ""
            raise ValueError(
                f"Payment for {payment_date.strftime('%B %Y')} is after contract end date "
                f"({effective_end_date}){termination_msg}. Contract period: {contract.start_date} to {effective_end_date}"
            )

    transaction = Transaction(
        amount=data.amount,
        source=data.source,
        status=PaymentStatus.SUCCESS,
        settlement_type=data.settlement_type,
        student_id=contract.student_id,
        contract_id=contract.id,
        payment_year=data.payment_year,
        payment_months=normalized_months,
        comment=data.comment,
        settlement_document_url=settlement_document_url,
        paid_at=data.paid_at or datetime.utcnow(),
        created_by_user_id=user_id,
    )
    db.add(transaction)
    await db.commit()
    await db.refresh(transaction)
    return transaction


async def assign_transaction(
    db: AsyncSession,
    transaction_id: int,
    student_id: int,
    contract_id: int,
) -> Transaction:
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    transaction = result.scalar_one_or_none()

    if not transaction:
        raise ValueError("Transaction not found")

    if transaction.status != PaymentStatus.UNASSIGNED:
        raise ValueError("Transaction is not unassigned")

    from app.models.domain import Student
    student_result = await db.execute(select(Student).where(Student.id == student_id))
    if not student_result.scalar_one_or_none():
        raise ValueError(f"Student with ID {student_id} not found")

    contract_result = await db.execute(select(Contract).where(Contract.id == contract_id))
    if not contract_result.scalar_one_or_none():
        raise ValueError(f"Contract with ID {contract_id} not found")

    transaction.student_id = student_id
    transaction.contract_id = contract_id
    transaction.status = PaymentStatus.SUCCESS
    if not transaction.paid_at:
        transaction.paid_at = datetime.utcnow()

    await db.commit()
    await db.refresh(transaction)
    return transaction


async def cancel_transaction(db: AsyncSession, transaction_id: int) -> Transaction:
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    transaction = result.scalar_one_or_none()

    if not transaction:
        raise ValueError("Transaction not found")

    transaction.status = PaymentStatus.CANCELLED
    await db.commit()
    await db.refresh(transaction)
    return transaction
