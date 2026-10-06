"""
Shared utility functions for Smart Hospital Management System.

All helpers here are pure functions with no AWS dependencies so they can
be unit-tested without mocking boto3.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


# ── ID generation ────────────────────────────────────────────────────────────

def generate_id() -> str:
    """Return a new UUID4 string."""
    return str(uuid.uuid4())


# ── Timestamps ───────────────────────────────────────────────────────────────

def current_time() -> str:
    """Return the current UTC time as an ISO-8601 string with a trailing 'Z'."""
    return datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


# ── HTTP responses ───────────────────────────────────────────────────────────

CORS_HEADERS: dict[str, str] = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


def make_response(status_code: int, body: Any) -> dict:
    """
    Return a Lambda proxy-compatible response dict.

    DynamoDB Decimal types are automatically converted to int/float so
    json.dumps does not raise a TypeError.
    """
    return {
        'statusCode': status_code,
        'headers': CORS_HEADERS,
        'body': json.dumps(body, default=_decimal_default),
    }


def ok(body: Any) -> dict:
    """200 OK shorthand."""
    return make_response(200, body)


def created(body: Any) -> dict:
    """201 Created shorthand."""
    return make_response(201, body)


def bad_request(message: str | list[str]) -> dict:
    """400 Bad Request shorthand."""
    key = 'errors' if isinstance(message, list) else 'error'
    return make_response(400, {key: message})


def not_found(message: str) -> dict:
    """404 Not Found shorthand."""
    return make_response(404, {'error': message})


def conflict(message: str) -> dict:
    """409 Conflict shorthand."""
    return make_response(409, {'error': message})


def internal_error(message: str = 'Internal server error') -> dict:
    """500 Internal Server Error shorthand."""
    return make_response(500, {'error': message})


# ── DynamoDB helpers ─────────────────────────────────────────────────────────

def _decimal_default(obj: Any) -> int | float:
    """JSON serialiser hook that converts Decimal → int or float."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(f'Object of type {type(obj)} is not JSON serialisable')


def build_update_expression(updates: dict[str, Any]) -> tuple[str, dict, dict]:
    """
    Build a DynamoDB UpdateExpression, ExpressionAttributeNames and
    ExpressionAttributeValues from a plain dict of {field: value} pairs.

    Returns:
        (update_expr, expr_names, expr_values)

    Example:
        >>> expr, names, vals = build_update_expression({'name': 'Alice', 'age': 30})
        >>> expr
        'SET #field0 = :val0, #field1 = :val1'
    """
    set_parts: list[str] = []
    expr_names: dict[str, str] = {}
    expr_values: dict[str, Any] = {}

    for i, (key, value) in enumerate(updates.items()):
        name_ph = f'#field{i}'
        val_ph = f':val{i}'
        set_parts.append(f'{name_ph} = {val_ph}')
        expr_names[name_ph] = key
        expr_values[val_ph] = value

    return 'SET ' + ', '.join(set_parts), expr_names, expr_values


# ── Pagination ───────────────────────────────────────────────────────────────

def get_pagination_params(event: dict, default_limit: int = 50) -> tuple[int, str | None]:
    """
    Extract 'limit' and 'lastKey' from query string parameters.

    Returns:
        (limit, last_key)  where last_key is None if not provided.
    """
    params = event.get('queryStringParameters') or {}
    try:
        limit = max(1, min(int(params.get('limit', default_limit)), 200))
    except (ValueError, TypeError):
        limit = default_limit
    return limit, params.get('lastKey')


# ── Validation helpers ────────────────────────────────────────────────────────

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

PHONE_RE = re.compile(r'^\+?[\d\s\-().]{7,20}$')

TIME_RE = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)$')


def is_valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(value))


def is_valid_phone(value: str) -> bool:
    return bool(PHONE_RE.match(value))


def is_valid_time(value: str) -> bool:
    """Return True if value is a valid 'HH:MM' 24-hour time string."""
    return bool(TIME_RE.match(value))


def is_valid_iso_date(value: str) -> bool:
    """Return True if value can be parsed as an ISO-8601 date (YYYY-MM-DD)."""
    try:
        datetime.strptime(value, '%Y-%m-%d')
        return True
    except (ValueError, TypeError):
        return False
