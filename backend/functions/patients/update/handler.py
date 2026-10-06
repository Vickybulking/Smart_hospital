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

# Fields that callers are allowed to update on a patient record
UPDATABLE_FIELDS = {'name', 'email', 'phone', 'dateOfBirth', 'address', 'bloodGroup', 'allergies', 'emergencyContact'}


def handler(event, context):
    """Update an existing patient record in DynamoDB (partial update – PATCH semantics on PUT)."""
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

        raw_body = event.get('body') or '{}'
        body = json.loads(raw_body)

        # Strip out any keys the caller shouldn't be able to overwrite
        updates = {k: v for k, v in body.items() if k in UPDATABLE_FIELDS}
        if not updates:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({
                    'error': 'No updatable fields provided',
                    'allowed': sorted(UPDATABLE_FIELDS),
                }),
            }

        # Basic email format check when email is being updated
        if 'email' in updates and '@' not in updates['email']:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'Valid email is required'}),
            }

        now = datetime.utcnow().isoformat() + 'Z'
        updates['updatedAt'] = now

        # Build a dynamic UpdateExpression from whichever fields were provided
        set_parts = []
        expr_names = {}
        expr_values = {}

        for i, (key, value) in enumerate(updates.items()):
            placeholder = f'#field{i}'
            value_placeholder = f':val{i}'
            set_parts.append(f'{placeholder} = {value_placeholder}')
            expr_names[placeholder] = key
            expr_values[value_placeholder] = value

        update_expr = 'SET ' + ', '.join(set_parts)

        table = dynamodb.Table(table_name)
        table.update_item(
            Key={'patientId': patient_id},
            UpdateExpression=update_expr,
            ConditionExpression='attribute_exists(patientId)',
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'patientId': patient_id,
                'message': 'Patient updated successfully',
                'updatedFields': list(updates.keys()),
            }),
        }

    except ClientError as e:
        code = e.response['Error']['Code']
        if code == 'ConditionalCheckFailedException':
            return {
                'statusCode': 404,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': f'Patient {patient_id} not found'}),
            }
        raise
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
        print(f'Unexpected error updating patient {patient_id}: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
