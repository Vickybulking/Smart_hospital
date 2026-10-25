import json
import os
import sys
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from auth import user_sub, is_group, response

dynamodb = boto3.resource('dynamodb')


def _deny(status, message):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
        },
        'body': json.dumps({'error': message}),
    }


def handler(event, context):
    """Cancel an appointment and release its slot lock atomically.

    Only the patient who booked it, the doctor it is assigned to, or an
    admin may cancel. The slot lock (doctorId#dateTime) is deleted in the
    same transaction so the time becomes bookable again.
    """
    appointment_id = (event.get('pathParameters') or {}).get('appointmentId')
    if not appointment_id:
        return _deny(400, 'appointmentId path parameter is required')

    table_name = os.environ.get('APPOINTMENTS_TABLE')
    slots_table_name = os.environ.get('APPOINTMENT_SLOTS_TABLE')
    if not table_name or not slots_table_name:
        return _deny(500, 'APPOINTMENTS_TABLE / APPOINTMENT_SLOTS_TABLE not configured')

    caller = user_sub(event)
    if not caller:
        return _deny(401, 'Authentication required')

    try:
        table = dynamodb.Table(table_name)
        existing = table.get_item(Key={'appointmentId': appointment_id}).get('Item')
        if not existing:
            return _deny(404, f'Appointment {appointment_id} not found')

        if not is_group(event, 'admin'):
            if existing.get('patientId') != caller and existing.get('doctorId') != caller:
                return _deny(403, 'You are not a participant in this appointment')

        now = datetime.utcnow().isoformat() + 'Z'
        slot_key = existing.get('doctorSlotKey') or f"{existing.get('doctorId')}#{existing.get('dateTime')}"

        # Cancel the appointment and free the slot in one atomic transaction:
        # if another flow already changed the appointment, both operations roll back.
        dynamodb.meta.client.transact_write_items(TransactItems=[
            {
                'Update': {
                    'TableName': table_name,
                    'Key': {'appointmentId': appointment_id},
                    'UpdateExpression': 'SET #s = :cancelled, updatedAt = :now, cancelledBy = :caller',
                    'ConditionExpression': 'attribute_exists(appointmentId) AND #s <> :cancelled',
                    'ExpressionAttributeNames': {'#s': 'status'},
                    'ExpressionAttributeValues': {
                        ':cancelled': 'cancelled',
                        ':now': now,
                        ':caller': caller,
                    },
                }
            },
            {
                'Delete': {
                    'TableName': slots_table_name,
                    'Key': {'slotKey': slot_key},
                    'ConditionExpression': 'attribute_exists(slotKey)',
                }
            },
        ])

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'appointmentId': appointment_id,
                'status': 'cancelled',
                'message': 'Appointment cancelled successfully and slot released',
            }),
        }

    except ClientError as e:
        code = e.response['Error']['Code']
        if code == 'ConditionalCheckFailedException':
            return _deny(409, 'Appointment not found, already cancelled, or the slot lock changed — retry')
        if code == 'TransactionCanceledException':
            return _deny(409, 'Appointment was already cancelled or modified concurrently')
        print(f'Unexpected error cancelling appointment {appointment_id}: {e}')
        return _deny(500, 'Internal server error')
    except Exception as e:
        print(f'Unexpected error cancelling appointment {appointment_id}: {e}')
        return _deny(500, 'Internal server error')
