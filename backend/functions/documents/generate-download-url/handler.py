import json
import boto3

def handler(event, context):
    """Generate pre-signed URL for document download"""
    try:
        file_name = event.get('queryStringParameters', {}).get('fileName', 'document.pdf')
        s3 = boto3.client('s3')
        
        presigned_url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': 'documents-bucket',
                'Key': file_name
            },
            ExpiresIn: 3600
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'downloadUrl': presigned_url
            })
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
