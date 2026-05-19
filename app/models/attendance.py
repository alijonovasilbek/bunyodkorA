from datetime import datetime, date
from sqlalchemy import String, DateTime, Date, Time, Boolean, Text, Integer, Enum as SAEnum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base
from app.models.base import TimestampMixin
from app.models.enums import AttendanceStatus, CoachDocType
from app.core.private_files import generate_private_file_token


class Session(Base, TimestampMixin):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    topic: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_time: Mapped[str | None] = mapped_column(String(10), nullable=True)
    end_time: Mapped[str | None] = mapped_column(String(10), nullable=True)
    station: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    konspekt_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    group: Mapped["Group"] = relationship("Group", back_populates="sessions")
    created_by: Mapped["User"] = relationship("User")
    attendances: Mapped[list["Attendance"]] = relationship("Attendance", back_populates="session", cascade="all, delete-orphan")


class Attendance(Base, TimestampMixin):
    __tablename__ = "attendances"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    status: Mapped[AttendanceStatus] = mapped_column(
        SAEnum(AttendanceStatus, native_enum=False, length=20), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    marked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    session: Mapped["Session"] = relationship("Session", back_populates="attendances")
    student: Mapped["Student"] = relationship("Student", back_populates="attendances")
    marked_by: Mapped["User"] = relationship("User")


class GateLog(Base, TimestampMixin):
    __tablename__ = "gate_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gate_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id", ondelete="SET NULL"), nullable=True
    )

    student: Mapped["Student"] = relationship("Student", back_populates="gate_logs")


class CoachMonthlyDocument(Base, TimestampMixin):
    __tablename__ = "coach_monthly_documents"
    __table_args__ = (
        UniqueConstraint("coach_id", "group_id", "year", "month", "doc_type", name="uq_coach_monthly_doc"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    doc_type: Mapped[CoachDocType] = mapped_column(
        SAEnum(CoachDocType, native_enum=False, length=20), nullable=False
    )
    file_key: Mapped[str] = mapped_column(String(500), nullable=False)

    coach: Mapped["User"] = relationship("User", foreign_keys=[coach_id])
    group: Mapped["Group"] = relationship("Group")


class GameDocument(Base, TimestampMixin):
    __tablename__ = "game_documents"
    __table_args__ = (
        UniqueConstraint("game_id", "coach_id", "doc_type", name="uq_game_document"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("group_games.id", ondelete="CASCADE"), nullable=False, index=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_type: Mapped[CoachDocType] = mapped_column(
        SAEnum(CoachDocType, native_enum=False, length=20), nullable=False
    )
    file_key: Mapped[str] = mapped_column(String(500), nullable=False)

    game: Mapped["GroupGame"] = relationship("GroupGame", back_populates="documents")
    coach: Mapped["User"] = relationship("User", foreign_keys=[coach_id])

    @property
    def file_url(self) -> str:
        return f"/coach-documents/games/{self.id}/file"
