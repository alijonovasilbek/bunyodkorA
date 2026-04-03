"""
Contract number allocation service.

Handles contract number generation based on student birth year, group identifier and capacity.
Format: {sequence}-{year}{identifier}
Examples: 1-2020B1, 2-2020B1, 3-2020B1 for group B1, students born in 2020
          1-2019C2, 2-2019C2, 3-2019C2 for group C2, students born in 2019

IMPORTANT:
- ACTIVE/EXPIRED/ARCHIVED/DELETED contracts keep their sequence reserved.
- TERMINATED contracts free their sequence for reuse.
"""
from datetime import date
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.domain import Contract, Group, Student
from app.models.enums import ContractStatus
from typing import Optional, List


class ContractNumberAllocationError(Exception):
    """Raised when contract number allocation fails"""
    pass


async def get_available_contract_numbers(
    db: AsyncSession,
    group_id: int,
    birth_year: int,
    archive_year: Optional[int] = None
) -> List[int]:
    """
    Get list of available contract numbers for a group and birth year.

    Returns list of available sequence numbers (1 to group capacity).
    Empty slots (from canceled contracts) are included.

    Args:
        db: Database session
        group_id: Group ID
        birth_year: Student's birth year
        archive_year: Archive year filter (defaults to current year)

    Returns:
        List of available sequence numbers
    """
    from datetime import datetime
    if archive_year is None:
        archive_year = datetime.now().year

    # Get group capacity
    group_result = await db.execute(select(Group).where(Group.id == group_id))
    group = group_result.scalar_one_or_none()

    if not group:
        raise ContractNumberAllocationError(f"Group with ID {group_id} not found")

    # Get sequence numbers currently reserved for this birth year in this group.
    # TERMINATED contracts are intentionally excluded so their numbers can be reused.
    contracts_result = await db.execute(
        select(Contract.sequence_number).where(
            and_(
                Contract.group_id == group_id,
                Contract.birth_year == birth_year,
                Contract.archive_year == archive_year,
                Contract.status.in_([
                    ContractStatus.ACTIVE,
                    ContractStatus.EXPIRED,
                    ContractStatus.ARCHIVED,
                    ContractStatus.DELETED,
                ])
            )
        )
    )
    used_sequences = set(row[0] for row in contracts_result.fetchall())

    # Find available sequences (1 to capacity)
    all_sequences = set(range(1, group.capacity + 1))
    available_sequences = sorted(all_sequences - used_sequences)

    return available_sequences


async def allocate_contract_number(
    db: AsyncSession,
    student_id: int,
    group_id: int
) -> tuple[str, int, int]:
    """
    Allocate a contract number for a student in a group.

    Returns the contract number string, birth year, and sequence number.

    Args:
        db: Database session
        student_id: Student ID
        group_id: Group ID

    Returns:
        Tuple of (contract_number, birth_year, sequence_number)
        Example: ("1-2020B1", 2020, 1) for group B1

    Raises:
        ContractNumberAllocationError: If allocation fails
    """
    # Get student to determine birth year
    student_result = await db.execute(select(Student).where(Student.id == student_id))
    student = student_result.scalar_one_or_none()

    if not student:
        raise ContractNumberAllocationError(f"Student with ID {student_id} not found")

    birth_year = student.date_of_birth.year

    # Get group to get identifier
    group_result = await db.execute(select(Group).where(Group.id == group_id))
    group = group_result.scalar_one_or_none()

    if not group:
        raise ContractNumberAllocationError(f"Group with ID {group_id} not found")

    # Get available numbers
    available_numbers = await get_available_contract_numbers(db, group_id, birth_year)

    if not available_numbers:
        raise ContractNumberAllocationError(
            f"No available contract numbers for group {group_id} and birth year {birth_year}. "
            f"Group may be at full capacity for this birth year."
        )

    # Use the first available number
    sequence_number = available_numbers[0]
    contract_number = f"{sequence_number}-{birth_year}{group.identifier}"

    return contract_number, birth_year, sequence_number


async def is_group_full(
    db: AsyncSession,
    group_id: int,
    birth_year: Optional[int] = None,
    archive_year: Optional[int] = None
) -> bool:
    """
    Check if a group is full.

    Args:
        db: Database session
        group_id: Group ID
        birth_year: Optional birth year to check capacity for specific year
        archive_year: Archive year filter (defaults to current year)

    Returns:
        True if group is full, False otherwise
    """
    from datetime import datetime
    if archive_year is None:
        archive_year = datetime.now().year

    # Get group capacity
    group_result = await db.execute(select(Group).where(Group.id == group_id))
    group = group_result.scalar_one_or_none()

    if not group:
        return True  # Treat non-existent group as full

    if birth_year:
        # Check capacity for specific birth year
        available = await get_available_contract_numbers(db, group_id, birth_year, archive_year)
        return len(available) == 0
    else:
        # Check overall capacity across all birth years for the archive year
        # IMPORTANT: Only ACTIVE contracts count toward capacity limit
        contracts_result = await db.execute(
            select(Contract).where(
                and_(
                    Contract.group_id == group_id,
                    Contract.archive_year == archive_year,
                    Contract.status == ContractStatus.ACTIVE  # Only ACTIVE!
                )
            )
        )
        active_contracts = contracts_result.scalars().all()

        return len(active_contracts) >= group.capacity


async def get_next_available_sequence(
    db: AsyncSession,
    group_id: int,
    birth_year: int
) -> Optional[int]:
    """
    Get the next available sequence number for a birth year in a group.

    Returns None if no sequences are available.
    """
    available = await get_available_contract_numbers(db, group_id, birth_year)
    return available[0] if available else None


async def validate_contract_number(
    db: AsyncSession,
    contract_number: str,
    group_id: int,
    birth_year: int,
    archive_year: Optional[int] = None
) -> tuple[bool, str, Optional[int]]:
    """
    Validate if a contract number is available for use.

    Args:
        db: Database session
        contract_number: Contract number to validate (e.g., "1-2020B1")
        group_id: Group ID
        birth_year: Student's birth year
        archive_year: Archive year filter (defaults to current year)

    Returns:
        Tuple of (is_valid, message, sequence_number)
        - is_valid: True if number is available
        - message: Error/success message
        - sequence_number: Extracted sequence number if valid
    """
    import re
    from datetime import datetime
    if archive_year is None:
        archive_year = datetime.now().year

    # Get group to verify identifier
    group_result = await db.execute(select(Group).where(Group.id == group_id))
    group = group_result.scalar_one_or_none()

    if not group:
        return False, f"Group {group_id} not found", None

    # Parse contract number (format: {seq}-{year}{identifier})
    try:
        if '-' not in contract_number:
            return False, "Contract number must contain '-' separator", None

        # Split by hyphen
        parts = contract_number.split('-', 1)
        if len(parts) != 2:
            return False, f"Invalid contract number format: {contract_number}. Expected format: {{seq}}-{{year}}{{identifier}}", None

        # First part should be sequence number
        try:
            sequence_number = int(parts[0])
        except ValueError:
            return False, f"Invalid sequence number: {parts[0]}. Must be a number.", None

        # Second part should be year + identifier
        year_and_identifier = parts[1]

        # Extract year (first 4 digits)
        match = re.match(r'^(\d{4})(.+)$', year_and_identifier)
        if not match:
            return False, f"Invalid format in '{year_and_identifier}'. Expected 4-digit year followed by identifier.", None

        extracted_year = int(match.group(1))
        extracted_identifier = match.group(2)

        # Verify year matches birth year
        if extracted_year != birth_year:
            return False, f"Contract year '{extracted_year}' doesn't match birth year {birth_year}", None

        # Verify identifier matches group
        if extracted_identifier != group.identifier:
            return False, f"Contract identifier '{extracted_identifier}' doesn't match group identifier '{group.identifier}'", None

    except Exception as e:
        return False, f"Invalid contract number format: {str(e)}", None

    # Check if sequence is within capacity
    if sequence_number < 1 or sequence_number > group.capacity:
        return False, f"Sequence number {sequence_number} is out of range (1-{group.capacity})", None

    # Check if this exact contract number already exists
    existing = await db.execute(
        select(Contract).where(
            and_(
                Contract.contract_number == contract_number,
                Contract.archive_year == archive_year
            )
        )
    )
    if existing.scalar_one_or_none():
        return False, f"Contract number {contract_number} is already used", None

    # Get available numbers
    available_numbers = await get_available_contract_numbers(db, group_id, birth_year, archive_year)

    if sequence_number not in available_numbers:
        # Find next available
        next_available = available_numbers[0] if available_numbers else None
        if next_available:
            return False, f"Number {sequence_number} is already used. Next available: {next_available}-{birth_year}{group.identifier}", next_available
        else:
            return False, f"No available numbers for birth year {birth_year} in this group", None

    return True, f"Contract number {contract_number} is available", sequence_number
