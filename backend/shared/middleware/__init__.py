"""
Middleware for Smart Hospital Management System Lambda functions.

Provides:
  - Cognito JWT claim extraction (no third-party libraries required —
    API Gateway already verifies the signature before invoking the function)
  - Role-based access control helpers
  - OPTIONS pre-flight handler
"""

from __future__ import annotations

import json
from functools import wraps
from typing import Any, Callable

CORS_HEADERS: dict[str, str] = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


# ── Cognito claims helpers ────────────────────────────────────────────────────

def get_claims(event: dict) -> dict:
    """
    Extract Cognito JWT claims from the API Gateway authoriser context.

    When Cognito authorisation is configured on the API, API Gateway
    validates the token and injects claims here — no manual JWT parsing needed.
    """
    return (
        (event.get('requestContext') or {})
        .get('authorizer', {})
        .get('claims', {})
    ) or {}


def get_user_sub(event: dict) -> str | None:
    """Return the Cognito sub (unique user ID) from the JWT claims."""
    return get_claims(event).get('sub')


def get_user_email(event: dict) -> str | None:
    """Return the user's email from the JWT claims."""
    return get_claims(event).get('email')


def get_user_groups(event: dict) -> list[str]:
    """
    Return the list of Cognito groups the caller belongs to.

    The claim value is a comma-separated string when there is more than
    one group, or a plain string for a single group.
    """
    raw = get_claims(event).get('cognito:groups', '')
    if isinstance(raw, list):
        return raw
    return [g.strip() for g in raw.split(',') if g.strip()]


def is_in_group(event: dict, group: str) -> bool:
    """Return True if the caller belongs to the given Cognito group."""
    return group in get_user_groups(event)


def is_admin(event: dict) -> bool:
    return is_in_group(event, 'admin')


def is_doctor(event: dict) -> bool:
    return is_in_group(event, 'doctor')


def is_patient(event: dict) -> bool:
    return is_in_group(event, 'patient')


# ── Response helpers ──────────────────────────────────────────────────────────

def _json_response(status_code: int, body: Any) -> dict:
    return {
        'statusCode': status_code,
        'headers': CORS_HEADERS,
        'body': json.dumps(body),
    }


def forbidden(message: str = 'Forbidden') -> dict:
    return _json_response(403, {'error': message})


def options_response() -> dict:
    """Return a 200 response for CORS pre-flight OPTIONS requests."""
    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': '',
    }


# ── Decorators ────────────────────────────────────────────────────────────────

def require_group(*groups: str) -> Callable:
    """
    Lambda handler decorator that enforces Cognito group membership.

    Usage:
        @require_group('admin', 'doctor')
        def handler(event, context):
            ...

    Returns 403 Forbidden if the caller is not in at least one of the
    specified groups.  OPTIONS requests are always passed through.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(event: dict, context: Any) -> dict:
            # Always allow CORS pre-flight
            if event.get('httpMethod') == 'OPTIONS':
                return options_response()

            caller_groups = set(get_user_groups(event))
            if not caller_groups.intersection(groups):
                return forbidden(
                    f'Access denied. Required group(s): {list(groups)}'
                )
            return func(event, context)
        return wrapper
    return decorator


def handle_options(func: Callable) -> Callable:
    """
    Decorator that short-circuits OPTIONS pre-flight requests before
    the handler runs any business logic.
    """
    @wraps(func)
    def wrapper(event: dict, context: Any) -> dict:
        if event.get('httpMethod') == 'OPTIONS':
            return options_response()
        return func(event, context)
    return wrapper
