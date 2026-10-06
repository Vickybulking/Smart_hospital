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
    """List all doctors from DynamoDB with optional pagination."""
    try:
        table_name = os.environ.get('DOCTORS_TABLE')
        if not table_name:
            raise EnvironmentError('DOCTORS_TABLE environment variable is not set')

        table = dynamodb.Table(table_name)

        # Support pagination via query string: ?limit=50&lastKey=<doctorId>
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', 50))

        scan_kwargs = {'Limit': limit}

        last_key = query_params.get('lastKey')
        if last_key:
            scan_kwargs['ExclusiveStartKey'] = {'doctorId': last_key}

        # Optional filter by specialty
        specialty = query_params.get('specialty')
        if specialty:
            scan_kwargs['FilterExpression'] = boto3.dynamodb.conditions.Attr('specialty').eq(specialty)

        response = table.scan(**scan_kwargs)
        items = response.get('Items', [])

        result = {'doctors': items, 'count': len(items)}

        # Return the last evaluated key so the client can paginate forward
        if 'LastEvaluatedKey' in response:
            result['lastKey'] = response['LastEvaluatedKey'].get('doctorId')

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
        print(f'Unexpected error listing doctors: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
