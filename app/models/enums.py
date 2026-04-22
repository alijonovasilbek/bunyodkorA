from enum import Enum


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class StudentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DELETED = "deleted"
    ARCHIVED = "archived"


class GroupStatus(str, Enum):
    """Group status for yearly archiving"""
    ACTIVE = "active"
    DELETED = "deleted"
    ARCHIVED = "archived"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNASSIGNED = "unassigned"


class PaymentSource(str, Enum):
    PAYME = "payme"
    CLICK = "click"
    BANK = "bank"
    CASH = "cash"
    MANUAL = "manual"


class PaymentSettlementType(str, Enum):
    PAYMENT = "payment"
    WAIVER_SPRAVKA = "waiver_spravka"


class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"


class DayOfWeek(str, Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"
