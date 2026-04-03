from typing import Annotated, Optional
from datetime import datetime, date
import json
from fastapi import APIRouter, Depends, HTTPException, Query, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.core.db import get_db
from app.core.s3 import upload_as_pdf_to_s3
from app.core.permissions import (
    PERM_FINANCE_TRANSACTIONS_VIEW,
    PERM_FINANCE_UNASSIGNED_VIEW,
    PERM_FINANCE_TRANSACTIONS_MANUAL,
    PERM_FINANCE_UNASSIGNED_ASSIGN,
    PERM_FINANCE_TRANSACTIONS_CANCEL,
)
from app.models.finance import Transaction
from app.models.domain import Student
from app.models.enums import PaymentStatus, PaymentSource, PaymentSettlementType
from app.schemas.transaction import (
    TransactionRead,
    ManualTransactionRead,
    ManualTransactionCreate,
    ManualTransactionPayload,
    TransactionAssign,
    TransactionReadWithStudentName,
    TransactionStatistics,
)
from app.schemas.common import DataResponse, PaginationMeta
from app.deps import require_permission, CurrentUser
from app.services.payment import create_manual_transaction, assign_transaction, cancel_transaction
from app.services.transaction_reporting import build_month_range, allocate_amount_for_period

router = APIRouter(prefix="/transactions", tags=["Transactions"])


def _parse_payment_months_form(payment_months_raw: str) -> list[int]:
    if not payment_months_raw or not payment_months_raw.strip():
        raise ValueError("payment_months is required")

    raw_value = payment_months_raw.strip()
    parsed_months: list[int]
    if raw_value.startswith("["):
        try:
            parsed = json.loads(raw_value)
            if not isinstance(parsed, list):
                raise ValueError
            parsed_months = [int(month_value) for month_value in parsed]
        except Exception:
            raise ValueError("Invalid payment_months format. Use JSON list like [1,2] or CSV like 1,2")
    else:
        try:
            parsed_months = [int(month_value.strip()) for month_value in raw_value.split(",") if month_value.strip()]
        except Exception:
            raise ValueError("Invalid payment_months format. Use comma-separated months like 1,2,3")

    if not parsed_months:
        raise ValueError("payment_months is required")
    return parsed_months


def _build_transaction_conditions(
    payment_year: int | None,
    from_date: Optional[datetime],
    to_date: Optional[datetime],
    status: Optional[str],
    source: Optional[str],
    student_id: Optional[int],
):
    conditions = []
    if payment_year is not None:
        conditions.append(Transaction.payment_year == payment_year)
    if from_date:
        conditions.append(Transaction.created_at >= from_date)
    if to_date:
        conditions.append(Transaction.created_at <= to_date)
    if status:
        conditions.append(Transaction.status == status)
    if source:
        conditions.append(Transaction.source == source)
    if student_id is not None:
        conditions.append(Transaction.student_id == student_id)
    return conditions


