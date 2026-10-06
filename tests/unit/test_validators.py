"""
Unit tests for shared/validators/__init__.py

Run with:  python -m pytest tests/unit/ -v
"""

import sys
import os

# Make the shared package importable without installing it
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'shared'))

import pytest
from validators import (
    validate_patient_data,
    validate_doctor_data,
    validate_appointment_data,
    validate_medical_record_data,
    validate_availability_data,
    validate_notification_data,
)


# ── Patient ───────────────────────────────────────────────────────────────────

class TestValidatePatientData:

    def test_valid_minimal(self):
        assert validate_patient_data({'name': 'Alice', 'email': 'alice@example.com'}) == []

    def test_valid_full(self):
        data = {
            'name': 'Alice',
            'email': 'alice@example.com',
            'phone': '+91-9876543210',
            'dateOfBirth': '1990-05-15',
            'bloodGroup': 'O+',
        }
        assert validate_patient_data(data) == []

    def test_missing_name(self):
        errors = validate_patient_data({'email': 'alice@example.com'})
        assert any('name' in e for e in errors)

    def test_missing_email(self):
        errors = validate_patient_data({'name': 'Alice'})
        assert any('email' in e for e in errors)

    def test_invalid_email(self):
        errors = validate_patient_data({'name': 'Alice', 'email': 'not-an-email'})
        assert any('email' in e.lower() for e in errors)

    def test_invalid_phone(self):
        errors = validate_patient_data({'name': 'Alice', 'email': 'a@b.com', 'phone': '12'})
        assert any('phone' in e.lower() for e in errors)

    def test_invalid_blood_group(self):
        errors = validate_patient_data({'name': 'Alice', 'email': 'a@b.com', 'bloodGroup': 'X+'})
        assert any('bloodGroup' in e for e in errors)

    def test_invalid_date_of_birth(self):
        errors = validate_patient_data({'name': 'Alice', 'email': 'a@b.com', 'dateOfBirth': '15/05/1990'})
        assert any('dateOfBirth' in e for e in errors)


# ── Doctor ────────────────────────────────────────────────────────────────────

class TestValidateDoctorData:

    def test_valid(self):
        data = {'name': 'Dr. Smith', 'email': 'smith@hospital.com', 'specialty': 'Cardiology'}
        assert validate_doctor_data(data) == []

    def test_missing_specialty(self):
        errors = validate_doctor_data({'name': 'Dr. Smith', 'email': 'smith@hospital.com'})
        assert any('specialty' in e for e in errors)

    def test_invalid_email(self):
        errors = validate_doctor_data({'name': 'Dr. X', 'email': 'bad', 'specialty': 'Cardiology'})
        assert any('email' in e.lower() for e in errors)


# ── Appointment ───────────────────────────────────────────────────────────────

class TestValidateAppointmentData:

    def test_valid(self):
        data = {
            'patientId': 'p-1',
            'doctorId': 'd-1',
            'dateTime': '2024-06-15T09:00:00Z',
        }
        assert validate_appointment_data(data) == []

    def test_missing_fields(self):
        errors = validate_appointment_data({})
        assert len(errors) >= 3

    def test_invalid_datetime_format(self):
        errors = validate_appointment_data({
            'patientId': 'p-1',
            'doctorId': 'd-1',
            'dateTime': '15-06-2024 09:00',  # Wrong format
        })
        assert any('dateTime' in e for e in errors)

    def test_reason_too_long(self):
        errors = validate_appointment_data({
            'patientId': 'p-1',
            'doctorId': 'd-1',
            'dateTime': '2024-06-15T09:00:00Z',
            'reason': 'x' * 501,
        })
        assert any('reason' in e for e in errors)

    def test_reason_exactly_500_chars_is_ok(self):
        errors = validate_appointment_data({
            'patientId': 'p-1',
            'doctorId': 'd-1',
            'dateTime': '2024-06-15T09:00:00Z',
            'reason': 'x' * 500,
        })
        assert errors == []


# ── Medical Record ────────────────────────────────────────────────────────────

class TestValidateMedicalRecordData:

    def test_valid(self):
        data = {'patientId': 'p-1', 'doctorId': 'd-1', 'title': 'Consultation Notes'}
        assert validate_medical_record_data(data) == []

    def test_missing_title(self):
        errors = validate_medical_record_data({'patientId': 'p-1', 'doctorId': 'd-1'})
        assert any('title' in e for e in errors)

    def test_title_too_long(self):
        errors = validate_medical_record_data({
            'patientId': 'p-1', 'doctorId': 'd-1', 'title': 'x' * 201
        })
        assert any('title' in e for e in errors)

    def test_invalid_record_date(self):
        errors = validate_medical_record_data({
            'patientId': 'p-1', 'doctorId': 'd-1', 'title': 'Test', 'recordDate': 'not-a-date'
        })
        assert any('recordDate' in e for e in errors)


# ── Availability ──────────────────────────────────────────────────────────────

class TestValidateAvailabilityData:

    def test_valid(self):
        data = {'availability': {'monday': ['09:00', '10:00'], 'tuesday': []}}
        assert validate_availability_data(data) == []

    def test_missing_availability_key(self):
        errors = validate_availability_data({})
        assert any('availability' in e for e in errors)

    def test_invalid_day(self):
        errors = validate_availability_data({'availability': {'funday': ['09:00']}})
        assert any('funday' in e for e in errors)

    def test_invalid_time_format(self):
        errors = validate_availability_data({'availability': {'monday': ['9:00', '25:00']}})
        assert len(errors) >= 1  # At least one bad time

    def test_times_not_a_list(self):
        errors = validate_availability_data({'availability': {'monday': '09:00'}})
        assert any('list' in e for e in errors)

    def test_valid_full_week(self):
        avail = {
            'monday': ['09:00', '10:00'],
            'tuesday': ['14:00'],
            'wednesday': [],
            'thursday': ['11:00', '15:00'],
            'friday': ['09:00'],
            'saturday': [],
            'sunday': [],
        }
        assert validate_availability_data({'availability': avail}) == []


# ── Notification ──────────────────────────────────────────────────────────────

class TestValidateNotificationData:

    def test_valid(self):
        assert validate_notification_data({'message': 'Your appointment is confirmed'}) == []

    def test_missing_message(self):
        errors = validate_notification_data({})
        assert any('message' in e for e in errors)

    def test_message_too_long(self):
        errors = validate_notification_data({'message': 'x' * 1601})
        assert any('1600' in e for e in errors)
