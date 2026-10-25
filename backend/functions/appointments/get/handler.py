import json
import os
import sys

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from auth import user_sub, is_group

dynamodb = boto3.resource('dynamodb')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


def handler(event, context):
    """Fetch a single appointment by appointmentId from DynamoDB."""
    try:
        appointment_id = (event.get('pathParameters') or {}).get('appointmentId')
        if not appointment_id:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'appointmentId path parameter is required'}),
            }

        table_name = os.environ.get('APPOINTMENTS_TABLE')
        if not table_name:
            raise EnvironmentError('APPOINTMENTS_TABLE environment variable is not set')

        table = dynamodb.Table(table_name)
        response = table.get_item(Key={'appointmentId': appointment_id})

        item = response.get('Item')
        if not item:
            return {
                'statusCode': 404,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': f'Appointment {appointment_id} not found'}),
            }

        # Patients see their own appointments, doctors see appointments
        # assigned to them, admins see everything.
        caller = user_sub(event)
        if not caller:
            return {
                'statusCode': 401,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'Authentication required'}),
            }
        if not is_group(event, 'admin'):
            if item.get('patientId') != caller and item.get('doctorId') != caller:
                return {
                    'statusCode': 403,
                    'headers': CORS_HEADERS,
                    'body': json.dumps({'error': 'You are not a participant in this appointment'}),
                }

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps(item),
        }

    except EnvironmentError as e:
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)}),
        }
    except Exception as e:
        print(f'Unexpected error fetching appointment {appointment_id}: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
