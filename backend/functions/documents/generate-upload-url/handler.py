import json
import os
import uuid

import boto3

s3 = boto3.client('s3')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}

PRESIGNED_URL_EXPIRY = 3600  # 1 hour


def handler(event, context):
    """Generate a pre-signed S3 PUT URL so the client can upload a document directly."""
    try:
        bucket_name = os.environ.get('DOCUMENTS_BUCKET')
        if not bucket_name:
            raise EnvironmentError('DOCUMENTS_BUCKET environment variable is not set')

        query_params = event.get('queryStringParameters') or {}
        body_raw = event.get('body') or '{}'
        try:
            body = json.loads(body_raw)
        except json.JSONDecodeError:
            body = {}

        # Accept content type from body or query string (default pdf)
        content_type = body.get('contentType') or query_params.get('contentType', 'application/pdf')

        # Derive file extension from content type
        ext_map = {
            'application/pdf': '.pdf',
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/dicom': '.dcm',
        }
        extension = ext_map.get(content_type, '.bin')

        # Generate a unique S3 key scoped by patientId when provided
        patient_id = body.get('patientId') or query_params.get('patientId', 'unknown')
        file_key = f'documents/{patient_id}/{uuid.uuid4().hex}{extension}'

        presigned_url = s3.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket_name,
                'Key': file_key,
                'ContentType': content_type,
            },
            ExpiresIn=PRESIGNED_URL_EXPIRY,
        )

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'uploadUrl': presigned_url,
                'fileKey': file_key,
                'expiresIn': PRESIGNED_URL_EXPIRY,
            }),
        }

    except EnvironmentError as e:
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)}),
        }
    except Exception as e:
        print(f'Unexpected error generating upload URL: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
