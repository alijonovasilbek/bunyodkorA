from datetime import datetime
from pydantic import BaseModel, Field


class SignatureSubmit(BaseModel):
    """Submit a digital signature"""
    signature_data: str = Field(description="Base64 encoded signature image data")


class SignatureVerify(BaseModel):
    """Verify signature token and get contract info"""
    contract_id: int
    contract_number: str
    student_name: str
    group_name: str
    start_date: str
    end_date: str
    monthly_fee: float
    is_valid: bool
    is_already_signed: bool
    message: str


class SignatureComplete(BaseModel):
    """Response after successful signature"""
    contract_id: int
    contract_number: str
    status: str  # "active"
    signed_at: datetime
    final_pdf_url: str
    message: str
