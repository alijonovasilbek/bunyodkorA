from datetime import date, datetime
from sqlalchemy import String, Date, DateTime, Integer, Numeric, Text, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base
from app.models.base import TimestampMixin
from app.models.enums import StudentStatus, ContractStatus, DayOfWeek, GroupStatus


class Student(Base, TimestampMixin):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    face_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    status: Mapped[StudentStatus] = mapped_column(
        SAEnum(StudentStatus, native_enum=False, length=20), default=StudentStatus.ACTIVE, nullable=False
    )

    # Archive year - used for yearly data separation (2025, 2026, etc.)
    archive_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True, server_default="2025")

    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)

    group: Mapped["Group"] = relationship("Group", back_populates="students")
    parents: Mapped[list["Parent"]] = relationship("Parent", back_populates="student", cascade="all, delete-orphan")
    contracts: Mapped[list["Contract"]] = relationship("Contract", back_populates="student", cascade="all, delete-orphan")
    attendances: Mapped[list["Attendance"]] = relationship("Attendance", back_populates="student", cascade="all, delete-orphan")
    gate_logs: Mapped[list["GateLog"]] = relationship("GateLog", back_populates="student", cascade="all, delete-orphan")


class Parent(Base, TimestampMixin):
    __tablename__ = "parents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    relationship_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)

    student: Mapped["Student"] = relationship("Student", back_populates="parents")


class Group(Base, TimestampMixin):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Unique constraint handled by partial index in database (unique only for non-DELETED groups)
    identifier: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule_days: Mapped[str | None] = mapped_column(String(255), nullable=True)
    schedule_time: Mapped[str | None] = mapped_column(String(50), nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    status: Mapped[GroupStatus] = mapped_column(
        SAEnum(GroupStatus, native_enum=False, length=20), default=GroupStatus.ACTIVE, nullable=False, index=True
    )

    # Birth year - which year students this group is for (e.g., 2015, 2017, 2020)
    birth_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Archive year - used for yearly data separation (2025, 2026, etc.)
    archive_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True, server_default="2025")

    coach_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    coach: Mapped["User"] = relationship("User")
    students: Mapped[list["Student"]] = relationship("Student", back_populates="group")
    sessions: Mapped[list["Session"]] = relationship("Session", back_populates="group")
    waiting_list: Mapped[list["WaitingList"]] = relationship("WaitingList", back_populates="group")


class Contract(Base, TimestampMixin):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    contract_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    monthly_fee: Mapped[int] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[ContractStatus] = mapped_column(
        SAEnum(ContractStatus, native_enum=False, length=20), default=ContractStatus.ACTIVE, nullable=False
    )

    # Archive year - used for yearly data separation (2025, 2026, etc.)
    archive_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True, server_default="2025")

    # Contract number allocation fields
    birth_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # Student birth year for contract numbering
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)  # Sequence within birth year (1-capacity)

    # Document file paths (JSON array stored as text)
    passport_copy_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    form_086_url: Mapped[str | None] = mapped_column(Text, nullable=True)  # Medical certificate
    heart_checkup_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    birth_certificate_url: Mapped[str | None] = mapped_column(Text, nullable=True)  # Passport or birth certificate
    contract_images_urls: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of 5 contract page URLs
    final_pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)  # Merged PDF with all documents

    # Editable fields (from handwritten parts)
    custom_fields: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON object for custom fields

    # Termination fields
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    termination_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)

    student: Mapped["Student"] = relationship("Student", back_populates="contracts")
    group: Mapped["Group"] = relationship("Group")
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="contract")
    terminated_by: Mapped["User"] = relationship("User", foreign_keys=[terminated_by_user_id])


class WaitingList(Base, TimestampMixin):
    """
    Waiting list for prospective students when a group is full.

    Stores student information directly without linking to students table.
    When a spot opens in the group, admin can contact parents and register the student.
    """
    __tablename__ = "waiting_list"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Student information (stored directly, not linked to students table)
    student_first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    student_last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    birth_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Parent information
    father_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    father_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mother_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mother_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Group assignment
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)

    # Priority and notes
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Higher priority = earlier in queue
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships (no student relationship - independent data)
    group: Mapped["Group"] = relationship("Group", back_populates="waiting_list")
    added_by: Mapped["User"] = relationship("User")
