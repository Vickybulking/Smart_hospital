import json
import os
import uuid
import sys
from datetime import datetime

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))

from auth import user_sub, is_group, response

dynamodb = boto3.resource('dynamodb')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}

REQUIRED_FIELDS = ['name', 'email', 'specialty']


def handler(event, context):
    """Create a doctor profile.

    - Doctors create their OWN profile: doctorId is forced to the caller's
      Cognito sub so nobody can register a profile for another doctor.
    - Admins may register a profile for any doctorId (staff provisioning).
    """
    try:
        caller = user_sub(event)
        if not caller:
            return response(401, {'error': 'Authentication required'})

        if is_group(event, 'doctor'):
            doctor_id = caller
        elif is_group(event, 'admin'):
            doctor_id = None  # decided below
        else:
            return response(403, {'error': 'Only doctors or admins can create doctor profiles'})

        raw_body = event.get('body') or '{}'
        body = json.loads(raw_body)

        errors = [f'{f} is required' for f in REQUIRED_FIELDS if not body.get(f)]
        if errors:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'errors': errors}),
            }

        if not doctor_id:
            doctor_id = body.get('doctorId') or str(uuid.uuid4())

        now = datetime.utcnow().isoformat() + 'Z'
        doctor = {
            'doctorId': doctor_id,
            'name': body['name'],
            'email': body['email'],
            'specialty': body['specialty'],
            'phone': body.get('phone', ''),
            'qualification': body.get('qualification', ''),
            'experience': body.get('experience', ''),
            'bio': body.get('bio', ''),
            'availability': {},
            'role': 'doctor',
            'createdAt': now,
            'updatedAt': now,
        }

        table_name = os.environ.get('DOCTORS_TABLE')
        if not table_name:
            raise EnvironmentError('DOCTORS_TABLE environment variable is not set')

        dynamodb.Table(table_name).put_item(Item=doctor)

        return {
            'statusCode': 201,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'doctorId': doctor_id,
                'message': 'Doctor profile saved successfully',
            }),
        }

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
        print(f'Unexpected error creating doctor profile: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
