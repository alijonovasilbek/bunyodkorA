from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.db import get_db
from app.core.permissions import PERM_COACH_DOCUMENTS_VIEW
from app.core.private_files import generate_private_file_token
from app.core.s3 import download_s3_object
from app.deps import require_permission
from app.models.attendance import CoachMonthlyDocument, GameDocument
from app.models.enums import CoachDocType
from app.schemas.coach_document import CoachMonthlyDocumentRead
from app.schemas.game import GameDocumentRead
from app.schemas.common import DataResponse, PaginationMeta

router = APIRouter(prefix="/coach-documents", tags=["Coach Documents"])


def _doc_to_read(doc: CoachMonthlyDocument) -> CoachMonthlyDocumentRead:
    return CoachMonthlyDocumentRead(
        id=doc.id,
        coach_id=doc.coach_id,
        group_id=doc.group_id,
        year=doc.year,
        month=doc.month,
        doc_type=doc.doc_type,
        file_url=f"/coach-documents/{doc.id}/file",
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.get(
    "",
    response_model=DataResponse[list[CoachMonthlyDocumentRead]],
    dependencies=[Depends(require_permission(PERM_COACH_DOCUMENTS_VIEW))],
)
async def get_all_coach_documents(
    db: Annotated[AsyncSession, Depends(get_db)],
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    coach_id: Optional[int] = Query(None),
    group_id: Optional[int] = Query(None),
    doc_type: Optional[CoachDocType] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Barcha coachlarning oylik reja va hisobotlari (permission: coach_documents:view)."""
    conditions = []
    if year:
        conditions.append(CoachMonthlyDocument.year == year)
    if month:
        conditions.append(CoachMonthlyDocument.month == month)
    if coach_id:
        conditions.append(CoachMonthlyDocument.coach_id == coach_id)
    if group_id:
        conditions.append(CoachMonthlyDocument.group_id == group_id)
    if doc_type:
        conditions.append(CoachMonthlyDocument.doc_type == doc_type)

    query = select(CoachMonthlyDocument).order_by(
        CoachMonthlyDocument.year.desc(),
        CoachMonthlyDocument.month.desc(),
        CoachMonthlyDocument.created_at.desc(),
    )
    if conditions:
        query = query.where(and_(*conditions))

    count_query = select(func.count(CoachMonthlyDocument.id))
    if conditions:
        count_query = count_query.where(and_(*conditions))

    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * page_size
    docs = (await db.execute(query.offset(offset).limit(page_size))).scalars().all()

    return DataResponse(
        data=[_doc_to_read(d) for d in docs],
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@router.get("/{doc_id}/file", include_in_schema=False)
async def get_coach_document_file(
    doc_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Faylni yuklab olish (token orqali himoyalangan)."""
    result = await db.execute(
        select(CoachMonthlyDocument).where(CoachMonthlyDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        file_bytes, content_type = await download_s3_object(doc.file_key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"File not found: {str(exc)}") from exc

    filename = doc.file_key.rsplit("/", 1)[-1]
    media_type = content_type or "application/octet-stream"
    disposition = "inline" if media_type == "application/pdf" or media_type.startswith("image/") else "attachment"
    return StreamingResponse(
        iter([file_bytes]),
        media_type=media_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


# ─── Game Documents ───────────────────────────────────────────────────────────

@router.get(
    "/games",
    response_model=DataResponse[list[GameDocumentRead]],
    dependencies=[Depends(require_permission(PERM_COACH_DOCUMENTS_VIEW))],
)
async def get_all_game_documents(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Optional[int] = Query(None),
    coach_id: Optional[int] = Query(None),
    doc_type: Optional[CoachDocType] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Barcha o'yinlar uchun plan va hisobotlar (permission: coach_documents:view)."""
    conditions = []
    if game_id:
        conditions.append(GameDocument.game_id == game_id)
    if coach_id:
        conditions.append(GameDocument.coach_id == coach_id)
    if doc_type:
        conditions.append(GameDocument.doc_type == doc_type)

    query = select(GameDocument).order_by(GameDocument.created_at.desc())
    count_query = select(func.count(GameDocument.id))
    if conditions:
        query = query.where(and_(*conditions))
        count_query = count_query.where(and_(*conditions))

    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * page_size
    docs = (await db.execute(query.offset(offset).limit(page_size))).scalars().all()

    return DataResponse(
        data=[GameDocumentRead.model_validate(d) for d in docs],
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@router.get("/games/{doc_id}/file", include_in_schema=False)
async def get_game_document_file(
    doc_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(GameDocument).where(GameDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        file_bytes, content_type = await download_s3_object(doc.file_key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"File not found: {str(exc)}") from exc

    filename = doc.file_key.rsplit("/", 1)[-1]
    media_type = content_type or "application/octet-stream"
    disposition = "inline" if media_type == "application/pdf" or media_type.startswith("image/") else "attachment"
    return StreamingResponse(
        iter([file_bytes]),
        media_type=media_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )
