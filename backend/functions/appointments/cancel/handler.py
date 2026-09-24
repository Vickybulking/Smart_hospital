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
    """Cancel an appointment by setting its status to 'cancelled' in DynamoDB."""
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
        now = datetime.utcnow().isoformat() + 'Z'

        # Conditional update: only proceed if the appointment exists and isn't already cancelled
        table.update_item(
            Key={'appointmentId': appointment_id},
            UpdateExpression='SET #s = :cancelled, updatedAt = :now',
            ConditionExpression='attribute_exists(appointmentId) AND #s <> :cancelled',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':cancelled': 'cancelled',
                ':now': now,
            },
        )

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'appointmentId': appointment_id,
                'status': 'cancelled',
                'message': 'Appointment cancelled successfully',
            }),
        }

    except ClientError as e:
        code = e.response['Error']['Code']
        if code == 'ConditionalCheckFailedException':
            # Either appointment doesn't exist or was already cancelled
            return {
                'statusCode': 409,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'Appointment not found or already cancelled'}),
            }
        raise
    except EnvironmentError as e:
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)}),
        }
    except Exception as e:
        print(f'Unexpected error cancelling appointment {appointment_id}: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
