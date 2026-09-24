import json
import boto3

def handler(event, context):
    """Delete a document"""
    try:
        file_name = event.get('queryStringParameters', {}).get('fileName', '')
        s3 = boto3.client('s3')
        
        s3.delete_object(
            Bucket='documents-bucket',
            Key=file_name
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Document deleted successfully'})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
