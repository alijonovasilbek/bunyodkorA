from datetime import datetime
from sqlalchemy import String, Numeric, DateTime, Text, Enum as SAEnum, ForeignKey, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base
from app.models.base import TimestampMixin
from app.models.enums import PaymentStatus, PaymentSource, PaymentSettlementType


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    amount: Mapped[int] = mapped_column(Numeric(15, 2), nullable=False)
    source: Mapped[PaymentSource] = mapped_column(
        SAEnum(PaymentSource, native_enum=False, length=20), nullable=False
    )
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, native_enum=False, length=20), default=PaymentStatus.PENDING, nullable=False
    )
    settlement_type: Mapped[PaymentSettlementType] = mapped_column(
        SAEnum(PaymentSettlementType, native_enum=False, length=30),
        default=PaymentSettlementType.PAYMENT,
        nullable=True,
        index=True,
    )

    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    settlement_document_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payment_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_months: Mapped[list | None] = mapped_column(JSON, nullable=True)  # List of months (1-12)


    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id", ondelete="SET NULL"), nullable=True
    )
    contract_id: Mapped[int | None] = mapped_column(
        ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    student: Mapped["Student"] = relationship("Student")
    contract: Mapped["Contract"] = relationship("Contract", back_populates="transactions")
    created_by: Mapped["User"] = relationship("User")
