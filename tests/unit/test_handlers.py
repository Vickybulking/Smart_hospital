"""
Unit tests for Lambda handler functions.

These tests mock boto3 so no real AWS calls are made.
Run with:  python -m pytest tests/unit/ -v
"""

import sys
import os
import json
from unittest.mock import MagicMock, patch

# Make shared and all function directories importable
BASE = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.join(BASE, 'backend', 'shared'))

import pytest


def auth_event(body=None, sub='user-1', groups=('patient',), path_params=None, method='POST'):
    """Build a Lambda proxy event that looks like an authorised API Gateway call."""
    event = {
        'httpMethod': method,
        'requestContext': {
            'authorizer': {
                'claims': {
                    'sub': sub,
                    'email': f'{sub}@example.com',
                    'cognito:groups': ','.join(groups),
                }
            }
        },
    }
    if body is not None:
        event['body'] = json.dumps(body)
    if path_params is not None:
        event['pathParameters'] = path_params
    return event


def _import(fn_path):
    """Import a function handler by absolute file path under a unique module
    name — avoids sys.modules collisions between same-named handler.py files."""
    import importlib.util
    sys.path.insert(0, os.path.join(BASE, 'backend', 'shared'))
    file_path = os.path.join(BASE, *fn_path, 'handler.py')
    name = 'carely_' + '_'.join(fn_path[1:])
    spec = importlib.util.spec_from_file_location(name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ── patients/create ───────────────────────────────────────────────────────────

class TestPatientsCreateHandler:

    @patch.dict(os.environ, {'PATIENTS_TABLE': 'test-patients'})
    @patch('boto3.resource')
    def test_create_success_scoped_to_caller(self, mock_resource):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.put_item.return_value = {}

        h = _import(['backend', 'functions', 'patients', 'create'])
        event = auth_event({'name': 'Alice', 'email': 'alice@example.com'}, sub='sub-1')
        resp = h.handler(event, None)

        assert resp['statusCode'] == 201
        body = json.loads(resp['body'])
        # Profile must be keyed by the Cognito sub, not a random UUID
        assert body['patientId'] == 'sub-1'
        saved = mock_table.put_item.call_args.kwargs['Item']
        assert saved['patientId'] == 'sub-1'
        assert saved['name'] == 'Alice'

    @patch.dict(os.environ, {'PATIENTS_TABLE': 'test-patients'})
    @patch('boto3.resource')
    def test_create_missing_name(self, mock_resource):
        h = _import(['backend', 'functions', 'patients', 'create'])
        resp = h.handler(auth_event({'email': 'alice@example.com'}, sub='sub-1'), None)
        assert resp['statusCode'] == 400
        assert 'errors' in json.loads(resp['body'])

    @patch.dict(os.environ, {'PATIENTS_TABLE': 'test-patients'})
    @patch('boto3.resource')
    def test_create_rejected_for_doctor(self, mock_resource):
        h = _import(['backend', 'functions', 'patients', 'create'])
        resp = h.handler(auth_event({'name': 'A', 'email': 'a@b.com'}, sub='sub-1', groups=('doctor',)), None)
        assert resp['statusCode'] == 403

    @patch.dict(os.environ, {'PATIENTS_TABLE': 'test-patients'})
    @patch('boto3.resource')
    def test_create_rejected_when_unauthenticated(self, mock_resource):
        h = _import(['backend', 'functions', 'patients', 'create'])
        resp = h.handler({'body': json.dumps({'name': 'A', 'email': 'a@b.com'})}, None)
        assert resp['statusCode'] == 403


# ── patients/get ──────────────────────────────────────────────────────────────

class TestPatientsGetHandler:

    @patch.dict(os.environ, {'PATIENTS_TABLE': 'test-patients'})
    @patch('boto3.resource')
    def test_patient_can_read_own_profile(self, mock_resource):
        patient = {'patientId': 'p-1', 'name': 'Alice', 'email': 'alice@example.com'}
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {'Item': patient}

        h = _import(['backend', 'functions', 'patients', 'get'])
        resp = h.handler(auth_event(None, sub='p-1', method='GET', path_params={'patientId': 'p-1'}), None)
        assert resp['statusCode'] == 200
        assert json.loads(resp['body'])['name'] == 'Alice'

    @patch.dict(os.environ, {'PATIENTS_TABLE': 'test-patients'})
    @patch('boto3.resource')
    def test_patient_cannot_read_other_profile(self, mock_resource):
        h = _import(['backend', 'functions', 'patients', 'get'])
        resp = h.handler(auth_event(None, sub='p-1', method='GET', path_params={'patientId': 'someone-else'}), None)
        assert resp['statusCode'] == 403

    @patch.dict(os.environ, {'PATIENTS_TABLE': 'test-patients'})
    @patch('boto3.resource')
    def test_doctor_can_read_any_profile(self, mock_resource):
        patient = {'patientId': 'p-2', 'name': 'Bob'}
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {'Item': patient}

        h = _import(['backend', 'functions', 'patients', 'get'])
        resp = h.handler(auth_event(None, sub='doc-1', groups=('doctor',), method='GET', path_params={'patientId': 'p-2'}), None)
        assert resp['statusCode'] == 200

    @patch.dict(os.environ, {'PATIENTS_TABLE': 'test-patients'})
    @patch('boto3.resource')
    def test_get_nonexistent_patient(self, mock_resource):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {}

        h = _import(['backend', 'functions', 'patients', 'get'])
        resp = h.handler(auth_event(None, sub='doc-1', groups=('doctor',), method='GET', path_params={'patientId': 'nonexistent'}), None)
        assert resp['statusCode'] == 404


# ── patients/list ─────────────────────────────────────────────────────────────

class TestPatientsListHandler:

    @patch.dict(os.environ, {'PATIENTS_TABLE': 'test-patients'})
    @patch('boto3.resource')
    def test_patient_cannot_list(self, mock_resource):
        h = _import(['backend', 'functions', 'patients', 'list'])
        resp = h.handler(auth_event(None, sub='p-1', groups=('patient',), method='GET'), None)
        assert resp['statusCode'] == 403

    @patch.dict(os.environ, {'PATIENTS_TABLE': 'test-patients'})
    @patch('boto3.resource')
    def test_admin_can_list(self, mock_resource):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.scan.return_value = {'Items': [{'patientId': 'p-1'}]}

        h = _import(['backend', 'functions', 'patients', 'list'])
        resp = h.handler(auth_event(None, sub='a-1', groups=('admin',), method='GET'), None)
        assert resp['statusCode'] == 200
        assert json.loads(resp['body'])['count'] == 1


# ── doctors/create ────────────────────────────────────────────────────────────

class TestDoctorsCreateHandler:

    @patch.dict(os.environ, {'DOCTORS_TABLE': 'test-doctors'})
    @patch('boto3.resource')
    def test_doctor_id_forced_to_caller_sub(self, mock_resource):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        h = _import(['backend', 'functions', 'doctors', 'create'])
        event = auth_event({'name': 'Dr. Maya', 'email': 'maya@x.com', 'specialty': 'Cardiology',
                            'doctorId': 'someone-else'}, sub='doc-1', groups=('doctor',))
        resp = h.handler(event, None)
        assert resp['statusCode'] == 201
        saved = mock_table.put_item.call_args.kwargs['Item']
        assert saved['doctorId'] == 'doc-1'  # client-supplied id is ignored

    @patch.dict(os.environ, {'DOCTORS_TABLE': 'test-doctors'})
    @patch('boto3.resource')
    def test_patient_cannot_create_doctor(self, mock_resource):
        h = _import(['backend', 'functions', 'doctors', 'create'])
        resp = h.handler(auth_event({'name': 'X', 'email': 'x@x.com', 'specialty': 'Y'}, sub='p-1'), None)
        assert resp['statusCode'] == 403


# ── appointments/create ───────────────────────────────────────────────────────

class TestAppointmentsCreateHandler:

    @patch.dict(os.environ, {
        'APPOINTMENTS_TABLE': 'test-appointments',
        'APPOINTMENT_SLOTS_TABLE': 'test-slots',
    })
    @patch('boto3.resource')
    def test_create_success(self, mock_resource):
        mock_resource.return_value.Table.return_value = MagicMock()

        h = _import(['backend', 'functions', 'appointments', 'create'])
        event = auth_event({'patientId': 'p-1', 'doctorId': 'd-1', 'dateTime': '2024-06-15T09:00:00Z'},
                           sub='p-1', groups=('patient',))
        resp = h.handler(event, None)
        assert resp['statusCode'] in (200, 201)

    @patch.dict(os.environ, {
        'APPOINTMENTS_TABLE': 'test-appointments',
        'APPOINTMENT_SLOTS_TABLE': 'test-slots',
    })
    @patch('boto3.resource')
    def test_missing_required_fields(self, mock_resource):
        h = _import(['backend', 'functions', 'appointments', 'create'])
        resp = h.handler(auth_event({'patientId': 'p-1'}, sub='p-1', groups=('patient',)), None)
        assert resp['statusCode'] == 400

    @patch.dict(os.environ, {
        'APPOINTMENTS_TABLE': 'test-appointments',
        'APPOINTMENT_SLOTS_TABLE': 'test-slots',
    })
    @patch('boto3.resource')
    def test_doctor_cannot_book(self, mock_resource):
        h = _import(['backend', 'functions', 'appointments', 'create'])
        resp = h.handler(auth_event({'patientId': 'p-1', 'doctorId': 'd-1', 'dateTime': '2024-06-15T09:00:00Z'},
                                    sub='d-1', groups=('doctor',)), None)
        assert resp['statusCode'] == 403


# ── appointments/cancel ───────────────────────────────────────────────────────

class TestAppointmentsCancelHandler:

    def _event(self, sub, groups):
        return auth_event(None, sub=sub, groups=groups, method='DELETE',
                          path_params={'appointmentId': 'appt-1'})

    @patch.dict(os.environ, {'APPOINTMENTS_TABLE': 'test-appointments', 'APPOINTMENT_SLOTS_TABLE': 'test-slots'})
    @patch('boto3.resource')
    def test_owner_can_cancel_and_slot_released(self, mock_resource):
        resource = mock_resource.return_value
        resource.Table.return_value.get_item.return_value = {'Item': {
            'appointmentId': 'appt-1', 'patientId': 'p-1', 'doctorId': 'd-1',
            'dateTime': '2026-06-15T09:00:00Z', 'status': 'pending',
            'doctorSlotKey': 'd-1#2026-06-15T09:00:00Z',
        }}
        resource.meta.client.transact_write_items.return_value = {}

        h = _import(['backend', 'functions', 'appointments', 'cancel'])
        resp = h.handler(self._event('p-1', ('patient',)), None)
        assert resp['statusCode'] == 200

        # The transaction must include the slot-lock delete
        tx = resource.meta.client.transact_write_items.call_args.kwargs['TransactItems']
        assert any('Delete' in item and item['Delete']['Key']['slotKey'] == 'd-1#2026-06-15T09:00:00Z' for item in tx)

    @patch.dict(os.environ, {'APPOINTMENTS_TABLE': 'test-appointments', 'APPOINTMENT_SLOTS_TABLE': 'test-slots'})
    @patch('boto3.resource')
    def test_non_participant_cannot_cancel(self, mock_resource):
        resource = mock_resource.return_value
        resource.Table.return_value.get_item.return_value = {'Item': {
            'appointmentId': 'appt-1', 'patientId': 'p-1', 'doctorId': 'd-1',
            'dateTime': '2026-06-15T09:00:00Z', 'status': 'pending',
        }}

        h = _import(['backend', 'functions', 'appointments', 'cancel'])
        resp = h.handler(self._event('p-999', ('patient',)), None)
        assert resp['statusCode'] == 403


# ── notifications ─────────────────────────────────────────────────────────────

class TestNotificationsHandler:

    @patch.dict(os.environ, {'NOTIFICATIONS_TOPIC_ARN': 'arn:aws:sns:us-east-1:123:test-topic'})
    @patch('boto3.client')
    def test_send_notification_success(self, mock_client):
        mock_sns = MagicMock()
        mock_client.return_value = mock_sns
        mock_sns.publish.return_value = {'MessageId': 'msg-1'}

        h = _import(['backend', 'functions', 'notifications'])
        resp = h.handler(auth_event({'message': 'Appointment confirmed'}, sub='d-1', groups=('doctor',)), None)
        assert resp['statusCode'] == 200
        mock_sns.publish.assert_called_once()

    @patch.dict(os.environ, {'NOTIFICATIONS_TOPIC_ARN': 'arn:aws:sns:us-east-1:123:test-topic'})
    @patch('boto3.client')
    def test_missing_message(self, mock_client):
        h = _import(['backend', 'functions', 'notifications'])
        resp = h.handler(auth_event({'subject': 'Only subject'}, sub='d-1', groups=('doctor',)), None)
        assert resp['statusCode'] == 400

    @patch.dict(os.environ, {'NOTIFICATIONS_TOPIC_ARN': 'arn:aws:sns:us-east-1:123:test-topic'})
    @patch('boto3.client')
    def test_patient_cannot_send(self, mock_client):
        h = _import(['backend', 'functions', 'notifications'])
        resp = h.handler(auth_event({'message': 'hi'}, sub='p-1', groups=('patient',)), None)
        assert resp['statusCode'] == 403
