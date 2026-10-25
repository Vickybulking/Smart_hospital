import json
import os
import sys
from datetime import datetime

import boto3

# Allow shared modules to be found when running locally or in Lambda
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))

from auth import user_sub, is_group, response
from validators import validate_patient_data

dynamodb = boto3.resource('dynamodb')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


def handler(event, context):
    """Create (or replace) the caller's own patient profile.

    The profile is keyed by the caller's Cognito sub so a patient can only
    ever write their own record — patientId from the body is ignored.
    """
    try:
        caller = user_sub(event)
        if not caller or not is_group(event, 'patient'):
            return response(403, {'error': 'Only authenticated patients can create patient profiles'})

        raw_body = event.get('body') or '{}'
        body = json.loads(raw_body)

        errors = validate_patient_data(body)
        if errors:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'errors': errors}),
            }

        now = datetime.utcnow().isoformat() + 'Z'
        patient = {
            'patientId': caller,
            'name': body['name'],
            'email': body['email'],
            'phone': body.get('phone', ''),
            'dateOfBirth': body.get('dateOfBirth', ''),
            'bloodGroup': body.get('bloodGroup', ''),
            'allergies': body.get('allergies', ''),
            'emergencyContact': body.get('emergencyContact', ''),
            'role': 'patient',
            'createdAt': now,
            'updatedAt': now,
        }

        table_name = os.environ.get('PATIENTS_TABLE')
        if not table_name:
            raise EnvironmentError('PATIENTS_TABLE environment variable is not set')

        dynamodb.Table(table_name).put_item(Item=patient)

        return {
            'statusCode': 201,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'patientId': caller,
                'message': 'Patient profile saved successfully',
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
        print(f'Unexpected error creating patient profile: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
