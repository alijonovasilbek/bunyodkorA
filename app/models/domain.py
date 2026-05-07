from datetime import date, datetime
from sqlalchemy import String, Date, DateTime, Integer, Text, Enum as SAEnum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base
from app.core.private_files import generate_private_file_token
from app.models.base import TimestampMixin
from app.models.enums import StudentStatus, DayOfWeek, GroupStatus


class Student(Base, TimestampMixin):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
    ampula: Mapped[str | None] = mapped_column(String(255), nullable=True)
    millati: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pnfl: Mapped[str] = mapped_column(String(14), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra_file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    passport_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    face_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    status: Mapped[StudentStatus] = mapped_column(
        SAEnum(StudentStatus, native_enum=False, length=20), default=StudentStatus.ACTIVE, nullable=False
    )

    # Archive year - used for yearly data separation (2025, 2026, etc.)
    archive_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True, server_default="2025")

    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)

    group: Mapped["Group"] = relationship("Group", back_populates="students")
    attendances: Mapped[list["Attendance"]] = relationship("Attendance", back_populates="student", cascade="all, delete-orphan")
    gate_logs: Mapped[list["GateLog"]] = relationship("GateLog", back_populates="student", cascade="all, delete-orphan")

    @property
    def extra_file_url(self) -> str | None:
        if not self.extra_file_key:
            return None
        return f"/students/files/{generate_private_file_token(self.extra_file_key)}"

    @property
    def passport_url(self) -> str | None:
        if not self.passport_key:
            return None
        return f"/students/files/{generate_private_file_token(self.passport_key)}"


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
    performance_tables: Mapped[list["GroupPerformanceTable"]] = relationship(
        "GroupPerformanceTable",
        back_populates="group",
        cascade="all, delete-orphan",
    )

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


class PresidentDocument(Base, TimestampMixin):
    __tablename__ = "president_document"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    image_keys: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array of S3 object keys
    document_key: Mapped[str | None] = mapped_column(Text, nullable=True)


class GroupPerformanceTable(Base, TimestampMixin):
    __tablename__ = "group_performance_tables"
    __table_args__ = (
        UniqueConstraint("group_id", "season_year", name="uq_group_performance_table_group_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    season_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    group: Mapped["Group"] = relationship("Group", back_populates="performance_tables")
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_user_id])
    updated_by: Mapped["User"] = relationship("User", foreign_keys=[updated_by_user_id])
    matches: Mapped[list["GroupPerformanceMatch"]] = relationship(
        "GroupPerformanceMatch",
        back_populates="table",
        cascade="all, delete-orphan",
        order_by="GroupPerformanceMatch.position",
    )
    cells: Mapped[list["GroupPerformanceCell"]] = relationship(
        "GroupPerformanceCell",
        back_populates="table",
        cascade="all, delete-orphan",
    )


class GroupPerformanceMatch(Base, TimestampMixin):
    __tablename__ = "group_performance_matches"
    __table_args__ = (
        UniqueConstraint("table_id", "position", name="uq_group_performance_match_table_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("group_performance_tables.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    tour_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    match_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    opponent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    table: Mapped["GroupPerformanceTable"] = relationship("GroupPerformanceTable", back_populates="matches")
    cells: Mapped[list["GroupPerformanceCell"]] = relationship(
        "GroupPerformanceCell",
        back_populates="match",
        cascade="all, delete-orphan",
    )


class GroupPerformanceCell(Base, TimestampMixin):
    __tablename__ = "group_performance_cells"
    __table_args__ = (
        UniqueConstraint("match_id", "student_id", name="uq_group_performance_cell_match_student"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("group_performance_tables.id", ondelete="CASCADE"), nullable=False, index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("group_performance_matches.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)

    table: Mapped["GroupPerformanceTable"] = relationship("GroupPerformanceTable", back_populates="cells")
    match: Mapped["GroupPerformanceMatch"] = relationship("GroupPerformanceMatch", back_populates="cells")
    student: Mapped["Student"] = relationship("Student")
