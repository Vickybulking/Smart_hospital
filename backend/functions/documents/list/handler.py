import json
import os
import sys
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from auth import user_sub, is_group

dynamodb = boto3.resource('dynamodb')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


def _json_default(obj):
    """DynamoDB numbers arrive as Decimal, which json.dumps rejects."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(f'Not JSON serializable: {type(obj)}')


def handler(event, context):
    """List document metadata, scoped by role.

    Patients always see only their own documents (their query parameters are
    ignored); doctors and admins may filter by patientId or list everything.
    """
    try:
        caller = user_sub(event)
        if not caller:
            return {
                'statusCode': 401,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'Authentication required'}),
            }

        query_params = event.get('queryStringParameters') or {}
        patient_id = query_params.get('patientId')

        if is_group(event, 'patient'):
            patient_id = caller
        elif not (is_group(event, 'doctor') or is_group(event, 'admin')):
            return {
                'statusCode': 403,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'Not authorised to list documents'}),
            }

        table_name = os.environ.get('DOCUMENTS_TABLE')
        if not table_name:
            raise EnvironmentError('DOCUMENTS_TABLE environment variable is not set')

        table = dynamodb.Table(table_name)

        limit = int(query_params.get('limit', 50))
        scan_kwargs = {'Limit': limit}

        if patient_id:
            scan_kwargs['FilterExpression'] = Attr('patientId').eq(patient_id)

        last_key = query_params.get('lastKey')
        if last_key:
            scan_kwargs['ExclusiveStartKey'] = {'documentId': last_key}

        result = table.scan(**scan_kwargs)
        documents = result.get('Items', [])

        body = {'documents': documents, 'count': len(documents)}
        if 'LastEvaluatedKey' in result:
            body['lastKey'] = result['LastEvaluatedKey'].get('documentId')

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps(body, default=_json_default),
        }

    except EnvironmentError as e:
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)}),
        }
    except Exception as e:
        print(f'Unexpected error listing documents: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
