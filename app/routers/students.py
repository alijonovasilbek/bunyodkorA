from typing import Annotated, Optional, List
import re
from io import BytesIO
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query, File, Form, UploadFile
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import selectinload
from datetime import datetime, date
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from app.core.db import get_db
from app.core.permissions import PERM_STUDENTS_VIEW, PERM_STUDENTS_EDIT, PERM_ATTENDANCE_VIEW
from app.models.domain import Student, Contract
from app.models.attendance import Attendance, GateLog, Session
from app.models.enums import StudentStatus, ContractStatus
from app.schemas.student import StudentRead, StudentCreate, StudentUpdate, StudentFullInfo
from app.schemas.contract import ContractRead
from app.schemas.attendance import AttendanceRead, GateLogRead
from app.schemas.common import DataResponse, PaginationMeta
from app.schemas.student_with_contract import StudentWithContractCreate, StudentWithContractResponse
from app.deps import require_permission, CurrentUser
from app.models.auth import User
from app.core.s3 import upload_image_to_s3, upload_pdf_to_s3, upload_as_pdf_to_s3
from app.utils.contract_pdf import ContractPDFGenerator

router = APIRouter(prefix="/students", tags=["Students"])


@router.get("/search", response_model=DataResponse[list[StudentRead]], dependencies=[Depends(require_permission(PERM_STUDENTS_VIEW))])
async def search_students(
    db: Annotated[AsyncSession, Depends(get_db)],
    query: str = Query(..., description="Search by first name, last name, ampula, contract number, or phone"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=2000),
):
    """
    Comprehensive search for students by:
    - First name
    - Last name
    - Ampula
    - Contract number
    - Phone number
    """
    from app.models.domain import Contract

    # Search students by name or phone
    students_query = select(Student).where(
        or_(
            Student.first_name.ilike(f"%{query}%"),
            Student.last_name.ilike(f"%{query}%"),
            Student.ampula.ilike(f"%{query}%"),
            Student.phone.ilike(f"%{query}%"),
        )
    ).distinct()

    # Search by contract number
    contracts_result = await db.execute(
        select(Contract.student_id).where(Contract.contract_number.ilike(f"%{query}%"))
    )
    student_ids_from_contracts = [row[0] for row in contracts_result.fetchall()]

    all_student_ids = set(student_ids_from_contracts)

    # If we found students via contracts or parents, add them to the query
    if all_student_ids:
        students_query = select(Student).where(
            or_(
                Student.first_name.ilike(f"%{query}%"),
                Student.last_name.ilike(f"%{query}%"),
                Student.ampula.ilike(f"%{query}%"),
                Student.phone.ilike(f"%{query}%"),
                Student.id.in_(all_student_ids)
            )
        ).distinct()

    # Apply pagination
    offset = (page - 1) * page_size
    result = await db.execute(students_query.offset(offset).limit(page_size))
    students = result.scalars().all()

    # Count total results
    count_query = select(func.count(Student.id.distinct())).where(
        or_(
            Student.first_name.ilike(f"%{query}%"),
            Student.last_name.ilike(f"%{query}%"),
            Student.ampula.ilike(f"%{query}%"),
            Student.phone.ilike(f"%{query}%"),
            Student.id.in_(all_student_ids) if all_student_ids else False
        )
    )
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return DataResponse(
        data=[StudentRead.model_validate(s) for s in students],
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
        ),
    )


