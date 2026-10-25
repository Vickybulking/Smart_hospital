import json
import os
import re
import sys
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from auth import user_sub, is_group

dynamodb = boto3.resource('dynamodb')

_ISO_DT_RE = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?Z?$')


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
    """Reschedule an appointment to a new dateTime.

    Only the booking patient (or an admin) may reschedule. The new slot is
    claimed with attribute_not_exists inside the same transaction that
    updates the appointment and releases the old slot, so two patients
    racing for the same new time cannot both win. Status resets to
    'pending' because the doctor must confirm the new time.
    """
    appointment_id = (event.get('pathParameters') or {}).get('appointmentId')
    if not appointment_id:
        return _deny(400, 'appointmentId path parameter is required')

    try:
        body = json.loads(event.get('body') or '{}')
    except json.JSONDecodeError:
        return _deny(400, 'Invalid JSON in request body')

    new_date_time = body.get('dateTime')
    if not new_date_time or not _ISO_DT_RE.match(str(new_date_time)):
        return _deny(400, '"dateTime" must be an ISO-8601 datetime string (e.g. 2026-09-21T10:30:00Z)')

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

        if not is_group(event, 'admin') and existing.get('patientId') != caller:
            return _deny(403, 'Only the patient who booked this appointment (or an admin) may reschedule it')

        if existing.get('status') == 'cancelled':
            return _deny(409, 'Cannot reschedule a cancelled appointment')

        doctor_id = existing.get('doctorId')
        old_slot_key = existing.get('doctorSlotKey') or f"{doctor_id}#{existing.get('dateTime')}"
        new_slot_key = f"{doctor_id}#{new_date_time}"
        if new_slot_key == old_slot_key:
            return _deny(400, 'New dateTime is identical to the current one')

        now = datetime.utcnow().isoformat() + 'Z'

        try:
            dynamodb.meta.client.transact_write_items(TransactItems=[
                {
                    'Update': {
                        'TableName': table_name,
                        'Key': {'appointmentId': appointment_id},
                        'UpdateExpression': 'SET dateTime = :new_dt, doctorSlotKey = :new_slot, #s = :pending, updatedAt = :now',
                        'ConditionExpression': 'attribute_exists(appointmentId) AND #s <> :cancelled',
                        'ExpressionAttributeNames': {'#s': 'status'},
                        'ExpressionAttributeValues': {
                            ':new_dt': new_date_time,
                            ':new_slot': new_slot_key,
                            ':pending': 'pending',
                            ':cancelled': 'cancelled',
                            ':now': now,
                        },
                    }
                },
                {
                    'Put': {
                        'TableName': slots_table_name,
                        'Item': {'slotKey': new_slot_key, 'appointmentId': appointment_id},
                        'ConditionExpression': 'attribute_not_exists(slotKey)',
                    }
                },
                {
                    'Delete': {
                        'TableName': slots_table_name,
                        'Key': {'slotKey': old_slot_key},
                        'ConditionExpression': 'attribute_exists(slotKey)',
                    }
                },
            ])
        except ClientError as e:
            if e.response['Error']['Code'] in ('ConditionalCheckFailedException', 'TransactionCanceledException'):
                return _deny(409, 'The requested new slot has already been taken, or the appointment changed — refresh and try again')
            raise

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'appointmentId': appointment_id,
                'newDateTime': new_date_time,
                'status': 'pending',
                'message': 'Appointment rescheduled successfully — awaiting doctor confirmation',
            }),
        }

    except Exception as e:
        print(f'Unexpected error rescheduling appointment {appointment_id}: {e}')
        return _deny(500, 'Internal server error')
