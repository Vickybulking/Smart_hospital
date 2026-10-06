"""
Unit tests for shared/utils/__init__.py

Run with:  python -m pytest tests/unit/ -v
"""

import sys
import os
from decimal import Decimal
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'shared'))

import pytest
from utils import (
    generate_id,
    current_time,
    make_response,
    ok,
    created,
    bad_request,
    not_found,
    conflict,
    internal_error,
    build_update_expression,
    get_pagination_params,
    is_valid_email,
    is_valid_phone,
    is_valid_time,
    is_valid_iso_date,
    CORS_HEADERS,
)
import json


# ── generate_id ───────────────────────────────────────────────────────────────

class TestGenerateId:
    def test_returns_string(self):
        assert isinstance(generate_id(), str)

    def test_unique(self):
        ids = {generate_id() for _ in range(100)}
        assert len(ids) == 100

    def test_uuid_format(self):
        import re
        uuid_re = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
        assert uuid_re.match(generate_id())


# ── current_time ──────────────────────────────────────────────────────────────

class TestCurrentTime:
    def test_ends_with_z(self):
        assert current_time().endswith('Z')

    def test_iso_parseable(self):
        from datetime import datetime
        t = current_time()
        # Drop the trailing Z for fromisoformat compatibility
        datetime.fromisoformat(t.replace('Z', '+00:00'))


# ── make_response ─────────────────────────────────────────────────────────────

class TestMakeResponse:
    def test_status_code(self):
        resp = make_response(200, {'key': 'value'})
        assert resp['statusCode'] == 200

    def test_cors_headers_present(self):
        resp = make_response(200, {})
        for header in CORS_HEADERS:
            assert header in resp['headers']

    def test_body_is_json_string(self):
        resp = make_response(200, {'hello': 'world'})
        body = json.loads(resp['body'])
        assert body == {'hello': 'world'}

    def test_decimal_serialised_as_int(self):
        resp = make_response(200, {'count': Decimal('5')})
        body = json.loads(resp['body'])
        assert body['count'] == 5
        assert isinstance(body['count'], int)

    def test_decimal_float_serialised(self):
        resp = make_response(200, {'score': Decimal('3.14')})
        body = json.loads(resp['body'])
        assert abs(body['score'] - 3.14) < 0.001


# ── Response shortcuts ────────────────────────────────────────────────────────

class TestResponseShortcuts:
    def test_ok(self):
        assert ok({'x': 1})['statusCode'] == 200

    def test_created(self):
        assert created({'id': 'abc'})['statusCode'] == 201

    def test_bad_request_string(self):
        resp = bad_request('Bad input')
        assert resp['statusCode'] == 400
        assert json.loads(resp['body'])['error'] == 'Bad input'

    def test_bad_request_list(self):
        resp = bad_request(['err1', 'err2'])
        assert resp['statusCode'] == 400
        assert json.loads(resp['body'])['errors'] == ['err1', 'err2']

    def test_not_found(self):
        resp = not_found('Item missing')
        assert resp['statusCode'] == 404

    def test_conflict(self):
        resp = conflict('Duplicate slot')
        assert resp['statusCode'] == 409

    def test_internal_error_default(self):
        resp = internal_error()
        assert resp['statusCode'] == 500
        assert 'Internal server error' in resp['body']


# ── build_update_expression ───────────────────────────────────────────────────

class TestBuildUpdateExpression:
    def test_single_field(self):
        expr, names, vals = build_update_expression({'name': 'Alice'})
        assert expr.startswith('SET')
        assert '#field0' in expr
        assert names['#field0'] == 'name'
        assert vals[':val0'] == 'Alice'

    def test_multiple_fields(self):
        expr, names, vals = build_update_expression({'a': 1, 'b': 2})
        assert '#field0' in expr and '#field1' in expr
        assert len(names) == 2
        assert len(vals) == 2

    def test_empty_dict(self):
        expr, names, vals = build_update_expression({})
        assert expr == 'SET '
        assert names == {}
        assert vals == {}


# ── get_pagination_params ─────────────────────────────────────────────────────

class TestGetPaginationParams:
    def _event(self, params: dict) -> dict:
        return {'queryStringParameters': params}

    def test_defaults(self):
        limit, last_key = get_pagination_params({})
        assert limit == 50
        assert last_key is None

    def test_custom_limit(self):
        limit, _ = get_pagination_params(self._event({'limit': '10'}))
        assert limit == 10

    def test_limit_capped_at_200(self):
        limit, _ = get_pagination_params(self._event({'limit': '9999'}))
        assert limit == 200

    def test_limit_minimum_1(self):
        limit, _ = get_pagination_params(self._event({'limit': '-5'}))
        assert limit == 1

    def test_last_key(self):
        _, last_key = get_pagination_params(self._event({'lastKey': 'abc-123'}))
        assert last_key == 'abc-123'

    def test_invalid_limit_uses_default(self):
        limit, _ = get_pagination_params(self._event({'limit': 'abc'}))
        assert limit == 50


# ── Validators ────────────────────────────────────────────────────────────────

class TestIsValidEmail:
    def test_valid(self):
        assert is_valid_email('user@example.com')
        assert is_valid_email('user+tag@hospital.org')

    def test_invalid(self):
        assert not is_valid_email('plaintext')
        assert not is_valid_email('@nodomain')
        assert not is_valid_email('no@')


class TestIsValidPhone:
    def test_valid(self):
        assert is_valid_phone('+91-9876543210')
        assert is_valid_phone('0800 123 456')
        assert is_valid_phone('+12025550123')

    def test_invalid_too_short(self):
        assert not is_valid_phone('123')


class TestIsValidTime:
    def test_valid(self):
        assert is_valid_time('09:00')
        assert is_valid_time('23:59')
        assert is_valid_time('00:00')

    def test_invalid(self):
        assert not is_valid_time('25:00')
        assert not is_valid_time('9:00')    # Missing leading zero
        assert not is_valid_time('09:60')
        assert not is_valid_time('nine')


class TestIsValidIsoDate:
    def test_valid(self):
        assert is_valid_iso_date('2024-01-15')

    def test_invalid_format(self):
        assert not is_valid_iso_date('15/01/2024')
        assert not is_valid_iso_date('2024-13-01')  # Month 13
        assert not is_valid_iso_date('not-a-date')
