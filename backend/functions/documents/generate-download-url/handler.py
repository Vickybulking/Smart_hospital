import json
import os

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
    """Generate a pre-signed S3 GET URL so the client can download a document directly."""
    try:
        bucket_name = os.environ.get('DOCUMENTS_BUCKET')
        if not bucket_name:
            raise EnvironmentError('DOCUMENTS_BUCKET environment variable is not set')

        query_params = event.get('queryStringParameters') or {}

        # Accept fileKey (preferred) or legacy fileName for backwards compatibility
        file_key = query_params.get('fileKey') or query_params.get('fileName')
        if not file_key:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'fileKey query parameter is required'}),
            }

        # Verify the object exists before issuing a URL to avoid handing out URLs for missing keys
        try:
            s3.head_object(Bucket=bucket_name, Key=file_key)
        except s3.exceptions.ClientError as head_err:
            error_code = head_err.response['Error']['Code']
            if error_code in ('404', 'NoSuchKey'):
                return {
                    'statusCode': 404,
                    'headers': CORS_HEADERS,
                    'body': json.dumps({'error': f'Document {file_key} not found in storage'}),
                }
            raise  # re-raise unexpected S3 errors

        presigned_url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': file_key,
            },
            ExpiresIn=PRESIGNED_URL_EXPIRY,
        )

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'downloadUrl': presigned_url,
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
        print(f'Unexpected error generating download URL: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
