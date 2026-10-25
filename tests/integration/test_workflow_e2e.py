"""End-to-end workflow test against the REAL handler code with moto-backed
DynamoDB (transactions enforced). No AWS account required.

Covers the core Carely loop:
  patient profile → doctor profile + availability → browse doctors →
  book appointment → double-booking rejected (409) → doctor approves →
  patient cancels → slot released → slot rebookable.
"""

import importlib
import json
import os
import sys
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

BASE = os.path.join(os.path.dirname(__file__), '..', '..')

PATIENT_SUB = 'patient-sub-0001'
PATIENT2_SUB = 'patient-sub-0002'
DOCTOR_SUB = 'doctor-sub-0001'

TABLES = {
    'PATIENTS_TABLE': 'integ-patients',
    'DOCTORS_TABLE': 'integ-doctors',
    'APPOINTMENTS_TABLE': 'integ-appointments',
    'APPOINTMENT_SLOTS_TABLE': 'integ-slots',
    'MEDICAL_RECORDS_TABLE': 'integ-records',
}


def load_handler(*path):
    """Import a function handler by absolute file path under a unique module
    name — `import handler` + reload is unreliable when several function
    directories share the same module name."""
    import importlib.util
    sys.path.insert(0, os.path.join(BASE, 'backend', 'shared'))
    file_path = os.path.join(BASE, *path, 'handler.py')
    name = 'carely_' + '_'.join(path[1:])
    spec = importlib.util.spec_from_file_location(name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def event(body=None, sub=None, groups=(), method='POST', path=None, query=None):
    e = {
        'httpMethod': method,
        'requestContext': {'authorizer': {'claims': {'sub': sub, 'cognito:groups': ','.join(groups)}}},
    }
    if body is not None:
        e['body'] = json.dumps(body)
    if path is not None:
        e['pathParameters'] = path
    if query is not None:
        e['queryStringParameters'] = query
    return e


def call(handler_module, ev):
    return handler_module.handler(ev, None)


@pytest.fixture
def aws():
    os.environ.update(TABLES)
    os.environ.setdefault('AWS_DEFAULT_REGION', 'ap-south-1')
    os.environ.setdefault('AWS_ACCESS_KEY_ID', 'testing')
    os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'testing')
    with mock_aws():
        dynamo = boto3.resource('dynamodb')
        for name, key in [('integ-patients', 'patientId'), ('integ-doctors', 'doctorId'),
                          ('integ-appointments', 'appointmentId'), ('integ-slots', 'slotKey'),
                          ('integ-records', 'recordId')]:
            dynamo.create_table(
                TableName=name,
                KeySchema=[{'AttributeName': key, 'KeyType': 'HASH'}],
                AttributeDefinitions=[{'AttributeName': key, 'AttributeType': 'S'}],
                BillingMode='PAY_PER_REQUEST',
            )
        yield dynamo


