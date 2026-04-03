"""
Schemas for creating student with contract and documents in one operation.
"""
from datetime import date
from typing import Optional, List
from pydantic import BaseModel, Field
from app.models.enums import StudentStatus
from app.schemas.contract import ContractCustomFields


class StudentWithContractCreate(BaseModel):
    """
    Create student with contract and all documents in one operation.

    Workflow:
    1. Upload all 9 documents first (using /uploads endpoints)
    2. Submit this request with all data
    3. System creates student, checks group capacity, creates contract
    4. Returns student ID, contract ID, and signature link
    """
    # Student basic info
    full_name: str = Field(min_length=1, max_length=255)
    date_of_birth: date
    gender: str = Field(pattern="^(male|female)$")
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = None
    status: StudentStatus = StudentStatus.ACTIVE

    # Parent info
    parent_name: Optional[str] = Field(default=None, max_length=255)
    parent_phone: Optional[str] = Field(default=None, max_length=20)

    # Group selection
    group_id: int

    # All 9 document URLs (already uploaded to S3)
    passport_copy_url: str = Field(description="URL of passport copy")
    form_086_url: str = Field(description="URL of medical form 086")
    heart_checkup_url: str = Field(description="URL of heart checkup")
    birth_certificate_url: str = Field(description="URL of birth certificate")
    contract_images_urls: List[str] = Field(description="List of 5 contract page URLs")

    # All handwritten fields from contract documents
    custom_fields: ContractCustomFields = Field(
        description="All handwritten data from contract documents"
    )


class StudentWithContractResponse(BaseModel):
    """Response after creating student with contract"""
    student_id: int
    student_full_name: str
    contract_id: int
    contract_number: str
    birth_year: int
    sequence_number: int
    group_id: int
    group_name: str
    signature_token: str
    signature_link: str
    contract_status: str
    message: str
