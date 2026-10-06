"""
Input validators for Smart Hospital Management System.

All functions return a list of error strings.  An empty list means valid.
"""

from __future__ import annotations

import re
from typing import Any


# ── Regex patterns ────────────────────────────────────────────────────────────
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_PHONE_RE = re.compile(r'^\+?[\d\s\-().]{7,20}$')
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_ISO_DT_RE = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?Z?$')
_TIME_RE = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)$')

VALID_DAYS = frozenset({
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'
})

BLOOD_GROUPS = frozenset({'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'})


# ── Generic helpers ───────────────────────────────────────────────────────────

def _required(data: dict, *fields: str) -> list[str]:
    return [f'"{f}" is required' for f in fields if not data.get(f)]


def _email(value: str, field: str = 'email') -> list[str]:
    if value and not _EMAIL_RE.match(value):
        return [f'"{field}" must be a valid email address']
    return []


def _phone(value: str, field: str = 'phone') -> list[str]:
    if value and not _PHONE_RE.match(value):
        return [f'"{field}" must be a valid phone number (7–20 digits, optional +/spaces/dashes)']
    return []


def _iso_datetime(value: str, field: str = 'dateTime') -> list[str]:
    if value and not _ISO_DT_RE.match(value):
        return [f'"{field}" must be an ISO-8601 datetime string (e.g. 2024-06-15T09:00:00Z)']
    return []


def _date(value: str, field: str = 'date') -> list[str]:
    if value and not _DATE_RE.match(value):
        return [f'"{field}" must be a date in YYYY-MM-DD format']
    return []


# ── Domain validators ─────────────────────────────────────────────────────────

def validate_patient_data(data: dict) -> list[str]:
    """
    Validate the payload for creating a new patient.

    Required: name, email
    Optional but validated: phone, dateOfBirth, bloodGroup
    """
    errors: list[str] = []
    errors += _required(data, 'name', 'email')
    errors += _email(data.get('email', ''))
    errors += _phone(data.get('phone', ''))
    errors += _date(data.get('dateOfBirth', ''), 'dateOfBirth')

    blood_group = data.get('bloodGroup', '')
    if blood_group and blood_group not in BLOOD_GROUPS:
        errors.append(f'"bloodGroup" must be one of {sorted(BLOOD_GROUPS)}')

    return errors


def validate_doctor_data(data: dict) -> list[str]:
    """
    Validate the payload for creating a new doctor.

    Required: name, email, specialty
    Optional but validated: phone
    """
    errors: list[str] = []
    errors += _required(data, 'name', 'email', 'specialty')
    errors += _email(data.get('email', ''))
    errors += _phone(data.get('phone', ''))
    return errors


def validate_appointment_data(data: dict) -> list[str]:
    """
    Validate the payload for booking an appointment.

    Required: patientId, doctorId, dateTime
    Optional but validated: reason (max 500 chars)
    """
    errors: list[str] = []
    errors += _required(data, 'patientId', 'doctorId', 'dateTime')
    errors += _iso_datetime(data.get('dateTime', ''))

    reason = data.get('reason', '')
    if reason and len(reason) > 500:
        errors.append('"reason" must not exceed 500 characters')

    return errors


def validate_medical_record_data(data: dict) -> list[str]:
    """
    Validate the payload for creating a medical record.

    Required: patientId, doctorId, title
    Optional but validated: recordDate
    """
    errors: list[str] = []
    errors += _required(data, 'patientId', 'doctorId', 'title')

    title = data.get('title', '')
    if title and len(title) > 200:
        errors.append('"title" must not exceed 200 characters')

    errors += _date(data.get('recordDate', ''), 'recordDate')
    return errors


def validate_availability_data(data: dict) -> list[str]:
    """
    Validate a doctor's weekly availability map.

    Expected format:
        {
          "monday": ["09:00", "10:00"],
          "tuesday": [],
          ...
        }
    """
    errors: list[str] = []
    availability = data.get('availability')

    if availability is None:
        return ['"availability" is required']

    if not isinstance(availability, dict):
        return ['"availability" must be an object keyed by day-of-week']

    for day, times in availability.items():
        if day.lower() not in VALID_DAYS:
            errors.append(f'Invalid day: "{day}". Must be one of {sorted(VALID_DAYS)}')
            continue

        if not isinstance(times, list):
            errors.append(f'Times for "{day}" must be a list of "HH:MM" strings')
            continue

        for t in times:
            if not isinstance(t, str) or not _TIME_RE.match(t):
                errors.append(f'Invalid time "{t}" for "{day}". Expected "HH:MM" (24-hour) format')

    return errors


def validate_notification_data(data: dict) -> list[str]:
    """Validate a notification payload. Required: message."""
    errors: list[str] = []
    errors += _required(data, 'message')
    msg = data.get('message', '')
    if msg and len(msg) > 1600:
        errors.append('"message" must not exceed 1600 characters (SNS limit)')
    return errors
