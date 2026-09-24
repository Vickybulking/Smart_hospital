import json
import os
import uuid
import sys
from datetime import datetime

import boto3

# Allow shared modules to be found when running locally or in Lambda
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))

from validators import validate_patient_data

dynamodb = boto3.resource('dynamodb')

# CORS headers included on every response so API Gateway / browsers don't reject
CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


def handler(event, context):
    """Create a new patient record in DynamoDB."""
    try:
        raw_body = event.get('body') or '{}'
        body = json.loads(raw_body)

        # --- Input validation ---
        errors = validate_patient_data(body)
        if errors:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'errors': errors}),
            }

        # --- Build patient item ---
        now = datetime.utcnow().isoformat() + 'Z'
        patient_id = str(uuid.uuid4())
        patient = {
            'patientId': patient_id,
            'name': body['name'],
            'email': body['email'],
            'phone': body.get('phone', ''),
            'dateOfBirth': body.get('dateOfBirth', ''),
            'role': 'patient',
            'createdAt': now,
            'updatedAt': now,
        }

        # --- Persist to DynamoDB ---
        table_name = os.environ.get('PATIENTS_TABLE')
        if not table_name:
            raise EnvironmentError('PATIENTS_TABLE environment variable is not set')

        table = dynamodb.Table(table_name)
        table.put_item(Item=patient)

        return {
            'statusCode': 201,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'patientId': patient_id,
                'message': 'Patient created successfully',
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
        print(f'Unexpected error creating patient: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }

}
