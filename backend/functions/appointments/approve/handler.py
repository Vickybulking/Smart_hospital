import json
import os
import sys
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from auth import is_group, response, user_sub

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')


def handler(event, context):
    if not user_sub(event) or not is_group(event, 'doctor'):
        return response(403, {'error': 'Only authenticated doctors can approve appointments'})
    appointment_id = (event.get('pathParameters') or {}).get('appointmentId')
    if not appointment_id:
        return response(400, {'error': 'appointmentId is required'})
    try:
        body = json.loads(event.get('body') or '{}')
        decision = body.get('decision')
        if decision not in ('confirmed', 'declined'):
            return response(400, {'error': "decision must be 'confirmed' or 'declined'"})
        table = dynamodb.Table(os.environ['APPOINTMENTS_TABLE'])
        now = datetime.utcnow().isoformat() + 'Z'
        result = table.update_item(
            Key={'appointmentId': appointment_id},
            UpdateExpression='SET #s = :status, updatedAt = :now, approvedBy = :doctor',
            ConditionExpression='attribute_exists(appointmentId) AND doctorId = :doctor AND #s = :pending',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':status': decision, ':pending': 'pending', ':doctor': user_sub(event), ':now': now},
            ReturnValues='ALL_NEW',
        )
        item = result['Attributes']
        topic = os.environ.get('NOTIFICATIONS_TOPIC_ARN')
        if topic:
            sns.publish(TopicArn=topic, Subject='Appointment update', Message=json.dumps({'patientId': item['patientId'], 'appointmentId': appointment_id, 'status': decision}))
        return response(200, {'appointmentId': appointment_id, 'status': decision, 'message': 'Appointment updated and patient notified'})
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return response(409, {'error': 'Appointment is not pending, not found, or belongs to another doctor'})
        return response(500, {'error': 'Unable to update appointment'})