@router.get("", response_model=DataResponse[list[StudentRead]], dependencies=[Depends(require_permission(PERM_STUDENTS_VIEW))])
async def get_students(
    db: Annotated[AsyncSession, Depends(get_db)],
    search: Optional[str] = None,
    group_id: Optional[int] = None,
    status: Optional[str] = None,
    archive_year: int | None = Query(None, description="Filter by archive year (defaults to current year)"),
    include_archived: bool = Query(False, description="Include archived students (default: only non-ARCHIVED)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=2000),
):
    """
    Get all students with optional filters.

    Default behavior:
    - Shows current year's students only
    - Shows only ACTIVE students unless filters are provided
    """
    from datetime import datetime as dt
    if archive_year is None:
        archive_year = dt.now().year

    query = select(Student).where(Student.archive_year == archive_year)

    # Status behavior:
    # - explicit status filter: return only that status
    # - include_archived=true: return all except DELETED
    # - default: ACTIVE only
    if status:
        query = query.where(Student.status == status)
    elif include_archived:
        query = query.where(Student.status != StudentStatus.DELETED)
    else:
        query = query.where(Student.status == StudentStatus.ACTIVE)

    if search:
        query = query.where(
            or_(
                Student.first_name.ilike(f"%{search}%"),
                Student.last_name.ilike(f"%{search}%"),
                Student.ampula.ilike(f"%{search}%"),
            )
        )
    if group_id:
        query = query.where(Student.group_id == group_id)
    offset = (page - 1) * page_size
    # Order by most recent first
    query = query.order_by(Student.created_at.desc())
    result = await db.execute(query.offset(offset).limit(page_size))
    students = result.scalars().all()

    count_query = select(func.count(Student.id)).where(Student.archive_year == archive_year)
    if status:
        count_query = count_query.where(Student.status == status)
    elif include_archived:
        count_query = count_query.where(Student.status != StudentStatus.DELETED)
    else:
        count_query = count_query.where(Student.status == StudentStatus.ACTIVE)
    if search:
        count_query = count_query.where(
            or_(
                Student.first_name.ilike(f"%{search}%"),
                Student.last_name.ilike(f"%{search}%"),
                Student.ampula.ilike(f"%{search}%"),
            )
        )
    if group_id:
        count_query = count_query.where(Student.group_id == group_id)
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return DataResponse(
        data=[StudentRead.model_validate(s) for s in students],
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


'''
@router.get("/unpaid", response_model=DataResponse[list[StudentDebtInfo]], dependencies=[Depends(require_permission(PERM_STUDENTS_VIEW))])
async def get_unpaid_students(
    db: Annotated[AsyncSession, Depends(get_db)],
    year: Optional[int] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    months: Optional[str] = Query(None, description="Comma-separated months (e.g., '1,2,3' for Jan, Feb, Mar)"),
    from_date: Optional[date] = Query(None, description="Start date for date range filtering (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date for date range filtering (YYYY-MM-DD)"),
    group_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=2000),
):
    """
    Get students who haven't paid for specified periods.

    Filters (use either year/month OR from_date/to_date):
    - year: Target year (defaults to current year)
    - month: Single month to check (1-12)
    - months: Multiple months as comma-separated string (e.g., "1,2,3")
    - from_date: Start date for date range (e.g., "2025-01-01")
    - to_date: End date for date range (e.g., "2025-03-31")
    - group_id: Filter by specific group

    Examples:
    - /unpaid?year=2025&month=1 - Debtors for January 2025
    - /unpaid?year=2025&months=1,2,3 - Debtors for Jan, Feb, Mar 2025
    - /unpaid?from_date=2025-01-01&to_date=2025-03-31 - Debtors for Q1 2025
    - /unpaid?year=2025 - Debtors for any month in 2025
    - /unpaid?year=2025&group_id=5 - Debtors in group 5 for 2025
    """
    target_months, _, _, _, _ = _build_unpaid_target_months(
        year=year,
        month=month,
        months=months,
        from_date=from_date,
        to_date=to_date,
    )

    debt_rows = await _collect_unpaid_rows(
        db=db,
        target_months=target_months,
        group_id=group_id,
        include_group_names=False,
    )

    # Apply pagination
    offset = (page - 1) * page_size
    paginated_rows = debt_rows[offset:offset + page_size]
    total = len(debt_rows)
    paginated_list = [
        StudentDebtInfo(
            student=StudentRead.model_validate(row["student"]),
            total_expected=row["total_expected"],
            total_paid=row["total_paid"],
            debt_amount=row["debt_amount"],
            active_contracts_count=row["active_contracts_count"],
        )
        for row in paginated_rows
    ]

    return DataResponse(
        data=paginated_list,
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@router.get("/unpaid/export", dependencies=[Depends(require_permission(PERM_STUDENTS_VIEW))])
async def export_unpaid_students(
    db: Annotated[AsyncSession, Depends(get_db)],
    year: Optional[int] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    months: Optional[str] = Query(None, description="Comma-separated months (e.g., '1,2,3')"),
    from_date: Optional[date] = Query(None, description="Start date for date range filtering (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date for date range filtering (YYYY-MM-DD)"),
    group_id: Optional[int] = None,
):
    """
    Export unpaid students data to Excel file with statistics.

    Same filters as /unpaid endpoint (use either year/month OR from_date/to_date):
    - year: Target year (defaults to current year)
    - month: Single month to check (1-12)
    - months: Multiple months as comma-separated string
    - from_date: Start date for date range (e.g., "2025-01-01")
    - to_date: End date for date range (e.g., "2025-03-31")
    - group_id: Filter by specific group
    """
    from app.models.domain import Group

    target_months, use_date_range, from_date, to_date, target_year = _build_unpaid_target_months(
        year=year,
        month=month,
        months=months,
        from_date=from_date,
        to_date=to_date,
    )

    # Get group name for filename if filtering by group
    group_name = ""
    if group_id:
        group_result = await db.execute(select(Group).where(Group.id == group_id))
        group = group_result.scalar_one_or_none()
        if group:
            group_name = f"_{group.name.replace(' ', '_')}"

    debt_rows = await _collect_unpaid_rows(
        db=db,
        target_months=target_months,
        group_id=group_id,
        include_group_names=True,
    )

    # Create Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Unpaid Students"

    # Define header style
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    header_alignment = Alignment(horizontal="center", vertical="center")

    # Define headers
    headers = [
        "ID",
        "First Name",
        "Last Name",
        "Phone",
        "Group",
        "Expected Amount",
        "Paid Amount",
        "Debt Amount",
        "Active Contracts"
    ]

    # Write headers
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment

    # Write data
    for row_num, debt_row in enumerate(debt_rows, 2):
        student = debt_row["student"]
        ws.cell(row=row_num, column=1, value=student.id)
        ws.cell(row=row_num, column=2, value=student.first_name)
        ws.cell(row=row_num, column=3, value=student.last_name)
        ws.cell(row=row_num, column=4, value=student.phone or "")
        ws.cell(row=row_num, column=5, value=debt_row["group_name"])
        ws.cell(row=row_num, column=6, value=debt_row["total_expected"])
        ws.cell(row=row_num, column=7, value=debt_row["total_paid"])
        ws.cell(row=row_num, column=8, value=debt_row["debt_amount"])
        ws.cell(row=row_num, column=9, value=debt_row["active_contracts_count"])

    # Adjust column widths
    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 15
    ws.column_dimensions['C'].width = 15
    ws.column_dimensions['D'].width = 15
    ws.column_dimensions['E'].width = 20
    ws.column_dimensions['F'].width = 15
    ws.column_dimensions['G'].width = 15
    ws.column_dimensions['H'].width = 15
    ws.column_dimensions['I'].width = 18

    # Add summary row
    if debt_rows:
        summary_row = len(debt_rows) + 3
        ws.cell(row=summary_row, column=1, value="TOTAL").font = Font(bold=True)
        ws.cell(row=summary_row, column=6, value=sum(row["total_expected"] for row in debt_rows)).font = Font(bold=True)
        ws.cell(row=summary_row, column=7, value=sum(row["total_paid"] for row in debt_rows)).font = Font(bold=True)
        ws.cell(row=summary_row, column=8, value=sum(row["debt_amount"] for row in debt_rows)).font = Font(bold=True)

    # Save to BytesIO
    excel_file = BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)

    # Generate filename based on filter type
    if use_date_range:
        date_str = f"{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}"
        filename = f"unpaid_students_{date_str}{group_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    else:
        # Extract just the month numbers for display
        month_nums = [m[1] for m in target_months]
        months_str = ",".join(map(str, month_nums)) if len(month_nums) <= 3 else "all"
        filename = f"unpaid_students_{target_year}_{months_str}{group_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    # Keep header ASCII-safe while preserving UTF-8 filename for clients.
    ascii_filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    encoded_filename = quote(filename)
    content_disposition = (
        f"attachment; filename=\"{ascii_filename}\"; "
        f"filename*=UTF-8''{encoded_filename}"
    )

    # Return as streaming response
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": content_disposition}
    )


'''

@router.get("/comprehensive-export", dependencies=[Depends(require_permission(PERM_STUDENTS_VIEW))])
async def export_comprehensive_student_data(
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Optional[date] = Query(None, description="Filter contracts from date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="Filter contracts to date (YYYY-MM-DD)"),
    group_id: Optional[int] = Query(None, description="Filter by specific group"),
    status: Optional[str] = Query(None, description="Filter by student status (active, archived, etc.)"),
):
    """
    Export comprehensive student data to Excel file including:
    - Student information (name, ampula, phone, address, date of birth, status)
    - Contract details (number, start/end dates, monthly fee, status, termination info)
    - Group information

    Filters:
    - from_date: Include contracts overlapping this start date
    - to_date: Include contracts overlapping this end date
    - group_id: Filter students by specific group
    - status: Filter by student status (e.g., 'active', 'archived')
    """
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date must be before or equal to to_date")

    # Build student query with filters
    students_query = select(Student).options(
        selectinload(Student.group),
        selectinload(Student.contracts)
    )

    if group_id:
        students_query = students_query.where(Student.group_id == group_id)

    if status:
        try:
            student_status = StudentStatus(status.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid student status: {status}")
        students_query = students_query.where(Student.status == student_status)

    students_result = await db.execute(
        students_query.order_by(Student.last_name.asc(), Student.first_name.asc())
    )
    students = students_result.scalars().all()
    active_students_count = sum(1 for s in students if s.status == StudentStatus.ACTIVE)
    inactive_students_count = sum(1 for s in students if s.status == StudentStatus.INACTIVE)

    # Prepare data for Excel
    student_data_list = []

    for student in students:
        group_name = student.group.name if student.group else "N/A"
        contracts = list(student.contracts)

        if from_date or to_date:
            filtered_contracts = []
            for contract in contracts:
                effective_end_date = contract.end_date
                if contract.terminated_at:
                    termination_date = contract.terminated_at.date()
                    if termination_date < effective_end_date:
                        effective_end_date = termination_date

                overlaps_from = from_date is None or effective_end_date >= from_date
                overlaps_to = to_date is None or contract.start_date <= to_date
                if overlaps_from and overlaps_to:
                    filtered_contracts.append(contract)
            contracts = filtered_contracts

        if not contracts:
            if from_date or to_date:
                continue
            student_data_list.append({
                "student_id": student.id,
                "first_name": student.first_name,
                "last_name": student.last_name,
                "date_of_birth": student.date_of_birth.strftime("%Y-%m-%d"),
                "height": student.height,
                "weight": student.weight,
                "ampula": student.ampula or "N/A",
                "pnfl": student.pnfl,
                "phone": student.phone or "N/A",
                "address": student.address or "N/A",
                "status": student.status.value,
                "group": group_name,
                "contract_number": "N/A",
                "contract_start": "N/A",
                "contract_end": "N/A",
                "contract_status": "N/A",
                "terminated_at": "N/A",
                "termination_reason": "N/A",
            })
            continue

        for contract in contracts:
            terminated_at_str = contract.terminated_at.strftime("%Y-%m-%d") if contract.terminated_at else "N/A"
            termination_reason = contract.termination_reason if contract.termination_reason else "N/A"

            student_data_list.append({
                "student_id": student.id,
                "first_name": student.first_name,
                "last_name": student.last_name,
                "date_of_birth": student.date_of_birth.strftime("%Y-%m-%d"),
                "height": student.height,
                "weight": student.weight,
                "ampula": student.ampula or "N/A",
                "pnfl": student.pnfl,
                "phone": student.phone or "N/A",
                "address": student.address or "N/A",
                "status": student.status.value,
                "group": group_name,
                "contract_number": contract.contract_number or "N/A",
                "contract_start": contract.start_date.strftime("%Y-%m-%d"),
                "contract_end": contract.end_date.strftime("%Y-%m-%d"),
                "contract_status": contract.status.value,
                "terminated_at": terminated_at_str,
                "termination_reason": termination_reason,
            })

    # Create Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Student Data"

    # Define header style
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Define headers
    headers = [
        "Student ID",
        "First Name",
        "Last Name",
        "Date of Birth",
        "Height",
        "Weight",
        "Ampula",
        "PNFL",
        "Phone",
        "Address",
        "Status",
        "Group",
        "Contract Number",
        "Contract Start",
        "Contract End",
        "Contract Status",
        "Terminated At",
        "Termination Reason",
    ]

    # Write headers
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment

    terminated_status_value = ContractStatus.TERMINATED.value
    non_terminated_rows = [
        row for row in student_data_list
        if row.get("contract_status") != terminated_status_value
    ]
    terminated_rows = [
        row for row in student_data_list
        if row.get("contract_status") == terminated_status_value
    ]

    def _row_sort_key(row: dict) -> tuple:
        return (
            str(row.get("last_name", "")),
            str(row.get("first_name", "")),
            int(row.get("student_id", 0)),
            str(row.get("contract_number", "")),
        )

    non_terminated_rows.sort(key=_row_sort_key)
    terminated_rows.sort(key=_row_sort_key)

    def _write_student_row(row_num: int, student_data: dict) -> None:
        ws.cell(row=row_num, column=1, value=student_data["student_id"])
        ws.cell(row=row_num, column=2, value=student_data["first_name"])
        ws.cell(row=row_num, column=3, value=student_data["last_name"])
        ws.cell(row=row_num, column=4, value=student_data["date_of_birth"])
        ws.cell(row=row_num, column=5, value=student_data["height"])
        ws.cell(row=row_num, column=6, value=student_data["weight"])
        ws.cell(row=row_num, column=7, value=student_data["ampula"])
        ws.cell(row=row_num, column=8, value=student_data["pnfl"])
        ws.cell(row=row_num, column=9, value=student_data["phone"])
        ws.cell(row=row_num, column=10, value=student_data["address"])
        ws.cell(row=row_num, column=11, value=student_data["status"])
        ws.cell(row=row_num, column=12, value=student_data["group"])
        ws.cell(row=row_num, column=13, value=student_data["contract_number"])
        ws.cell(row=row_num, column=14, value=student_data["contract_start"])
        ws.cell(row=row_num, column=15, value=student_data["contract_end"])
        ws.cell(row=row_num, column=16, value=student_data["contract_status"])
        ws.cell(row=row_num, column=17, value=student_data["terminated_at"])
        ws.cell(row=row_num, column=18, value=student_data["termination_reason"])

    current_row = 2
    for row in non_terminated_rows:
        _write_student_row(current_row, row)
        current_row += 1

    # Leave one blank row before terminated rows.
    if non_terminated_rows and terminated_rows:
        current_row += 1

    for row in terminated_rows:
        _write_student_row(current_row, row)
        current_row += 1

    # Adjust column widths
    column_widths = {
        'A': 12, 'B': 15, 'C': 15, 'D': 15, 'E': 10, 'F': 10,
        'G': 18, 'H': 18, 'I': 15, 'J': 30, 'K': 12, 'L': 20,
        'M': 18, 'N': 15, 'O': 15, 'P': 15, 'Q': 15, 'R': 20
    }

    for col, width in column_widths.items():
        ws.column_dimensions[col].width = width

    # Add summary row
    if student_data_list:
        summary_row = current_row + 1
        ws.cell(row=summary_row, column=1, value="TOTALS").font = Font(bold=True)

        # Add metadata
        metadata_row = summary_row + 2
        ws.cell(row=metadata_row, column=1, value=f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}").font = Font(italic=True)
        if from_date or to_date:
            from_display = from_date.strftime('%Y-%m-%d') if from_date else "..."
            to_display = to_date.strftime('%Y-%m-%d') if to_date else "..."
            ws.cell(row=metadata_row + 1, column=1, value=f"Contract Period Filter: {from_display} to {to_display}").font = Font(italic=True)
        ws.cell(row=metadata_row + 2, column=1, value=f"Total Students: {len(students)}").font = Font(italic=True)
        ws.cell(row=metadata_row + 3, column=1, value=f"Total Contracts: {len(student_data_list)}").font = Font(italic=True)
        ws.cell(row=metadata_row + 4, column=1, value=f"Active Students: {active_students_count}").font = Font(italic=True)
        ws.cell(row=metadata_row + 5, column=1, value=f"Inactive Students: {inactive_students_count}").font = Font(italic=True)

    # Save to BytesIO
    excel_file = BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)

    # Generate filename
    group_suffix = f"_group{group_id}" if group_id else ""
    status_suffix = f"_{status}" if status else ""
    if from_date or to_date:
        from_part = from_date.strftime('%Y%m%d') if from_date else "start"
        to_part = to_date.strftime('%Y%m%d') if to_date else "end"
        date_str = f"{from_part}_{to_part}"
    else:
        date_str = datetime.now().strftime('%Y%m%d')
    filename = f"comprehensive_student_data_{date_str}{group_suffix}{status_suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    # Return as streaming response
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.post("", response_model=DataResponse[StudentRead], dependencies=[Depends(require_permission(PERM_STUDENTS_EDIT))])
async def create_student(
    data: StudentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    existing_pnfl = await db.execute(select(Student).where(Student.pnfl == data.pnfl))
    if existing_pnfl.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="PNFL already exists. Please use a unique PNFL")

    if data.face_id:
        existing_face_id = await db.execute(select(Student).where(Student.face_id == data.face_id))
        if existing_face_id.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Face ID already exists. Please use a unique Face ID")

    if data.group_id:
        from app.models.domain import Group
        group_result = await db.execute(select(Group).where(Group.id == data.group_id))
        group = group_result.scalar_one_or_none()
        if not group:
            raise HTTPException(status_code=404, detail=f"Group with ID {data.group_id} not found")

        # Check group capacity by ACTIVE contracts only.
        # Terminated contracts do not occupy group slots.
        if data.status == StudentStatus.ACTIVE:
            active_students_count = await db.execute(
                select(func.count(Contract.id)).where(
                    Contract.group_id == data.group_id,
                    Contract.status == ContractStatus.ACTIVE
                )
            )
            current_count = active_students_count.scalar() or 0

            if current_count >= group.capacity:
                raise HTTPException(
                    status_code=409,
                    detail=f"Group '{group.name}' is at full capacity ({group.capacity} active contracts). "
                           f"Cannot add more active contracts. Consider adding to waiting list instead."
                )

    student = Student(**data.model_dump())
    db.add(student)
    await db.commit()
    await db.refresh(student)
    return DataResponse(data=StudentRead.model_validate(student))

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException
import asyncio

@router.post("/create-with-contract")
async def create_student_with_contract(
    user: Annotated[User, Depends(require_permission(PERM_STUDENTS_EDIT))],
    db: Annotated[AsyncSession, Depends(get_db)],

    student_data: str = Form(..., description="Student payload as JSON string. Required fields: first_name, last_name, date_of_birth, height, weight, pnfl, group_id."),
    contract_data: str = Form(..., description="Contract payload as JSON string. Required keys: contract_number, shartnoma_muddati.boshlanish."),

    passport_copy: UploadFile | None = File(None, description="Optional. Profile image; if sent, used as student image and included in attachment PDF flow."),
    form_086: UploadFile | None = File(None, description="Optional. Medical form 086 document."),
    heart_checkup: UploadFile | None = File(None, description="Optional. Heart checkup document."),
    birth_certificate: UploadFile | None = File(None, description="Optional. Birth certificate front side."),
    contract_image_1: UploadFile | None = File(None, description="Optional attachment #1. Usually birth certificate back side."),
    contract_image_2: UploadFile | None = File(None, description="Optional attachment #2. Usually father passport front side."),
    contract_image_3: UploadFile | None = File(None, description="Optional attachment #3. Usually father passport back side."),
    contract_image_4: UploadFile | None = File(None, description="Optional attachment #4. Usually mother passport front side."),
    contract_image_5: UploadFile | None = File(None, description="Optional attachment #5. Usually mother passport back side."),
):
    """
    Create student with contract in one operation.

    Contract number must be provided by admin:
    - Use GET /contracts/next-available/{group_id} to get the next number
    - Admin must enter the contract_number manually
    - Numbers must be sequential
    - Terminated contracts release their number and it can be reused

    student_data JSON structure:
    ```json
    {
      "first_name": "Alvaro",
      "last_name": "Marata",
      "date_of_birth": "2010-12-06",
      "height": 152,
      "weight": 43,
      "ampula": "hujumchi",
      "pnfl": "12345678901234",
      "phone": "998901234567",
      "address": "Toshkent shahar",
      "status": "active",
      "group_id": 1
    }
    ```

    contract_data JSON structure:
    ```json
    {
      "contract_number": "5-2014B1",
      "student": {
        "student_fio": "Alvaro Marata",
        "birth_year": "2010",
        "student_address": "Toshkent shahar"
      },
      "buyurtmachi": {
        "fio": "Valiy",
        "pasport_seriya": "AA 1234567",
        "pasport_kim_bergan": "Chilonzor IIB",
        "pasport_qachon_bergan": "15.03.2018",
        "manzil": "Toshkent shahar",
        "telefon": "+998901234567"
      },
      "tarbiyalanuvchi": {
        "fio": "Alvaro Marata",
        "tugilganlik_guvohnoma": "I-AA 9876543",
        "tugilganlik_yil": 2010,
        "guvohnoma_kim_bergan": "FHDYO",
        "guvohnoma_qachon_bergan": "12.04.2012"
      },
      "shartnoma_muddati": {
        "boshlanish": "2026-01-06",
        "tugash": "2026-12-06",
        "yil": "2026"
      }
    }
    ```

    Notes:
    - Required keys in contract_data: contract_number, shartnoma_muddati.boshlanish
    - shartnoma_muddati.tugash optional; yuborilmasa 1 yilga avtomatik hisoblanadi
    - student, buyurtmachi, tarbiyalanuvchi bloklari custom_fields sifatida saqlanadi
    - sana va student.student_image yuborish shart emas
    - tarbiyalanuvchi.tugilganlik_guvohnoma bo'lsa duplicate tekshiruvi ishlaydi
    """
    from app.models.domain import Group, Contract
    from app.models.enums import ContractStatus, StudentStatus
    from app.services.contract_allocation import is_group_full, validate_contract_number
    import json
    import os
    import tempfile
    from datetime import datetime
    import time

    try:
        student_info = json.loads(student_data)
        contract_info = json.loads(contract_data)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

    first_name = student_info.get("first_name")
    last_name = student_info.get("last_name")
    date_of_birth = student_info.get("date_of_birth")
    height = student_info.get("height")
    weight = student_info.get("weight")
    ampula = student_info.get("ampula")
    pnfl = str(student_info.get("pnfl") or "").strip()
    phone = student_info.get("phone")
    address = student_info.get("address")
    status = student_info.get("status", "active")
    group_id = student_info.get("group_id")

    if not all([first_name, last_name, date_of_birth, group_id, pnfl]) or height in (None, "") or weight in (None, ""):
        raise HTTPException(
            status_code=400,
            detail="Missing required fields in student_data: first_name, last_name, date_of_birth, height, weight, pnfl, group_id",
        )
    if len(pnfl) != 14:
        raise HTTPException(status_code=400, detail="PNFL must be exactly 14 characters")
    try:
        height = int(height)
        weight = int(weight)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="height and weight must be integers")

    existing_pnfl = await db.execute(select(Student).where(Student.pnfl == pnfl))
    if existing_pnfl.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="PNFL already exists. Please use a unique PNFL")

    buyurtmachi = contract_info.get("buyurtmachi", {})
    student_block = dict(contract_info.get("student", {}))
    tarbiyalanuvchi = contract_info.get("tarbiyalanuvchi", {})
    shartnoma_muddati = contract_info.get("shartnoma_muddati", {})

    contract_number = contract_info.get("contract_number")
    if not contract_number:
        raise HTTPException(
            status_code=400,
            detail="contract_number is required in contract_data. Use GET /contracts/next-available/{group_id} to get the next available number.",
        )

    tugilganlik_guvohnoma = tarbiyalanuvchi.get("tugilganlik_guvohnoma")
    if tugilganlik_guvohnoma:
        existing_birth_cert = await db.execute(
            select(Contract.id).where(
                func.jsonb_extract_path_text(
                    cast(Contract.custom_fields, JSONB),
                    "tarbiyalanuvchi",
                    "tugilganlik_guvohnoma",
                ) == tugilganlik_guvohnoma
            )
        )
        if existing_birth_cert.scalar():
            raise HTTPException(
                status_code=400,
                detail=f"Bunday student mavjud. Tug'ilganlik guvohnomasi '{tugilganlik_guvohnoma}' allaqachon bazada mavjud.",
            )

    group_result = await db.execute(select(Group).where(Group.id == group_id))
    group = group_result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail=f"Group with ID {group_id} not found")

    birth_year = group.birth_year
    if await is_group_full(db, group_id, birth_year):
        raise HTTPException(
            status_code=409,
            detail=f"Group '{group.name}' is full (capacity: {group.capacity}). Cannot create contract. Add to waiting list instead.",
        )

    try:
        for file in [
            passport_copy,
            form_086,
            heart_checkup,
            birth_certificate,
            contract_image_1,
            contract_image_2,
            contract_image_3,
            contract_image_4,
            contract_image_5,
        ]:
            if file is not None:
                file.file.seek(0)

        async def upload_or_none(file, folder):
            if file is None:
                return None
            return await upload_as_pdf_to_s3(file, folder)

        async def upload_image_or_none(file, folder):
            if file is None:
                return None
            return await upload_image_to_s3(file, folder)

        async def upload_with_type(file, folder, as_image):
            if as_image:
                return await upload_image_or_none(file, folder)
            return await upload_or_none(file, folder)

        upload_jobs = [
            (passport_copy, "student-documents", True),
            (form_086, "student-documents", False),
            (heart_checkup, "student-documents", False),
            (birth_certificate, "student-documents", False),
            (contract_image_1, "contracts", False),
            (contract_image_2, "contracts", False),
            (contract_image_3, "contracts", False),
            (contract_image_4, "contracts", False),
            (contract_image_5, "contracts", False),
        ]
        results = await asyncio.gather(*[upload_with_type(file, folder, as_image) for file, folder, as_image in upload_jobs])
        passport_copy_url, form_086_url, heart_checkup_url, birth_certificate_url, *contract_images_urls = results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading files to S3: {str(e)}")

    if isinstance(date_of_birth, str):
        date_of_birth = datetime.strptime(date_of_birth, "%Y-%m-%d").date()

    current_year = datetime.now().year
    student_status = StudentStatus.ACTIVE if str(status).lower() == "active" else StudentStatus.INACTIVE
    student = Student(
        first_name=first_name,
        last_name=last_name,
        date_of_birth=date_of_birth,
        height=height,
        weight=weight,
        ampula=ampula,
        pnfl=pnfl,
        phone=phone,
        address=address,
        status=student_status,
        group_id=group_id,
        archive_year=current_year,
    )
    db.add(student)
    await db.flush()
    await db.refresh(student)

    is_valid, message, sequence_number = await validate_contract_number(db, contract_number, group_id, birth_year, current_year)
    if not is_valid:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Invalid contract number: {message}. Use GET /contracts/next-available/{group_id} to get the next available number.",
        )

    start_date_str = shartnoma_muddati.get("boshlanish")
    end_date_str = shartnoma_muddati.get("tugash")
    year_val = shartnoma_muddati.get("yil")

    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        else:
            raise ValueError("boshlanish sanasi kiritilmagan")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Sana formati noto'g'ri (boshlanish): {str(e)}")

    try:
        if end_date_str and str(end_date_str).isdigit():
            end_date = datetime(int(year_val or start_date.year), 12, int(end_date_str)).date()
        elif end_date_str:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        else:
            end_date = start_date + relativedelta(years=1)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Sana formati noto'g'ri (tugash): {str(e)}")

    contract_images_json_str = json.dumps(contract_images_urls)
    custom_fields_json_str = json.dumps(contract_info, ensure_ascii=False, default=str)
    existing_contract = await db.execute(select(Contract).where(Contract.contract_number == contract_number))
    if existing_contract.scalar():
        raise HTTPException(status_code=400, detail=f"Shartnoma raqami '{contract_number}' allaqachon mavjud.")

    contract = Contract(
        contract_number=contract_number,
        birth_year=birth_year,
        sequence_number=sequence_number,
        start_date=start_date,
        end_date=end_date,
        status=ContractStatus.ACTIVE,
        student_id=student.id,
        group_id=group_id,
        archive_year=current_year,
        passport_copy_url=passport_copy_url,
        form_086_url=form_086_url,
        heart_checkup_url=heart_checkup_url,
        birth_certificate_url=birth_certificate_url,
        contract_images_urls=contract_images_json_str,
        custom_fields=custom_fields_json_str,
    )
    db.add(contract)

    pdf_data = {
        "render_text_content": False,
        "shartnoma_raqami": contract_number,
        "student": student_block,
        "sana": {
            "kun": f"{start_date.day:02d}",
            "oy": str(start_date.month),
            "yil": str(start_date.year),
        },
        "buyurtmachi": buyurtmachi,
        "tarbiyalanuvchi": tarbiyalanuvchi,
        "shartnoma_muddati": {
            "boshlanish": start_date.strftime("%d.%m.%Y"),
            "tugash": end_date.strftime("%d.%m.%Y"),
            "yil": str(start_date.year),
        },
        "passport_copy_url": passport_copy_url,
        "form_086_url": form_086_url,
        "heart_checkup_url": heart_checkup_url,
        "birth_certificate_url": birth_certificate_url,
        "contract_images_urls": contract_images_urls,
    }
    pdf_data["student"]["student_image"] = passport_copy_url

    temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf_path = temp_pdf.name
    temp_pdf.close()

    try:
        generator = ContractPDFGenerator(pdf_data)
        final_pdf_path = await asyncio.to_thread(generator.generate, pdf_path)

        pdf_s3_url = None
        if final_pdf_path and isinstance(final_pdf_path, (str, os.PathLike)):
            pdf_s3_url = await upload_pdf_to_s3(final_pdf_path, contract_number)
            contract.final_pdf_url = pdf_s3_url

        await db.commit()
        await db.refresh(contract)

        try:
            time.sleep(0.2)
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
            if final_pdf_path and os.path.exists(final_pdf_path):
                os.unlink(final_pdf_path)
        except Exception:
            pass

        return DataResponse(data={
            "message": "Student and contract created successfully",
            "student_id": student.id,
            "contract_id": contract.id,
            "contract_number": contract_number,
            "pdf_url": pdf_s3_url,
        })
    except Exception as e:
        await db.rollback()
        try:
            time.sleep(0.2)
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
            if 'final_pdf_path' in locals() and final_pdf_path and os.path.exists(final_pdf_path):
                os.unlink(final_pdf_path)
        except Exception:
            pass

        raise HTTPException(
            status_code=500,
            detail=f"Failed to create contract: {str(e)}. Student and contract data have been rolled back.",
        )


