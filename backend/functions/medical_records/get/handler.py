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
    """Fetch a single medical record by recordId from DynamoDB."""
    try:
        record_id = (event.get('pathParameters') or {}).get('recordId')
        if not record_id:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'recordId path parameter is required'}),
            }

        table_name = os.environ.get('MEDICAL_RECORDS_TABLE')
        if not table_name:
            raise EnvironmentError('MEDICAL_RECORDS_TABLE environment variable is not set')

        table = dynamodb.Table(table_name)
        response = table.get_item(Key={'recordId': record_id})

        item = response.get('Item')
        if not item:
            return {
                'statusCode': 404,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': f'Record {record_id} not found'}),
            }

        # Patients may only read their own records; doctors and admins may
        # read any record (doctors are the authors of clinical documentation).
        caller = user_sub(event)
        if not caller:
            return {
                'statusCode': 401,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'Authentication required'}),
            }
        if is_group(event, 'patient') and item.get('patientId') != caller:
            return {
                'statusCode': 403,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'Patients may only view their own medical records'}),
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
        print(f'Unexpected error fetching medical record {record_id}: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
