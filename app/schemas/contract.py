from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from app.models.enums import ContractStatus


class TerminatedByUser(BaseModel):
    """User who terminated the contract"""
    id: int
    full_name: str

    class Config:
        from_attributes = True


# Custom fields schemas for handwritten data
class StudentInfo(BaseModel):
    """Student information from application form (Image 1)"""
    birth_year: int
    first_name: str
    last_name: str
    patronymic: Optional[str] = None
    address: str = Field(description="Full address: region, city, district, street, house, apartment")
    phone: str

class ContractCreateBody(BaseModel):
    student_id: int
    group_id: int
    contract_number: str
    custom_fields: dict  # or ContractCustomFields if you already have the Pydantic model

class ParentInfo(BaseModel):
    """Parent/Guardian information from application form (Image 1)"""
    full_name: str = Field(description="Parent full name (father or mother)")
    occupation: str = Field(description="Parent's occupation")
    phone: str


class PassportInfo(BaseModel):
    """Passport/Document information"""
    series_number: str = Field(description="Passport series and number (e.g., АЕ 2220863)")
    issued_by: str = Field(description="By whom it was issued")
    issue_date: date = Field(description="Date of issue")


class BirthCertificateInfo(BaseModel):
    """Student birth certificate information"""
    full_name: str = Field(description="Student full name on certificate")
    series: str = Field(description="Certificate series")
    issued_by: str = Field(description="By whom it was issued")
    issue_date: date = Field(description="Date of issue")


class ContractTermsInfo(BaseModel):
    """Contract terms from contract pages (Image 3)"""
    contract_start_date: date = Field(description="Contract validity start date")
    contract_end_date: date = Field(description="Contract validity end date")
    monthly_fee: float = Field(description="Monthly subscription fee amount")


class CustomerInfo(BaseModel):
    """Customer information from signature page (Image 4)"""
    full_name: str
    passport_number: str
    passport_issued_by: str
    passport_issue_date: date
    address: str
    phone: str


class ContractCustomFields(BaseModel):
    """All custom fields from handwritten parts of contract"""
    # From Image 1 - Application
    contract_creation_date: date
    customer: CustomerInfo
    student: StudentInfo
    father: Optional[ParentInfo] = None
    mother: Optional[ParentInfo] = None

    # From Image 2 - Contract pages
    parent_passport: PassportInfo
    student_birth_certificate: BirthCertificateInfo

    # From Image 3 - Contract terms
    contract_terms: ContractTermsInfo





class ContractRead(BaseModel):
    id: int
    contract_number: str
    start_date: date
    end_date: date
    monthly_fee: float
    status: ContractStatus
    student_id: int
    group_id: Optional[int] = None

    # Contract number allocation
    birth_year: int
    sequence_number: int

    # Document URLs
    passport_copy_url: Optional[str] = None
    form_086_url: Optional[str] = None
    heart_checkup_url: Optional[str] = None
    birth_certificate_url: Optional[str] = None
    contract_images_urls: Optional[str] = None  # JSON string
    final_pdf_url: Optional[str] = None

    # Custom fields
    custom_fields: Optional[str] = None  # JSON string

    # Termination
    terminated_at: Optional[datetime] = None
    terminated_by_user_id: Optional[int] = None
    termination_reason: Optional[str] = None
    terminated_by: Optional[TerminatedByUser] = None

    created_at: datetime

    class Config:
        from_attributes = True


class ContractCreateWithDocuments(BaseModel):
    """Create contract with all documents and handwritten data"""
    student_id: int
    group_id: int
    contract_number: str
    custom_fields: ContractCustomFields = Field(
        description="All handwritten data from contract documents"
    )

    # Document URLs (must be uploaded first)
    passport_copy_url: str = Field(description="URL of passport copy document")
    form_086_url: str = Field(description="URL of medical form 086")
    heart_checkup_url: str = Field(description="URL of heart checkup document")
    birth_certificate_url: str = Field(description="URL of birth certificate or passport")
    contract_images_urls: List[str] = Field(description="List of 5 contract page image URLs")

    # All handwritten fields captured by admin


class ContractUpdate(BaseModel):
    """Update contract fields"""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    monthly_fee: Optional[float] = None
    status: Optional[ContractStatus] = None
    custom_fields: Optional[ContractCustomFields] = None


class ContractTerminate(BaseModel):
    termination_reason: str
    terminated_at: Optional[datetime] = None


class MonthlyFeeUpdate(BaseModel):
    """Update contract monthly fee"""
    monthly_fee: float = Field(gt=0, description="New monthly fee amount (must be greater than 0)")


class ContractDatesUpdate(BaseModel):
    """Update contract start/end dates"""
    start_date: Optional[date] = Field(None, description="New contract start date")
    end_date: Optional[date] = Field(None, description="New contract end date")


class ContractNumberInfo(BaseModel):
    """Information about available contract numbers"""
    group_id: int
    group_name: str
    group_capacity: int
    birth_year: int
    available_numbers: List[int]
    total_available: int
    total_used: int
    is_full: bool


class NextAvailableNumber(BaseModel):
    """Next available contract number"""
    next_available: Optional[int]
    contract_number: Optional[str]
    birth_year: int
    is_full: bool


# class ContractCreatedResponse(BaseModel):
#     """Response after creating a contract with documents"""
#     contract_id: int
#     contract_number: str
#     birth_year: int
#     sequence_number: int
#     signature_token: str
#     signature_link: str
#     message: str
#     status: str  # "pending_signature" or "active"
class ContractCreatedResponse(BaseModel):
    contract_id: int
    contract_number: str
    birth_year: int
    sequence_number: int
    message: str
    pdf_url: str


class ContractReadWithStudentName(BaseModel):
    """Contract with student full name instead of student_id"""
    id: int
    contract_number: str
    start_date: date
    end_date: date
    monthly_fee: float
    status: ContractStatus
    student_full_name: str  # Instead of student_id
    group_id: Optional[int] = None

    # Contract number allocation
    birth_year: int
    sequence_number: int

    # Document URLs
    passport_copy_url: Optional[str] = None
    form_086_url: Optional[str] = None
    heart_checkup_url: Optional[str] = None
    birth_certificate_url: Optional[str] = None
    contract_images_urls: Optional[str] = None  # JSON string
    final_pdf_url: Optional[str] = None

    # Custom fields
    custom_fields: Optional[str] = None  # JSON string

    # Termination
    terminated_at: Optional[datetime] = None
    terminated_by_user_id: Optional[int] = None
    termination_reason: Optional[str] = None
    terminated_by: Optional[TerminatedByUser] = None

    created_at: datetime

    class Config:
        from_attributes = True


class TerminatedStudentRead(BaseModel):
    contract_id: int
    contract_number: str
    original_contract_number: Optional[str] = None
    start_date: date
    end_date: date
    monthly_fee: float
    contract_status: ContractStatus

    student_id: int
    student_first_name: str
    student_last_name: str
    student_height: int
    student_weight: int
    student_pnfl: str
    student_phone: Optional[str] = None
    student_group_id: Optional[int] = None
    student_group_name: Optional[str] = None
    student_group_identifier: Optional[str] = None

    terminated_at: Optional[datetime] = None
    termination_reason: Optional[str] = None
    terminated_by_user_id: Optional[int] = None
    terminated_by_full_name: Optional[str] = None
