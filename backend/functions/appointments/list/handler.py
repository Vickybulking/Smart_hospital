import json
import os

import boto3
from boto3.dynamodb.conditions import Attr
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from auth import user_sub, is_group, response

dynamodb = boto3.resource('dynamodb')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


def handler(event, context):
    """List appointments from DynamoDB. Optionally filter by patientId or doctorId."""
    try:
        table_name = os.environ.get('APPOINTMENTS_TABLE')
        if not table_name:
            raise EnvironmentError('APPOINTMENTS_TABLE environment variable is not set')

        table = dynamodb.Table(table_name)

        if not user_sub(event):
            return response(401, {'error': 'Authentication required'})
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', 50))
        patient_id = user_sub(event) if is_group(event, 'patient') else None
        doctor_id = user_sub(event) if is_group(event, 'doctor') else None
        if is_group(event, 'admin'):
            patient_id = query_params.get('patientId')
            doctor_id = query_params.get('doctorId')

        scan_kwargs = {'Limit': limit}

        # Apply filter if caller wants appointments for a specific patient or doctor
        if patient_id:
            scan_kwargs['FilterExpression'] = Attr('patientId').eq(patient_id)
        elif doctor_id:
            scan_kwargs['FilterExpression'] = Attr('doctorId').eq(doctor_id)

        # Pagination cursor
        last_key = query_params.get('lastKey')
        if last_key:
            scan_kwargs['ExclusiveStartKey'] = {'appointmentId': last_key}

        response = table.scan(**scan_kwargs)
        appointments = response.get('Items', [])
        next_key = response.get('LastEvaluatedKey', {}).get('appointmentId')

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'appointments': appointments,
                'count': len(appointments),
                'nextKey': next_key,
            }),
        }

    except EnvironmentError as e:
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)}),
        }
    except Exception as e:
        print(f'Unexpected error listing appointments: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
