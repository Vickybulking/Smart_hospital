import json
import os
import sys

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from auth import user_sub, is_group, response

sns = boto3.client('sns')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


def handler(event, context):
    """Publish a notification message to the SNS topic (doctor/admin only)."""
    try:
        caller = user_sub(event)
        if not caller:
            return response(401, {'error': 'Authentication required'})
        if not (is_group(event, 'doctor') or is_group(event, 'admin')):
            return response(403, {'error': 'Only doctors and admins can send notifications'})

        raw_body = event.get('body') or '{}'
        body = json.loads(raw_body)

        message = body.get('message', '').strip()
        subject = body.get('subject', 'Smart Hospital Notification').strip()

        if not message:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'message is required'}),
            }

        # Read the real topic ARN injected by CloudFormation — never hardcode account IDs
        topic_arn = os.environ.get('NOTIFICATIONS_TOPIC_ARN')
        if not topic_arn:
            raise EnvironmentError('NOTIFICATIONS_TOPIC_ARN environment variable is not set')

        sns.publish(
            TopicArn=topic_arn,
            Message=message,
            Subject=subject,
        )

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'message': 'Notification sent successfully'}),
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
        print(f'Unexpected error sending notification: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
