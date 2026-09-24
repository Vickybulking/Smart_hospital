import json
import os
import sys
import uuid
from datetime import datetime

import boto3

# Allow shared modules to be found
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))

from validators import validate_appointment_data
from auth import response, user_sub, is_group
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


def handler(event, context):
    """Create a new appointment record in DynamoDB."""
    try:
        if not user_sub(event) or not is_group(event, 'patient'):
            return response(403, {'error': 'Only authenticated patients can create appointments'})

        raw_body = event.get('body') or '{}'
        body = json.loads(raw_body)

        # --- Input validation ---
        errors = validate_appointment_data(body)
        if errors:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'errors': errors}),
            }

        # --- Build appointment item ---
        now = datetime.utcnow().isoformat() + 'Z'
        appointment_id = str(uuid.uuid4())
        appointment = {
            'appointmentId': appointment_id,
            'patientId': user_sub(event),
            'doctorId': body['doctorId'],
            'dateTime': body['dateTime'],
            'doctorSlotKey': f"{body['doctorId']}#{body['dateTime']}",
            'reason': body.get('reason', ''),
            'status': 'pending',
            'type': 'appointment',
            'createdAt': now,
            'updatedAt': now,
        }

        # --- Persist to DynamoDB ---
        table_name = os.environ.get('APPOINTMENTS_TABLE')
        if not table_name:
            raise EnvironmentError('APPOINTMENTS_TABLE environment variable is not set')

        slots_table_name = os.environ.get('APPOINTMENT_SLOTS_TABLE')
        if not slots_table_name:
            raise EnvironmentError('APPOINTMENT_SLOTS_TABLE environment variable is not set')
        slot_key = appointment['doctorSlotKey']
        # Lock the slot and create the appointment atomically.
        dynamodb.meta.client.transact_write_items(TransactItems=[
            {'Put': {'TableName': slots_table_name, 'Item': {'slotKey': slot_key, 'appointmentId': appointment_id}, 'ConditionExpression': 'attribute_not_exists(slotKey)'}},
            {'Put': {'TableName': table_name, 'Item': appointment}},
        ])

        return {
            'statusCode': 201,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'appointmentId': appointment_id,
                'message': 'Appointment created successfully',
            }),
        }
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return response(409, {'error': 'That doctor slot is already booked'})
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
        print(f'Unexpected error creating appointment: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
