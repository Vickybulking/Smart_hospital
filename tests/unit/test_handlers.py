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


# ── patients/create ───────────────────────────────────────────────────────────

class TestPatientsCreateHandler:

    def _import_handler(self):
        fn_path = os.path.join(BASE, 'backend', 'functions', 'patients', 'create')
        sys.path.insert(0, fn_path)
        import importlib
        import handler as h
        importlib.reload(h)  # ensure fresh import each test
        return h

    def _make_event(self, body: dict) -> dict:
        return {'body': json.dumps(body)}

    @patch.dict(os.environ, {'PATIENTS_TABLE': 'test-patients'})
    @patch('boto3.resource')
    def test_create_success(self, mock_resource):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.put_item.return_value = {}

        h = self._import_handler()
        event = self._make_event({'name': 'Alice', 'email': 'alice@example.com'})
        resp = h.handler(event, None)

        assert resp['statusCode'] == 201
        body = json.loads(resp['body'])
        assert 'patientId' in body
        mock_table.put_item.assert_called_once()

    @patch.dict(os.environ, {'PATIENTS_TABLE': 'test-patients'})
    @patch('boto3.resource')
    def test_create_missing_name(self, mock_resource):
        h = self._import_handler()
        resp = h.handler(self._make_event({'email': 'alice@example.com'}), None)
        assert resp['statusCode'] == 400
        body = json.loads(resp['body'])
        assert 'errors' in body

    @patch.dict(os.environ, {}, clear=True)
    @patch('boto3.resource')
    def test_missing_env_var(self, mock_resource):
        # Ensure PATIENTS_TABLE is definitely not set
        os.environ.pop('PATIENTS_TABLE', None)
        h = self._import_handler()
        resp = h.handler(self._make_event({'name': 'Alice', 'email': 'a@b.com'}), None)
        assert resp['statusCode'] == 500


# ── patients/get ──────────────────────────────────────────────────────────────

class TestPatientsGetHandler:

    def _import_handler(self):
        fn_path = os.path.join(BASE, 'backend', 'functions', 'patients', 'get')
        sys.path.insert(0, fn_path)
        import importlib
        import handler as h
        importlib.reload(h)
        return h

    @patch.dict(os.environ, {'PATIENTS_TABLE': 'test-patients'})
    @patch('boto3.resource')
    def test_get_existing_patient(self, mock_resource):
        patient = {'patientId': 'p-1', 'name': 'Alice', 'email': 'alice@example.com'}
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {'Item': patient}

        h = self._import_handler()
        event = {'pathParameters': {'patientId': 'p-1'}}
        resp = h.handler(event, None)

        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body['name'] == 'Alice'

    @patch.dict(os.environ, {'PATIENTS_TABLE': 'test-patients'})
    @patch('boto3.resource')
    def test_get_nonexistent_patient(self, mock_resource):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {}  # No 'Item' key

        h = self._import_handler()
        resp = h.handler({'pathParameters': {'patientId': 'nonexistent'}}, None)
        assert resp['statusCode'] == 404

    @patch.dict(os.environ, {'PATIENTS_TABLE': 'test-patients'})
    @patch('boto3.resource')
    def test_missing_path_param(self, mock_resource):
        h = self._import_handler()
        resp = h.handler({'pathParameters': {}}, None)
        assert resp['statusCode'] == 400


# ── appointments/create ───────────────────────────────────────────────────────

class TestAppointmentsCreateHandler:

    def _import_handler(self):
        fn_path = os.path.join(BASE, 'backend', 'functions', 'appointments', 'create')
        sys.path.insert(0, fn_path)
        import importlib
        import handler as h
        importlib.reload(h)
        return h

    @patch.dict(os.environ, {
        'APPOINTMENTS_TABLE': 'test-appointments',
        'APPOINTMENT_SLOTS_TABLE': 'test-slots',
    })
    @patch('boto3.resource')
    def test_create_success(self, mock_resource):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.put_item.return_value = {}

        h = self._import_handler()
        event = {
            'requestContext': {
                'authorizer': {
                    'claims': {
                        'sub': 'p-1',
                        'cognito:groups': 'patient',
                    }
                }
            },
            'body': json.dumps({
                'patientId': 'p-1',
                'doctorId': 'd-1',
                'dateTime': '2024-06-15T09:00:00Z',
            })
        }
        resp = h.handler(event, None)
        # Accept 200 or 201
        assert resp['statusCode'] in (200, 201)

    @patch.dict(os.environ, {
        'APPOINTMENTS_TABLE': 'test-appointments',
        'APPOINTMENT_SLOTS_TABLE': 'test-slots',
    })
    @patch('boto3.resource')
    def test_missing_required_fields(self, mock_resource):
        h = self._import_handler()
        resp = h.handler({
            'requestContext': {
                'authorizer': {
                    'claims': {
                        'sub': 'p-1',
                        'cognito:groups': 'patient',
                    }
                }
            },
            'body': json.dumps({'patientId': 'p-1'})
        }, None)
        assert resp['statusCode'] == 400


# ── notifications ─────────────────────────────────────────────────────────────

class TestNotificationsHandler:

    def _import_handler(self):
        fn_path = os.path.join(BASE, 'backend', 'functions', 'notifications')
        sys.path.insert(0, fn_path)
        import importlib
        import handler as h
        importlib.reload(h)
        return h

    @patch.dict(os.environ, {'NOTIFICATIONS_TOPIC_ARN': 'arn:aws:sns:us-east-1:123:test-topic'})
    @patch('boto3.client')
    def test_send_notification_success(self, mock_client):
        mock_sns = MagicMock()
        mock_client.return_value = mock_sns
        mock_sns.publish.return_value = {'MessageId': 'msg-1'}

        h = self._import_handler()
        event = {'body': json.dumps({'message': 'Appointment confirmed'})}
        resp = h.handler(event, None)

        assert resp['statusCode'] == 200
        mock_sns.publish.assert_called_once()

    @patch.dict(os.environ, {'NOTIFICATIONS_TOPIC_ARN': 'arn:aws:sns:us-east-1:123:test-topic'})
    @patch('boto3.client')
    def test_missing_message(self, mock_client):
        h = self._import_handler()
        resp = h.handler({'body': json.dumps({'subject': 'Only subject'})}, None)
        assert resp['statusCode'] == 400
