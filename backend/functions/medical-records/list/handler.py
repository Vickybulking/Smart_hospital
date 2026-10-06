import json
import os

import boto3
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource('dynamodb')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


def handler(event, context):
    """List medical records from DynamoDB, optionally filtered by patientId or doctorId."""
    try:
        table_name = os.environ.get('MEDICAL_RECORDS_TABLE')
        if not table_name:
            raise EnvironmentError('MEDICAL_RECORDS_TABLE environment variable is not set')

        table = dynamodb.Table(table_name)

        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', 50))
        patient_id = query_params.get('patientId')
        doctor_id = query_params.get('doctorId')

        scan_kwargs = {'Limit': limit}

        # Build filter expression from optional query params
        filter_expr = None
        if patient_id:
            filter_expr = Attr('patientId').eq(patient_id)
        if doctor_id:
            doctor_filter = Attr('doctorId').eq(doctor_id)
            filter_expr = filter_expr & doctor_filter if filter_expr else doctor_filter

        if filter_expr is not None:
            scan_kwargs['FilterExpression'] = filter_expr

        last_key = query_params.get('lastKey')
        if last_key:
            scan_kwargs['ExclusiveStartKey'] = {'recordId': last_key}

        response = table.scan(**scan_kwargs)
        items = response.get('Items', [])

        result = {'records': items, 'count': len(items)}

        if 'LastEvaluatedKey' in response:
            result['lastKey'] = response['LastEvaluatedKey'].get('recordId')

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps(result),
        }

    except EnvironmentError as e:
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)}),
        }
    except Exception as e:
        print(f'Unexpected error listing medical records: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