def test_full_core_workflow(aws):
    # ── 1. Patient creates their own profile ────────────────────────────────
    patients_create = load_handler('backend', 'functions', 'patients', 'create')
    resp = call(patients_create, event(
        {'name': 'Priya Sharma', 'email': 'priya@carely.demo', 'phone': '+91 90000 00001',
         'dateOfBirth': '1998-04-12', 'bloodGroup': 'O+'},
        sub=PATIENT_SUB, groups=('patient',)))
    assert resp['statusCode'] == 201
    assert json.loads(resp['body'])['patientId'] == PATIENT_SUB

    # ── 2. Patients cannot list all patients ────────────────────────────────
    patients_list = load_handler('backend', 'functions', 'patients', 'list')
    resp = call(patients_list, event(method='GET', sub=PATIENT_SUB, groups=('patient',)))
    assert resp['statusCode'] == 403

    # ── 3. Doctor creates their own profile (id forced to their sub) ───────
    doctors_create = load_handler('backend', 'functions', 'doctors', 'create')
    resp = call(doctors_create, event(
        {'name': 'Dr. Maya Patel', 'email': 'maya@carely.demo', 'specialty': 'Cardiology',
         'doctorId': 'forged-id'},
        sub=DOCTOR_SUB, groups=('doctor',)))
    assert resp['statusCode'] == 201
    assert json.loads(resp['body'])['doctorId'] == DOCTOR_SUB

    # ── 4. Doctor sets weekly availability ──────────────────────────────────
    avail_set = load_handler('backend', 'functions', 'doctors', 'availability', 'set')
    resp = call(avail_set, event(
        {'availability': {'monday': ['09:00', '10:30'], 'wednesday': ['14:00']}},
        sub=DOCTOR_SUB, groups=('doctor',), method='PUT',
        path={'doctorId': DOCTOR_SUB}))
    assert resp['statusCode'] == 200

    # A different doctor cannot set someone else's availability
    resp = call(avail_set, event(
        {'availability': {'monday': ['09:00']}},
        sub='doctor-sub-9999', groups=('doctor',), method='PUT',
        path={'doctorId': DOCTOR_SUB}))
    assert resp['statusCode'] == 403

    # ── 5. Patient browses doctors and sees availability ───────────────────
    doctors_list = load_handler('backend', 'functions', 'doctors', 'list')
    resp = call(doctors_list, event(method='GET', sub=PATIENT_SUB, groups=('patient',)))
    assert resp['statusCode'] == 200
    doctors = json.loads(resp['body'])['doctors']
    assert len(doctors) == 1
    assert doctors[0]['availability']['monday'] == ['09:00', '10:30']

    # ── 6. Patient books an available slot ──────────────────────────────────
    appt_create = load_handler('backend', 'functions', 'appointments', 'create')
    slot = '2026-11-02T09:00:00Z'  # a Monday
    resp = call(appt_create, event(
        {'patientId': PATIENT_SUB, 'doctorId': DOCTOR_SUB, 'dateTime': slot, 'reason': 'Chest check'},
        sub=PATIENT_SUB, groups=('patient',)))
    assert resp['statusCode'] == 201
    appointment_id = json.loads(resp['body'])['appointmentId']

    # ── 7. A second patient cannot book the same slot (double-booking) ─────
    resp = call(appt_create, event(
        {'patientId': PATIENT2_SUB, 'doctorId': DOCTOR_SUB, 'dateTime': slot},
        sub=PATIENT2_SUB, groups=('patient',)))
    assert resp['statusCode'] == 409

    # ── 8. Doctor sees the pending request and approves it ─────────────────
    appt_list = load_handler('backend', 'functions', 'appointments', 'list')
    resp = call(appt_list, event(method='GET', sub=DOCTOR_SUB, groups=('doctor',)))
    assert resp['statusCode'] == 200
    items = json.loads(resp['body'])['appointments']
    assert len(items) == 1 and items[0]['status'] == 'pending'

    with patch.dict(os.environ, {'NOTIFICATIONS_TOPIC_ARN': ''}):
        approve = load_handler('backend', 'functions', 'appointments', 'approve')
        resp = call(approve, event(
            {'decision': 'confirmed'}, sub=DOCTOR_SUB, groups=('doctor',),
            method='PUT', path={'appointmentId': appointment_id}))
    assert resp['statusCode'] == 200, resp['body']

    # ── 9. Patient cancels; the slot lock must be released ─────────────────
    cancel = load_handler('backend', 'functions', 'appointments', 'cancel')
    resp = call(cancel, event(method='DELETE', sub=PATIENT_SUB, groups=('patient',),
                                path={'appointmentId': appointment_id}))
    assert resp['statusCode'] == 200

    # ── 10. The freed slot is bookable again by another patient ────────────
    resp = call(appt_create, event(
        {'patientId': PATIENT2_SUB, 'doctorId': DOCTOR_SUB, 'dateTime': slot},
        sub=PATIENT2_SUB, groups=('patient',)))
    assert resp['statusCode'] == 201

    # ── 11. An unrelated patient cannot cancel someone else's appointment ──
    appt2_id = json.loads(resp['body'])['appointmentId']
    resp = call(cancel, event(method='DELETE', sub=PATIENT_SUB, groups=('patient',),
                                path={'appointmentId': appt2_id}))
    assert resp['statusCode'] == 403


def test_medical_records_are_doctor_authorised_and_patient_scoped(aws):
    mr_create = load_handler('backend', 'functions', 'medical_records', 'create')
    resp = call(mr_create, event(
        {'patientId': PATIENT_SUB, 'doctorId': 'forged', 'title': 'Consultation note',
         'notes': 'Stable; review in 2 weeks'},
        sub=DOCTOR_SUB, groups=('doctor',)))
    assert resp['statusCode'] == 201
    record_id = json.loads(resp['body'])['recordId']

    # Authorship was forced to the calling doctor
    mr_get = load_handler('backend', 'functions', 'medical_records', 'get')
    resp = call(mr_get, event(method='GET', sub=PATIENT_SUB, groups=('patient',),
                                path={'recordId': record_id}))
    item = json.loads(resp['body'])
    assert resp['statusCode'] == 200
    assert item['doctorId'] == DOCTOR_SUB

    # A different patient cannot read it
    resp = call(mr_get, event(method='GET', sub=PATIENT2_SUB, groups=('patient',),
                                path={'recordId': record_id}))
    assert resp['statusCode'] == 403

    # Patients cannot author records
    resp = call(mr_create, event(
        {'patientId': PATIENT_SUB, 'title': 'Self note'},
        sub=PATIENT_SUB, groups=('patient',)))
    assert resp['statusCode'] == 403
