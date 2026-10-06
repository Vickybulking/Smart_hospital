"""
Unit tests for shared/middleware/__init__.py

Run with:  python -m pytest tests/unit/ -v
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'shared'))

import pytest
from middleware import (
    get_claims,
    get_user_sub,
    get_user_email,
    get_user_groups,
    is_in_group,
    is_admin,
    is_doctor,
    is_patient,
    forbidden,
    options_response,
    require_group,
    handle_options,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _event_with_claims(**claims) -> dict:
    """Build a minimal API Gateway event with the given Cognito claims."""
    return {
        'httpMethod': 'GET',
        'requestContext': {
            'authorizer': {
                'claims': claims
            }
        }
    }


def _event_with_groups(*groups) -> dict:
    return _event_with_claims(**{
        'sub': 'user-123',
        'email': 'user@example.com',
        'cognito:groups': ','.join(groups),
    })


def _options_event() -> dict:
    return {'httpMethod': 'OPTIONS'}


# ── get_claims ────────────────────────────────────────────────────────────────

class TestGetClaims:
    def test_returns_claims_dict(self):
        event = _event_with_claims(sub='abc', email='a@b.com')
        claims = get_claims(event)
        assert claims['sub'] == 'abc'

    def test_empty_event_returns_empty(self):
        assert get_claims({}) == {}

    def test_missing_authorizer_returns_empty(self):
        event = {'requestContext': {}}
        assert get_claims(event) == {}


# ── get_user_sub / get_user_email ─────────────────────────────────────────────

class TestGetUserIdentity:
    def test_sub(self):
        event = _event_with_claims(sub='user-999')
        assert get_user_sub(event) == 'user-999'

    def test_email(self):
        event = _event_with_claims(email='doc@hospital.com')
        assert get_user_email(event) == 'doc@hospital.com'

    def test_none_when_missing(self):
        assert get_user_sub({}) is None
        assert get_user_email({}) is None


# ── get_user_groups ───────────────────────────────────────────────────────────

class TestGetUserGroups:
    def test_single_group(self):
        event = _event_with_groups('doctor')
        assert get_user_groups(event) == ['doctor']

    def test_multiple_groups(self):
        event = _event_with_groups('doctor', 'admin')
        groups = get_user_groups(event)
        assert 'doctor' in groups
        assert 'admin' in groups

    def test_empty_when_no_claim(self):
        event = _event_with_claims(sub='x')
        assert get_user_groups(event) == []

    def test_list_type_claim(self):
        """API Gateway may already parse the groups claim as a Python list."""
        event = {
            'httpMethod': 'GET',
            'requestContext': {
                'authorizer': {
                    'claims': {'cognito:groups': ['admin', 'doctor']}
                }
            }
        }
        groups = get_user_groups(event)
        assert 'admin' in groups
        assert 'doctor' in groups


# ── is_admin / is_doctor / is_patient ─────────────────────────────────────────

class TestGroupChecks:
    def test_is_admin(self):
        assert is_admin(_event_with_groups('admin'))
        assert not is_admin(_event_with_groups('doctor'))

    def test_is_doctor(self):
        assert is_doctor(_event_with_groups('doctor'))
        assert not is_doctor(_event_with_groups('patient'))

    def test_is_patient(self):
        assert is_patient(_event_with_groups('patient'))
        assert not is_patient(_event_with_groups('admin'))


# ── forbidden / options_response ─────────────────────────────────────────────

class TestResponseHelpers:
    def test_forbidden_status(self):
        resp = forbidden()
        assert resp['statusCode'] == 403
        assert json.loads(resp['body'])['error'] == 'Forbidden'

    def test_forbidden_custom_message(self):
        resp = forbidden('Admins only')
        assert 'Admins only' in resp['body']

    def test_options_response(self):
        resp = options_response()
        assert resp['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in resp['headers']


# ── @require_group ────────────────────────────────────────────────────────────

class TestRequireGroup:
    def _make_handler(self, *groups):
        @require_group(*groups)
        def dummy_handler(event, context):
            return {'statusCode': 200, 'body': 'ok'}
        return dummy_handler

    def test_allows_member(self):
        h = self._make_handler('doctor')
        resp = h(_event_with_groups('doctor'), None)
        assert resp['statusCode'] == 200

    def test_blocks_non_member(self):
        h = self._make_handler('admin')
        resp = h(_event_with_groups('patient'), None)
        assert resp['statusCode'] == 403

    def test_allows_any_of_multiple_groups(self):
        h = self._make_handler('admin', 'doctor')
        assert h(_event_with_groups('doctor'), None)['statusCode'] == 200
        assert h(_event_with_groups('admin'), None)['statusCode'] == 200
        assert h(_event_with_groups('patient'), None)['statusCode'] == 403

    def test_passes_options_through(self):
        h = self._make_handler('admin')
        resp = h(_options_event(), None)
        assert resp['statusCode'] == 200


# ── @handle_options ───────────────────────────────────────────────────────────

class TestHandleOptions:
    def test_returns_options_response_on_options(self):
        @handle_options
        def h(event, context):
            return {'statusCode': 200, 'body': 'reached'}

        resp = h(_options_event(), None)
        assert resp['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in resp['headers']

    def test_passes_non_options_to_handler(self):
        @handle_options
        def h(event, context):
            return {'statusCode': 200, 'body': 'reached'}

        resp = h({'httpMethod': 'GET'}, None)
        assert resp['body'] == 'reached'
