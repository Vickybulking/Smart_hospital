import json
import boto3
import uuid
from datetime import datetime

def handler(event, context):
    """Generate pre-signed URL for document upload"""
    try:
        file_name = uuid.uuid4().hex + '.pdf'
        s3 = boto3.client('s3')
        
        presigned_url = s3.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': 'documents-bucket',
                'Key': file_name,
                'ContentType': 'application/pdf'
            },
            ExpiresIn: 3600
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'uploadUrl': presigned_url,
                'fileName': file_name
            })
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
