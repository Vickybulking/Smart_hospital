import json
import os
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


def handler(event, context):
    """Reschedule an appointment by updating its dateTime in DynamoDB."""
    try:
        appointment_id = (event.get('pathParameters') or {}).get('appointmentId')
        if not appointment_id:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'appointmentId path parameter is required'}),
            }

        raw_body = event.get('body') or '{}'
        body = json.loads(raw_body)
        new_date_time = body.get('dateTime')

        if not new_date_time:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'dateTime is required in the request body'}),
            }

        table_name = os.environ.get('APPOINTMENTS_TABLE')
        if not table_name:
            raise EnvironmentError('APPOINTMENTS_TABLE environment variable is not set')

        table = dynamodb.Table(table_name)
        now = datetime.utcnow().isoformat() + 'Z'

        # Conditional update: only reschedule if the appointment exists and isn't cancelled
        table.update_item(
            Key={'appointmentId': appointment_id},
            UpdateExpression='SET dateTime = :new_dt, #s = :booked, updatedAt = :now',
            ConditionExpression='attribute_exists(appointmentId) AND #s <> :cancelled',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':new_dt': new_date_time,
                ':booked': 'booked',
                ':cancelled': 'cancelled',
                ':now': now,
            },
        )

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'appointmentId': appointment_id,
                'newDateTime': new_date_time,
                'status': 'booked',
                'message': 'Appointment rescheduled successfully',
            }),
        }

    except ClientError as e:
        code = e.response['Error']['Code']
        if code == 'ConditionalCheckFailedException':
            return {
                'statusCode': 409,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'Appointment not found or already cancelled — cannot reschedule'}),
            }
        raise
    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Invalid JSON in request body'}),
        }
    except EnvironmentError as e:
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)}),
        }
    except Exception as e:
        print(f'Unexpected error rescheduling appointment {appointment_id}: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
