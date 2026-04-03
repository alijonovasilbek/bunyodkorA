from typing import Annotated, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.core.db import get_db
from app.core.permissions import PERM_GATE_LOGS_VIEW
from app.models.attendance import GateLog
from app.schemas.attendance import GateCallbackRequest, GateCallbackResponse, GateLogRead
from app.schemas.common import DataResponse, PaginationMeta
from app.deps import require_permission
from app.services.gate import process_gate_entry

router = APIRouter(prefix="/gate", tags=["Gate"])


@router.post("/callback", response_model=GateCallbackResponse)
async def gate_callback(
    data: GateCallbackRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    allowed, reason, student_id = await process_gate_entry(
        db,
        student_id=data.student_id,
        face_id=data.face_id,
    )

    return GateCallbackResponse(
        allowed=allowed,
        reason=reason,
        student_id=student_id,
    )


@router.get("/logs", response_model=DataResponse[list[GateLogRead]], dependencies=[Depends(require_permission(PERM_GATE_LOGS_VIEW))])
async def get_gate_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    student_id: Optional[int] = None,
    allowed: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = select(GateLog)
    conditions = []

    if from_date:
        conditions.append(GateLog.gate_timestamp >= from_date)
    if to_date:
        conditions.append(GateLog.gate_timestamp <= to_date)
    if student_id:
        conditions.append(GateLog.student_id == student_id)
    if allowed is not None:
        conditions.append(GateLog.allowed == allowed)

    if conditions:
        query = query.where(and_(*conditions))

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    logs = result.scalars().all()

    count_query = select(func.count(GateLog.id))
    if conditions:
        count_query = count_query.where(and_(*conditions))

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return DataResponse(
        data=[GateLogRead.model_validate(log) for log in logs],
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )
