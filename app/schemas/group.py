from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel, Field, field_validator
import re


def normalize_identifier(identifier: str) -> str:
    """
    Normalize identifier to Latin letters and numbers only (uppercase).

    Converts common Cyrillic look-alikes to Latin equivalents:
    - А, В, С, Е, К, М, Н, О, Р, Т, Х (Cyrillic) → A, B, C, E, K, M, N, O, P, T, X (Latin)

    Examples:
    - "В1" (Cyrillic B) → "B1" (Latin B)
    - "С2" (Cyrillic C) → "C2" (Latin C)
    - "b1" → "B1"
    """
    # Cyrillic to Latin mapping for look-alike characters
    cyrillic_to_latin = {
        'А': 'A', 'а': 'a',
        'В': 'B', 'в': 'b',
        'С': 'C', 'с': 'c',
        'Е': 'E', 'е': 'e',
        'К': 'K', 'к': 'k',
        'М': 'M', 'м': 'm',
        'Н': 'H', 'н': 'h',
        'О': 'O', 'о': 'o',
        'Р': 'P', 'р': 'p',
        'Т': 'T', 'т': 't',
        'Х': 'X', 'х': 'x',
    }

    # Replace Cyrillic characters with Latin equivalents
    normalized = ''.join(cyrillic_to_latin.get(char, char) for char in identifier)

    # Convert to uppercase
    normalized = normalized.upper()

    # Remove any characters that are not Latin letters or numbers
    normalized = re.sub(r'[^A-Z0-9-]', '', normalized)

    return normalized


class GroupRead(BaseModel):
    id: int
    name: str
    identifier: str
    birth_year: int
    description: Optional[str] = None
    schedule_days: Optional[str] = None
    schedule_time: Optional[str] = None
    capacity: int = 100
    coach_id: Optional[int] = None
    created_at: datetime

    # Optional stats - populated when requested
    active_students_count: Optional[int] = Field(default=None, description="Number of active students in this group")
    waiting_list_count: Optional[int] = Field(default=None, description="Number of students waiting to join this group")

    class Config:
        from_attributes = True


class GroupCreate(BaseModel):
    name: str
    identifier: str = Field(description="Unique identifier like 1B, 2B, 1C, etc.")
    birth_year: int = Field(description="Birth year of students in this group (e.g., 2010, 2015, 2020)")
    description: Optional[str] = None
    schedule_days: Optional[str] = None
    schedule_time: Optional[str] = None
    capacity: int = Field(default=25, ge=1, le=50, description="Maximum number of students in group")
    coach_id: Optional[int] = None

    @field_validator('identifier')
    @classmethod
    def normalize_identifier_field(cls, v: str) -> str:
        """
        Normalize and validate identifier format.

        Valid formats: B1, C2, A10, etc.
        - Must start with uppercase letter (A-Z)
        - Must end with number (1-9, 10, 11, etc.)
        - No dashes, underscores, or other characters allowed

        Invalid formats: 1B, B-1, B_1, BB1, 1, etc.
        """
        if not v:
            raise ValueError('Identifier cannot be empty')

        # Normalize to uppercase and remove Cyrillic characters
        normalized = normalize_identifier(v)
        if not normalized:
            raise ValueError('Identifier must contain at least one Latin letter or number')

        # Validate format: must be uppercase letter(s) followed by number(s)
        # Pattern: ^[A-Z]+[0-9]+$
        if not re.match(r'^[A-Z][0-9]+$', normalized):
            raise ValueError(
                'Identifier must start with ONE uppercase letter followed by numbers '
                '(valid: B1, C2, A10; invalid: 1B, B-1, B_1, BB1)'
            )

        return normalized


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    identifier: Optional[str] = None
    birth_year: Optional[int] = None
    description: Optional[str] = None
    schedule_days: Optional[str] = None
    schedule_time: Optional[str] = None
    capacity: Optional[int] = Field(default=None, ge=1, le=50)
    coach_id: Optional[int] = None

    # Note: No validator for identifier in updates
    # Identifier changes are blocked in the router layer (groups.py)
    # This allows updating old groups with legacy identifier formats (e.g., "B", "C")
    # New groups must follow strict validation (letter + number)


class GroupCapacityByYear(BaseModel):
    """Capacity info for a specific birth year"""
    used: int
    available: int


class GroupCapacityInfo(BaseModel):
    """Detailed capacity information for a group"""
    group_id: int
    group_name: str
    capacity: int
    active_students: int
    available_slots: int
    waiting_list_count: int
    by_birth_year: Dict[str, GroupCapacityByYear]


class GroupsByYear(BaseModel):
    """Groups organized by birth year"""
    birth_year: int
    groups: list[GroupRead]
    total_groups: int


class GroupedByYearResponse(BaseModel):
    """Response for groups grouped by birth year"""
    data: list[GroupsByYear]
    total_birth_years: int


class GroupStatisticsByBirthYear(BaseModel):
    """Statistics for groups of a specific birth year"""
    birth_year: int
    total_groups: int
    total_capacity: int
    total_used: int
    total_available: int


class GroupStatistics(BaseModel):
    """Overall statistics for all groups"""
    total_groups: int
    total_capacity: int
    total_used: int
    total_available: int
    filled_groups_count: int  # Groups where capacity == used
    by_birth_year: list[GroupStatisticsByBirthYear]
