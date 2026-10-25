import json
import os
import sys
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from auth import user_sub, is_group, response

dynamodb = boto3.resource('dynamodb')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}

# Fields callers are allowed to update on a doctor record
UPDATABLE_FIELDS = {'name', 'email', 'phone', 'specialty', 'department', 'qualification', 'experience', 'bio'}


def handler(event, context):
    """Update an existing doctor record in DynamoDB (partial update – PATCH semantics on PUT)."""
    try:
        # Doctors may only update their own profile; admins may update any.
        caller = user_sub(event)
        if not caller:
            return response(401, {'error': 'Authentication required'})
        doctor_id = (event.get('pathParameters') or {}).get('doctorId')
        if is_group(event, 'doctor') and caller != doctor_id:
            return response(403, {'error': 'Doctors may only update their own profile'})
        if not (is_group(event, 'doctor') or is_group(event, 'admin')):
            return response(403, {'error': 'Only the doctor or an admin may update this profile'})

        if not doctor_id:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'doctorId path parameter is required'}),
            }

        table_name = os.environ.get('DOCTORS_TABLE')
        if not table_name:
            raise EnvironmentError('DOCTORS_TABLE environment variable is not set')

        raw_body = event.get('body') or '{}'
        body = json.loads(raw_body)

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

        if 'email' in updates and '@' not in updates['email']:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'Valid email is required'}),
            }

        now = datetime.utcnow().isoformat() + 'Z'
        updates['updatedAt'] = now

        # Build a dynamic UpdateExpression
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
            Key={'doctorId': doctor_id},
            UpdateExpression=update_expr,
            ConditionExpression='attribute_exists(doctorId)',
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'doctorId': doctor_id,
                'message': 'Doctor updated successfully',
                'updatedFields': list(updates.keys()),
            }),
        }

    except ClientError as e:
        code = e.response['Error']['Code']
        if code == 'ConditionalCheckFailedException':
            return {
                'statusCode': 404,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': f'Doctor {doctor_id} not found'}),
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
        print(f'Unexpected error updating doctor {doctor_id}: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
