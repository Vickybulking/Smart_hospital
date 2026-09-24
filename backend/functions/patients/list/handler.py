import json
import os

import boto3

dynamodb = boto3.resource('dynamodb')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


def handler(event, context):
    """List all patients from DynamoDB with optional pagination."""
    try:
        table_name = os.environ.get('PATIENTS_TABLE')
        if not table_name:
            raise EnvironmentError('PATIENTS_TABLE environment variable is not set')

        table = dynamodb.Table(table_name)

        # Support pagination via query string: ?lastKey=<patientId>
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', 50))

        scan_kwargs = {'Limit': limit}

        # If a pagination cursor was supplied, resume from that key
        last_key = query_params.get('lastKey')
        if last_key:
            scan_kwargs['ExclusiveStartKey'] = {'patientId': last_key}

        response = table.scan(**scan_kwargs)
        patients = response.get('Items', [])

        # Return the last evaluated key so callers can request the next page
        next_key = response.get('LastEvaluatedKey', {}).get('patientId')

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'patients': patients,
                'count': len(patients),
                'nextKey': next_key,
            }),
        }

    except EnvironmentError as e:
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)}),
        }
    except Exception as e:
        print(f'Unexpected error listing patients: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
