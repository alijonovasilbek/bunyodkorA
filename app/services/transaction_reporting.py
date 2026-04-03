from datetime import date
from decimal import Decimal
from dateutil.relativedelta import relativedelta


def build_month_range(from_date: date, to_date: date) -> list[tuple[int, int]]:
    if from_date > to_date:
        return []

    months: list[tuple[int, int]] = []
    current_date = from_date.replace(day=1)
    end_date = to_date.replace(day=1)

    while current_date <= end_date:
        months.append((current_date.year, current_date.month))
        current_date += relativedelta(months=1)
    return months


def normalize_unique_months(payment_months: list | None) -> list[int]:
    normalized: list[int] = []
    for month_value in (payment_months or []):
        try:
            month_num = int(month_value)
        except (TypeError, ValueError):
            continue
        if 1 <= month_num <= 12:
            normalized.append(month_num)
    return sorted(set(normalized))


def allocate_amount_for_period(
    amount: object,
    payment_year: int | None,
    payment_months: list | None,
    month_set: set[tuple[int, int]],
) -> tuple[list[int], Decimal]:
    if payment_year is None:
        return [], Decimal("0")

    unique_months = normalize_unique_months(payment_months)
    if not unique_months:
        return [], Decimal("0")

    matched_months = [
        month_num for month_num in unique_months if (payment_year, month_num) in month_set
    ]
    if not matched_months:
        return [], Decimal("0")

    amount_decimal = Decimal(str(amount))
    per_month_amount = amount_decimal / Decimal(len(unique_months))
    allocated_amount = per_month_amount * Decimal(len(matched_months))
    return matched_months, allocated_amount
