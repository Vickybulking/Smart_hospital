import json
import os
import sys
import uuid
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

REQUIRED_FIELDS = ['patientId', 'title']


def handler(event, context):
    """Create a new medical record in DynamoDB.

    Only doctors author clinical records; doctorId is forced to the calling
    doctor's Cognito sub so a record can never be attributed to another doctor.
    """
    try:
        caller = user_sub(event)
        if not caller or not is_group(event, 'doctor'):
            return response(403, {'error': 'Only authenticated doctors can create medical records'})

        raw_body = event.get('body') or '{}'
        body = json.loads(raw_body)

        # --- Input validation ---
        errors = [f'{f} is required' for f in REQUIRED_FIELDS if not body.get(f)]
        if errors:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'errors': errors}),
            }

        # --- Build record item ---
        now = datetime.utcnow().isoformat() + 'Z'
        record_id = str(uuid.uuid4())
        record = {
            'recordId': record_id,
            'patientId': body['patientId'],
            'doctorId': caller,
            'title': body['title'],
            'notes': body.get('notes', ''),
            'contentUrl': body.get('contentUrl', ''),
            'type': body.get('type', 'general'),
            'createdAt': now,
            'updatedAt': now,
        }

        # --- Persist to DynamoDB ---
        table_name = os.environ.get('MEDICAL_RECORDS_TABLE')
        if not table_name:
            raise EnvironmentError('MEDICAL_RECORDS_TABLE environment variable is not set')

        table = dynamodb.Table(table_name)
        table.put_item(Item=record)

        return {
            'statusCode': 201,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'recordId': record_id,
                'message': 'Medical record created successfully',
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
        print(f'Unexpected error creating medical record: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
