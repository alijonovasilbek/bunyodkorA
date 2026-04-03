"""
File upload endpoints for documents.

Handles uploading contract documents, student documents, and other files to AWS S3.
"""
from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from app.core.permissions import PERM_CONTRACTS_EDIT
from app.deps import require_permission
from app.services.file_upload import file_upload_service, FileUploadError


router = APIRouter(prefix="/uploads", tags=["Uploads"])


class UploadResponse(BaseModel):
    """Response after successful file upload"""
    url: str
    filename: str
    message: str


class MultipleUploadResponse(BaseModel):
    """Response after successful multiple file uploads"""
    urls: List[str]
    count: int
    message: str

#
# @router.post("/contract-document", response_model=UploadResponse, dependencies=[Depends(require_permission(PERM_CONTRACTS_EDIT))])
# async def upload_contract_document(
#     file: UploadFile = File(..., description="Contract document file (image or PDF)")
# ):
#     """
#     Upload a single contract document to AWS S3.
#
#     Supported file types: images (PNG, JPG, JPEG), PDF
#     File is stored in S3 with path: contracts/YYYY-MM-DD/uuid_timestamp.ext
#
#     Returns the public URL of the uploaded file.
#     """
#     if not file_upload_service:
#         raise HTTPException(
#             status_code=503,
#             detail="File upload service is not configured. Please set AWS credentials in environment variables."
#         )
#
#     # Validate file type
#     allowed_types = ["image/png", "image/jpeg", "image/jpg", "application/pdf"]
#     if file.content_type not in allowed_types:
#         raise HTTPException(
#             status_code=400,
#             detail=f"Invalid file type. Allowed types: PNG, JPG, JPEG, PDF. Got: {file.content_type}"
#         )
#
#     # Validate file size (max 10MB)
#     max_size = 10 * 1024 * 1024  # 10MB
#     file.file.seek(0, 2)  # Seek to end
#     file_size = file.file.tell()
#     file.file.seek(0)  # Reset to beginning
#
#     if file_size > max_size:
#         raise HTTPException(
#             status_code=400,
#             detail=f"File too large. Maximum size: 10MB. Got: {file_size / 1024 / 1024:.2f}MB"
#         )
#
#     try:
#         url = await file_upload_service.upload_file(file, prefix="contracts")
#
#         return UploadResponse(
#             url=url,
#             filename=file.filename,
#             message="File uploaded successfully"
#         )
#
#     except FileUploadError as e:
#         raise HTTPException(status_code=500, detail=str(e))
#
#
# @router.post("/contract-documents", response_model=MultipleUploadResponse, dependencies=[Depends(require_permission(PERM_CONTRACTS_EDIT))])
# async def upload_contract_documents(
#     files: List[UploadFile] = File(..., description="Multiple contract document files")
# ):
#     """
#     Upload multiple contract documents to AWS S3.
#
#     Useful for uploading all 5 contract pages at once.
#     Each file is validated and uploaded to S3.
#
#     Returns list of public URLs in the same order as uploaded files.
#     """
#     if not file_upload_service:
#         raise HTTPException(
#             status_code=503,
#             detail="File upload service is not configured. Please set AWS credentials in environment variables."
#         )
#
#     if len(files) > 10:
#         raise HTTPException(
#             status_code=400,
#             detail=f"Too many files. Maximum 10 files per upload. Got: {len(files)}"
#         )
#
#     # Validate all files first
#     allowed_types = ["image/png", "image/jpeg", "image/jpg", "application/pdf"]
#     max_size = 10 * 1024 * 1024  # 10MB
#
#     for file in files:
#         if file.content_type not in allowed_types:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Invalid file type for {file.filename}. Allowed types: PNG, JPG, JPEG, PDF"
#             )
#
#         file.file.seek(0, 2)
#         file_size = file.file.tell()
#         file.file.seek(0)
#
#         if file_size > max_size:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"File {file.filename} too large. Maximum size: 10MB"
#             )
#
#     try:
#         urls = await file_upload_service.upload_multiple_files(files, prefix="contracts")
#
#         return MultipleUploadResponse(
#             urls=urls,
#             count=len(urls),
#             message=f"Successfully uploaded {len(urls)} file(s)"
#         )
#
#     except FileUploadError as e:
#         raise HTTPException(status_code=500, detail=str(e))
#
#
# @router.post("/student-document", response_model=UploadResponse, dependencies=[Depends(require_permission(PERM_CONTRACTS_EDIT))])
# async def upload_student_document(
#     file: UploadFile = File(..., description="Student document (passport, birth certificate, medical form, etc.)")
# ):
#     """
#     Upload a single student document to AWS S3.
#
#     Used for:
#     - Passport copy
#     - Birth certificate
#     - Medical form (086)
#     - Heart checkup
#     - Other student documents
#
#     Returns the public URL of the uploaded file.
#     """
#     if not file_upload_service:
#         raise HTTPException(
#             status_code=503,
#             detail="File upload service is not configured. Please set AWS credentials in environment variables."
#         )
#
#     # Validate file type
#     allowed_types = ["image/png", "image/jpeg", "image/jpg", "application/pdf"]
#     if file.content_type not in allowed_types:
#         raise HTTPException(
#             status_code=400,
#             detail=f"Invalid file type. Allowed types: PNG, JPG, JPEG, PDF"
#         )
#
#     # Validate file size (max 10MB)
#     max_size = 10 * 1024 * 1024
#     file.file.seek(0, 2)
#     file_size = file.file.tell()
#     file.file.seek(0)
#
#     if file_size > max_size:
#         raise HTTPException(
#             status_code=400,
#             detail=f"File too large. Maximum size: 10MB"
#         )
#
#     try:
#         url = await file_upload_service.upload_file(file, prefix="students")
#
#         return UploadResponse(
#             url=url,
#             filename=file.filename,
#             message="File uploaded successfully"
#         )
#
#     except FileUploadError as e:
#         raise HTTPException(status_code=500, detail=str(e))
#
#
# @router.post("/student-documents", response_model=MultipleUploadResponse, dependencies=[Depends(require_permission(PERM_CONTRACTS_EDIT))])
# async def upload_student_documents(
#     files: List[UploadFile] = File(..., description="Multiple student documents")
# ):
#     """
#     Upload multiple student documents to AWS S3.
#
#     Useful for uploading all required student documents at once:
#     - Passport copy
#     - Birth certificate
#     - Medical form (086)
#     - Heart checkup
#
#     Returns list of public URLs in the same order as uploaded files.
#     """
#     if not file_upload_service:
#         raise HTTPException(
#             status_code=503,
#             detail="File upload service is not configured. Please set AWS credentials in environment variables."
#         )
#
#     if len(files) > 10:
#         raise HTTPException(
#             status_code=400,
#             detail=f"Too many files. Maximum 10 files per upload"
#         )
#
#     # Validate all files
#     allowed_types = ["image/png", "image/jpeg", "image/jpg", "application/pdf"]
#     max_size = 10 * 1024 * 1024
#
#     for file in files:
#         if file.content_type not in allowed_types:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Invalid file type for {file.filename}"
#             )
#
#         file.file.seek(0, 2)
#         file_size = file.file.tell()
#         file.file.seek(0)
#
#         if file_size > max_size:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"File {file.filename} too large. Maximum size: 10MB"
#             )
#
#     try:
#         urls = await file_upload_service.upload_multiple_files(files, prefix="students")
#
#         return MultipleUploadResponse(
#             urls=urls,
#             count=len(urls),
#             message=f"Successfully uploaded {len(urls)} file(s)"
#         )
#
#     except FileUploadError as e:
#         raise HTTPException(status_code=500, detail=str(e))
