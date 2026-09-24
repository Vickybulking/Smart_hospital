import json
import os

import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


def handler(event, context):
    """Fetch a single patient by patientId from DynamoDB."""
    try:
        patient_id = (event.get('pathParameters') or {}).get('patientId')
        if not patient_id:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'patientId path parameter is required'}),
            }

        table_name = os.environ.get('PATIENTS_TABLE')
        if not table_name:
            raise EnvironmentError('PATIENTS_TABLE environment variable is not set')

        table = dynamodb.Table(table_name)
        response = table.get_item(Key={'patientId': patient_id})

        # DynamoDB returns an empty response (no 'Item' key) when not found
        item = response.get('Item')
        if not item:
            return {
                'statusCode': 404,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': f'Patient {patient_id} not found'}),
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
        print(f'Unexpected error fetching patient {patient_id}: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
