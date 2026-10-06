import json
import os

import boto3

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


def handler(event, context):
    """Delete a document and remove both its S3 object and metadata record."""
    try:
        bucket_name = os.environ.get('DOCUMENTS_BUCKET')
        table_name = os.environ.get('DOCUMENTS_TABLE')

        if not bucket_name:
            raise EnvironmentError('DOCUMENTS_BUCKET environment variable is not set')
        if not table_name:
            raise EnvironmentError('DOCUMENTS_TABLE environment variable is not set')

        document_id = (event.get('pathParameters') or {}).get('documentId')
        if not document_id:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'documentId path parameter is required'}),
            }

        # --- 1. Fetch metadata to get the S3 file key ---
        table = dynamodb.Table(table_name)
        meta_response = table.get_item(Key={'documentId': document_id})
        item = meta_response.get('Item')

        if not item:
            return {
                'statusCode': 404,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': f'Document {document_id} not found'}),
            }

        file_key = item.get('fileKey', '')

        # --- 2. Delete the S3 object ---
        if file_key:
            s3.delete_object(Bucket=bucket_name, Key=file_key)

        # --- 3. Remove the metadata record as well ---
        table.delete_item(Key={'documentId': document_id})

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'message': f'Document {document_id} deleted successfully'}),
        }

    except EnvironmentError as e:
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)}),
        }
    except Exception as e:
        print(f'Unexpected error deleting document {document_id}: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
