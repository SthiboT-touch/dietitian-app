"""Shared server-side validation for new patient registration (BRS FR-1.2).

Only applies to NEW registrations. Existing client ID values are not altered.
Phone numbers are stored in South African E.164 format for consistency.
"""

from datetime import date
import re

_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


def validate_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 150 or not _EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Enter a valid email address (for example, name@example.com).")
    return email


def validate_sa_phone(value: str) -> str:
    # Allow a single familiar international prefix, spaces, hyphens and brackets.
    raw = value.strip()
    if not re.fullmatch(r"\+?[0-9 ()-]+", raw):
        raise ValueError("Enter a valid South African phone number, such as 082 123 4567.")
    digits = re.sub(r"[ ()-]", "", raw)
    if re.fullmatch(r"0[1-8][0-9]{8}", digits):
        return "+27" + digits[1:]
    if re.fullmatch(r"(?:\+27|27)[1-8][0-9]{8}", digits):
        return "+27" + digits.lstrip("+")[2:]
    raise ValueError(
        "Enter a 10-digit South African number (e.g. 082 123 4567 or +27 82 123 4567)."
    )


def validate_sa_id_number(value: str) -> str:
    sa_id = value.strip()
    if not re.fullmatch(r"[0-9]{13}", sa_id):
        raise ValueError("South African ID must contain exactly 13 digits.")
    # SA identity numbers use the Luhn check on all 13 digits.
    total = 0
    for position, character in enumerate(reversed(sa_id)):
        digit = int(character)
        if position % 2:
            digit *= 2
            digit = digit // 10 + digit % 10
        total += digit
    if total % 10:
        raise ValueError("South African ID checksum is invalid.")
    return sa_id


def validate_sa_id(value: str, birth_date: date) -> str:
    sa_id = validate_sa_id_number(value)
    if sa_id[:6] != birth_date.strftime("%y%m%d"):
        raise ValueError("Date of birth must match the first six digits of the ID number.")
    if birth_date > date.today():
        raise ValueError("Date of birth cannot be in the future.")
    if birth_date.year < 1900:
        raise ValueError("Please check the date of birth.")
    return sa_id
