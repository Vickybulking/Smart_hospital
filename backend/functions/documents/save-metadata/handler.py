import json
import os
import uuid
from datetime import datetime

import boto3

dynamodb = boto3.resource('dynamodb')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}

REQUIRED_FIELDS = ['patientId', 'fileKey', 'fileName']


def handler(event, context):
    """Save document metadata to DynamoDB after a successful S3 upload."""
    try:
        table_name = os.environ.get('DOCUMENTS_TABLE')
        if not table_name:
            raise EnvironmentError('DOCUMENTS_TABLE environment variable is not set')

        raw_body = event.get('body') or '{}'
        body = json.loads(raw_body)

        # --- Input validation ---
        errors = [f'{f} is required' for f in REQUIRED_FIELDS if not body.get(f)]
        if errors:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'errors': errors}),
            }

        now = datetime.utcnow().isoformat() + 'Z'
        document_id = str(uuid.uuid4())

        document = {
            'documentId': document_id,
            'patientId': body['patientId'],
            'fileKey': body['fileKey'],       # S3 object key returned by generate-upload-url
            'fileName': body['fileName'],     # Human-readable display name
            'contentType': body.get('contentType', 'application/pdf'),
            'description': body.get('description', ''),
            'doctorId': body.get('doctorId', ''),
            'recordId': body.get('recordId', ''),  # Optional link to a medical record
            'uploadedBy': body.get('uploadedBy', ''),
            'sizeBytes': body.get('sizeBytes', 0),
            'status': 'active',
            'createdAt': now,
            'updatedAt': now,
        }

        table = dynamodb.Table(table_name)
        table.put_item(Item=document)

        return {
            'statusCode': 201,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'documentId': document_id,
                'message': 'Document metadata saved successfully',
            }),
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
        print(f'Unexpected error saving document metadata: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