@router.get("/{student_id}", response_model=DataResponse[StudentRead], dependencies=[Depends(require_permission(PERM_STUDENTS_VIEW))])
async def get_student(
    student_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    return DataResponse(data=StudentRead.model_validate(student))


@router.get("/fullinfo/{student_id}", response_model=DataResponse[StudentFullInfo], dependencies=[Depends(require_permission(PERM_STUDENTS_VIEW))])
async def get_student_full_info(
    student_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get complete student information including:
    - Student details
    - Contracts
    - Group
    - Coach (teacher)
    - Attendance records
    """
    from app.models.domain import Contract, Group
    from app.models.auth import User

    # Fetch student
    student_result = await db.execute(select(Student).where(Student.id == student_id))
    student = student_result.scalar_one_or_none()

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Fetch contracts
    contracts_result = await db.execute(
        select(Contract)
        .options(selectinload(Contract.terminated_by))
        .where(Contract.student_id == student_id)
    )
    contracts = contracts_result.scalars().all()

    # Fetch group and coach if student has a group
    group = None
    coach = None
    if student.group_id:
        group_result = await db.execute(select(Group).where(Group.id == student.group_id))
        group = group_result.scalar_one_or_none()

        if group and group.coach_id:
            coach_result = await db.execute(
                select(User).where(User.id == group.coach_id)
            )
            coach = coach_result.scalar_one_or_none()

    # Fetch attendance records
    attendances_result = await db.execute(
        select(Attendance).where(Attendance.student_id == student_id).order_by(Attendance.created_at.desc())
    )
    attendances = attendances_result.scalars().all()

    from app.models.enums import ContractStatus
    # Count active contracts
    active_contracts_count = sum(1 for c in contracts if c.status == ContractStatus.ACTIVE)

    # Build the full info response
    from app.schemas.group import GroupRead
    from app.schemas.auth import UserRead

    full_info = StudentFullInfo(
        student=StudentRead.model_validate(student),
        contracts=[ContractRead.model_validate(c) for c in contracts],
        group=GroupRead.model_validate(group) if group else None,
        coach=UserRead.model_validate(coach) if coach else None,
        attendances=[AttendanceRead.model_validate(a) for a in attendances],
        active_contracts_count=active_contracts_count,
    )

    return DataResponse(data=full_info)


@router.patch("/{student_id}", response_model=DataResponse[StudentRead], dependencies=[Depends(require_permission(PERM_STUDENTS_EDIT))])
async def update_student(
    student_id: int,
    data: StudentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    update_data = data.model_dump(exclude_unset=True)

    # Prevent changing student's group once assigned
    if "group_id" in update_data and student.group_id is not None:
        if update_data["group_id"] != student.group_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot change student's group. Students cannot be transferred between groups."
            )

    if "face_id" in update_data and update_data["face_id"] is not None:
        existing_face_id = await db.execute(
            select(Student).where(Student.face_id == update_data["face_id"], Student.id != student_id)
        )
        if existing_face_id.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Face ID already exists. Please use a unique Face ID")

    if "pnfl" in update_data and update_data["pnfl"] is not None:
        existing_pnfl = await db.execute(
            select(Student).where(Student.pnfl == update_data["pnfl"], Student.id != student_id)
        )
        if existing_pnfl.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="PNFL already exists. Please use a unique PNFL")

    # Check capacity when assigning to a group or changing status to ACTIVE
    target_group_id = update_data.get("group_id", student.group_id)
    target_status = update_data.get("status", student.status)

    # Determine if this update will make student ACTIVE in a group
    will_be_active_in_group = (
        target_group_id is not None and
        target_status == StudentStatus.ACTIVE and
        (student.group_id != target_group_id or student.status != StudentStatus.ACTIVE)
    )

    if will_be_active_in_group:
        from app.models.domain import Group
        group_result = await db.execute(select(Group).where(Group.id == target_group_id))
        group = group_result.scalar_one_or_none()

        if not group:
            raise HTTPException(status_code=404, detail=f"Group with ID {target_group_id} not found")

        # Count current ACTIVE contracts in target group (excluding this student's contracts).
        active_students_count = await db.execute(
            select(func.count(func.distinct(Contract.student_id))).where(
                Contract.group_id == target_group_id,
                Contract.status == ContractStatus.ACTIVE,
                Contract.student_id != student_id,
            )
        )
        current_count = active_students_count.scalar() or 0

        if current_count >= group.capacity:
            raise HTTPException(
                status_code=409,
                detail=f"Group '{group.name}' is at full capacity ({group.capacity} active contracts). "
                       f"Cannot add more active contracts. Consider adding to waiting list instead."
            )
    elif "group_id" in update_data and update_data["group_id"] is not None:
        # Just validate group exists if only changing group
        from app.models.domain import Group
        group_result = await db.execute(select(Group).where(Group.id == update_data["group_id"]))
        if not group_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail=f"Group with ID {update_data['group_id']} not found")

    for field, value in update_data.items():
        setattr(student, field, value)

    await db.commit()
    await db.refresh(student)
    return DataResponse(data=StudentRead.model_validate(student))


@router.get("/{student_id}/contracts", response_model=DataResponse[list[ContractRead]], dependencies=[Depends(require_permission(PERM_STUDENTS_VIEW))])
async def get_student_contracts(
    student_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from app.models.domain import Contract
    result = await db.execute(
        select(Contract)
        .options(selectinload(Contract.terminated_by))
        .where(Contract.student_id == student_id)
    )
    contracts = result.scalars().all()
    return DataResponse(data=[ContractRead.model_validate(c) for c in contracts])


'''
@router.get("/{student_id}/transactions", response_model=DataResponse[list[TransactionRead]], dependencies=[Depends(require_permission(PERM_STUDENTS_VIEW))])
async def get_student_transactions(
    student_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Transaction).where(Transaction.student_id == student_id))
    transactions = result.scalars().all()
    return DataResponse(data=[TransactionRead.model_validate(t) for t in transactions])


'''

@router.get("/{student_id}/attendance", response_model=DataResponse[list[AttendanceRead]], dependencies=[Depends(require_permission(PERM_STUDENTS_VIEW))])
async def get_student_attendance(
    student_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Attendance).where(Attendance.student_id == student_id))
    attendance = result.scalars().all()
    return DataResponse(data=[AttendanceRead.model_validate(a) for a in attendance])


@router.get("/{student_id}/gatelogs", response_model=DataResponse[list[GateLogRead]], dependencies=[Depends(require_permission(PERM_STUDENTS_VIEW))])
async def get_student_gatelogs(
    student_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(GateLog).where(GateLog.student_id == student_id))
    logs = result.scalars().all()
    return DataResponse(data=[GateLogRead.model_validate(l) for l in logs])


@router.get("/attendances/all", response_model=DataResponse[list[AttendanceRead]], dependencies=[Depends(require_permission(PERM_ATTENDANCE_VIEW))])
async def get_all_attendances(
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
    group_id: Optional[int] = Query(None, description="Filter by group ID"),
    student_id: Optional[int] = Query(None, description="Filter by student ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=2000, description="Items per page"),
):
    """
    Get all student attendances with filters.

    This endpoint allows authorized users to view all attendance records
    with various filters including date range, group, and student.

    Filters:
    - from_date: Filter by session date (start)
    - to_date: Filter by session date (end)
    - group_id: Filter by specific group
    - student_id: Filter by specific student
    - page: Page number for pagination
    - page_size: Number of records per page (max 2000)

    Note: This is for viewing marked attendances (coach-created).
    Turnstile/gate attendance is handled separately.
    """
    from sqlalchemy.orm import selectinload

    # Build query for all attendances
    attendance_query = select(Attendance).options(
        selectinload(Attendance.student),
        selectinload(Attendance.session).selectinload(Session.group),
        selectinload(Attendance.marked_by)
    )

    # Apply date filters via session
    if from_date or to_date:
        attendance_query = attendance_query.join(Session)
        if from_date:
            attendance_query = attendance_query.where(Session.session_date >= from_date)
        if to_date:
            attendance_query = attendance_query.where(Session.session_date <= to_date)

    # Apply group filter via session
    if group_id:
        if not (from_date or to_date):  # Only join if not already joined
            attendance_query = attendance_query.join(Session)
        attendance_query = attendance_query.where(Session.group_id == group_id)

    # Apply student filter
    if student_id:
        attendance_query = attendance_query.where(Attendance.student_id == student_id)

    # Order by most recent first
    attendance_query = attendance_query.order_by(Attendance.created_at.desc())

    # Get total count for pagination
    count_query = select(func.count()).select_from(attendance_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    attendance_query = attendance_query.offset(offset).limit(page_size)

    # Execute query
    attendances_result = await db.execute(attendance_query)
    attendances = attendances_result.scalars().all()

    return DataResponse(
        data=[AttendanceRead.model_validate(a) for a in attendances],
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@router.delete("/{student_id}", response_model=DataResponse[dict], dependencies=[Depends(require_permission(PERM_STUDENTS_EDIT))])
async def delete_student(
    student_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Soft delete a student by setting their status to DELETED.
    The student is not actually removed from the database.

    For permanent deletion, use DELETE /students/{student_id}/hard-delete
    """
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Soft delete: set status to DELETED instead of actually deleting
    student.status = StudentStatus.DELETED
    await db.commit()

    return DataResponse(data={"message": "Student deleted successfully"})


@router.delete("/{student_id}/hard-delete", response_model=DataResponse[dict], dependencies=[Depends(require_permission(PERM_STUDENTS_EDIT))])
async def hard_delete_student(
    student_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    **PERMANENT DELETION** - Remove student and all related data from database.

    **WARNING**: This action is irreversible!

    Deletes:
    - Student record
    - All contracts (CASCADE)
    - All transactions (CASCADE)
    - All attendance records (CASCADE)
    - All gate logs (CASCADE)
    - All waiting list entries (CASCADE)

    **Contract numbers are freed** and can be reused after deletion.

    Use this only when:
    - Student record was created by mistake
    - Duplicate entry needs to be removed
    - GDPR/data removal request

    For normal operations, use soft delete (DELETE /students/{student_id})
    """
    from sqlalchemy import delete as sql_delete

    # First get student name for response
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    student_name = f"{student.first_name} {student.last_name}"

    # HARD DELETE using raw SQL to avoid SQLAlchemy relationship loading issues
    # CASCADE will automatically delete:
    # - contracts, transactions, attendance, gate_logs, waiting_list
    await db.execute(sql_delete(Student).where(Student.id == student_id))
    await db.commit()

    return DataResponse(data={
        "message": "Student permanently deleted from database",
        "student_id": student_id,
        "student_name": student_name,
        "warning": "This action is irreversible. All related data has been removed."
    })


@router.post("/bulk-delete", response_model=DataResponse[dict], dependencies=[Depends(require_permission(PERM_STUDENTS_EDIT))])
async def bulk_delete_students(
    student_ids: list[int],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Soft delete multiple students by setting their status to DELETED.
    Students are not actually removed from the database.
    """
    if not student_ids:
        raise HTTPException(status_code=400, detail="No student IDs provided")

    deleted_count = 0
    errors = []

    for student_id in student_ids:
        try:
            result = await db.execute(select(Student).where(Student.id == student_id))
            student = result.scalar_one_or_none()

            if not student:
                errors.append({"student_id": student_id, "error": "Student not found"})
                continue

            # Soft delete: set status to DELETED instead of actually deleting
            student.status = StudentStatus.DELETED
            deleted_count += 1
        except Exception as e:
            errors.append({"student_id": student_id, "error": str(e)})

    await db.commit()

    return DataResponse(data={
        "message": f"Deleted {deleted_count} student(s)",
        "deleted_count": deleted_count,
        "total_requested": len(student_ids),
        "errors": errors if errors else None
    })