@router.get("", response_model=DataResponse[list[TransactionRead]], dependencies=[Depends(require_permission(PERM_FINANCE_TRANSACTIONS_VIEW))])
async def get_transactions(
    db: Annotated[AsyncSession, Depends(get_db)],
    payment_year: int | None = Query(None, description="Filter by payment year (optional, shows all years if not specified)"),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    student_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    Get all transactions with optional filters.

    Default behavior:
    - Shows all transactions from all years
    - Can filter by payment_year, date range, status, source, student
    """
    conditions = _build_transaction_conditions(
        payment_year=payment_year,
        from_date=from_date,
        to_date=to_date,
        status=status,
        source=source,
        student_id=student_id,
    )

    query = select(
        Transaction.id,
        Transaction.external_id,
        Transaction.amount,
        Transaction.source,
        Transaction.status,
        Transaction.settlement_type,
        Transaction.paid_at,
        Transaction.comment,
        Transaction.settlement_document_url,
        Transaction.payment_year,
        Transaction.payment_months,
        Transaction.student_id,
        Transaction.contract_id,
        Transaction.created_by_user_id,
        Transaction.created_at,
    )
    if conditions:
        query = query.where(and_(*conditions))

    # Order by most recent first
    query = query.order_by(Transaction.created_at.desc())

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    transactions = result.mappings().all()

    count_query = select(func.count(Transaction.id))
    if conditions:
        count_query = count_query.where(and_(*conditions))

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return DataResponse(
        data=[TransactionRead(**dict(row)) for row in transactions],
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@router.get("/withname", response_model=DataResponse[list[TransactionReadWithStudentName]], dependencies=[Depends(require_permission(PERM_FINANCE_TRANSACTIONS_VIEW))])
async def get_transactions_with_student_name(
    db: Annotated[AsyncSession, Depends(get_db)],
    payment_year: int | None = Query(None, description="Filter by payment year (optional, shows all years if not specified)"),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    student_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    Get all transactions with student full name instead of student_id.

    Same functionality as GET /transactions but returns student's full name (first_name + last_name)
    instead of student_id.

    Default behavior:
    - Shows all transactions from all years
    - Can filter by payment_year, date range, status, source, student
    """
    conditions = _build_transaction_conditions(
        payment_year=payment_year,
        from_date=from_date,
        to_date=to_date,
        status=status,
        source=source,
        student_id=student_id,
    )

    # Build query with left join to Student table and only required columns.
    query = select(
        Transaction.id,
        Transaction.external_id,
        Transaction.amount,
        Transaction.source,
        Transaction.status,
        Transaction.settlement_type,
        Transaction.paid_at,
        Transaction.comment,
        Transaction.settlement_document_url,
        Transaction.payment_year,
        Transaction.payment_months,
        Transaction.student_id,
        Transaction.contract_id,
        Transaction.created_by_user_id,
        Transaction.created_at,
        Student.first_name.label("student_first_name"),
        Student.last_name.label("student_last_name"),
    ).outerjoin(
        Student, Transaction.student_id == Student.id
    )

    if conditions:
        query = query.where(and_(*conditions))

    # Order by most recent first
    query = query.order_by(Transaction.created_at.desc())

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    rows = result.mappings().all()

    # Build response with student full name
    transactions_with_names = []
    for row in rows:
        first_name = row.get("student_first_name")
        last_name = row.get("student_last_name")
        full_name = None
        if first_name or last_name:
            full_name = f"{first_name or ''} {last_name or ''}".strip()

        transaction_dict = {
            "id": row["id"],
            "external_id": row["external_id"],
            "amount": row["amount"],
            "source": row["source"],
            "status": row["status"],
            "settlement_type": row["settlement_type"],
            "paid_at": row["paid_at"],
            "comment": row["comment"],
            "settlement_document_url": row["settlement_document_url"],
            "payment_year": row["payment_year"],
            "payment_months": row["payment_months"],
            "student_id": row["student_id"],
            "student_full_name": full_name,
            "contract_id": row["contract_id"],
            "created_by_user_id": row["created_by_user_id"],
            "created_at": row["created_at"],
        }
        transactions_with_names.append(TransactionReadWithStudentName(**transaction_dict))

    # Count query (same conditions)
    count_query = select(func.count(Transaction.id))
    if conditions:
        count_query = count_query.where(and_(*conditions))

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return DataResponse(
        data=transactions_with_names,
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@router.get("/unassigned", response_model=DataResponse[list[TransactionRead]], dependencies=[Depends(require_permission(PERM_FINANCE_UNASSIGNED_VIEW))])
async def get_unassigned_transactions(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Transaction)
        .where(Transaction.status == PaymentStatus.UNASSIGNED)
        .offset(offset)
        .limit(page_size)
    )
    transactions = result.scalars().all()

    count_result = await db.execute(
        select(func.count(Transaction.id)).where(Transaction.status == PaymentStatus.UNASSIGNED)
    )
    total = count_result.scalar()

    return DataResponse(
        data=[TransactionRead.model_validate(t) for t in transactions],
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@router.get("/transactionstatistics", response_model=DataResponse[TransactionStatistics], dependencies=[Depends(require_permission(PERM_FINANCE_TRANSACTIONS_VIEW))])
async def get_transaction_statistics(
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Optional[date] = Query(None, description="Start date for month-based calculation (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date for month-based calculation (YYYY-MM-DD)"),
    group_id: Optional[int] = Query(None, description="Filter by student group"),
    status: Optional[str] = Query(None, description="Filter by student status (active, archived, etc.)"),
):
    """
    Statistics computed with the same month-allocation logic as comprehensive export.
    This keeps total_paid aligned with Excel's "Total Paid" summary for the same period.
    """
    from decimal import Decimal
    from datetime import date as date_type
    from fastapi import HTTPException

    today = date_type.today()
    if from_date is None:
        from_date = date_type(today.year, 1, 1)
    if to_date is None:
        to_date = date_type(today.year, 12, 31)

    if from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date must be before or equal to to_date")

    target_months = build_month_range(from_date, to_date)

    month_set = set(target_months)
    if not target_months:
        return DataResponse(
            data=TransactionStatistics(
                from_date=from_date,
                to_date=to_date,
                total_paid=0.0,
                successful_transactions=0,
                click_transactions=0,
                payme_transactions=0,
                bank_transactions=0,
            )
        )

    min_year = min(y for y, _ in target_months)
    max_year = max(y for y, _ in target_months)

    conditions = [
        Transaction.status == PaymentStatus.SUCCESS,
        Transaction.student_id.isnot(None),
        Transaction.contract_id.isnot(None),
        Transaction.payment_year.isnot(None),
        Transaction.payment_year >= min_year,
        Transaction.payment_year <= max_year,
    ]
    if group_id is not None:
        conditions.append(Student.group_id == group_id)
    if status:
        conditions.append(Student.status == status)

    result = await db.execute(
        select(
            Transaction.id,
            Transaction.source,
            Transaction.amount,
            Transaction.payment_year,
            Transaction.payment_months,
        )
        .join(Student, Transaction.student_id == Student.id)
        .where(and_(*conditions))
    )
    rows = result.all()

    total_paid = Decimal("0")
    successful_transactions = 0
    click_transactions = 0
    payme_transactions = 0
    bank_transactions = 0

    for row in rows:
        matched_months, allocated_amount = allocate_amount_for_period(
            amount=row.amount,
            payment_year=row.payment_year,
            payment_months=row.payment_months,
            month_set=month_set,
        )
        if not matched_months:
            continue

        successful_transactions += 1
        if row.source == PaymentSource.CLICK:
            click_transactions += 1
        elif row.source == PaymentSource.PAYME:
            payme_transactions += 1
        elif row.source == PaymentSource.BANK:
            bank_transactions += 1

        total_paid += allocated_amount

    return DataResponse(
        data=TransactionStatistics(
            from_date=from_date,
            to_date=to_date,
            total_paid=float(total_paid.quantize(Decimal("0.01"))),
            successful_transactions=successful_transactions,
            click_transactions=click_transactions,
            payme_transactions=payme_transactions,
            bank_transactions=bank_transactions,
        )
    )


@router.get("/{transaction_id}", response_model=DataResponse[TransactionRead], dependencies=[Depends(require_permission(PERM_FINANCE_TRANSACTIONS_VIEW))])
async def get_transaction(
    transaction_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    transaction = result.scalar_one_or_none()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return DataResponse(data=TransactionRead.model_validate(transaction))


@router.post("/manual", response_model=DataResponse[ManualTransactionRead], dependencies=[Depends(require_permission(PERM_FINANCE_TRANSACTIONS_MANUAL))])
async def create_manual_transaction_endpoint(
    data: ManualTransactionPayload,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        manual_data = ManualTransactionCreate(
            amount=data.amount,
            source=data.source,
            contract_number=data.contract_number,
            payment_year=data.payment_year,
            payment_months=data.payment_months,
            settlement_type=PaymentSettlementType.PAYMENT,
            comment=data.comment,
            paid_at=data.paid_at,
        )
        transaction = await create_manual_transaction(db, manual_data, user.id)
        return DataResponse(data=ManualTransactionRead.model_validate(transaction))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/manual/with-proof", response_model=DataResponse[TransactionRead], dependencies=[Depends(require_permission(PERM_FINANCE_TRANSACTIONS_MANUAL))])
async def create_manual_transaction_with_proof_endpoint(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    contract_number: str = Form(...),
    source: PaymentSource = Form(...),
    amount: float = Form(...),
    payment_year: int = Form(...),
    payment_months: str = Form(..., description="Comma-separated months or JSON list. Example: 2 or 1,2 or [1,2]"),
    settlement_type: PaymentSettlementType = Form(PaymentSettlementType.WAIVER_SPRAVKA),
    comment: Optional[str] = Form(None),
    paid_at: Optional[datetime] = Form(None),
    proof_file: Optional[UploadFile] = File(None),
):
    try:
        parsed_months = _parse_payment_months_form(payment_months)
        proof_file_url: Optional[str] = None
        if proof_file is not None:
            proof_file_url = await upload_as_pdf_to_s3(proof_file, folder="transactions/spravka")

        data = ManualTransactionCreate(
            amount=amount,
            source=source,
            contract_number=contract_number,
            payment_year=payment_year,
            payment_months=parsed_months,
            settlement_type=settlement_type,
            comment=comment,
            paid_at=paid_at,
        )
        transaction = await create_manual_transaction(
            db=db,
            data=data,
            user_id=user.id,
            settlement_document_url=proof_file_url,
        )
        return DataResponse(data=TransactionRead.model_validate(transaction))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload proof file: {str(e)}")


@router.patch("/{transaction_id}/assign", response_model=DataResponse[TransactionRead], dependencies=[Depends(require_permission(PERM_FINANCE_UNASSIGNED_ASSIGN))])
async def assign_transaction_endpoint(
    transaction_id: int,
    data: TransactionAssign,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        transaction = await assign_transaction(db, transaction_id, data.student_id, data.contract_id)
        return DataResponse(data=TransactionRead.model_validate(transaction))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{transaction_id}/cancel", response_model=DataResponse[TransactionRead], dependencies=[Depends(require_permission(PERM_FINANCE_TRANSACTIONS_CANCEL))])
async def cancel_transaction_endpoint(
    transaction_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        transaction = await cancel_transaction(db, transaction_id)
        return DataResponse(data=TransactionRead.model_validate(transaction))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{transaction_id}", response_model=DataResponse[dict], dependencies=[Depends(require_permission(PERM_FINANCE_TRANSACTIONS_CANCEL))])
async def delete_transaction(
    transaction_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    transaction = result.scalar_one_or_none()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    await db.delete(transaction)
    await db.commit()

    return DataResponse(data={"message": "Transaction deleted successfully"})


@router.post("/bulk-delete", response_model=DataResponse[dict], dependencies=[Depends(require_permission(PERM_FINANCE_TRANSACTIONS_CANCEL))])
async def bulk_delete_transactions(
    transaction_ids: list[int],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Bulk delete multiple transactions by their IDs"""
    if not transaction_ids:
        raise HTTPException(status_code=400, detail="No transaction IDs provided")

    deleted_count = 0
    errors = []

    for transaction_id in transaction_ids:
        try:
            result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
            transaction = result.scalar_one_or_none()

            if not transaction:
                errors.append({"transaction_id": transaction_id, "error": "Transaction not found"})
                continue

            await db.delete(transaction)
            deleted_count += 1
        except Exception as e:
            errors.append({"transaction_id": transaction_id, "error": str(e)})

    await db.commit()

    return DataResponse(data={
        "message": f"Deleted {deleted_count} transaction(s)",
        "deleted_count": deleted_count,
        "total_requested": len(transaction_ids),
        "errors": errors if errors else None
    })
