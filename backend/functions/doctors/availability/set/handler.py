import json
import os
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}

VALID_DAYS = {'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'}


def _validate_availability(availability: dict) -> list[str]:
    """Return a list of validation error strings, empty list if valid."""
    errors = []

    if not isinstance(availability, dict):
        return ['availability must be an object keyed by day-of-week']

    for day, times in availability.items():
        if day.lower() not in VALID_DAYS:
            errors.append(f'Invalid day: "{day}". Must be one of {sorted(VALID_DAYS)}')
            continue

        if not isinstance(times, list):
            errors.append(f'Times for "{day}" must be a list of "HH:MM" strings')
            continue

        for t in times:
            if not isinstance(t, str) or len(t) != 5 or t[2] != ':':
                errors.append(f'Invalid time "{t}" for "{day}". Expected "HH:MM" format')
            else:
                h, m = t.split(':')
                if not (h.isdigit() and m.isdigit() and 0 <= int(h) <= 23 and 0 <= int(m) <= 59):
                    errors.append(f'Time "{t}" for "{day}" is out of range')

    return errors


def handler(event, context):
    """
    Set / replace a doctor's weekly availability schedule.

    Expected request body:
    {
        "availability": {
            "monday":    ["09:00", "10:00", "14:00"],
            "tuesday":   ["09:00", "11:00"],
            "wednesday": [],
            ...
        }
    }

    Performs a conditional update so the operation fails with 404 if the
    doctor record doesn't exist, preventing silent creation of ghost records.
    """
    try:
        doctor_id = (event.get('pathParameters') or {}).get('doctorId')
        if not doctor_id:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'doctorId path parameter is required'}),
            }

        table_name = os.environ.get('DOCTORS_TABLE')
        if not table_name:
            raise EnvironmentError('DOCTORS_TABLE environment variable is not set')

        raw_body = event.get('body') or '{}'
        body = json.loads(raw_body)

        availability = body.get('availability')
        if availability is None:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': '"availability" field is required'}),
            }

        # Normalise day keys to lowercase
        availability = {k.lower(): v for k, v in availability.items()}

        errors = _validate_availability(availability)
        if errors:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'errors': errors}),
            }

        now = datetime.utcnow().isoformat() + 'Z'

        table = dynamodb.Table(table_name)
        table.update_item(
            Key={'doctorId': doctor_id},
            UpdateExpression='SET availability = :avail, updatedAt = :now',
            ConditionExpression='attribute_exists(doctorId)',
            ExpressionAttributeValues={
                ':avail': availability,
                ':now': now,
            },
        )

        total_slots = sum(len(v) for v in availability.values() if isinstance(v, list))

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'doctorId': doctor_id,
                'message': 'Availability updated successfully',
                'totalSlots': total_slots,
                'updatedAt': now,
            }),
        }

    except ClientError as e:
        code = e.response['Error']['Code']
        if code == 'ConditionalCheckFailedException':
            return {
                'statusCode': 404,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': f'Doctor {doctor_id} not found'}),
            }
        raise
    except EnvironmentError as e:
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)}),
        }
    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Invalid JSON in request body'}),
        }
    except Exception as e:
        print(f'Unexpected error setting availability for doctor {doctor_id}: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
