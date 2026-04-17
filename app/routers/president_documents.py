import json
import mimetypes
import os
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.permissions import (
    PERM_PRESIDENT_DOCUMENTS_CREATE,
    PERM_PRESIDENT_DOCUMENTS_DELETE,
    PERM_PRESIDENT_DOCUMENTS_EDIT,
    PERM_PRESIDENT_DOCUMENTS_VIEW,
)
from app.core.private_files import generate_private_file_token, verify_private_file_token
from app.core.s3 import download_s3_object, extract_key_from_url, upload_image_to_s3, upload_private_document_to_s3
from app.deps import require_permission
from app.models.domain import PresidentDocument
from app.schemas.common import DataResponse, PaginationMeta
from app.schemas.president_document import PresidentDocumentRead


router = APIRouter(prefix="/president-documents", tags=["President Documents"])


def _build_private_file_url(key: str | None) -> str | None:
    if not key:
        return None
    return f"/president-documents/files/{generate_private_file_token(key)}"


def _serialize_president_document(document: PresidentDocument) -> PresidentDocumentRead:
    image_keys = json.loads(document.image_keys or "[]")
    return PresidentDocumentRead(
        id=document.id,
        name=document.name,
        description=document.description,
        image_urls=[_build_private_file_url(key) for key in image_keys],
        document_url=_build_private_file_url(document.document_key),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.get("", response_model=DataResponse[list[PresidentDocumentRead]], dependencies=[Depends(require_permission(PERM_PRESIDENT_DOCUMENTS_VIEW))])
async def list_president_documents(
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = Query(None, description="Search by name or description"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    query = select(PresidentDocument)
    count_query = select(func.count(PresidentDocument.id))

    if search:
        search_filter = or_(
            PresidentDocument.name.ilike(f"%{search}%"),
            PresidentDocument.description.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    query = query.order_by(PresidentDocument.created_at.desc())
    offset = (page - 1) * page_size

    result = await db.execute(query.offset(offset).limit(page_size))
    rows = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return DataResponse(
        data=[_serialize_president_document(row) for row in rows],
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@router.post("", response_model=DataResponse[PresidentDocumentRead], dependencies=[Depends(require_permission(PERM_PRESIDENT_DOCUMENTS_CREATE))])
async def create_president_document(
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str = Form(..., description="Document name"),
    description: str = Form(..., description="Document description"),
    images: list[UploadFile] = File(..., description="1 to 10 images"),
    document: UploadFile | None = File(None, description="Optional PDF/DOC/DOCX document"),
):
    name = name.strip()
    description = description.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not description:
        raise HTTPException(status_code=400, detail="description is required")
    if not images:
        raise HTTPException(status_code=400, detail="At least 1 image is required")
    if len(images) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 images allowed")

    image_keys: list[str] = []
    try:
        for image in images:
            image_url = await upload_image_to_s3(image, folder="president_pictures")
            image_keys.append(extract_key_from_url(image_url))

        document_key = None
        if document is not None:
            document_key = await upload_private_document_to_s3(document, folder="president_documents")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to upload files: {str(exc)}") from exc

    record = PresidentDocument(
        name=name,
        description=description,
        image_keys=json.dumps(image_keys),
        document_key=document_key,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return DataResponse(data=_serialize_president_document(record))


@router.get("/{document_id}", response_model=DataResponse[PresidentDocumentRead], dependencies=[Depends(require_permission(PERM_PRESIDENT_DOCUMENTS_VIEW))])
async def get_president_document(
    document_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(PresidentDocument).where(PresidentDocument.id == document_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="President document not found")
    return DataResponse(data=_serialize_president_document(record))


@router.patch("/{document_id}", response_model=DataResponse[PresidentDocumentRead], dependencies=[Depends(require_permission(PERM_PRESIDENT_DOCUMENTS_EDIT))])
async def update_president_document(
    document_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str | None = Form(None),
    description: str | None = Form(None),
    images: list[UploadFile] | None = File(None, description="If sent, replaces existing image set"),
    document: UploadFile | None = File(None, description="If sent, replaces existing document"),
):
    result = await db.execute(select(PresidentDocument).where(PresidentDocument.id == document_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="President document not found")

    if name is not None:
        stripped_name = name.strip()
        if not stripped_name:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        record.name = stripped_name

    if description is not None:
        stripped_description = description.strip()
        if not stripped_description:
            raise HTTPException(status_code=400, detail="description cannot be empty")
        record.description = stripped_description

    if images is not None:
        if not images:
            raise HTTPException(status_code=400, detail="At least 1 image is required when replacing images")
        if len(images) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 images allowed")
        try:
            image_keys: list[str] = []
            for image in images:
                image_url = await upload_image_to_s3(image, folder="president_pictures")
                image_keys.append(extract_key_from_url(image_url))
            record.image_keys = json.dumps(image_keys)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to upload images: {str(exc)}") from exc

    if document is not None:
        try:
            record.document_key = await upload_private_document_to_s3(document, folder="president_documents")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to upload document: {str(exc)}") from exc

    await db.commit()
    await db.refresh(record)
    return DataResponse(data=_serialize_president_document(record))


@router.delete("/{document_id}", response_model=DataResponse[dict], dependencies=[Depends(require_permission(PERM_PRESIDENT_DOCUMENTS_DELETE))])
async def delete_president_document(
    document_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(PresidentDocument).where(PresidentDocument.id == document_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="President document not found")

    await db.delete(record)
    await db.commit()
    return DataResponse(data={"message": "President document deleted successfully"})


@router.get("/files/{token}", include_in_schema=False)
async def get_president_document_file(token: str):
    payload = verify_private_file_token(token)
    key = payload["key"]

    try:
        file_bytes, content_type = await download_s3_object(key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"File not found: {str(exc)}") from exc

    filename = os.path.basename(key)
    if not content_type:
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    disposition_type = "inline" if content_type.startswith("image/") or content_type == "application/pdf" else "attachment"
    headers = {"Content-Disposition": f'{disposition_type}; filename="{filename}"'}

    return StreamingResponse(iter([file_bytes]), media_type=content_type, headers=headers)
