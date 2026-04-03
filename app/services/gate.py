from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.domain import Student
from app.models.attendance import GateLog
from app.services.debt import check_current_month_payment


async def process_gate_entry(
    db: AsyncSession,
    student_id: int = None,
    face_id: str = None,
) -> tuple[bool, str, int]:
    if student_id:
        result = await db.execute(select(Student).where(Student.id == student_id))
        student = result.scalar_one_or_none()
    elif face_id:
        result = await db.execute(select(Student).where(Student.face_id == face_id))
        student = result.scalar_one_or_none()
    else:
        return False, "No student identifier provided", None

    if not student:
        log = GateLog(
            student_id=None,
            allowed=False,
            reason="Student not found",
            gate_timestamp=datetime.utcnow(),
        )
        db.add(log)
        await db.commit()
        return False, "Student not found", None

    has_paid = await check_current_month_payment(db, student.id)

    if not has_paid:
        log = GateLog(
            student_id=student.id,
            allowed=False,
            reason="No payment for current month",
            gate_timestamp=datetime.utcnow(),
        )
        db.add(log)
        await db.commit()
        return False, "No payment for current month", student.id

    log = GateLog(
        student_id=student.id,
        allowed=True,
        reason="OK",
        gate_timestamp=datetime.utcnow(),
    )
    db.add(log)
    await db.commit()

    return True, "OK", student.id
